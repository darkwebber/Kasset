import os
import time
import json
import logging
import gc
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

class ModelClient:
    """Wrapper around MLX-VLM to handle model loading, inference, and streaming."""
    
    def __init__(self, model_path: str = MODEL_PATH):
        self.model_path = model_path
        self.model = None
        self.processor = None
        self.config = None
        self._temp_files: list = []  # Track temp files for cleanup
        self.load_model()

    def load_model(self):
        """Load the MLX model into memory."""
        try:
            logger.info(f"Loading model: {self.model_path}")
            logger.info("This may take 15-30s. If downloading for the first time, it may take longer.")
            t0 = time.time()
            
            self.model, self.processor = load(self.model_path)
            self.config = load_config(self.model_path)

            # Inject the simple template to avoid Qwen3.5 tool-calling errors
            _SIMPLE_TEMPLATE = (
                "{%- if enable_thinking is not defined -%}"
                    "{%- set enable_thinking = true -%}"
                "{%- endif -%}"
                "{%- for message in messages -%}"
                    "{{- '<|im_start|>' + message['role'] + '\\n' "
                        "+ message['content'] + '<|im_end|>\\n' -}}"
                "{%- endfor -%}"
                "{%- if add_generation_prompt -%}"
                    "{{- '<|im_start|>assistant\\n' -}}"
                    "{%- if enable_thinking -%}"
                        "{{- '<think>\\n' -}}"
                    "{%- else -%}"
                        "{{- '<think>\\n\\n</think>\\n\\n' -}}"
                    "{%- endif -%}"
                "{%- endif -%}"
            )
            self._original_template = None
            if hasattr(self.processor, "tokenizer"):
                self._original_template = getattr(self.processor.tokenizer, "chat_template", None)
                self.processor.tokenizer.chat_template = _SIMPLE_TEMPLATE
            
            logger.info(f"✅ Model loaded successfully in {time.time() - t0:.1f}s")
            
        except Exception as e:
            logger.error(f"Failed to load model {self.model_path}: {e}")
            self.model = None
            self.processor = None

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
        """
        try:
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
    ) -> str:
        """Non-streaming generation."""
        if not self.is_healthy():
            raise RuntimeError("Model is not loaded")
            
        has_image = bool(image_filepath and str(image_filepath).strip())
        prompt = self._build_prompt(messages, thinking, has_image)
        
        temp = 1.0 if thinking else 0.7
        top_p = 0.95 if thinking else 0.8
        
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
                top_p=top_p,
                top_k=20,
                repetition_penalty=1.05,
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
                    top_p=top_p,
                    top_k=20,
                    repetition_penalty=1.05,
                    verbose=False,
                )
            else:
                raise
        logger.info(f"Generated {len(output.text)} chars in {time.time()-t0:.1f}s")
        return output.text

    def stream_generate(
        self,
        messages: List[Dict],
        image: str = None,
        max_tokens: int = DEFAULT_TOKENS,
        thinking: bool = True,
    ) -> Generator[str, None, None]:
        """Yields text chunks as they are generated."""
        if not self.is_healthy():
            raise RuntimeError("Model is not loaded")
            
        has_image = bool(image and str(image).strip())
        prompt = self._build_prompt(messages, thinking, has_image)
        
        temp = 1.0 if thinking else 0.7
        top_p = 0.95 if thinking else 0.8
        
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
                top_p=top_p,
                top_k=20,
                repetition_penalty=1.05,
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
                    top_p=top_p,
                    top_k=20,
                    repetition_penalty=1.05,
                ):
                    yield chunk.text if hasattr(chunk, "text") else str(chunk)
            else:
                raise
