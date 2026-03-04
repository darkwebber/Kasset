"""
model_server.py — Qwen3.5-9B MLX 4-bit inference server (vision + text)
Run first:  python model_server.py
"""

import json
import logging
import os
import tempfile
import time
from typing import Dict, Any, List, Tuple
import gradio as gr
from PIL import Image
from utils import validate_image_file, MAX_IMAGE_SIZE_MB

try:
    from mlx_vlm import load, generate, stream_generate
    from mlx_vlm.prompt_utils import apply_chat_template
    from mlx_vlm.utils import load_config
except ImportError as e:
    logging.error(f"MLX VLM not installed: {e}")
    raise

# ──────────────────────────────────────────
# 1. LOGGING AND CONFIGURATION
# ──────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODEL_PATH = os.environ.get("MODEL_PATH", "mlx-community/Qwen3.5-9B-MLX-4bit")
MAX_TOKENS = 32768
DEFAULT_TOKENS = 4096
MAX_IMAGE_DIMENSION = 768   # Aggressive resize — fewer visual tokens = much faster inference
VISION_TOKEN_CAP = 4096     # Hard cap on tokens for vision tasks (prevents runaway thinking)

# ──────────────────────────────────────────
# 2. MODEL LOADING (SIMPLIFIED)
# ──────────────────────────────────────────
print(f"🚀 Initializing {MODEL_PATH} on Apple Silicon...")
try:
    model, processor = load(MODEL_PATH)
    config = load_config(MODEL_PATH)

    # Override the complex Qwen3.5 Jinja template to avoid the
    # "No user query found in messages" error caused by ns.multi_step_tool
    # logic in the official template.  This simplified version handles
    # system/user/assistant messages and the enable_thinking flag correctly.
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
    processor.tokenizer.chat_template = _SIMPLE_TEMPLATE
    logger.info("Applied simplified chat template (avoids multi_step_tool error)")

    print("✅ Model loaded successfully.\n")
except Exception as e:
    logger.error(f"Failed to load model: {e}")
    print(f"❌ Model loading failed: {e}")
    print("Please ensure the model is downloaded and accessible.")
    model, processor, config = None, None, None

# ──────────────────────────────────────────
# 3. INFERENCE LOGIC
# ──────────────────────────────────────────
def validate_messages(messages: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """Validate and sanitize input messages."""
    try:
        if not isinstance(messages, list):
            return False, "Messages must be a list"
            
        if not messages:
            return False, "Messages list cannot be empty"
            
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                return False, f"Message {i} must be a dictionary"
                
            if "role" not in msg or "content" not in msg:
                return False, f"Message {i} missing required 'role' or 'content' fields"
                
            if msg["role"] not in ["system", "user", "assistant"]:
                return False, f"Message {i} has invalid role: {msg['role']}"
                
            if not isinstance(msg["content"], str):
                return False, f"Message {i} content must be a string"
                
            # Check for content length limits
            if len(msg["content"]) > 10000:  # Reasonable limit
                return False, f"Message {i} content too long (>10k characters)"
                
        return True, "Valid messages"
    except Exception as e:
        logger.error(f"Message validation error: {e}")
        return False, f"Validation error: {str(e)}"

def _resize_image_if_needed(image_path: str) -> str:
    """Resize image if larger than MAX_IMAGE_DIMENSION to reduce visual tokens.
    
    Returns the (possibly new) image path. Original is untouched.
    """
    try:
        with Image.open(image_path) as img:
            # Convert to RGB (drop alpha — fewer bytes, faster processing)
            if img.mode != "RGB":
                img = img.convert("RGB")

            w, h = img.size
            longest = max(w, h)
            if longest <= MAX_IMAGE_DIMENSION:
                logger.info(f"Image {w}x{h} — within limit, no resize needed")
                return image_path

            scale = MAX_IMAGE_DIMENSION / longest
            new_w, new_h = int(w * scale), int(h * scale)
            resized = img.resize((new_w, new_h), Image.BILINEAR)  # faster than LANCZOS

            # Save as JPEG (smaller file, faster load by model)
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            resized.save(tmp.name, "JPEG", quality=85)
            logger.info(f"Resized image {w}x{h} → {new_w}x{new_h} (JPEG, {tmp.name})")
            return tmp.name
    except Exception as e:
        logger.warning(f"Image resize failed ({e}), using original")
        return image_path


def _build_chatml_fallback(messages: List[Dict[str, Any]], enable_thinking: bool) -> str:
    """Manually build a ChatML prompt as a fallback."""
    prompt = ""
    for msg in messages:
        prompt += f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"
    prompt += "<|im_start|>assistant\n"
    if enable_thinking:
        # Cue the model to start a thinking block (matches real template behavior)
        prompt += "<think>\n"
    else:
        # Pre-fill an empty think block to suppress CoT
        prompt += "<think>\n\n</think>\n\n"
    return prompt

def _build_prompt(messages: List[Dict[str, Any]], image_filepath: str, has_image: bool, enable_thinking: bool) -> str:
    """Build prompt for the model with proper handling of vision and text."""
    logger.debug(f"Building prompt: has_image={has_image}, enable_thinking={enable_thinking}, "
                 f"num_messages={len(messages)}, roles={[m['role'] for m in messages]}")
    try:
        template_handled_thinking = False
        if has_image:
            # ── Vision path: use mlx_vlm's apply_chat_template ──────────────
            # Get the actual user text from the latest user message
            user_text = ""
            for msg in reversed(messages):
                if msg["role"] == "user" and msg["content"] not in ("[IMAGE]", "", None):
                    user_text = msg["content"]
                    break
            # If user sent image with no text, use actionable default
            if not user_text:
                user_text = "Analyze this image. If it contains a problem or coding task, solve it completely with working code. Otherwise, describe what you see."

            prompt = apply_chat_template(
                processor, config, user_text, num_images=1
            )

            # Prepend system prompt + prior conversation turns
            prior = ""
            for msg in messages[:-1]:
                content = "[Image]" if msg["content"] == "[IMAGE]" else msg["content"]
                prior += f"<|im_start|>{msg['role']}\n{content}<|im_end|>\n"
            if prior:
                prompt = prior + prompt

        else:
            # ── Text-only path: use tokenizer's apply_chat_template ──────────
            try:
                prompt = processor.tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=enable_thinking,
                )
                template_handled_thinking = True
            except Exception as tmpl_err:
                # Template may not support enable_thinking (TypeError) or may
                # reject the messages with it set (ValueError in Qwen3.5 MLX).
                # Retry without the kwarg before falling to full ChatML fallback.
                logger.warning(f"apply_chat_template with enable_thinking failed: {tmpl_err}")
                prompt = processor.tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )

        # Add thinking tags if the template didn't handle them (vision path)
        if not template_handled_thinking:
            if enable_thinking:
                prompt += "<think>\n"
            else:
                prompt += "<think>\n\n</think>\n\n"

        return prompt
    except Exception as e:
        logger.error(f"Prompt building error: {e}")
        logger.info("Falling back to manual ChatML prompt construction")
        return _build_chatml_fallback(messages, enable_thinking)

def _prepare_inference(messages_json, image_filepath, max_new_tokens, enable_thinking):
    """Shared validation and setup for streaming and non-streaming inference.

    Returns (error_string, params_dict). error_string is None on success.
    """
    if not isinstance(messages_json, str) or not messages_json.strip():
        return "Invalid messages JSON", None
    try:
        messages = json.loads(messages_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON format - {str(e)}", None

    is_valid, validation_msg = validate_messages(messages)
    if not is_valid:
        return validation_msg, None

    try:
        max_new_tokens = int(max_new_tokens)
    except (TypeError, ValueError):
        return "Invalid token limit type", None
    if max_new_tokens < 1 or max_new_tokens > MAX_TOKENS:
        return f"Invalid token limit (must be 1-{MAX_TOKENS})", None

    if model is None or processor is None:
        return "Model not loaded. Please check the model path and restart the server.", None

    has_image = bool(image_filepath and image_filepath.strip())
    if has_image:
        is_valid, validation_msg = validate_image_file(image_filepath)
        if not is_valid:
            return validation_msg, None

    prompt = _build_prompt(messages, image_filepath, has_image, enable_thinking)
    logger.info(f"Generated prompt type: {'vision' if has_image else 'text-only'}")
    logger.info(f"Prompt length: {len(prompt)} chars")
    logger.debug(f"Prompt preview: {prompt[:200]}...")

    if enable_thinking:
        temp, top_p_val = 1.0, 0.95
    else:
        temp, top_p_val = 0.7, 0.8

    inference_image = None
    if has_image:
        inference_image = _resize_image_if_needed(image_filepath)
        max_new_tokens = min(max_new_tokens, VISION_TOKEN_CAP)
        logger.info(f"Vision task: capped tokens to {max_new_tokens}")

    return None, {
        "prompt": prompt,
        "inference_image": inference_image,
        "max_new_tokens": max_new_tokens,
        "temp": temp,
        "top_p_val": top_p_val,
        "has_image": has_image,
    }


def run_inference(
    messages_json: str,
    image_filepath: str,
    max_new_tokens: int = DEFAULT_TOKENS,
    enable_thinking: bool = True,
) -> str:
    """Non-streaming inference with error handling."""
    try:
        error, params = _prepare_inference(messages_json, image_filepath, max_new_tokens, enable_thinking)
        if error:
            return f"❌ **Error:** {error}"

        t0 = time.time()
        output = generate(
            model, processor,
            prompt=params["prompt"],
            image=params["inference_image"],
            max_tokens=params["max_new_tokens"],
            temperature=params["temp"],
            top_p=params["top_p_val"],
            top_k=20,
            repetition_penalty=1.05,
            verbose=False,
        )
        elapsed = time.time() - t0
        result = output.text if hasattr(output, "text") else str(output)
        logger.info(f"Inference done in {elapsed:.1f}s | {len(result)} chars | "
                    f"{'vision' if params['has_image'] else 'text'}")

        if not result or not isinstance(result, str):
            return "❌ **Error:** Model generated empty or invalid response"
        return result
    except Exception as e:
        logger.error(f"Inference error: {e}")
        return f"❌ **Inference Error:** {str(e)}"


def run_inference_stream(
    messages_json: str,
    image_filepath: str,
    max_new_tokens: int = DEFAULT_TOKENS,
    enable_thinking: bool = True,
):
    """Streaming inference - yields accumulated text as tokens are generated."""
    try:
        error, params = _prepare_inference(messages_json, image_filepath, max_new_tokens, enable_thinking)
        if error:
            yield f"❌ **Error:** {error}"
            return

        accumulated = ""
        t0 = time.time()
        for chunk in stream_generate(
            model, processor,
            prompt=params["prompt"],
            image=params["inference_image"],
            max_tokens=params["max_new_tokens"],
            temperature=params["temp"],
            top_p=params["top_p_val"],
            top_k=20,
            repetition_penalty=1.05,
        ):
            token = chunk.text if hasattr(chunk, "text") else str(chunk)
            accumulated += token
            yield accumulated

        elapsed = time.time() - t0
        logger.info(f"Stream done in {elapsed:.1f}s | {len(accumulated)} chars | "
                    f"{'vision' if params['has_image'] else 'text'}")

        if not accumulated:
            yield "❌ **Error:** Model generated empty response"
    except Exception as e:
        logger.error(f"Stream error: {e}")
        yield f"❌ **Generation Error:** {str(e)}"


# ──────────────────────────────────────────
# 4. GRADIO API SERVER WITH IMPROVED ERROR HANDLING
# ──────────────────────────────────────────
with gr.Blocks(title="Qwen3.5-9B Inference Server") as server_app:
    gr.Markdown("## 🤖 Qwen3.5-9B MLX 4-bit Inference Server")
    
    # Status indicator
    with gr.Row():
        status_display = gr.Markdown("🟡 **Status:** Starting up...")
    
    # Model info
    with gr.Accordion("Model Information", open=False):
        gr.Markdown(f"- **Model:** {MODEL_PATH}\n- **Max Tokens:** {MAX_TOKENS}\n- **Max Image Size:** {MAX_IMAGE_SIZE_MB}MB")

    # Hidden API interface
    with gr.Row(visible=False):
        msg_input = gr.Textbox(label="messages_json")
        img_input = gr.Textbox(label="image_filepath")
        tokens_input = gr.Slider(1, MAX_TOKENS, value=DEFAULT_TOKENS, step=1, label="max_new_tokens")
        think_input = gr.Checkbox(value=True, label="enable_thinking")
        output_box = gr.Textbox(label="response")

    def check_model_status():
        """Check and update model status."""
        try:
            if model is not None and processor is not None:
                return "🟢 **Status:** Model ready and accepting requests"
            else:
                return "🔴 **Status:** Model failed to load - check logs"
        except Exception as e:
            return f"🔴 **Status:** Error - {str(e)}"
    
    # API endpoint with error handling
    def safe_run_inference(messages_json, image_filepath, max_new_tokens, enable_thinking):
        """Wrapper for safe inference execution."""
        try:
            result = run_inference(messages_json, image_filepath, max_new_tokens, enable_thinking)
            return result
        except Exception as e:
            logger.error(f"API inference error: {e}")
            return f"❌ **API Error:** {str(e)}"
    
    gr.Button("Generate", visible=False).click(
        fn=safe_run_inference,
        inputs=[msg_input, img_input, tokens_input, think_input],
        outputs=output_box,
        api_name="chat",
    )

    # Streaming endpoint — yields accumulated text token-by-token
    gr.Button("Stream", visible=False).click(
        fn=run_inference_stream,
        inputs=[msg_input, img_input, tokens_input, think_input],
        outputs=output_box,
        api_name="chat_stream",
    )
    
    # Update status on load
    server_app.load(
        check_model_status,
        outputs=[status_display]
    )

if __name__ == "__main__":
    try:
        logger.info("Starting Qwen3.5-9B MLX Inference Server...")
        
        server_app.launch(
            server_port=7861,
            server_name="0.0.0.0",
            share=False,
            show_error=True,
            quiet=False,
            theme=gr.themes.Base()
        )
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        print(f"❌ **Server Startup Error:** {e}")
        print("Please check if port 7861 is available and try again.")
