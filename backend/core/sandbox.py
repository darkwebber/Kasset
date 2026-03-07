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
    import csv as _csv
    _SHARED_GLOBALS['csv'] = _csv
except ImportError:
    pass
try:
    import re as _re
    _SHARED_GLOBALS['re'] = _re
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
    workspace = os.path.join(os.path.expanduser("~"), ".qwen-studio", "workspace")
    os.makedirs(workspace, exist_ok=True)
    return workspace


def execute_python_sandbox(code: str) -> dict:
    """
    Executes Python code safely, capturing stdout/stderr and matplotlib plots.
    Returns a dict with 'output' (str) and 'images' (list of base64 data URIs).
    Uses a shared global environment so variables persist across executions.
    """
    output_capture = io.StringIO()
    images = []

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

    return {
        "output": output.strip(),
        "images": images,
    }

