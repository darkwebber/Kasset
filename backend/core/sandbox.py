import sys
import os
import io
import contextlib
import base64
import traceback
import re

# Force non-interactive backend before any matplotlib import
os.environ['MPLBACKEND'] = 'Agg'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
# Monkey-patch plt.show to be a complete no-op
plt.show = lambda *args, **kwargs: None

# Global state to persist across multiple executions within a single session
_SHARED_GLOBALS = {
    'plt': plt,
    'pd': None,  # lazy-loaded if needed
    'np': None,
    '__name__': '__main__',
}

# Try to make common data libs available initially
try:
    import pandas as pd
    _SHARED_GLOBALS['pd'] = pd
except ImportError:
    pass
try:
    import numpy as np
    _SHARED_GLOBALS['np'] = np
except ImportError:
    pass
try:
    import scipy
    import scipy.stats
    _SHARED_GLOBALS['scipy'] = scipy
except ImportError:
    pass
try:
    import seaborn as sns
    _SHARED_GLOBALS['sns'] = sns
except ImportError:
    pass
try:
    import math as _math
    _SHARED_GLOBALS['math'] = _math
except ImportError:
    pass

# ML/DL libraries — pre-load if available
try:
    import sklearn
    _SHARED_GLOBALS['sklearn'] = sklearn
    from sklearn import model_selection, preprocessing, metrics, ensemble, linear_model, cluster, decomposition
    _SHARED_GLOBALS['model_selection'] = model_selection
    _SHARED_GLOBALS['preprocessing'] = preprocessing
    _SHARED_GLOBALS['metrics'] = metrics
except ImportError:
    pass
try:
    import torch
    _SHARED_GLOBALS['torch'] = torch
except ImportError:
    pass
try:
    import torchvision
    _SHARED_GLOBALS['torchvision'] = torchvision
except ImportError:
    pass
try:
    import PIL
    from PIL import Image as PILImage
    _SHARED_GLOBALS['PIL'] = PIL
    _SHARED_GLOBALS['PILImage'] = PILImage
except ImportError:
    pass
try:
    import json as _json
    _SHARED_GLOBALS['json'] = _json
except ImportError:
    pass
try:
    import re as _re
    _SHARED_GLOBALS['re'] = _re
except ImportError:
    pass
try:
    import plotly
    import plotly.graph_objects as go
    import plotly.express as px
    _SHARED_GLOBALS['plotly'] = plotly
    _SHARED_GLOBALS['go'] = go
    _SHARED_GLOBALS['px'] = px
except ImportError:
    pass

# ──────────────────────────────────────────
# PRE-BUILT VISUALIZATION HELPERS
# ──────────────────────────────────────────

def _qchart_bar(labels, values, title="", xlabel="", ylabel="", horizontal=False, color=None):
    """Quick bar chart. Usage: qchart_bar(['A','B','C'], [10,20,15], title='My Chart')"""
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = color or ['#58a6ff', '#3fb950', '#f85149', '#a371f7', '#d29922', '#e3b341']
    if isinstance(colors, str): colors = [colors]
    bar_colors = [colors[i % len(colors)] for i in range(len(labels))]
    if horizontal:
        ax.barh(labels, values, color=bar_colors, edgecolor='#30363d')
    else:
        ax.bar(labels, values, color=bar_colors, edgecolor='#30363d')
    if title: ax.set_title(title)
    if xlabel: ax.set_xlabel(xlabel)
    if ylabel: ax.set_ylabel(ylabel)
    ax.grid(axis='y' if not horizontal else 'x', alpha=0.3)
    plt.tight_layout()

def _qchart_pie(labels, values, title="", colors=None):
    """Quick pie chart. Usage: qchart_pie(['A','B','C'], [30,50,20], title='Distribution')"""
    fig, ax = plt.subplots(figsize=(8, 8))
    clrs = colors or ['#58a6ff', '#3fb950', '#f85149', '#a371f7', '#d29922', '#e3b341']
    ax.pie(values, labels=labels, autopct='%1.1f%%', colors=clrs[:len(labels)],
           textprops={'color': '#e6edf3'}, wedgeprops={'edgecolor': '#30363d'})
    if title: ax.set_title(title)
    plt.tight_layout()

def _qchart_line(x, y_series, labels=None, title="", xlabel="", ylabel=""):
    """Quick line chart. y_series can be a single list or list of lists for multiple lines.
    Usage: qchart_line([1,2,3], [[10,20,15],[5,25,10]], labels=['A','B'], title='Trend')"""
    fig, ax = plt.subplots(figsize=(10, 6))
    if not isinstance(y_series[0], (list, tuple)):
        y_series = [y_series]
    colors = ['#58a6ff', '#3fb950', '#f85149', '#a371f7', '#d29922', '#e3b341']
    for i, y in enumerate(y_series):
        label = labels[i] if labels and i < len(labels) else f'Series {i+1}'
        ax.plot(x, y, color=colors[i % len(colors)], label=label, marker='o', markersize=4)
    if labels: ax.legend()
    if title: ax.set_title(title)
    if xlabel: ax.set_xlabel(xlabel)
    if ylabel: ax.set_ylabel(ylabel)
    ax.grid(alpha=0.3)
    plt.tight_layout()

def _qchart_scatter(x, y, title="", xlabel="", ylabel="", color=None, size=None):
    """Quick scatter plot. Usage: qchart_scatter(x_data, y_data, title='Correlation')"""
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(x, y, c=color or '#58a6ff', s=size or 50, alpha=0.7, edgecolors='#30363d')
    if title: ax.set_title(title)
    if xlabel: ax.set_xlabel(xlabel)
    if ylabel: ax.set_ylabel(ylabel)
    ax.grid(alpha=0.3)
    plt.tight_layout()

def _qchart_hist(data, bins=30, title="", xlabel="", ylabel="Count", color=None):
    """Quick histogram. Usage: qchart_hist(data_list, bins=20, title='Distribution')"""
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(data, bins=bins, color=color or '#58a6ff', alpha=0.7, edgecolor='#30363d')
    if title: ax.set_title(title)
    if xlabel: ax.set_xlabel(xlabel)
    if ylabel: ax.set_ylabel(ylabel)
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()

def _qchart_heatmap(data, xlabels=None, ylabels=None, title="", cmap='viridis'):
    """Quick heatmap. data should be a 2D list or numpy array.
    Usage: qchart_heatmap([[1,2],[3,4]], xlabels=['A','B'], ylabels=['X','Y'])"""
    import numpy as _np
    fig, ax = plt.subplots(figsize=(10, 8))
    arr = _np.array(data)
    im = ax.imshow(arr, cmap=cmap, aspect='auto')
    fig.colorbar(im, ax=ax)
    if xlabels: ax.set_xticks(range(len(xlabels))); ax.set_xticklabels(xlabels, rotation=45, ha='right')
    if ylabels: ax.set_yticks(range(len(ylabels))); ax.set_yticklabels(ylabels)
    # Add value annotations
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            ax.text(j, i, f'{arr[i,j]:.1f}', ha='center', va='center', color='white', fontsize=9)
    if title: ax.set_title(title)
    plt.tight_layout()

# Register visualization helpers in shared globals
_SHARED_GLOBALS['qchart_bar'] = _qchart_bar
_SHARED_GLOBALS['qchart_pie'] = _qchart_pie
_SHARED_GLOBALS['qchart_line'] = _qchart_line
_SHARED_GLOBALS['qchart_scatter'] = _qchart_scatter
_SHARED_GLOBALS['qchart_hist'] = _qchart_hist
_SHARED_GLOBALS['qchart_heatmap'] = _qchart_heatmap


# ──────────────────────────────────────────
# IMAGE EDITING HELPERS
# ──────────────────────────────────────────

def _img_load(path: str):
    """Load an image from path. Returns PIL Image. Usage: img = img_load('photo.jpg')"""
    from PIL import Image as _Img
    p = os.path.expanduser(path)
    img = _Img.open(p)
    if img.mode == 'RGBA':
        pass  # keep alpha
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    abs_p = os.path.abspath(p)
    # Track as current working image for cross-turn persistence
    _SHARED_GLOBALS['_current_image_path'] = abs_p
    _SHARED_GLOBALS['_current_image'] = img
    # Track original image separately (only set on first load, not on _current_edit reloads)
    workspace = os.path.join(os.path.expanduser("~"), ".kasset", "workspace")
    if not abs_p.startswith(workspace):
        _SHARED_GLOBALS['_original_image'] = img.copy()
        _SHARED_GLOBALS['_original_image_path'] = abs_p
    return img

def _img_save(img, path: str = None, fmt: str = None, quality: int = 92):
    """Save image to path. If no path, saves to workspace with auto-name. Returns saved path.
    Usage: img_save(img, 'output.png') or img_save(img, fmt='webp')"""
    workspace = os.path.join(os.path.expanduser("~"), ".kasset", "workspace")
    os.makedirs(workspace, exist_ok=True)
    if path is None:
        import time as _t
        ext = fmt or 'png'
        path = os.path.join(workspace, f"edited_{int(_t.time())}.{ext}")
    else:
        p = os.path.expanduser(path)
        if not os.path.isabs(p):
            path = os.path.join(workspace, p)
        else:
            path = p
    save_fmt = fmt.upper() if fmt else None
    if save_fmt == 'JPG':
        save_fmt = 'JPEG'
    img.save(path, format=save_fmt, quality=quality)
    return path

def _img_show(img):
    """Display an image inline (auto-captured as plot). Usage: img_show(img)"""
    # Auto-save current working image for cross-turn persistence
    workspace = os.path.join(os.path.expanduser("~"), ".kasset", "workspace")
    os.makedirs(workspace, exist_ok=True)
    save_path = os.path.join(workspace, "_current_edit.png")
    if hasattr(img, 'save'):
        img.save(save_path)
        _SHARED_GLOBALS['_current_image_path'] = save_path
        _SHARED_GLOBALS['_current_image'] = img
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.imshow(img)
    ax.axis('off')
    plt.tight_layout(pad=0)

def _img_adjust(img, brightness=1.0, contrast=1.0, saturation=1.0, sharpness=1.0):
    """Adjust brightness, contrast, saturation, sharpness. Values: 1.0=no change, >1=increase, <1=decrease.
    Usage: img = img_adjust(img, brightness=1.3, saturation=0.5)"""
    from PIL import ImageEnhance as _Enh
    if brightness != 1.0:
        img = _Enh.Brightness(img).enhance(brightness)
    if contrast != 1.0:
        img = _Enh.Contrast(img).enhance(contrast)
    if saturation != 1.0:
        img = _Enh.Color(img).enhance(saturation)
    if sharpness != 1.0:
        img = _Enh.Sharpness(img).enhance(sharpness)
    return img

def _img_hue_shift(img, degrees: float = 0):
    """Shift hue by N degrees (0-360). Usage: img = img_hue_shift(img, 90)"""
    import numpy as _np
    from PIL import Image as _Img
    hsv = img.convert('HSV')
    arr = _np.array(hsv)
    arr[:, :, 0] = (arr[:, :, 0].astype(int) + int(degrees * 255 / 360)) % 256
    return _Img.fromarray(arr, 'HSV').convert('RGB')

def _img_crop(img, left: int, top: int, right: int, bottom: int):
    """Crop image to box (left, top, right, bottom). Usage: img = img_crop(img, 100, 100, 500, 400)"""
    return img.crop((left, top, right, bottom))

def _img_resize(img, width: int, height: int = None):
    """Resize image. If height is None, maintains aspect ratio. Usage: img = img_resize(img, 800)"""
    from PIL import Image as _Img
    if height is None:
        ratio = width / img.width
        height = int(img.height * ratio)
    return img.resize((width, height), _Img.LANCZOS)

def _img_rotate(img, degrees: float, expand: bool = True):
    """Rotate image by degrees (counter-clockwise). Usage: img = img_rotate(img, 45)"""
    return img.rotate(degrees, expand=expand, fillcolor=(0, 0, 0))

def _img_flip(img, direction: str = "horizontal"):
    """Flip image. direction: 'horizontal' or 'vertical'. Usage: img = img_flip(img, 'vertical')"""
    from PIL import Image as _Img
    if direction == "horizontal":
        return img.transpose(_Img.FLIP_LEFT_RIGHT)
    return img.transpose(_Img.FLIP_TOP_BOTTOM)

def _img_grayscale(img):
    """Convert to grayscale. Usage: img = img_grayscale(img)"""
    return img.convert('L').convert('RGB')

def _img_convert(input_path: str, output_path: str):
    """Convert image between formats. Usage: img_convert('photo.png', 'photo.webp')"""
    from PIL import Image as _Img
    img = _Img.open(os.path.expanduser(input_path))
    workspace = os.path.join(os.path.expanduser("~"), ".kasset", "workspace")
    if not os.path.isabs(output_path):
        output_path = os.path.join(workspace, output_path)
    fmt = output_path.rsplit('.', 1)[-1].upper()
    if fmt == 'JPG':
        fmt = 'JPEG'
        if img.mode == 'RGBA':
            img = img.convert('RGB')
    img.save(output_path, format=fmt)
    return output_path

def _img_draw_rect(img, left: int, top: int, right: int, bottom: int, color="red", width: int = 3):
    """Draw rectangle on image. Usage: img = img_draw_rect(img, 50, 50, 200, 200, color='#ff0000')"""
    from PIL import ImageDraw as _Draw
    draw = _Draw.Draw(img)
    draw.rectangle([left, top, right, bottom], outline=color, width=width)
    return img

def _img_draw_text(img, x: int, y: int, text: str, color="white", size: int = 24):
    """Draw text on image. Usage: img = img_draw_text(img, 10, 10, 'Hello!', size=36)"""
    from PIL import ImageDraw as _Draw, ImageFont as _Font
    draw = _Draw.Draw(img)
    try:
        font = _Font.truetype("/System/Library/Fonts/Helvetica.ttc", size)
    except Exception:
        font = _Font.load_default()
    draw.text((x, y), text, fill=color, font=font)
    return img

def _img_blur(img, radius: int = 5):
    """Apply Gaussian blur. Usage: img = img_blur(img, radius=10)"""
    from PIL import ImageFilter as _Filt
    return img.filter(_Filt.GaussianBlur(radius=radius))

def _img_edge_detect(img):
    """Detect edges in image. Usage: img = img_edge_detect(img)"""
    from PIL import ImageFilter as _Filt
    return img.filter(_Filt.FIND_EDGES)

def _img_threshold(img, threshold: int = 128):
    """Binary threshold segmentation. Usage: img = img_threshold(img, 128)"""
    gray = img.convert('L')
    return gray.point(lambda p: 255 if p > threshold else 0).convert('RGB')

def _img_color_replace(img, from_color, to_color, tolerance: int = 30):
    """Replace a color with another. Colors as (R,G,B) tuples.
    Usage: img = img_color_replace(img, (255,0,0), (0,0,255), tolerance=40)"""
    import numpy as _np
    from PIL import Image as _Img
    arr = _np.array(img)
    fc = _np.array(from_color)
    tc = _np.array(to_color)
    mask = _np.all(_np.abs(arr.astype(int) - fc.astype(int)) <= tolerance, axis=-1)
    arr[mask] = tc
    return _Img.fromarray(arr)

# ── Named color ranges for HSV-based operations ──
_COLOR_RANGES = {
    'red':     ((0, 50, 50),   (10, 255, 255),  (170, 50, 50),  (180, 255, 255)),
    'orange':  ((10, 50, 50),  (25, 255, 255),  None, None),
    'yellow':  ((25, 50, 50),  (35, 255, 255),  None, None),
    'green':   ((35, 50, 50),  (85, 255, 255),  None, None),
    'cyan':    ((85, 50, 50),  (100, 255, 255), None, None),
    'blue':    ((100, 50, 50), (130, 255, 255), None, None),
    'purple':  ((130, 50, 50), (155, 255, 255), None, None),
    'magenta': ((155, 50, 50), (170, 255, 255), None, None),
    'pink':    ((155, 30, 150),(175, 255, 255), None, None),
    'brown':   ((10, 50, 20),  (25, 200, 150),  None, None),
    'white':   ((0, 0, 200),   (180, 30, 255),  None, None),
    'black':   ((0, 0, 0),     (180, 255, 50),  None, None),
    'gray':    ((0, 0, 50),    (180, 30, 200),  None, None),
}

def _resolve_color_name(name: str):
    """Resolve a color name to a target RGB tuple."""
    _name_to_rgb = {
        'red': (220, 30, 30), 'orange': (240, 160, 30), 'yellow': (240, 230, 40),
        'green': (30, 180, 50), 'cyan': (30, 210, 210), 'blue': (40, 60, 220),
        'purple': (140, 40, 200), 'magenta': (210, 40, 180), 'pink': (240, 130, 170),
        'brown': (140, 80, 30), 'white': (255, 255, 255), 'black': (10, 10, 10),
        'gray': (130, 130, 130), 'grey': (130, 130, 130), 'gold': (218, 175, 32),
        'golden': (218, 175, 32), 'teal': (0, 160, 160), 'navy': (20, 20, 100),
        'lime': (50, 220, 50), 'violet': (130, 50, 200), 'indigo': (75, 0, 130),
        'maroon': (128, 0, 0), 'olive': (128, 128, 0), 'salmon': (250, 128, 114),
        'coral': (255, 127, 80), 'turquoise': (64, 224, 208), 'lavender': (180, 130, 220),
    }
    return _name_to_rgb.get(name.lower().strip())

def _img_color_range_replace(img, from_color: str, to_color, tolerance: int = 30):
    """Replace all pixels of a named color range with a target color.
    from_color: color name like 'yellow', 'blue', 'red', 'green', 'purple', etc.
    to_color: color name (str) OR (R,G,B) tuple.
    tolerance: widens the HSV range (0-100). Default 30.
    Usage: img = img_color_range_replace(img, 'yellow', 'purple')
           img = img_color_range_replace(img, 'blue', (0, 255, 0), tolerance=40)"""
    import numpy as _np
    from PIL import Image as _Img
    import colorsys

    # Resolve to_color
    if isinstance(to_color, str):
        tc = _resolve_color_name(to_color)
        if tc is None:
            raise ValueError(f"Unknown color name: '{to_color}'. Use an (R,G,B) tuple or known name.")
    else:
        tc = tuple(to_color)

    from_key = from_color.lower().strip()
    if from_key not in _COLOR_RANGES:
        raise ValueError(f"Unknown source color: '{from_color}'. Known: {', '.join(sorted(_COLOR_RANGES.keys()))}")

    lo1, hi1, lo2, hi2 = _COLOR_RANGES[from_key]

    # Widen range by tolerance
    def widen(lo, hi, tol):
        s_tol = int(tol * 2.55)  # scale 0-100 to 0-255
        v_tol = int(tol * 2.55)
        return (
            max(lo[0] - tol // 6, 0), max(lo[1] - s_tol, 0), max(lo[2] - v_tol, 0)
        ), (
            min(hi[0] + tol // 6, 180), min(hi[1] + s_tol, 255), min(hi[2] + v_tol, 255)
        )

    # Convert to HSV (PIL's HSV uses 0-255 for H, unlike OpenCV's 0-180)
    hsv = _np.array(img.convert('HSV'))
    # Scale PIL H (0-255) to OpenCV-style H (0-180) for range matching
    h_scaled = (hsv[:, :, 0].astype(_np.float32) / 255.0 * 180.0).astype(_np.uint8)
    s = hsv[:, :, 1]
    v = hsv[:, :, 2]

    lo1_w, hi1_w = widen(lo1, hi1, tolerance)
    mask = (
        (h_scaled >= lo1_w[0]) & (h_scaled <= hi1_w[0]) &
        (s >= lo1_w[1]) & (s <= hi1_w[1]) &
        (v >= lo1_w[2]) & (v <= hi1_w[2])
    )
    # Second range for wrap-around colors like red
    if lo2 is not None:
        lo2_w, hi2_w = widen(lo2, hi2, tolerance)
        mask2 = (
            (h_scaled >= lo2_w[0]) & (h_scaled <= hi2_w[0]) &
            (s >= lo2_w[1]) & (s <= hi2_w[1]) &
            (v >= lo2_w[2]) & (v <= hi2_w[2])
        )
        mask = mask | mask2

    # Blend: replace matched pixels with target color, preserving luminance
    arr = _np.array(img.convert('RGB')).copy()
    tc_arr = _np.array(tc, dtype=_np.uint8)

    # Preserve relative brightness by blending with original luminance
    orig_luma = (0.299 * arr[:,:,0] + 0.587 * arr[:,:,1] + 0.114 * arr[:,:,2])
    tc_luma = 0.299 * tc_arr[0] + 0.587 * tc_arr[1] + 0.114 * tc_arr[2]
    scale = _np.where(tc_luma > 0, orig_luma / (tc_luma + 1e-6), 1.0)
    scale = _np.clip(scale, 0.3, 2.5)

    for c in range(3):
        chan = arr[:, :, c].astype(_np.float32)
        chan[mask] = _np.clip(tc_arr[c] * scale[mask], 0, 255)
        arr[:, :, c] = chan.astype(_np.uint8)

    matched = int(_np.sum(mask))
    total = mask.shape[0] * mask.shape[1]
    print(f"Replaced {matched:,} pixels ({matched*100/total:.1f}%) from '{from_color}' to target color.")
    return _Img.fromarray(arr)

def _img_tint(img, color, strength: float = 0.3):
    """Apply a color tint/wash over the entire image.
    color: color name (str) or (R,G,B) tuple. strength: 0.0-1.0 (default 0.3).
    Usage: img = img_tint(img, 'green', 0.4)
           img = img_tint(img, (255, 200, 0), 0.2)"""
    import numpy as _np
    from PIL import Image as _Img
    if isinstance(color, str):
        tc = _resolve_color_name(color)
        if tc is None:
            raise ValueError(f"Unknown color name: '{color}'.")
    else:
        tc = tuple(color)
    strength = max(0.0, min(1.0, strength))
    arr = _np.array(img.convert('RGB')).astype(_np.float32)
    tint = _np.array(tc, dtype=_np.float32)
    result = arr * (1.0 - strength) + tint * strength
    return _Img.fromarray(_np.clip(result, 0, 255).astype(_np.uint8))

def _img_adjust_highlights(img, brightness: float = 1.3, saturation: float = 1.0, threshold: float = 0.65):
    """Adjust brightness/saturation of only the bright areas (highlights).
    threshold: 0.0-1.0, pixels above this luminance are affected (default 0.65).
    Usage: img = img_adjust_highlights(img, brightness=1.4, saturation=1.3)"""
    import numpy as _np
    from PIL import Image as _Img, ImageEnhance as _Enh
    arr = _np.array(img.convert('RGB')).astype(_np.float32)
    gray = _np.mean(arr, axis=2) / 255.0
    # Soft mask with feathering
    mask = _np.clip((gray - threshold) / (1.0 - threshold + 1e-6), 0, 1)
    mask3 = _np.stack([mask]*3, axis=2)
    # Apply adjustments to a copy
    adjusted = img.copy()
    if brightness != 1.0:
        adjusted = _Enh.Brightness(adjusted).enhance(brightness)
    if saturation != 1.0:
        adjusted = _Enh.Color(adjusted).enhance(saturation)
    adj_arr = _np.array(adjusted).astype(_np.float32)
    # Blend: adjusted in highlight regions, original elsewhere
    result = arr * (1.0 - mask3) + adj_arr * mask3
    return _Img.fromarray(_np.clip(result, 0, 255).astype(_np.uint8))

def _img_adjust_shadows(img, brightness: float = 1.3, saturation: float = 1.0, threshold: float = 0.35):
    """Adjust brightness/saturation of only the dark areas (shadows).
    threshold: 0.0-1.0, pixels below this luminance are affected (default 0.35).
    Usage: img = img_adjust_shadows(img, brightness=1.5)"""
    import numpy as _np
    from PIL import Image as _Img, ImageEnhance as _Enh
    arr = _np.array(img.convert('RGB')).astype(_np.float32)
    gray = _np.mean(arr, axis=2) / 255.0
    mask = _np.clip((threshold - gray) / (threshold + 1e-6), 0, 1)
    mask3 = _np.stack([mask]*3, axis=2)
    adjusted = img.copy()
    if brightness != 1.0:
        adjusted = _Enh.Brightness(adjusted).enhance(brightness)
    if saturation != 1.0:
        adjusted = _Enh.Color(adjusted).enhance(saturation)
    adj_arr = _np.array(adjusted).astype(_np.float32)
    result = arr * (1.0 - mask3) + adj_arr * mask3
    return _Img.fromarray(_np.clip(result, 0, 255).astype(_np.uint8))

def _img_overlay_color(img, color, mode: str = 'multiply', opacity: float = 0.5):
    """Overlay a color onto the image with a blending mode.
    color: name (str) or (R,G,B). mode: 'multiply', 'screen', 'overlay'. opacity: 0.0-1.0.
    Usage: img = img_overlay_color(img, 'gold', mode='overlay', opacity=0.3)"""
    import numpy as _np
    from PIL import Image as _Img
    if isinstance(color, str):
        tc = _resolve_color_name(color)
        if tc is None:
            raise ValueError(f"Unknown color name: '{color}'.")
    else:
        tc = tuple(color)
    opacity = max(0.0, min(1.0, opacity))
    arr = _np.array(img.convert('RGB')).astype(_np.float32) / 255.0
    c = _np.array(tc, dtype=_np.float32) / 255.0
    if mode == 'multiply':
        blended = arr * c
    elif mode == 'screen':
        blended = 1.0 - (1.0 - arr) * (1.0 - c)
    elif mode == 'overlay':
        low = 2.0 * arr * c
        high = 1.0 - 2.0 * (1.0 - arr) * (1.0 - c)
        blended = _np.where(arr < 0.5, low, high)
    else:
        raise ValueError(f"Unknown blend mode: '{mode}'. Use 'multiply', 'screen', or 'overlay'.")
    result = arr * (1.0 - opacity) + blended * opacity
    return _Img.fromarray((_np.clip(result, 0, 1) * 255).astype(_np.uint8))

def _img_get_original():
    """Get the original (unedited) image from the current session.
    Usage: original = img_get_original()"""
    if '_original_image' in _SHARED_GLOBALS and _SHARED_GLOBALS['_original_image'] is not None:
        return _SHARED_GLOBALS['_original_image'].copy()
    raise RuntimeError("No original image stored. Load an image first with img_load().")

def _img_info(img):
    """Get image metadata. Usage: img_info(img)"""
    return f"Size: {img.size[0]}x{img.size[1]}, Mode: {img.mode}, Format: {getattr(img, 'format', 'N/A')}"

# Register image editing helpers
_SHARED_GLOBALS['img_load'] = _img_load
_SHARED_GLOBALS['img_save'] = _img_save
_SHARED_GLOBALS['img_show'] = _img_show
_SHARED_GLOBALS['img_adjust'] = _img_adjust
_SHARED_GLOBALS['img_hue_shift'] = _img_hue_shift
_SHARED_GLOBALS['img_crop'] = _img_crop
_SHARED_GLOBALS['img_resize'] = _img_resize
_SHARED_GLOBALS['img_rotate'] = _img_rotate
_SHARED_GLOBALS['img_flip'] = _img_flip
_SHARED_GLOBALS['img_grayscale'] = _img_grayscale
_SHARED_GLOBALS['img_convert'] = _img_convert
_SHARED_GLOBALS['img_draw_rect'] = _img_draw_rect
_SHARED_GLOBALS['img_draw_text'] = _img_draw_text
_SHARED_GLOBALS['img_blur'] = _img_blur
_SHARED_GLOBALS['img_edge_detect'] = _img_edge_detect
_SHARED_GLOBALS['img_threshold'] = _img_threshold
_SHARED_GLOBALS['img_color_replace'] = _img_color_replace
_SHARED_GLOBALS['img_color_range_replace'] = _img_color_range_replace
_SHARED_GLOBALS['img_tint'] = _img_tint
_SHARED_GLOBALS['img_adjust_highlights'] = _img_adjust_highlights
_SHARED_GLOBALS['img_adjust_shadows'] = _img_adjust_shadows
_SHARED_GLOBALS['img_overlay_color'] = _img_overlay_color
_SHARED_GLOBALS['img_get_original'] = _img_get_original
_SHARED_GLOBALS['img_info'] = _img_info


def apply_custom_matplotlib_style():
    """Apply a dark retro-futuristic theme to matplotlib."""
    try:
        plt.style.use('dark_background')
        plt.rcParams.update({
            'axes.facecolor': '#0d1117',
            'figure.facecolor': '#0d1117',
            'axes.edgecolor': '#30363d',
            'grid.color': '#30363d',
            'text.color': '#e6edf3',
            'xtick.color': '#8b949e',
            'ytick.color': '#8b949e',
            'axes.labelcolor': '#8b949e',
            'axes.titlecolor': '#e6edf3',
            'font.family': 'sans-serif',
            'axes.titlesize': 14,
            'axes.titleweight': 'bold',
            'figure.dpi': 150,
            'lines.linewidth': 2.5,
            'lines.color': '#58a6ff',
            'axes.prop_cycle': plt.cycler('color', ['#58a6ff', '#3fb950', '#f85149', '#a371f7', '#d29922', '#e3b341'])
        })
    except Exception:
        pass


def _get_workspace_dir() -> str:
    """Return the agent workspace directory, creating it if needed."""
    workspace = os.path.join(os.path.expanduser("~"), ".kasset", "workspace")
    os.makedirs(workspace, exist_ok=True)
    return workspace


# ──────────────────────────────────────────
# PYTHON CODE SAFETY PRE-CHECK
# ──────────────────────────────────────────

# Patterns that indicate potentially destructive operations
_DANGEROUS_PATTERNS = [
    # Direct OS-level command execution
    (r'\bos\.system\s*\(', 'os.system() — use run_command tool instead'),
    (r'\bos\.popen\s*\(', 'os.popen() — use run_command tool instead'),
    (r'\bos\.exec[vlpe]*\s*\(', 'os.exec*() — direct process replacement not allowed'),
    (r'\bos\.spawn[vlpe]*\s*\(', 'os.spawn*() — use run_command tool instead'),
    (r'\bos\.remove\s*\(', 'os.remove() — file deletion requires run_command tool'),
    (r'\bos\.unlink\s*\(', 'os.unlink() — file deletion requires run_command tool'),
    (r'\bos\.rmdir\s*\(', 'os.rmdir() — directory removal requires run_command tool'),
    (r'\bos\.removedirs\s*\(', 'os.removedirs() — directory removal requires run_command tool'),
    # Subprocess
    (r'\bsubprocess\.\w+\s*\(', 'subprocess — use run_command tool for shell commands'),
    # shutil destructive ops
    (r'\bshutil\.rmtree\s*\(', 'shutil.rmtree() — recursive deletion not allowed'),
    (r'\bshutil\.move\s*\(', 'shutil.move() — file moves require run_command tool'),
    # ctypes / low-level
    (r'\bctypes\b', 'ctypes — low-level C interface not allowed in sandbox'),
    # Networking (exfiltration risk)
    (r'\bsocket\.socket\s*\(', 'socket — direct network access not allowed'),
    (r'\burllib\.request\b', 'urllib.request — use read_url tool instead'),
    (r'\brequests\.(get|post|put|delete|patch|head)\s*\(', 'requests — use read_url tool instead'),
    # Dynamic import tricks
    (r'\b__import__\s*\(', '__import__() — use normal import statements'),
    (r'\bimportlib\.import_module\s*\(', 'importlib — use normal import statements'),
    # Code generation / eval / exec
    (r'\beval\s*\(', 'eval() — not allowed in sandbox'),
    (r'\bexec\s*\(', 'exec() — not allowed in sandbox'),
    (r'\bcompile\s*\(', 'compile() — not allowed in sandbox'),
    # Bypass tricks
    (r'\bgetattr\s*\(\s*__builtins__', 'getattr(__builtins__) — not allowed in sandbox'),
    (r'\bchr\s*\(.*\)\s*\+\s*chr\s*\(', 'chr() string building — not allowed in sandbox'),
]

_DANGEROUS_COMPILED = [(re.compile(p), msg) for p, msg in _DANGEROUS_PATTERNS]

def _check_python_safety(code: str) -> list:
    """
    Scan Python code for dangerous patterns. Returns a list of
    (pattern_description, line_number) tuples for any matches found.
    Skips patterns found inside comments or string literals (best-effort).
    """
    violations = []
    lines = code.split('\n')
    for line_no, line in enumerate(lines, 1):
        # Strip comments
        stripped = re.sub(r'#.*$', '', line)
        # Skip empty lines
        if not stripped.strip():
            continue
        for pattern, desc in _DANGEROUS_COMPILED:
            if pattern.search(stripped):
                violations.append((desc, line_no))
    return violations


def execute_python_sandbox(code: str) -> dict:
    """
    Executes Python code safely, capturing stdout/stderr, matplotlib plots, and Plotly HTML.
    Returns a dict with 'output' (str), 'images' (list of base64 data URIs),
    and optionally 'html' (str) for interactive Plotly figures.
    Uses a shared global environment so variables persist across executions.
    """
    # Pre-execution safety check
    violations = _check_python_safety(code)
    if violations:
        details = "\n".join(f"  Line {ln}: {desc}" for desc, ln in violations)
        return {
            "output": (
                f"[BLOCKED] The code contains {len(violations)} potentially dangerous operation(s):\n"
                f"{details}\n\n"
                f"These operations are not allowed in the Python sandbox for safety. "
                f"Use the appropriate tools instead (run_command for shell ops, read_url for web requests). "
                f"Rewrite your code to avoid these patterns."
            ),
            "images": [],
        }

    output_capture = io.StringIO()
    images = []
    html_artifact = ""

    # Run in workspace dir so saved files don't clutter the repo
    workspace = _get_workspace_dir()
    prev_cwd = os.getcwd()
    os.chdir(workspace)

    # Ensure custom style is applied before every execution
    apply_custom_matplotlib_style()

    # Neutralize plt.show() calls and ensure non-interactive backend
    safe_code = re.sub(r'plt\.show\s*\([^)]*\)', '# plt.show() [auto-captured]', code)
    # Also handle matplotlib.pyplot.show()
    safe_code = re.sub(r'matplotlib\.pyplot\.show\s*\([^)]*\)', '# pyplot.show() [auto-captured]', safe_code)
    
    # Re-inject plt.show as no-op in case code re-imports
    _SHARED_GLOBALS['plt'] = plt
    plt.show = lambda *args, **kwargs: None

    # Snapshot existing Plotly figures before execution so we only capture NEW ones
    _pre_plotly_ids = set()
    try:
        import plotly.graph_objects as _go
        _pre_plotly_ids = {id(v) for v in _SHARED_GLOBALS.values() if isinstance(v, _go.Figure)}
    except ImportError:
        pass

    try:
        with contextlib.redirect_stdout(output_capture), contextlib.redirect_stderr(output_capture):
            exec(safe_code, _SHARED_GLOBALS)

            if len(plt.get_fignums()) > 0:
                for i in plt.get_fignums():
                    fig = plt.figure(i)
                    buf = io.BytesIO()
                    # Use a slightly transparent background for better blending
                    fig.savefig(buf, format='png', bbox_inches='tight', facecolor='#0d1117', edgecolor='none')
                    buf.seek(0)
                    img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                    images.append(f"data:image/png;base64,{img_b64}")
                plt.close('all')

            # Capture only NEW Plotly figures created during this execution
            try:
                import plotly.graph_objects as _go
                new_figs = [v for v in _SHARED_GLOBALS.values()
                            if isinstance(v, _go.Figure) and id(v) not in _pre_plotly_ids]
                if new_figs:
                    pfig = new_figs[-1]
                    # Apply dark theme and fill layout
                    pfig.update_layout(
                        template='plotly_dark',
                        paper_bgcolor='#0d1117',
                        plot_bgcolor='#0d1117',
                        autosize=True,
                        margin=dict(l=20, r=20, t=40, b=20),
                        height=480,
                    )
                    html_artifact = pfig.to_html(
                        include_plotlyjs='cdn',
                        full_html=True,
                        config={'displayModeBar': True, 'responsive': True}
                    )
            except (ImportError, Exception):
                pass

        output = output_capture.getvalue()
        if not output and not images:
            output = "Code executed successfully (no output)."

    except ModuleNotFoundError as e:
        missing = e.name or str(e)
        output = (
            f"MISSING_PACKAGE: {missing}\n"
            f"The package '{missing}' is not installed. "
            f"Ask the user if they'd like to install it. If they agree, "
            f"run: execute_python with code: import subprocess; subprocess.check_call(['pip', 'install', '{missing}'])\n"
            f"Then retry your original code."
        )
    except Exception as e:
        output = output_capture.getvalue() + "\n" + traceback.format_exc()
    finally:
        os.chdir(prev_cwd)

    result = {
        "output": output.strip(),
        "images": images,
    }
    if html_artifact:
        result["html"] = html_artifact
    return result

