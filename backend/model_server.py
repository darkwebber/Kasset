import os
import time
import json
import logging
import gc
import threading
from pathlib import Path
from typing import List, Dict, Any, Generator, Tuple, Optional
from PIL import Image

# ─── MLX Imports ──────────────────────────────────────────
try:
    import mlx.core as mx
    from mlx_vlm import load, generate, stream_generate
    from mlx_vlm.prompt_utils import apply_chat_template
    from mlx_vlm.utils import load_config
except ImportError as e:
    print(f"❌ Error: MLX dependencies not found. Please run 'pip install mlx-vlm'")
    print(f"Details: {e}")
    exit(1)

# ──────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Model defaults
MODEL_PATH = os.environ.get("MODEL_PATH", "mlx-community/Qwen3.5-9B-MLX-4bit")
MAX_TOKENS = 32768
DEFAULT_TOKENS = 4096
VISION_TOKEN_CAP = 4096
MAX_IMAGE_DIMENSION = 768

from .core.inference_backend import InferenceBackend


class ModelClient(InferenceBackend):
    """MLX-VLM inference backend. Implements InferenceBackend interface."""
    
    def __init__(self, model_path: str = MODEL_PATH, lazy: bool = False):
        self.model_path = model_path
        self.model = None
        self.processor = None
        self.config = None
        self._temp_files: list = []  # Track temp files for cleanup
        self._loading = False
        self._load_error: str | None = None
        self._load_time: float = 0
        self._image_cache: dict = {}  # source_path -> (mtime, prepared_path)
        self._inference_lock = threading.Lock()  # Prevent concurrent inference
        if not lazy:
            self.load_model()

    def load_model(self):
        """Load the MLX model into memory."""
        self._loading = True
        self._load_error = None
        target_path = self.model_path  # Capture target at start for race detection
        try:
            logger.info(f"Loading model: {target_path}")
            logger.info("This may take 15-30s. If downloading for the first time, it may take longer.")
            t0 = time.time()
            
            model, processor = load(target_path)
            config = load_config(target_path)

            # Race condition: if model_path changed during loading, discard result
            if self.model_path != target_path:
                logger.info(f"Model path changed during loading ({target_path} → {self.model_path}), discarding")
                del model, processor, config
                gc.collect()
                return

            self.model = model
            self.processor = processor
            self.config = config

            # Store reference to the native template (for debugging)
            self._original_template = None
            if hasattr(self.processor, "tokenizer"):
                self._original_template = getattr(self.processor.tokenizer, "chat_template", None)
            # NOTE: We use the native Qwen3.5 chat template as-is.
            # The previous _SIMPLE_TEMPLATE override broke native tool-calling format.
            # The native template properly handles:
            #   - Thinking tags (<think>...</think>)
            #   - Tool call format (Qwen3-Coder XML)
            #   - Rolling checkpoint (strip thinking from old messages)
            #   - Message framing (ChatML)
            
            self._load_time = time.time() - t0
            logger.info(f"\u2705 Model loaded successfully in {self._load_time:.1f}s")
            
        except Exception as e:
            # If path changed during load, this error is from the old load — ignore
            if self.model_path != target_path:
                logger.info(f"Load of {target_path} interrupted (switched to {self.model_path})")
                return
            logger.error(f"Failed to load model {target_path}: {e}")
            self._load_error = str(e)
            self.model = None
            self.processor = None
        finally:
            # Only clear loading flag if we're still the target
            if self.model_path == target_path:
                self._loading = False

    def load_model_async(self):
        """Start model loading in a background thread. Server can accept requests immediately."""
        import threading
        self._loading = True
        t = threading.Thread(target=self.load_model, daemon=True)
        t.start()
        return t

    @staticmethod
    def list_available_models() -> List[Dict[str, Any]]:
        """List MLX models available in the HuggingFace cache directory."""
        hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
        models = []
        if not hf_cache.exists():
            return models

        for model_dir in sorted(hf_cache.iterdir()):
            if not model_dir.is_dir() or not model_dir.name.startswith("models--"):
                continue
            # Parse "models--org--name" → "org/name"
            parts = model_dir.name.split("--", 2)
            if len(parts) < 3:
                continue
            model_id = f"{parts[1]}/{parts[2]}"

            # Check for a valid snapshot with config.json
            snapshots = model_dir / "snapshots"
            if not snapshots.exists():
                continue
            has_config = False
            size_bytes = 0
            for snap in snapshots.iterdir():
                if snap.is_dir():
                    cfg = snap / "config.json"
                    if cfg.exists():
                        has_config = True
                        # Estimate total size from snapshot
                        for f in snap.rglob("*"):
                            if f.is_file():
                                size_bytes += f.stat().st_size
                        break

            if has_config:
                models.append({
                    "id": model_id,
                    "size_gb": round(size_bytes / (1024**3), 1),
                    "is_mlx": "mlx" in model_id.lower() or "MLX" in model_id,
                })

        return models

    def model_status(self) -> dict:
        """Return model health status for the /api/health endpoint."""
        if self._loading:
            return {"status": "loading", "model": self.model_path}
        if self._load_error:
            return {"status": "error", "model": self.model_path, "error": self._load_error}
        if self.is_healthy():
            return {"status": "ready", "model": self.model_path, "load_time_s": round(self._load_time, 1)}
        return {"status": "not_loaded", "model": self.model_path}

    def is_healthy(self) -> bool:
        return self.model is not None and self.processor is not None

    def cleanup_temp_files(self):
        """Remove any temporary resized image files created during inference."""
        for f in self._temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except OSError:
                pass
        self._temp_files.clear()

    def _prepare_image(self, image_path: str) -> str:
        """Validate, auto-rotate (EXIF), and resize image for vision inference.
        
        Returns the path to a ready-to-use image (may be a temp file).
        Tracks temp files for later cleanup via cleanup_temp_files().
        Uses a cache keyed on (path, mtime) to skip re-processing unchanged images.
        """
        try:
            # Check cache: if same file at same mtime, reuse prepared path
            try:
                current_mtime = os.path.getmtime(image_path)
                cached = self._image_cache.get(image_path)
                if cached and cached[0] == current_mtime and os.path.exists(cached[1]):
                    logger.info(f"Using cached prepared image for {image_path}")
                    return cached[1]
            except OSError:
                pass

            img = Image.open(image_path)

            # Auto-rotate based on EXIF orientation (phone photos)
            try:
                from PIL import ImageOps
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass

            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            elif img.mode == "RGBA":
                # Flatten alpha onto white background for VLM compatibility
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background

            w, h = img.size
            longest = max(w, h)
            needs_resize = longest > MAX_IMAGE_DIMENSION
            needs_save = needs_resize or img.mode != "RGB"

            if not needs_save:
                img.close()
                try:
                    self._image_cache[image_path] = (current_mtime, image_path)
                except Exception:
                    pass
                return image_path

            if needs_resize:
                ratio = MAX_IMAGE_DIMENSION / longest
                new_size = (int(w * ratio), int(h * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                logger.info(f"Resized image from {w}x{h} to {new_size[0]}x{new_size[1]}")

            import tempfile
            fd, temp_path = tempfile.mkstemp(suffix=".jpg", prefix="kasset_img_")
            os.close(fd)
            img.save(temp_path, "JPEG", quality=92)
            img.close()
            self._temp_files.append(temp_path)
            try:
                self._image_cache[image_path] = (current_mtime, temp_path)
            except Exception:
                pass
            return temp_path
        except Exception as e:
            logger.error(f"Image preparation failed: {e}")
            return None

    def _build_prompt(self, messages: List[Dict], enable_thinking: bool = True, has_image: bool = False) -> str:
        """Build the appropriate prompt using the processor's chat template."""
        clean_msgs = []
        for i, m in enumerate(messages):
            content = m["content"]
            if isinstance(content, list):
                text_parts = [p.get("text", "") for p in content if p.get("type") == "text"]
                content = " ".join(text_parts).strip()
            if content:
                clean_msgs.append({"role": m["role"], "content": str(content)})

        if enable_thinking and clean_msgs and clean_msgs[0]["role"] == "system":
            clean_msgs[0]["content"] += "\nRespond with your thought process inside <think>...</think> tags before providing the final answer."

        if has_image:
            # ── Vision path ──────────────────────────────────────
            # mlx_vlm's apply_chat_template expects a plain user text string
            # + num_images so it can properly insert image placeholder tokens.
            # Passing a messages list with raw <image> text does NOT work —
            # the tokenizer won't convert it to vision tokens.
            user_text = ""
            for msg in reversed(clean_msgs):
                if msg["role"] == "user" and msg["content"].strip():
                    user_text = msg["content"]
                    break
            if not user_text:
                user_text = "Describe what you see in this image."

            prompt = apply_chat_template(
                self.processor, self.config, user_text, num_images=1
            )

            # Prepend system prompt + prior conversation as ChatML
            prior = ""
            for msg in clean_msgs[:-1]:
                prior += f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"
            if prior:
                prompt = prior + prompt

            # Append thinking tags (vision template doesn't handle them)
            if enable_thinking:
                prompt += "<think>\n"
            else:
                prompt += "<think>\n\n</think>\n\n"

            return prompt
        else:
            # ── Text-only path ───────────────────────────────────
            return apply_chat_template(
                self.processor,
                self.config,
                clean_msgs,
                add_generation_prompt=True,
                enable_thinking=enable_thinking
            )

    def generate(
        self,
        messages: List[Dict],
        image_filepath: str = None,
        max_tokens: int = DEFAULT_TOKENS,
        thinking: bool = True,
        temperature: float = None,
        top_p: float = None,
    ) -> str:
        """Non-streaming generation."""
        if not self.is_healthy():
            raise RuntimeError("Model is not loaded")
        if not self._inference_lock.acquire(timeout=5):
            raise RuntimeError("Model is busy with another request. Please wait.")
            
        has_image = bool(image_filepath and str(image_filepath).strip())
        prompt = self._build_prompt(messages, thinking, has_image)
        
        # Use provided values or fall back to defaults
        temp = temperature if temperature is not None else 0.6
        tp = top_p if top_p is not None else 0.95
        
        inference_image = None
        if has_image:
            inference_image = self._prepare_image(image_filepath)
            if inference_image is None:
                has_image = False
                prompt = self._build_prompt(messages, thinking, False)
                logger.warning("Image prep failed, falling back to text-only")
            else:
                max_tokens = min(max_tokens, VISION_TOKEN_CAP)
            
        t0 = time.time()
        try:
            output = generate(
                self.model, self.processor,
                prompt=prompt,
                image=inference_image,
                max_tokens=max_tokens,
                temperature=temp,
                top_p=tp,
                top_k=20,
                repetition_penalty=1.0,
                verbose=False,
            )
        except Exception as e:
            if inference_image and "token" in str(e).lower():
                logger.warning(f"Vision inference failed ({e}), retrying text-only")
                prompt = self._build_prompt(messages, thinking, False)
                output = generate(
                    self.model, self.processor,
                    prompt=prompt,
                    image=None,
                    max_tokens=max_tokens,
                    temperature=temp,
                    top_p=tp,
                    top_k=20,
                    repetition_penalty=1.0,
                    verbose=False,
                )
            else:
                raise
        finally:
            self._inference_lock.release()
        logger.info(f"Generated {len(output.text)} chars in {time.time()-t0:.1f}s")
        return output.text

    def stream_generate(
        self,
        messages: List[Dict],
        image: str = None,
        max_tokens: int = DEFAULT_TOKENS,
        thinking: bool = True,
        temperature: float = None,
        top_p: float = None,
    ) -> Generator[str, None, None]:
        """Yields text chunks as they are generated."""
        if not self.is_healthy():
            raise RuntimeError("Model is not loaded")
        if not self._inference_lock.acquire(timeout=5):
            raise RuntimeError("Model is busy with another request. Please wait.")
            
        has_image = bool(image and str(image).strip())
        prompt = self._build_prompt(messages, thinking, has_image)
        
        # Use provided values or fall back to defaults
        temp = temperature if temperature is not None else 0.6
        tp = top_p if top_p is not None else 0.95
        
        inference_image = None
        if has_image:
            inference_image = self._prepare_image(image)
            if inference_image is None:
                has_image = False
                prompt = self._build_prompt(messages, thinking, False)
                logger.warning("Image prep failed, falling back to text-only")
            else:
                max_tokens = min(max_tokens, VISION_TOKEN_CAP)
            
        try:
            for chunk in stream_generate(
                self.model, self.processor,
                prompt=prompt,
                image=inference_image,
                max_tokens=max_tokens,
                temperature=temp,
                top_p=tp,
                top_k=20,
                repetition_penalty=1.0,
            ):
                yield chunk.text if hasattr(chunk, "text") else str(chunk)
        except Exception as e:
            if inference_image and "token" in str(e).lower():
                logger.warning(f"Vision inference failed ({e}), retrying text-only")
                prompt = self._build_prompt(messages, thinking, False)
                for chunk in stream_generate(
                    self.model, self.processor,
                    prompt=prompt,
                    image=None,
                    max_tokens=max_tokens,
                    temperature=temp,
                    top_p=tp,
                    top_k=20,
                    repetition_penalty=1.0,
                ):
                    yield chunk.text if hasattr(chunk, "text") else str(chunk)
            else:
                raise
        finally:
            self._inference_lock.release()
