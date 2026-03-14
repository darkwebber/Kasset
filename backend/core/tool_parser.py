"""
tool_parser.py — Tool call extraction, parsing, and error diagnosis.

Extracted from agent.py for modularity. Handles multiple XML/JSON formats
that models produce, with robust fallback parsing for malformed output.
"""

import json
import logging
import re
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────
# ERROR DOCUMENTATION CACHE
# ──────────────────────────────────────────
# Local cache of error patterns → fixes. Checked before generic hints.
# Persisted to ~/.kasset/cache/error_docs.json for cross-session reuse.

_ERROR_DOC_CACHE_PATH = Path.home() / ".kasset" / "cache" / "error_docs.json"

# Built-in common error patterns (shipped with the app)
_BUILTIN_ERROR_DOCS: List[Dict[str, str]] = [
    # ── Plotly ──
    {"pattern": "invalid property specified.*colorbar", "fix": "Remove `colorbar` from Scatter3d — use `marker=dict(colorbar=...)` instead.", "lib": "plotly"},
    {"pattern": "invalid property.*surfacecolor.*scatter3d", "fix": "Scatter3d doesn't support `surfacecolor`. Use `marker=dict(color=values, colorscale='Viridis')` instead.", "lib": "plotly"},
    {"pattern": "invalid property.*line_color", "fix": "Use `line=dict(color='...')` instead of `line_color`.", "lib": "plotly"},
    {"pattern": "make_subplots.*3d", "fix": "NEVER use make_subplots for 3D. Use `fig = go.Figure()` directly and add traces.", "lib": "plotly"},
    {"pattern": "sample_colorscale|sample_colors|interpolate_color", "fix": "These Plotly color functions don't exist. Use `colorscale='Viridis'` parameter on traces.", "lib": "plotly"},
    {"pattern": "cannot convert.*to.*EagerTensor", "fix": "Mixing numpy and plotly arrays. Ensure all data is numpy arrays via `np.array()`.", "lib": "plotly"},
    # ── Matplotlib ──
    {"pattern": "unknown property.*ax\\.", "fix": "Check matplotlib property names. Use `ax.set_xlabel()`, `ax.set_ylabel()`, `ax.set_title()` — not direct assignment.", "lib": "matplotlib"},
    {"pattern": "posx and posy should be finite", "fix": "Your data contains NaN or Inf. Filter with `np.isfinite()` before plotting.", "lib": "matplotlib"},
    {"pattern": "invalid rgba arg", "fix": "Color format invalid. Use hex strings like '#ff0000', named colors like 'red', or tuples like (1.0, 0.0, 0.0, 1.0).", "lib": "matplotlib"},
    # ── Pandas ──
    {"pattern": "keyerror.*columns", "fix": "Column not found. Use `df.columns.tolist()` to see available columns.", "lib": "pandas"},
    {"pattern": "cannot reindex from a duplicate axis", "fix": "DataFrame has duplicate index values. Use `df.reset_index(drop=True)` first.", "lib": "pandas"},
    {"pattern": "cannot convert.*to numeric", "fix": "Column contains non-numeric data. Use `pd.to_numeric(df['col'], errors='coerce')` to convert.", "lib": "pandas"},
    # ── Numpy ──
    {"pattern": "could not broadcast.*shapes", "fix": "Array shape mismatch. Check shapes with `.shape` and use `np.meshgrid()` for coordinate grids or `np.broadcast_to()` to align.", "lib": "numpy"},
    {"pattern": "operands could not be broadcast together", "fix": "Shape mismatch in operation. Verify both arrays have compatible shapes. Use `.reshape()` or `np.meshgrid()`.", "lib": "numpy"},
    # ── MediaPipe ──
    {"pattern": "module 'mediapipe' has no attribute 'solutions'", "fix": "mediapipe >= 0.10.18 removed the `solutions` namespace. Use the new Tasks API instead: `import mediapipe as mp; from mediapipe.tasks.python import vision; detector = vision.FaceDetector.create_from_options(...)`. Or pin `mediapipe==0.10.14` which still has `mp.solutions`.", "lib": "mediapipe"},
    {"pattern": "mediapipe.*face_detection.*not found", "fix": "Use the MediaPipe Tasks API: `from mediapipe.tasks.python.vision import FaceDetector` instead of the deprecated `mp.solutions.face_detection`.", "lib": "mediapipe"},
    {"pattern": "mediapipe.*face_mesh.*not found", "fix": "Use the MediaPipe Tasks API: `from mediapipe.tasks.python.vision import FaceLandmarker` instead of `mp.solutions.face_mesh`.", "lib": "mediapipe"},
    {"pattern": "mediapipe.*selfie_segmentation", "fix": "Use `from mediapipe.tasks.python.vision import ImageSegmenter` instead of the deprecated `mp.solutions.selfie_segmentation`.", "lib": "mediapipe"},
    # ── OpenCV ──
    {"pattern": "cv2.*has no attribute.*data", "fix": "OpenCV data files moved. Use `cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')` — note `cv2.data.haarcascades` is a directory path string.", "lib": "opencv"},
    {"pattern": "error.*-215.*!empty.*cascade", "fix": "Cascade XML file not found. Use the full path: `cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'`.", "lib": "opencv"},
    {"pattern": "cv2.*error.*resize.*assertion", "fix": "Image resize failed — likely empty image or invalid dimensions. Check `img.shape` before resizing and ensure width/height > 0.", "lib": "opencv"},
    {"pattern": "cv2\\.cvtcolor.*error", "fix": "Color conversion failed. Ensure the image has the expected number of channels (e.g., 3 for BGR→RGB). Check with `img.shape`.", "lib": "opencv"},
    # ── PIL / Pillow ──
    {"pattern": "cannot write mode.*as jpeg", "fix": "JPEG doesn't support alpha. Convert first: `img = img.convert('RGB')` before saving as JPEG.", "lib": "pillow"},
    {"pattern": "image file is truncated", "fix": "Incomplete image file. Add `from PIL import ImageFile; ImageFile.LOAD_TRUNCATED_IMAGES = True` to handle partial files.", "lib": "pillow"},
    {"pattern": "decoder.*not available", "fix": "Pillow was built without this format's decoder. Reinstall: `pip install --force-reinstall Pillow`.", "lib": "pillow"},
    {"pattern": "cannot identify image file", "fix": "File is not a valid image or is corrupted. Verify the file path and that the file is a supported format (JPEG, PNG, etc.).", "lib": "pillow"},
    # ── rembg ──
    {"pattern": "rembg.*onnxruntime.*not found", "fix": "rembg requires onnxruntime. Install: `pip install onnxruntime`. On Apple Silicon use: `pip install onnxruntime-silicon`.", "lib": "rembg"},
    {"pattern": "rembg.*model.*download", "fix": "rembg model downloads on first use (~170MB). If it fails, check internet connection or pre-download with `from rembg import new_session; new_session('u2net')`.", "lib": "rembg"},
    # ── SciPy ──
    {"pattern": "scipy.*sparse.*not.*implemented", "fix": "This sparse operation isn't supported. Convert to dense first: `matrix.toarray()` or use a different sparse format.", "lib": "scipy"},
    {"pattern": "scipy.*linalg.*singular matrix", "fix": "Matrix is singular (non-invertible). Add regularization: `A + np.eye(n) * 1e-6` or use `np.linalg.lstsq` instead of `np.linalg.solve`.", "lib": "scipy"},
    # ── Seaborn ──
    {"pattern": "seaborn.*is not a valid.*kind", "fix": "Invalid plot kind. Valid seaborn relplot kinds: 'scatter', 'line'. Valid catplot kinds: 'strip', 'swarm', 'box', 'violin', 'boxen', 'point', 'bar', 'count'.", "lib": "seaborn"},
    # ── General Python ──
    {"pattern": "unexpected indent", "fix": "Fix indentation — likely mixed tabs and spaces or extra indent. Use consistent 4-space indentation.", "lib": "python"},
    {"pattern": "expected an indented block", "fix": "Empty block after if/for/def/class. Add `pass` or the intended code with proper indentation.", "lib": "python"},
    {"pattern": "unterminated string literal", "fix": "String not closed. Check for mismatched quotes. Use triple-quotes for multi-line strings.", "lib": "python"},
    {"pattern": "f-string.*backslash", "fix": "Backslashes not allowed in f-string expressions. Assign to a variable first, then use in the f-string.", "lib": "python"},
    {"pattern": "maximum recursion depth exceeded", "fix": "Infinite recursion. Add a base case to your recursive function or rewrite iteratively.", "lib": "python"},
    {"pattern": "object is not subscriptable", "fix": "Trying to index something that isn't a list/dict/tuple. Check the type with `type()` — you may have `None` where you expected a collection.", "lib": "python"},
    {"pattern": "'NoneType' object has no attribute", "fix": "A function returned None unexpectedly. Check the return value before using it. Common cause: forgetting `return` in a function.", "lib": "python"},
    {"pattern": "too many values to unpack", "fix": "The iterable has more elements than variables. Check the structure with `print()` before unpacking.", "lib": "python"},
    {"pattern": "not enough values to unpack", "fix": "The iterable has fewer elements than expected. Verify length with `len()` before unpacking.", "lib": "python"},
]

# Runtime cache (loaded from disk + built-in)
_error_doc_cache: Optional[List[Dict[str, str]]] = None


def _load_error_cache() -> List[Dict[str, str]]:
    """Load error doc cache from disk, merge with built-ins."""
    global _error_doc_cache
    if _error_doc_cache is not None:
        return _error_doc_cache

    _error_doc_cache = list(_BUILTIN_ERROR_DOCS)
    try:
        if _ERROR_DOC_CACHE_PATH.exists():
            with open(_ERROR_DOC_CACHE_PATH) as f:
                user_docs = json.load(f)
            if isinstance(user_docs, list):
                _error_doc_cache.extend(user_docs)
                logger.debug("Loaded %d cached error docs from disk", len(user_docs))
    except Exception as e:
        logger.warning("Failed to load error doc cache: %s", e)

    return _error_doc_cache


def add_error_doc(pattern: str, fix: str, lib: str = "unknown") -> None:
    """Add a new error pattern → fix to the persistent cache."""
    global _error_doc_cache
    cache = _load_error_cache()

    # Avoid duplicates
    for doc in cache:
        if doc.get("pattern") == pattern:
            doc["fix"] = fix
            break
    else:
        cache.append({"pattern": pattern, "fix": fix, "lib": lib})

    # Persist user-added entries (exclude built-ins)
    user_entries = cache[len(_BUILTIN_ERROR_DOCS):]
    try:
        _ERROR_DOC_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_ERROR_DOC_CACHE_PATH, "w") as f:
            json.dump(user_entries, f, indent=2)
    except Exception as e:
        logger.warning("Failed to save error doc cache: %s", e)


def lookup_error_doc(error_text: str) -> Optional[str]:
    """Check cached error patterns for a matching fix."""
    cache = _load_error_cache()
    err_lower = error_text.lower()
    for doc in cache:
        try:
            if re.search(doc["pattern"], err_lower):
                return f"[Cached fix ({doc.get('lib', '?')})]: {doc['fix']}"
        except re.error:
            if doc["pattern"].lower() in err_lower:
                return f"[Cached fix ({doc.get('lib', '?')})]: {doc['fix']}"
    return None


# ──────────────────────────────────────────
# AUTO-RESOLVE: web search → extract fix → cache
# ──────────────────────────────────────────

_resolve_lock = threading.Lock()
# Track recently-searched signatures to avoid re-searching within a session
_recently_searched: set = set()


def _extract_error_signature(error_text: str) -> Optional[str]:
    """Extract a concise, searchable error signature from a traceback.
    Returns the last meaningful exception line, stripped of local paths."""
    lines = error_text.strip().splitlines()
    # Walk from the bottom to find the actual exception line
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        # Skip file/line references
        if stripped.startswith("File ") or stripped.startswith("Traceback"):
            continue
        # Skip pure code context lines (start with caret or are very short)
        if stripped.startswith("^") or len(stripped) < 10:
            continue
        # Strip local file paths for cleaner search queries
        cleaned = re.sub(r'/[\w/._-]+\.py', '<module>', stripped)
        cleaned = re.sub(r'line \d+', '', cleaned).strip()
        if len(cleaned) > 15:
            return cleaned[:150]
    return None


def _search_web_for_fix(query: str) -> Optional[str]:
    """Perform a DuckDuckGo search and extract a concise fix from snippets."""
    try:
        from duckduckgo_search import DDGS
        ddgs = DDGS()
        results = list(ddgs.text(query, max_results=5))
        if not results:
            return None

        # Collect snippets that look like they contain fixes
        snippets = []
        for r in results:
            body = r.get("body", "")
            title = r.get("title", "")
            if body:
                snippets.append(f"{title}: {body}")

        if not snippets:
            return None

        combined = "\n".join(snippets[:3])
        # Try to extract the most actionable sentence
        fix = _extract_fix_from_text(combined)
        return fix
    except Exception as e:
        logger.debug("Web search for error fix failed: %s", e)
        return None


def _extract_fix_from_text(text: str) -> Optional[str]:
    """Extract the most actionable fix sentence from web search snippets."""
    # Split into sentences
    sentences = re.split(r'(?<=[.!])\s+', text)

    # Score sentences by actionability keywords
    action_keywords = [
        "use ", "install ", "replace ", "change ", "update ", "upgrade ",
        "instead", "fix", "solve", "workaround", "solution",
        "pip install", "import ", "try ", "add ", "remove ",
        "downgrade", "should be", "must be", "you need",
    ]
    scored = []
    for s in sentences:
        s_stripped = s.strip()
        if len(s_stripped) < 20 or len(s_stripped) > 300:
            continue
        score = sum(1 for kw in action_keywords if kw in s_stripped.lower())
        # Bonus for code-like content
        if '`' in s_stripped or '(' in s_stripped:
            score += 1
        if score > 0:
            scored.append((score, s_stripped))

    if not scored:
        # Fallback: return first non-trivial snippet
        for s in sentences:
            if len(s.strip()) > 30:
                return s.strip()[:250]
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    # Take top 1-2 sentences
    top = scored[:2]
    fix = " ".join(s for _, s in top)
    return fix[:400]


def auto_resolve_error(error_text: str, tool_name: str = "") -> Optional[str]:
    """Full auto-resolve pipeline:
    1. Check local cache for a matching fix
    2. If miss: extract error signature → web search → extract fix → cache it
    3. Return actionable fix string or None

    Thread-safe. Skips web search for signatures already searched this session.
    """
    # Step 1: local cache
    cached = lookup_error_doc(error_text)
    if cached:
        logger.info("Error doc cache HIT")
        return cached

    # Step 2: extract searchable signature
    signature = _extract_error_signature(error_text)
    if not signature:
        return None

    # Skip if we already searched this signature in this session
    sig_key = signature[:80].lower()
    if sig_key in _recently_searched:
        logger.debug("Skipping repeat web search for: %s", sig_key)
        return None

    # Step 3: web search (with lock to prevent concurrent searches)
    with _resolve_lock:
        # Double-check after acquiring lock
        if sig_key in _recently_searched:
            return lookup_error_doc(error_text)
        _recently_searched.add(sig_key)

        # Build a focused search query
        lang = "python"
        if tool_name == "execute_cpp":
            lang = "c++"
        query = f"{lang} {signature}"
        logger.info("Auto-resolving error via web search: %s", query[:120])

        fix_text = _search_web_for_fix(query)
        if not fix_text:
            logger.info("Web search returned no actionable fix")
            return None

        # Step 4: cache the discovered fix
        # Build a regex pattern from the signature
        pattern = re.escape(signature[:80].lower())
        # Detect library from error text
        lib = _detect_lib(error_text)
        add_error_doc(pattern, fix_text, lib=lib)
        logger.info("Cached new error doc: pattern=%s lib=%s fix=%s", pattern[:60], lib, fix_text[:80])

        return f"[Web-resolved fix ({lib})]: {fix_text}"


def _detect_lib(error_text: str) -> str:
    """Best-effort library detection from error text."""
    err = error_text.lower()
    lib_markers = [
        ("mediapipe", "mediapipe"), ("cv2", "opencv"), ("opencv", "opencv"),
        ("plotly", "plotly"), ("matplotlib", "matplotlib"), ("seaborn", "seaborn"),
        ("pandas", "pandas"), ("numpy", "numpy"), ("scipy", "scipy"),
        ("pillow", "pillow"), ("pil", "pillow"), ("rembg", "rembg"),
        ("torch", "pytorch"), ("sklearn", "scikit-learn"), ("tensorflow", "tensorflow"),
        ("onnx", "onnxruntime"),
    ]
    for marker, lib in lib_markers:
        if marker in err:
            return lib
    return "python"


def parse_thinking(raw: str) -> Tuple[str, str]:
    """Extract thinking content from model output.
    Returns (thinking_text, answer_text)."""
    tag_pairs = [
        ("<think>", "</think>"),
        ("<|thinking|>", "<|/thinking|>"),
    ]
    for open_tag, close_tag in tag_pairs:
        if close_tag in raw:
            if open_tag in raw:
                start = raw.index(open_tag) + len(open_tag)
                end = raw.index(close_tag)
                thought = raw[start:end].strip()
                answer = (raw[:raw.index(open_tag)] + raw[end + len(close_tag):]).strip()
                return thought, answer
            else:
                parts = raw.split(close_tag, 1)
                return parts[0].strip(), parts[1].strip()

    for open_tag, _ in tag_pairs:
        if open_tag in raw:
            start = raw.index(open_tag) + len(open_tag)
            return raw[start:].strip(), ""

    return "", raw.strip()


def _try_parse_xml_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """Parse Qwen3-Coder native XML tool call format.
    Format: <tool_call><function=name><parameter=key>value</parameter>...</function></tool_call>
    """
    # Match the native XML format with function= and parameter= attributes
    func_match = re.search(
        r'<tool_call>\s*<function=(\w+)>(.*?)</function>\s*</tool_call>',
        text, re.DOTALL | re.IGNORECASE
    )
    if not func_match:
        # Also try unclosed variant: <tool_call><function=name>...(no closing tags)
        func_match = re.search(
            r'<tool_call>\s*<function=(\w+)>(.*?)(?:</function>|$)',
            text, re.DOTALL | re.IGNORECASE
        )
    if not func_match:
        return None

    name = func_match.group(1)
    body = func_match.group(2)
    params = {}

    # Extract all <parameter=key>value</parameter> pairs
    for pm in re.finditer(r'<parameter=(\w+)>(.*?)</parameter>', body, re.DOTALL):
        params[pm.group(1)] = pm.group(2)

    if name:
        logger.info(f"Parsed Qwen3-Coder XML tool call: {name}({list(params.keys())})")
        return {"name": name, "arguments": params}
    return None


def extract_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """Extract tool call from model output. Handles multiple formats robustly:
    1. Qwen3-Coder XML: <tool_call><function=name><parameter=key>value</parameter></function></tool_call>
    2. JSON in XML tags: <tool_call>{"name": ..., "arguments": ...}</tool_call>
    3. Various fallback JSON formats
    """
    # 0. Qwen3-Coder native XML format (highest priority — matches training distribution)
    xml_result = _try_parse_xml_tool_call(text)
    if xml_result:
        return xml_result

    # 1. Standard JSON: <tool_call>...</tool_call>
    match = re.search(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL | re.IGNORECASE)
    if match:
        return _try_parse_tool_json(match.group(1))

    # 2. Unclosed tag: <tool_call>...{json}... (no closing tag — very common)
    match = re.search(r"<tool_call>\s*(.*)", text, re.DOTALL | re.IGNORECASE)
    if match:
        result = _try_parse_tool_json(match.group(1))
        if result:
            return result

    # 3. Alternative tag format: <|tool_call|>...<|/tool_call|>
    match = re.search(r"<\|tool_call\|>\s*(.*?)(?:<\|/tool_call\|>|$)", text, re.DOTALL)
    if match:
        result = _try_parse_tool_json(match.group(1))
        if result:
            return result

    # 4. Raw JSON with "name" and "arguments" keys (no tags at all)
    match = re.search(r'\{\s*"name"\s*:\s*"(\w+)"\s*,\s*"arguments"\s*:', text, re.DOTALL)
    if match:
        start = match.start()
        result = _try_parse_tool_json(text[start:])
        if result:
            return result

    return None


def _fix_json_newlines(s: str) -> str:
    """Escape raw newlines/tabs inside JSON strings that the model forgot to escape."""
    return s.replace('\r\n', '\\n').replace('\r', '\\n').replace('\n', '\\n').replace('\t', '\\t')


def _try_parse_tool_json(raw: str) -> Optional[Dict[str, Any]]:
    """Attempt to parse a tool call JSON from potentially messy model output."""
    raw = raw.strip()
    if not raw:
        return None

    # Try direct parse first
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "name" in obj:
            return obj
    except json.JSONDecodeError:
        pass

    # Try with fixed newlines (model often puts raw newlines in code strings)
    try:
        obj = json.loads(_fix_json_newlines(raw))
        if isinstance(obj, dict) and "name" in obj:
            return obj
    except json.JSONDecodeError:
        pass

    # Extract the first complete JSON object using brace-depth counting
    brace_depth = 0
    start = None
    for i, ch in enumerate(raw):
        if ch == '{':
            if start is None:
                start = i
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0 and start is not None:
                candidate = raw[start:i + 1]
                for attempt in (candidate, _fix_json_newlines(candidate)):
                    try:
                        obj = json.loads(attempt)
                        if isinstance(obj, dict) and "name" in obj:
                            return obj
                    except json.JSONDecodeError:
                        pass
                start = None

    # Dedicated extraction for tools with large string content that often fails JSON parsing
    name_match = re.search(r'"name"\s*:\s*"(\w+)"', raw)
    if name_match:
        tool_name = name_match.group(1)

        # Map of tool_name -> primary content field for direct string extraction
        _large_content_tools = {
            "execute_python": "code",
            "execute_cpp": "code",
            "write_file": "content",
            "html_preview": "html",
        }

        primary_field = _large_content_tools.get(tool_name)
        if primary_field:
            field_match = re.search(rf'"{primary_field}"\s*:\s*"', raw)
            if field_match:
                field_start = field_match.end()
                i = field_start
                chars = []
                while i < len(raw):
                    if raw[i] == '\\' and i + 1 < len(raw):
                        chars.append(raw[i:i+2])
                        i += 2
                    elif raw[i] == '"':
                        break
                    else:
                        chars.append(raw[i])
                        i += 1
                value = ''.join(chars)
                value = value.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
                logger.info(f"Extracted {primary_field} for {tool_name} ({len(value)} chars) via direct scan")

                # Try to extract other simple string args too (e.g. path, title)
                args = {primary_field: value}
                for other_field in ("path", "title", "filename", "language", "mode"):
                    fm = re.search(rf'"{other_field}"\s*:\s*"([^"]*)"', raw)
                    if fm:
                        args[other_field] = fm.group(1)
                return {"name": tool_name, "arguments": args}

        # For other tools, try regex extraction of arguments
        args_match = re.search(r'"arguments"\s*:\s*\{', raw)
        if args_match:
            depth = 0
            astart = args_match.end() - 1
            for i in range(astart, len(raw)):
                if raw[i] == '{': depth += 1
                elif raw[i] == '}': depth -= 1
                if depth == 0:
                    args_str = raw[astart:i+1]
                    for attempt in (args_str, _fix_json_newlines(args_str)):
                        try:
                            args = json.loads(attempt)
                            return {"name": tool_name, "arguments": args}
                        except json.JSONDecodeError:
                            pass
                    break

    if '<tool_call>' in raw.lower() or '"name"' in raw:
        logger.warning(f"Failed to parse tool call from: {raw[:200]}")
    return None


def has_tool_call_attempt(text: str) -> bool:
    """Check if the model attempted a tool call but it failed to parse."""
    lower = text.lower()
    return (
        '<tool_call>' in lower
        or '<|tool_call|>' in lower
        or '<function=' in lower  # Qwen3-Coder native XML format
    )


def diagnose_tool_call_error(text: str) -> str:
    """Analyze a failed tool call and produce a clear error message for the model."""
    match = re.search(r'<tool_call>\s*(.*?)(?:</tool_call>|$)', text, re.DOTALL | re.IGNORECASE)
    if not match:
        match = re.search(r'<\|tool_call\|>\s*(.*?)(?:<\|/tool_call\|>|$)', text, re.DOTALL)

    raw_json = match.group(1).strip() if match else ""
    snippet = raw_json[:300] if raw_json else text[-300:]

    issues = []
    if raw_json:
        brace_count = raw_json.count('{') - raw_json.count('}')
        if brace_count > 0:
            issues.append(f"Unclosed braces: {brace_count} opening '{{' without matching '}}'.")
        elif brace_count < 0:
            issues.append(f"Extra closing braces: {abs(brace_count)} unmatched '}}'.")

        if '"code"' in raw_json:
            code_start = raw_json.find('"code"')
            code_section = raw_json[code_start:]
            in_str = False
            for i, ch in enumerate(code_section):
                if ch == '"' and (i == 0 or code_section[i-1] != '\\'):
                    in_str = not in_str
                if in_str and ch == '\n':
                    issues.append("Raw newlines inside the 'code' string value. Use \\n instead of actual line breaks.")
                    break

        if '"name"' not in raw_json:
            issues.append("Missing 'name' key in the tool call JSON.")
        if '"arguments"' not in raw_json:
            issues.append("Missing 'arguments' key in the tool call JSON.")

        try:
            json.loads(raw_json)
        except json.JSONDecodeError as e:
            issues.append(f"JSON parse error: {e.msg} at position {e.pos}.")
    else:
        issues.append("The <tool_call> tag was found but no JSON content was extracted.")

    issue_text = "\n".join(f"  - {i}" for i in issues) if issues else "  - Unknown JSON formatting error."

    return (
        f"[SYSTEM] Your previous tool call failed to parse. Here's what went wrong:\n"
        f"{issue_text}\n\n"
        f"Your malformed output was:\n```\n{snippet}\n```\n\n"
        f"Fix the tool call and try again. Accepted formats:\n"
        f"- JSON: <tool_call>{{\"name\": \"tool_name\", \"arguments\": {{...}}}}</tool_call>\n"
        f"- XML: <tool_call><function=tool_name><parameter=key>value</parameter></function></tool_call>\n"
        f"- Use \\n for newlines and \\\" for quotes inside string values.\n"
        f"- Do NOT put any text after the </tool_call> tag."
    )


def enrich_tool_error(tool_name: str, tool_args: dict, error_result: str) -> str:
    """Produce actionable feedback when a tool execution fails."""
    hints = []
    err = error_result.lower()
    err_raw = error_result

    if "no such file" in err or "does not exist" in err or "filenotfounderror" in err:
        path_hint = tool_args.get("path", tool_args.get("directory", ""))
        hints.append("The file/path doesn't exist. Use `list_directory` or `search_files` to verify the correct path first.")
        if path_hint:
            from pathlib import PurePosixPath
            parent = str(PurePosixPath(path_hint).parent)
            hints.append(f"Try: list_directory(\"{parent}\") to see what exists.")
    elif "permission" in err and "denied" in err:
        hints.append("Permission denied. The sandbox cannot access this path. Try a different location or use ~/.")
    elif "isadirectoryerror" in err:
        hints.append("You tried to read a directory as a file. Use `list_directory` instead of `read_file`.")
    elif "notadirectoryerror" in err:
        hints.append("You tried to list a file as a directory. Use `read_file` instead of `list_directory`.")
    elif "syntaxerror" in err or "indentationerror" in err:
        line_match = re.search(r'line (\d+)', err_raw)
        line_info = f" at line {line_match.group(1)}" if line_match else ""
        hints.append(f"Syntax/indentation error{line_info}. Fix the specific line — do NOT rewrite the entire script.")
    elif "nameerror" in err:
        var_match = re.search(r"name '(\w+)' is not defined", err_raw)
        if var_match:
            hints.append(f"Variable `{var_match.group(1)}` is not defined. Check spelling, or define it before use. Remember: variables persist across execute_python calls.")
        else:
            hints.append("A variable is not defined. Check your variable names and ensure they're defined before use.")
    elif "typeerror" in err:
        hints.append("Type mismatch. Check function argument types and return values.")
    elif "keyerror" in err:
        key_match = re.search(r"KeyError:\s*['\"]?(\w+)", err_raw)
        key_info = f" Key `{key_match.group(1)}` not found." if key_match else ""
        hints.append(f"Dictionary key not found.{key_info} Use `.get()` for safe access or check available keys with `.keys()`.")
    elif "indexerror" in err:
        hints.append("List index out of range. Check the length of your list/array before indexing.")
    elif "valueerror" in err:
        prop_match = re.search(r"Invalid property specified for object of type ['\"]?[\w.]+['\"]?:\s*['\"](\w+)['\"]", err_raw)
        if prop_match:
            bad_prop = prop_match.group(1)
            hints.append(f"Property `{bad_prop}` does NOT exist on this Plotly object. REMOVE it entirely.")
        else:
            hints.append("Invalid value. Check that input data is in the expected format.")
    elif "attributeerror" in err:
        attr_match = re.search(r"has no attribute '(\w+)'", err_raw)
        if attr_match:
            hints.append(f"Object has no attribute `{attr_match.group(1)}`. Check the object type with `type()` and use `dir()` to see available attributes.")
        else:
            hints.append("Attribute error. Verify the object type and available methods.")
    elif "modulenotfounderror" in err or "no module named" in err:
        mod_match = re.search(r"No module named ['\"](\w+)", err_raw)
        mod_name = mod_match.group(1) if mod_match else "the module"
        hints.append(f"Module `{mod_name}` is not installed. Pre-available: pandas, numpy, matplotlib, scipy, seaborn, plotly, Pillow, sympy.")
    elif "zerodivisionerror" in err:
        hints.append("Division by zero. Add a check before dividing.")
    elif "timed out" in err:
        hints.append("Command timed out (30s limit). Simplify the operation or break into smaller steps.")
    elif "blocked" in err:
        hints.append("This command is blocked for safety. Use an alternative approach.")
    elif "consent_required" in err:
        hints.append("This command needs user approval. Wait for the consent prompt.")
    elif "command not found" in err:
        cmd_match = re.search(r"(\w+): command not found", err_raw)
        if cmd_match:
            hints.append(f"`{cmd_match.group(1)}` is not installed. Try an alternative tool or approach.")
    elif "exit" in err and re.search(r'exit (\d+)', err):
        exit_match = re.search(r'exit (\d+)', err)
        hints.append(f"Command exited with code {exit_match.group(1)}. Check stderr output above for details.")
    elif "traceback" in err and not hints:
        hints.append("An exception occurred. Read the traceback carefully and fix only the failing line(s).")

    # Check error documentation cache for a more specific fix
    cached_fix = lookup_error_doc(error_result)
    if cached_fix:
        hints.insert(0, cached_fix)

    # For truly unfamiliar errors with tracebacks, suggest web search
    if not hints and "traceback" in err:
        # Extract the actual exception line for a focused search query
        exc_lines = [l.strip() for l in err_raw.strip().splitlines() if l.strip() and not l.strip().startswith("File ") and not l.strip().startswith("Traceback")]
        exc_summary = exc_lines[-1] if exc_lines else ""
        if exc_summary and len(exc_summary) > 10:
            hints.append(f"Unfamiliar error. Consider using `search_web` with query: \"python {exc_summary[:100]}\" to find the fix.")
        else:
            hints.append("An exception occurred. Read the traceback carefully and fix only the failing line(s).")

    base = f"Tool result for {tool_name}: {error_result}"
    if hints:
        base += "\n[Diagnosis: " + " ".join(hints) + "]"
    return base
