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

# Base globals shared across all sessions (libraries only — immutable references)
_BASE_GLOBALS = {
    'plt': plt,
    'pd': None,  # lazy-loaded if needed
    'np': None,
    '__name__': '__main__',
}

# Legacy alias — points to default session globals
_SHARED_GLOBALS = _BASE_GLOBALS

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
    # Monkey-patch fig.show() to be a no-op — sandbox auto-captures figures
    _orig_fig_show = go.Figure.show
    go.Figure.show = lambda self, *args, **kwargs: None
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

# Register visualization helpers in base globals
_BASE_GLOBALS['qchart_bar'] = _qchart_bar
_BASE_GLOBALS['qchart_pie'] = _qchart_pie
_BASE_GLOBALS['qchart_line'] = _qchart_line
_BASE_GLOBALS['qchart_scatter'] = _qchart_scatter
_BASE_GLOBALS['qchart_hist'] = _qchart_hist
_BASE_GLOBALS['qchart_heatmap'] = _qchart_heatmap


# ──────────────────────────────────────────
# DIAGRAM HELPERS (for teaching / explanations)
# ──────────────────────────────────────────

def _qdiagram_flowchart(steps: list, title: str = "", direction: str = "vertical"):
    """Draw a flowchart / process diagram.
    steps: list of str labels (or list of {label, shape} dicts).
           shape: 'box' (default), 'diamond', 'oval', 'parallelogram'
    direction: 'vertical' (top-down) or 'horizontal' (left-right)
    Example: qdiagram_flowchart(["Start", "Process A", {"label": "Decision?", "shape": "diamond"}, "End"])
    """
    import matplotlib.patches as mpatches
    n = len(steps)
    if n == 0:
        return
    # Normalize steps
    nodes = []
    for s in steps:
        if isinstance(s, str):
            nodes.append({"label": s, "shape": "box"})
        else:
            nodes.append({"label": s.get("label", ""), "shape": s.get("shape", "box")})

    vertical = direction.startswith("v")
    fig_w = 10 if vertical else max(10, n * 2.5)
    fig_h = max(6, n * 1.4) if vertical else 6
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(-1, 10)
    ax.set_ylim(-0.5, n + 0.5)
    ax.axis('off')

    colors = ['#58a6ff', '#3fb950', '#f85149', '#a371f7', '#d29922', '#e3b341']

    for i, node in enumerate(nodes):
        if vertical:
            cx, cy = 5, n - 1 - i
        else:
            cx, cy = i * (9.0 / max(1, n - 1)) + 0.5 if n > 1 else 5, 2
        color = colors[i % len(colors)]

        shape = node["shape"]
        if shape == "diamond":
            diamond = mpatches.FancyBboxPatch((cx - 1.2, cy - 0.35), 2.4, 0.7,
                boxstyle="round,pad=0.1", facecolor=color + "30", edgecolor=color, linewidth=2)
            ax.add_patch(diamond)
        elif shape == "oval":
            ellipse = mpatches.Ellipse((cx, cy), 2.6, 0.7,
                facecolor=color + "30", edgecolor=color, linewidth=2)
            ax.add_patch(ellipse)
        else:
            rect = mpatches.FancyBboxPatch((cx - 1.3, cy - 0.3), 2.6, 0.6,
                boxstyle="round,pad=0.15", facecolor=color + "30", edgecolor=color, linewidth=2)
            ax.add_patch(rect)

        ax.text(cx, cy, node["label"], ha='center', va='center',
                fontsize=11, color='#e6edf3', fontweight='bold', wrap=True)

        # Arrow to next
        if i < n - 1:
            if vertical:
                nx, ny = 5, n - 2 - i
                ax.annotate('', xy=(nx, ny + 0.4), xytext=(cx, cy - 0.4),
                    arrowprops=dict(arrowstyle='->', color='#8b949e', lw=2))
            else:
                next_cx = (i + 1) * (9.0 / max(1, n - 1)) + 0.5 if n > 1 else 5
                ax.annotate('', xy=(next_cx - 1.3, cy), xytext=(cx + 1.3, cy),
                    arrowprops=dict(arrowstyle='->', color='#8b949e', lw=2))

    if title:
        ax.set_title(title, fontsize=14, fontweight='bold', color='#e6edf3', pad=15)
    plt.tight_layout()

def _qdiagram_concept_map(center: str, branches: dict, title: str = ""):
    """Draw a radial concept/mind map.
    center: label for the central node
    branches: dict of {label: [sub-items]} or {label: str}
    Example: qdiagram_concept_map("HashMap", {"put()": ["hash key", "find bucket", "insert"], "get()": ["hash key", "find bucket", "return value"]})
    """
    import math
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.set_xlim(-6, 6)
    ax.set_ylim(-5, 5)
    ax.axis('off')
    colors = ['#58a6ff', '#3fb950', '#f85149', '#a371f7', '#d29922', '#e3b341']

    # Center node
    center_circle = plt.Circle((0, 0), 0.8, color='#58a6ff', alpha=0.3, linewidth=2)
    center_circle.set_edgecolor('#58a6ff')
    ax.add_patch(center_circle)
    ax.text(0, 0, center, ha='center', va='center', fontsize=13, fontweight='bold', color='#e6edf3')

    branch_keys = list(branches.keys())
    n_branches = len(branch_keys)
    for bi, key in enumerate(branch_keys):
        angle = 2 * math.pi * bi / n_branches - math.pi / 2
        bx = 3.0 * math.cos(angle)
        by = 3.0 * math.sin(angle)
        color = colors[bi % len(colors)]

        # Line from center to branch
        ax.plot([0, bx], [0, by], color=color, lw=2, alpha=0.6)
        # Branch node
        branch_circle = plt.Circle((bx, by), 0.6, color=color, alpha=0.2, linewidth=2)
        branch_circle.set_edgecolor(color)
        ax.add_patch(branch_circle)
        ax.text(bx, by, key, ha='center', va='center', fontsize=10, fontweight='bold', color='#e6edf3')

        # Sub-items
        subs = branches[key]
        if isinstance(subs, str):
            subs = [subs]
        if not isinstance(subs, list):
            subs = [str(subs)]
        for si, sub in enumerate(subs):
            sub_angle = angle + (si - len(subs) / 2 + 0.5) * 0.35
            sx = bx + 1.8 * math.cos(sub_angle)
            sy = by + 1.8 * math.sin(sub_angle)
            ax.plot([bx, sx], [by, sy], color=color, lw=1.2, alpha=0.4)
            ax.text(sx, sy, sub, ha='center', va='center', fontsize=9, color='#8b949e',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='#161b22', edgecolor=color, alpha=0.8))

    if title:
        ax.set_title(title, fontsize=14, fontweight='bold', color='#e6edf3', pad=15)
    plt.tight_layout()

def _qdiagram_array(values: list, labels: list = None, highlights: list = None, title: str = ""):
    """Draw an array / list / table visualization.
    values: list of cell values
    labels: optional index labels (same length as values)
    highlights: optional list of indices to highlight
    Example: qdiagram_array([10, 20, 30, 40], labels=["0", "1", "2", "3"], highlights=[1, 3], title="My Array")
    """
    n = len(values)
    if n == 0:
        return
    highlights = set(highlights or [])
    cell_w = max(1.2, min(2.0, 12.0 / n))
    fig_w = min(16, n * cell_w + 2)
    fig, ax = plt.subplots(figsize=(fig_w, 2.5))
    ax.set_xlim(-0.5, n * cell_w + 0.5)
    ax.set_ylim(-1, 2)
    ax.axis('off')

    for i, val in enumerate(values):
        x = i * cell_w + 0.5
        color = '#58a6ff' if i in highlights else '#30363d'
        fill = '#58a6ff20' if i in highlights else '#161b22'
        rect = plt.Rectangle((x, 0), cell_w - 0.1, 1.0,
            facecolor=fill, edgecolor=color, linewidth=2, clip_on=False)
        ax.add_patch(rect)
        ax.text(x + (cell_w - 0.1) / 2, 0.5, str(val), ha='center', va='center',
                fontsize=12, fontweight='bold', color='#e6edf3')
        if labels:
            lbl = labels[i] if i < len(labels) else str(i)
            ax.text(x + (cell_w - 0.1) / 2, -0.3, lbl, ha='center', va='center',
                    fontsize=9, color='#8b949e')

    if title:
        ax.set_title(title, fontsize=13, fontweight='bold', color='#e6edf3', pad=10)
    plt.tight_layout()

def _qdiagram_linked_list(values: list, title: str = "", circular: bool = False):
    """Draw a linked list visualization.
    values: list of node values
    Example: qdiagram_linked_list([1, 2, 3, 4], title="Singly Linked List")
    """
    n = len(values)
    if n == 0:
        return
    node_w = 1.5
    gap = 1.0
    fig_w = min(16, n * (node_w + gap) + 1)
    fig, ax = plt.subplots(figsize=(fig_w, 2.5))
    ax.set_xlim(-0.5, n * (node_w + gap) + 0.5)
    ax.set_ylim(-0.5, 2)
    ax.axis('off')

    colors = ['#58a6ff', '#3fb950', '#f85149', '#a371f7', '#d29922', '#e3b341']
    for i, val in enumerate(values):
        x = i * (node_w + gap) + 0.5
        color = colors[i % len(colors)]
        # Node box
        rect = plt.Rectangle((x, 0.2), node_w, 0.8,
            facecolor=color + '20', edgecolor=color, linewidth=2, clip_on=False)
        ax.add_patch(rect)
        # Value
        ax.text(x + node_w * 0.4, 0.6, str(val), ha='center', va='center',
                fontsize=12, fontweight='bold', color='#e6edf3')
        # Pointer box
        ptr_rect = plt.Rectangle((x + node_w * 0.7, 0.2), node_w * 0.3, 0.8,
            facecolor='#0d1117', edgecolor=color, linewidth=1.5, clip_on=False)
        ax.add_patch(ptr_rect)
        # Arrow to next
        if i < n - 1:
            ax.annotate('', xy=(x + node_w + gap, 0.6), xytext=(x + node_w, 0.6),
                arrowprops=dict(arrowstyle='->', color='#8b949e', lw=2))
        elif circular:
            # Curved arrow back to first
            ax.annotate('', xy=(0.5, 0.2), xytext=(x + node_w, 0.6),
                arrowprops=dict(arrowstyle='->', color='#f85149', lw=2,
                    connectionstyle="arc3,rad=-0.4"))
        else:
            # Null pointer
            ax.text(x + node_w * 0.85, 0.6, '∅', ha='center', va='center',
                    fontsize=10, color='#f85149')

    if title:
        ax.set_title(title, fontsize=13, fontweight='bold', color='#e6edf3', pad=10)
    plt.tight_layout()

def _qdiagram_tree(root: dict, title: str = ""):
    """Draw a binary tree visualization.
    root: nested dict {val, left?, right?}
    Example: qdiagram_tree({"val": 10, "left": {"val": 5, "left": {"val": 2}, "right": {"val": 7}}, "right": {"val": 15}})
    """
    # Collect nodes via BFS with positions
    if not root:
        return
    nodes = []
    edges = []

    def _traverse(node, x, y, dx):
        if not node:
            return
        idx = len(nodes)
        nodes.append((x, y, str(node.get("val", "?"))))
        if node.get("left"):
            child_idx = len(nodes)
            edges.append((idx, child_idx))
            _traverse(node["left"], x - dx, y - 1.5, dx * 0.55)
        if node.get("right"):
            child_idx = len(nodes)
            edges.append((idx, child_idx))
            _traverse(node["right"], x + dx, y - 1.5, dx * 0.55)

    _traverse(root, 0, 0, 3.0)
    if not nodes:
        return

    xs = [n[0] for n in nodes]
    ys = [n[1] for n in nodes]
    margin = 2
    fig, ax = plt.subplots(figsize=(max(8, (max(xs) - min(xs)) + 4), max(5, (max(ys) - min(ys)) * -1 + 4)))
    ax.set_xlim(min(xs) - margin, max(xs) + margin)
    ax.set_ylim(min(ys) - margin, max(ys) + margin)
    ax.axis('off')

    colors = ['#58a6ff', '#3fb950', '#f85149', '#a371f7', '#d29922', '#e3b341']
    # Edges first
    for pi, ci in edges:
        ax.plot([nodes[pi][0], nodes[ci][0]], [nodes[pi][1], nodes[ci][1]],
                color='#8b949e', lw=2, zorder=1)
    # Nodes
    for i, (x, y, val) in enumerate(nodes):
        color = colors[i % len(colors)]
        circle = plt.Circle((x, y), 0.5, color=color, alpha=0.25, linewidth=2, zorder=2)
        circle.set_edgecolor(color)
        ax.add_patch(circle)
        ax.text(x, y, val, ha='center', va='center', fontsize=12,
                fontweight='bold', color='#e6edf3', zorder=3)

    if title:
        ax.set_title(title, fontsize=14, fontweight='bold', color='#e6edf3', pad=15)
    ax.set_aspect('equal')
    plt.tight_layout()

def _qdiagram_hashtable(buckets: dict, title: str = "Hash Table"):
    """Draw a hash table with buckets and chaining.
    buckets: dict of {bucket_index: [values]} or {bucket_index: value}
    Example: qdiagram_hashtable({0: ["apple", "avocado"], 1: [], 2: ["banana"], 3: ["cherry", "cranberry", "coconut"]})
    """
    n_buckets = max(buckets.keys()) + 1 if buckets else 0
    if n_buckets == 0:
        return

    fig_h = max(4, n_buckets * 0.8 + 1)
    max_chain = max((len(v) if isinstance(v, list) else 1) for v in buckets.values()) if buckets else 1
    fig_w = max(8, 3 + max_chain * 2.5)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(-0.5, 3 + max_chain * 2.5)
    ax.set_ylim(-0.5, n_buckets + 0.5)
    ax.axis('off')

    colors = ['#58a6ff', '#3fb950', '#f85149', '#a371f7', '#d29922', '#e3b341']

    for i in range(n_buckets):
        y = n_buckets - 1 - i
        color = colors[i % len(colors)]
        # Bucket label
        rect = plt.Rectangle((0, y - 0.25), 1.5, 0.5,
            facecolor=color + '20', edgecolor=color, linewidth=2)
        ax.add_patch(rect)
        ax.text(0.75, y, f"[{i}]", ha='center', va='center',
                fontsize=11, fontweight='bold', color='#e6edf3')

        vals = buckets.get(i, [])
        if not isinstance(vals, list):
            vals = [vals]
        for j, val in enumerate(vals):
            nx = 2.2 + j * 2.2
            # Chain node
            node_rect = plt.Rectangle((nx, y - 0.2), 1.8, 0.4,
                facecolor='#161b22', edgecolor=color, linewidth=1.5)
            ax.add_patch(node_rect)
            ax.text(nx + 0.9, y, str(val), ha='center', va='center',
                    fontsize=10, color='#e6edf3')
            # Arrow
            if j == 0:
                ax.annotate('', xy=(nx, y), xytext=(1.5, y),
                    arrowprops=dict(arrowstyle='->', color='#8b949e', lw=1.5))
            else:
                prev_nx = 2.2 + (j - 1) * 2.2
                ax.annotate('', xy=(nx, y), xytext=(prev_nx + 1.8, y),
                    arrowprops=dict(arrowstyle='->', color='#8b949e', lw=1.5))

    if title:
        ax.set_title(title, fontsize=14, fontweight='bold', color='#e6edf3', pad=15)
    plt.tight_layout()

def _qdiagram_stack_queue(values: list, kind: str = "stack", title: str = ""):
    """Draw a stack or queue visualization.
    values: list of items (top/front first)
    kind: 'stack' or 'queue'
    Example: qdiagram_stack_queue([10, 20, 30], kind="stack", title="Call Stack")
    """
    n = len(values)
    if n == 0:
        return
    colors = ['#58a6ff', '#3fb950', '#f85149', '#a371f7', '#d29922', '#e3b341']

    if kind == "stack":
        fig, ax = plt.subplots(figsize=(4, max(3, n * 0.8 + 1)))
        ax.set_xlim(-0.5, 4)
        ax.set_ylim(-1, n + 1)
        ax.axis('off')
        for i, val in enumerate(values):
            y = n - 1 - i
            color = colors[i % len(colors)]
            rect = plt.Rectangle((0.5, y), 3, 0.7,
                facecolor=color + '20', edgecolor=color, linewidth=2)
            ax.add_patch(rect)
            ax.text(2, y + 0.35, str(val), ha='center', va='center',
                    fontsize=12, fontweight='bold', color='#e6edf3')
            if i == 0:
                ax.text(3.7, y + 0.35, '← TOP', fontsize=9, color='#58a6ff', va='center')
    else:
        fig, ax = plt.subplots(figsize=(max(6, n * 2), 3))
        ax.set_xlim(-0.5, n * 2 + 1)
        ax.set_ylim(-0.5, 2)
        ax.axis('off')
        for i, val in enumerate(values):
            x = i * 1.8 + 0.5
            color = colors[i % len(colors)]
            rect = plt.Rectangle((x, 0.3), 1.5, 0.8,
                facecolor=color + '20', edgecolor=color, linewidth=2)
            ax.add_patch(rect)
            ax.text(x + 0.75, 0.7, str(val), ha='center', va='center',
                    fontsize=12, fontweight='bold', color='#e6edf3')
            if i == 0:
                ax.text(x + 0.75, 1.4, '↑ FRONT', fontsize=9, color='#58a6ff', ha='center')
            if i == n - 1:
                ax.text(x + 0.75, 1.4, '↑ BACK', fontsize=9, color='#f85149', ha='center')

    if title:
        ax.set_title(title or kind.capitalize(), fontsize=13, fontweight='bold', color='#e6edf3', pad=10)
    plt.tight_layout()

# Register diagram helpers in base globals
_BASE_GLOBALS['qdiagram_flowchart'] = _qdiagram_flowchart
_BASE_GLOBALS['qdiagram_concept_map'] = _qdiagram_concept_map
_BASE_GLOBALS['qdiagram_array'] = _qdiagram_array
_BASE_GLOBALS['qdiagram_linked_list'] = _qdiagram_linked_list
_BASE_GLOBALS['qdiagram_tree'] = _qdiagram_tree
_BASE_GLOBALS['qdiagram_hashtable'] = _qdiagram_hashtable
_BASE_GLOBALS['qdiagram_stack_queue'] = _qdiagram_stack_queue


# ──────────────────────────────────────────
# IMAGE EDITING HELPERS
# ──────────────────────────────────────────

def _img_load(path: str = None):
    """Load an image from path. Returns PIL Image.
    Usage: img = img_load('/full/path/photo.jpg')  — first load
           img = img_load()  — reload current working image for follow-up edits"""
    from PIL import Image as _Img
    if path is None:
        # No-arg: return current working image for follow-up edits
        current = _SHARED_GLOBALS.get('_current_image')
        if current is not None:
            return current.copy()
        current_path = _SHARED_GLOBALS.get('_current_image_path')
        if current_path and os.path.exists(current_path):
            path = current_path
        else:
            raise FileNotFoundError("No image loaded yet. Call img_load('/full/path/to/image.jpg') first.")
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
    # Push current state to history before overwriting
    if '_current_image' in _SHARED_GLOBALS and _SHARED_GLOBALS['_current_image'] is not None:
        import time as _ht
        hist = _SHARED_GLOBALS.setdefault('_edit_history', [])
        redo = _SHARED_GLOBALS.setdefault('_edit_redo', [])
        if len(hist) >= 30:
            hist.pop(0)
        hist.append({'image': _SHARED_GLOBALS['_current_image'].copy(), 'ts': _ht.time()})
        redo.clear()
    # Auto-save current working image for cross-turn persistence
    workspace = os.path.join(os.path.expanduser("~"), ".kasset", "workspace")
    os.makedirs(workspace, exist_ok=True)
    save_path = os.path.join(workspace, "_current_edit.png")
    if hasattr(img, 'save'):
        img.save(save_path)
        _SHARED_GLOBALS['_current_image_path'] = save_path
        _SHARED_GLOBALS['_current_image'] = img
    w, h = img.size if hasattr(img, 'size') else (800, 800)
    max_dim = 8
    aspect = w / max(h, 1)
    if aspect >= 1:
        fw, fh = max_dim, max_dim / aspect
    else:
        fw, fh = max_dim * aspect, max_dim
    fig, ax = plt.subplots(figsize=(fw, fh))
    ax.imshow(img)
    ax.axis('off')
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
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

def _normalize_polygon_points(points, w: int, h: int):
    """Normalize polygon points into in-bounds integer (x, y) tuples."""
    norm = []
    for p in points or []:
        x = y = None
        if isinstance(p, dict):
            x = p.get('x')
            y = p.get('y')
        elif isinstance(p, (list, tuple)) and len(p) >= 2:
            x, y = p[0], p[1]
        if x is None or y is None:
            continue
        try:
            xi = int(round(float(x)))
            yi = int(round(float(y)))
        except Exception:
            continue
        xi = max(0, min(w - 1, xi))
        yi = max(0, min(h - 1, yi))
        if not norm or (xi, yi) != norm[-1]:
            norm.append((xi, yi))
    if len(norm) >= 2 and norm[0] == norm[-1]:
        norm = norm[:-1]
    if len(norm) < 3:
        raise ValueError("img_crop_polygon/img_mask_from_polygon needs at least 3 valid points")
    return norm

def _img_crop_polygon(img, points, feather: int = 0):
    """Crop image to a freeform polygon shape. Returns RGBA with transparency outside the polygon.
    points: list of (x, y) tuples defining the polygon in image coordinates.
    feather: optional edge softening radius (0 = hard edge).
    Usage: img = img_crop_polygon(img, [(100,50),(300,50),(350,200),(250,300),(80,250)])"""
    from PIL import Image as _Img, ImageDraw as _Draw, ImageFilter as _Filt
    w, h = img.size
    poly = _normalize_polygon_points(points, w, h)
    # Build polygon mask
    mask = _Img.new('L', (w, h), 0)
    draw = _Draw.Draw(mask)
    draw.polygon(poly, fill=255)
    if feather > 0:
        mask = mask.filter(_Filt.GaussianBlur(radius=feather))
    # Composite onto transparent background
    rgba = img.convert('RGBA')
    result = _Img.new('RGBA', (w, h), (0, 0, 0, 0))
    result.paste(rgba, mask=mask)
    # Crop to polygon bounding box
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    bbox = (max(0, min(xs)), max(0, min(ys)), min(w, max(xs) + 1), min(h, max(ys) + 1))
    result = result.crop(bbox)
    print(f"Polygon crop: {len(poly)} vertices, bbox {bbox[2]-bbox[0]}x{bbox[3]-bbox[1]}, feather={feather}")
    return result

def _img_mask_from_polygon(img, points, feather: int = 0):
    """Create a mask image from a polygon. Returns a grayscale mask (white=inside, black=outside).
    Same size as img. Use with img_apply_to_region, img_blur_region, img_fill_region, etc.
    points: list of (x, y) tuples in image coordinates.
    feather: optional edge softening radius.
    Usage: mask = img_mask_from_polygon(img, [(100,50),(300,50),(250,300)])"""
    from PIL import Image as _Img, ImageDraw as _Draw, ImageFilter as _Filt
    w, h = img.size
    poly = _normalize_polygon_points(points, w, h)
    mask = _Img.new('L', (w, h), 0)
    draw = _Draw.Draw(mask)
    draw.polygon(poly, fill=255)
    if feather > 0:
        mask = mask.filter(_Filt.GaussianBlur(radius=feather))
    print(f"Polygon mask: {len(poly)} vertices, {w}x{h}, feather={feather}")
    return mask

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

def _img_tint_highlights(img, color, strength: float = 0.4, threshold: float = 0.6):
    """Apply a color tint ONLY to the bright areas (highlights) of the image.
    color: color name (str) or (R,G,B) tuple. strength: 0.0-1.0. threshold: luminance cutoff (0.0-1.0).
    Usage: img = img_tint_highlights(img, 'blue', 0.5)"""
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
    gray = _np.mean(arr, axis=2) / 255.0
    mask = _np.clip((gray - threshold) / (1.0 - threshold + 1e-6), 0, 1)
    mask3 = _np.stack([mask]*3, axis=2)
    tint = _np.array(tc, dtype=_np.float32)
    tinted = arr * (1.0 - strength) + tint * strength
    result = arr * (1.0 - mask3) + tinted * mask3
    return _Img.fromarray(_np.clip(result, 0, 255).astype(_np.uint8))

def _img_tint_shadows(img, color, strength: float = 0.4, threshold: float = 0.4):
    """Apply a color tint ONLY to the dark areas (shadows) of the image.
    color: color name (str) or (R,G,B) tuple. strength: 0.0-1.0. threshold: luminance cutoff (0.0-1.0).
    Usage: img = img_tint_shadows(img, 'purple', 0.3)"""
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
    gray = _np.mean(arr, axis=2) / 255.0
    mask = _np.clip((threshold - gray) / (threshold + 1e-6), 0, 1)
    mask3 = _np.stack([mask]*3, axis=2)
    tint = _np.array(tc, dtype=_np.float32)
    tinted = arr * (1.0 - strength) + tint * strength
    result = arr * (1.0 - mask3) + tinted * mask3
    return _Img.fromarray(_np.clip(result, 0, 255).astype(_np.uint8))

def _img_vignette(img, strength: float = 0.5, radius: float = 0.8):
    """Add a vignette (darkened edges) effect.
    strength: 0.0-1.0 (how dark the edges get). radius: 0.0-1.0 (how far from center the effect starts).
    Usage: img = img_vignette(img, strength=0.6)"""
    import numpy as _np
    from PIL import Image as _Img
    arr = _np.array(img.convert('RGB')).astype(_np.float32)
    h, w = arr.shape[:2]
    Y, X = _np.ogrid[:h, :w]
    cy, cx = h / 2, w / 2
    dist = _np.sqrt(((X - cx) / cx) ** 2 + ((Y - cy) / cy) ** 2)
    vignette = _np.clip((dist - radius) / (1.0 - radius + 1e-6), 0, 1) * strength
    vignette3 = _np.stack([vignette]*3, axis=2)
    result = arr * (1.0 - vignette3)
    return _Img.fromarray(_np.clip(result, 0, 255).astype(_np.uint8))

def _img_get_original():
    """Get the original (unedited) image from the current session.
    Usage: original = img_get_original()"""
    if '_original_image' in _SHARED_GLOBALS and _SHARED_GLOBALS['_original_image'] is not None:
        return _SHARED_GLOBALS['_original_image'].copy()
    raise RuntimeError("No original image stored. Load an image first with img_load().")

def _img_info(img):
    """Get image metadata. Usage: img_info(img)"""
    return f"Size: {img.size[0]}x{img.size[1]}, Mode: {img.mode}, Format: {getattr(img, 'format', 'N/A')}"

def _img_sepia(img, strength: float = 1.0):
    """Apply sepia tone effect. strength: 0.0-1.0 (default 1.0).
    Usage: img = img_sepia(img, 0.8)"""
    import numpy as _np
    from PIL import Image as _Img
    arr = _np.array(img.convert('RGB')).astype(_np.float32)
    sepia_matrix = _np.array([
        [0.393, 0.769, 0.189],
        [0.349, 0.686, 0.168],
        [0.272, 0.534, 0.131],
    ])
    sepia_arr = arr @ sepia_matrix.T
    strength = max(0.0, min(1.0, strength))
    result = arr * (1.0 - strength) + sepia_arr * strength
    return _Img.fromarray(_np.clip(result, 0, 255).astype(_np.uint8))

def _img_invert(img):
    """Invert image colors. Usage: img = img_invert(img)"""
    from PIL import ImageOps as _Ops
    if img.mode == 'RGBA':
        r, g, b, a = img.split()
        from PIL import Image as _Img
        rgb = _Img.merge('RGB', (r, g, b))
        inv = _Ops.invert(rgb)
        ri, gi, bi = inv.split()
        return _Img.merge('RGBA', (ri, gi, bi, a))
    return _Ops.invert(img.convert('RGB'))

def _img_opacity(img, opacity: float = 0.5):
    """Set image opacity (transparency). opacity: 0.0 (transparent) to 1.0 (opaque).
    Usage: img = img_opacity(img, 0.7)"""
    from PIL import Image as _Img
    opacity = max(0.0, min(1.0, opacity))
    rgba = img.convert('RGBA')
    r, g, b, a = rgba.split()
    import numpy as _np
    a_arr = _np.array(a).astype(_np.float32) * opacity
    a = _Img.fromarray(a_arr.astype(_np.uint8))
    return _Img.merge('RGBA', (r, g, b, a))

def _img_posterize(img, bits: int = 4):
    """Reduce color depth for a poster-like effect. bits: 1-8 (fewer = more dramatic).
    Usage: img = img_posterize(img, 3)"""
    from PIL import ImageOps as _Ops
    return _Ops.posterize(img.convert('RGB'), max(1, min(8, bits)))

def _img_solarize(img, threshold: int = 128):
    """Solarize effect — invert tones above threshold. threshold: 0-255.
    Usage: img = img_solarize(img, 128)"""
    from PIL import ImageOps as _Ops
    return _Ops.solarize(img.convert('RGB'), threshold)

def _img_emboss(img):
    """Apply emboss filter for a raised surface effect.
    Usage: img = img_emboss(img)"""
    from PIL import ImageFilter as _Filt
    return img.filter(_Filt.EMBOSS)

def _img_sharpen(img, amount: float = 2.0, radius: int = 2, threshold: int = 3):
    """Unsharp mask sharpening. amount: strength (1.0-5.0). radius: blur radius. threshold: edge threshold.
    Usage: img = img_sharpen(img, amount=2.5)"""
    from PIL import ImageFilter as _Filt
    return img.filter(_Filt.UnsharpMask(radius=radius, percent=int(amount * 100), threshold=threshold))

def _img_auto_contrast(img, cutoff: float = 0.5):
    """Auto-adjust contrast by stretching histogram. cutoff: % of lightest/darkest pixels to clip.
    Usage: img = img_auto_contrast(img)"""
    from PIL import ImageOps as _Ops
    return _Ops.autocontrast(img.convert('RGB'), cutoff=cutoff)

def _img_equalize(img):
    """Equalize histogram for automatic tonal correction.
    Usage: img = img_equalize(img)"""
    from PIL import ImageOps as _Ops
    return _Ops.equalize(img.convert('RGB'))

def _img_channel_mix(img, r_mult: float = 1.0, g_mult: float = 1.0, b_mult: float = 1.0):
    """Adjust individual RGB channel intensities. Values: 0.0-3.0 (1.0 = no change).
    Usage: img = img_channel_mix(img, r_mult=1.5, g_mult=0.8, b_mult=0.5)"""
    import numpy as _np
    from PIL import Image as _Img
    arr = _np.array(img.convert('RGB')).astype(_np.float32)
    arr[:, :, 0] *= max(0.0, min(3.0, r_mult))
    arr[:, :, 1] *= max(0.0, min(3.0, g_mult))
    arr[:, :, 2] *= max(0.0, min(3.0, b_mult))
    return _Img.fromarray(_np.clip(arr, 0, 255).astype(_np.uint8))

def _img_gradient_map(img, color_start, color_end):
    """Map image luminance to a two-color gradient. Colors: names (str) or (R,G,B) tuples.
    Usage: img = img_gradient_map(img, 'navy', 'gold')"""
    import numpy as _np
    from PIL import Image as _Img
    cs = _resolve_color_name(color_start) if isinstance(color_start, str) else tuple(color_start)
    ce = _resolve_color_name(color_end) if isinstance(color_end, str) else tuple(color_end)
    if cs is None:
        raise ValueError(f"Unknown color: '{color_start}'")
    if ce is None:
        raise ValueError(f"Unknown color: '{color_end}'")
    gray = _np.array(img.convert('L')).astype(_np.float32) / 255.0
    cs_arr = _np.array(cs, dtype=_np.float32)
    ce_arr = _np.array(ce, dtype=_np.float32)
    result = _np.zeros((*gray.shape, 3), dtype=_np.float32)
    for c in range(3):
        result[:, :, c] = cs_arr[c] * (1.0 - gray) + ce_arr[c] * gray
    return _Img.fromarray(_np.clip(result, 0, 255).astype(_np.uint8))

def _img_noise(img, amount: float = 25.0):
    """Add random noise to image. amount: noise strength in pixel units (0-100).
    Usage: img = img_noise(img, 30)"""
    import numpy as _np
    from PIL import Image as _Img
    arr = _np.array(img.convert('RGB')).astype(_np.float32)
    noise = _np.random.normal(0, amount, arr.shape)
    return _Img.fromarray(_np.clip(arr + noise, 0, 255).astype(_np.uint8))

def _img_pixelate(img, block_size: int = 10):
    """Pixelate (mosaic) effect. block_size: pixel block size.
    Usage: img = img_pixelate(img, 15)"""
    from PIL import Image as _Img
    w, h = img.size
    small = img.resize((max(1, w // block_size), max(1, h // block_size)), _Img.NEAREST)
    return small.resize((w, h), _Img.NEAREST)

def _img_border(img, width: int = 10, color="white"):
    """Add a border around the image.
    Usage: img = img_border(img, 20, 'black')"""
    from PIL import ImageOps as _Ops
    if isinstance(color, str):
        c = _resolve_color_name(color)
        if c is None:
            c = color  # let PIL try to parse it
        color = c
    return _Ops.expand(img.convert('RGB'), border=width, fill=color)

def _img_preview(img):
    """Display an image inline WITHOUT saving to working state. Use for previews.
    Usage: img_preview(img)"""
    w, h = img.size if hasattr(img, 'size') else (800, 800)
    max_dim = 6
    aspect = w / max(h, 1)
    if aspect >= 1:
        fw, fh = max_dim, max_dim / aspect
    else:
        fw, fh = max_dim * aspect, max_dim
    fig, ax = plt.subplots(figsize=(fw, fh))
    ax.imshow(img)
    ax.axis('off')
    ax.set_title('Preview (not saved)', fontsize=10, color='#8b949e')
    fig.subplots_adjust(left=0, right=1, top=0.93, bottom=0)
    plt.tight_layout(pad=0)

# Register image editing helpers in base globals
_BASE_GLOBALS['img_load'] = _img_load
_BASE_GLOBALS['img_save'] = _img_save
_BASE_GLOBALS['img_show'] = _img_show
_BASE_GLOBALS['img_adjust'] = _img_adjust
_BASE_GLOBALS['img_hue_shift'] = _img_hue_shift
_BASE_GLOBALS['img_crop'] = _img_crop
_BASE_GLOBALS['img_crop_polygon'] = _img_crop_polygon
_BASE_GLOBALS['img_mask_from_polygon'] = _img_mask_from_polygon
_BASE_GLOBALS['img_resize'] = _img_resize
_BASE_GLOBALS['img_rotate'] = _img_rotate
_BASE_GLOBALS['img_flip'] = _img_flip
_BASE_GLOBALS['img_grayscale'] = _img_grayscale
_BASE_GLOBALS['img_convert'] = _img_convert
_BASE_GLOBALS['img_draw_rect'] = _img_draw_rect
_BASE_GLOBALS['img_draw_text'] = _img_draw_text
_BASE_GLOBALS['img_blur'] = _img_blur
_BASE_GLOBALS['img_edge_detect'] = _img_edge_detect
_BASE_GLOBALS['img_threshold'] = _img_threshold
_BASE_GLOBALS['img_color_replace'] = _img_color_replace
_BASE_GLOBALS['img_color_range_replace'] = _img_color_range_replace
_BASE_GLOBALS['img_tint'] = _img_tint
_BASE_GLOBALS['img_adjust_highlights'] = _img_adjust_highlights
_BASE_GLOBALS['img_adjust_shadows'] = _img_adjust_shadows
_BASE_GLOBALS['img_overlay_color'] = _img_overlay_color
_BASE_GLOBALS['img_tint_highlights'] = _img_tint_highlights
_BASE_GLOBALS['img_tint_shadows'] = _img_tint_shadows
_BASE_GLOBALS['img_vignette'] = _img_vignette
_BASE_GLOBALS['img_get_original'] = _img_get_original
_BASE_GLOBALS['img_info'] = _img_info
_BASE_GLOBALS['img_sepia'] = _img_sepia
_BASE_GLOBALS['img_invert'] = _img_invert
_BASE_GLOBALS['img_opacity'] = _img_opacity
_BASE_GLOBALS['img_posterize'] = _img_posterize
_BASE_GLOBALS['img_solarize'] = _img_solarize
_BASE_GLOBALS['img_emboss'] = _img_emboss
_BASE_GLOBALS['img_sharpen'] = _img_sharpen
_BASE_GLOBALS['img_auto_contrast'] = _img_auto_contrast
_BASE_GLOBALS['img_equalize'] = _img_equalize
_BASE_GLOBALS['img_channel_mix'] = _img_channel_mix
_BASE_GLOBALS['img_gradient_map'] = _img_gradient_map
_BASE_GLOBALS['img_noise'] = _img_noise
_BASE_GLOBALS['img_pixelate'] = _img_pixelate
_BASE_GLOBALS['img_border'] = _img_border
_BASE_GLOBALS['img_preview'] = _img_preview


# ──────────────────────────────────────────
# PHASE 1D — UNDO / REDO HISTORY
# ──────────────────────────────────────────

def _img_undo():
    """Undo the last edit and return the previous image state.
    Usage: img = img_undo()"""
    hist = _SHARED_GLOBALS.get('_edit_history', [])
    if not hist:
        raise RuntimeError("Nothing to undo — edit history is empty.")
    entry = hist.pop()
    redo = _SHARED_GLOBALS.setdefault('_edit_redo', [])
    if '_current_image' in _SHARED_GLOBALS and _SHARED_GLOBALS['_current_image'] is not None:
        redo.append({'image': _SHARED_GLOBALS['_current_image'].copy(), 'ts': entry['ts']})
    img = entry['image']
    workspace = os.path.join(os.path.expanduser("~"), ".kasset", "workspace")
    os.makedirs(workspace, exist_ok=True)
    save_path = os.path.join(workspace, "_current_edit.png")
    img.save(save_path)
    _SHARED_GLOBALS['_current_image_path'] = save_path
    _SHARED_GLOBALS['_current_image'] = img
    print(f"Undo successful. {len(hist)} state(s) remaining in history.")
    return img

def _img_redo():
    """Re-apply the last undone edit.
    Usage: img = img_redo()"""
    redo = _SHARED_GLOBALS.get('_edit_redo', [])
    if not redo:
        raise RuntimeError("Nothing to redo.")
    entry = redo.pop()
    hist = _SHARED_GLOBALS.setdefault('_edit_history', [])
    if '_current_image' in _SHARED_GLOBALS and _SHARED_GLOBALS['_current_image'] is not None:
        hist.append({'image': _SHARED_GLOBALS['_current_image'].copy(), 'ts': entry['ts']})
    img = entry['image']
    workspace = os.path.join(os.path.expanduser("~"), ".kasset", "workspace")
    os.makedirs(workspace, exist_ok=True)
    save_path = os.path.join(workspace, "_current_edit.png")
    img.save(save_path)
    _SHARED_GLOBALS['_current_image_path'] = save_path
    _SHARED_GLOBALS['_current_image'] = img
    print(f"Redo successful. {len(redo)} redo state(s) remaining.")
    return img

def _img_history():
    """List all edit states in the undo history.
    Usage: img_history()"""
    import time as _t
    hist = _SHARED_GLOBALS.get('_edit_history', [])
    if not hist:
        print("Edit history is empty.")
        return []
    lines = []
    for i, entry in enumerate(hist):
        age = _t.time() - entry['ts']
        w, h = entry['image'].size
        if age < 60:
            age_str = f"{int(age)}s ago"
        elif age < 3600:
            age_str = f"{int(age/60)}m ago"
        else:
            age_str = f"{int(age/3600)}h ago"
        lines.append(f"  [{i}] {w}x{h} — {age_str}")
    print(f"Edit history ({len(hist)} states):\n" + "\n".join(lines))
    return hist

def _img_revert(n: int):
    """Revert to a specific state in the edit history (by index).
    Usage: img = img_revert(0)  — revert to the earliest saved state"""
    hist = _SHARED_GLOBALS.get('_edit_history', [])
    if n < 0 or n >= len(hist):
        raise ValueError(f"Invalid history index {n}. Range: 0-{len(hist)-1}")
    img = hist[n]['image'].copy()
    # Trim history to that point
    _SHARED_GLOBALS['_edit_history'] = hist[:n]
    _SHARED_GLOBALS['_edit_redo'] = []
    workspace = os.path.join(os.path.expanduser("~"), ".kasset", "workspace")
    os.makedirs(workspace, exist_ok=True)
    save_path = os.path.join(workspace, "_current_edit.png")
    img.save(save_path)
    _SHARED_GLOBALS['_current_image_path'] = save_path
    _SHARED_GLOBALS['_current_image'] = img
    print(f"Reverted to state [{n}].")
    return img

_BASE_GLOBALS['img_undo'] = _img_undo
_BASE_GLOBALS['img_redo'] = _img_redo
_BASE_GLOBALS['img_history'] = _img_history
_BASE_GLOBALS['img_revert'] = _img_revert


# ──────────────────────────────────────────
# PHASE 1A — COMPOSITION & LAYERING
# ──────────────────────────────────────────

def _img_create(width: int, height: int, color="white"):
    """Create a blank image canvas.
    Usage: canvas = img_create(800, 600, 'black')"""
    from PIL import Image as _Img
    if isinstance(color, str):
        c = _resolve_color_name(color)
        if c is None:
            c = color
        color = c
    return _Img.new('RGB', (width, height), color)

def _img_paste(base, overlay, x: int = 0, y: int = 0, mask=None):
    """Paste overlay image onto base at position (x, y). Optional mask for shaped pasting.
    Usage: img = img_paste(base, overlay, 100, 50)
           img = img_paste(base, overlay, 0, 0, mask=my_mask)"""
    result = base.copy()
    if overlay.mode == 'RGBA' and mask is None:
        result.paste(overlay, (x, y), overlay)
    elif mask is not None:
        if mask.mode != 'L':
            mask = mask.convert('L')
        result.paste(overlay, (x, y), mask)
    else:
        result.paste(overlay, (x, y))
    return result

def _img_composite(fg, bg, mask):
    """Alpha-aware composite: combine fg and bg using a grayscale mask.
    White mask pixels = fg, black = bg.
    Usage: img = img_composite(foreground, background, mask)"""
    from PIL import Image as _Img
    fg_rgb = fg.convert('RGB')
    bg_rgb = bg.convert('RGB')
    if mask.mode != 'L':
        mask = mask.convert('L')
    if fg_rgb.size != bg_rgb.size:
        bg_rgb = bg_rgb.resize(fg_rgb.size, _Img.LANCZOS)
    if mask.size != fg_rgb.size:
        mask = mask.resize(fg_rgb.size, _Img.LANCZOS)
    return _Img.composite(fg_rgb, bg_rgb, mask)

def _img_blend(img1, img2, alpha: float = 0.5):
    """Linear blend of two images. alpha=0.0 gives img1, alpha=1.0 gives img2.
    Usage: img = img_blend(photo, overlay, 0.3)"""
    from PIL import Image as _Img
    i1 = img1.convert('RGB')
    i2 = img2.convert('RGB')
    if i1.size != i2.size:
        i2 = i2.resize(i1.size, _Img.LANCZOS)
    return _Img.blend(i1, i2, alpha)

def _img_alpha_paste(base, overlay, x: int = 0, y: int = 0):
    """Paste an RGBA overlay onto base preserving alpha transparency.
    Usage: img = img_alpha_paste(background, logo_with_alpha, 50, 50)"""
    result = base.convert('RGBA')
    ov = overlay.convert('RGBA')
    result.paste(ov, (x, y), ov)
    return result.convert('RGB')

def _img_stack_h(images, gap: int = 0, bg_color="white"):
    """Stack images horizontally with optional gap.
    Usage: img = img_stack_h([img1, img2, img3], gap=10)"""
    from PIL import Image as _Img
    if not images:
        raise ValueError("No images provided.")
    max_h = max(im.size[1] for im in images)
    total_w = sum(im.size[0] for im in images) + gap * (len(images) - 1)
    if isinstance(bg_color, str):
        c = _resolve_color_name(bg_color)
        bg_color = c if c else bg_color
    canvas = _Img.new('RGB', (total_w, max_h), bg_color)
    x_off = 0
    for im in images:
        canvas.paste(im.convert('RGB'), (x_off, (max_h - im.size[1]) // 2))
        x_off += im.size[0] + gap
    return canvas

def _img_stack_v(images, gap: int = 0, bg_color="white"):
    """Stack images vertically with optional gap.
    Usage: img = img_stack_v([img1, img2], gap=5)"""
    from PIL import Image as _Img
    if not images:
        raise ValueError("No images provided.")
    max_w = max(im.size[0] for im in images)
    total_h = sum(im.size[1] for im in images) + gap * (len(images) - 1)
    if isinstance(bg_color, str):
        c = _resolve_color_name(bg_color)
        bg_color = c if c else bg_color
    canvas = _Img.new('RGB', (max_w, total_h), bg_color)
    y_off = 0
    for im in images:
        canvas.paste(im.convert('RGB'), ((max_w - im.size[0]) // 2, y_off))
        y_off += im.size[1] + gap
    return canvas

_BASE_GLOBALS['img_create'] = _img_create
_BASE_GLOBALS['img_paste'] = _img_paste
_BASE_GLOBALS['img_composite'] = _img_composite
_BASE_GLOBALS['img_blend'] = _img_blend
_BASE_GLOBALS['img_alpha_paste'] = _img_alpha_paste
_BASE_GLOBALS['img_stack_h'] = _img_stack_h
_BASE_GLOBALS['img_stack_v'] = _img_stack_v


# ──────────────────────────────────────────
# PHASE 1B — ENHANCED DRAWING & ANNOTATION
# ──────────────────────────────────────────

def _img_draw_circle(img, cx: int, cy: int, r: int, color="red", width: int = 3, fill=None):
    """Draw a circle on the image.
    Usage: img = img_draw_circle(img, 200, 200, 50, color='blue', fill='lightblue')"""
    from PIL import ImageDraw as _Draw
    draw = _Draw.Draw(img)
    bbox = [cx - r, cy - r, cx + r, cy + r]
    draw.ellipse(bbox, outline=color, width=width, fill=fill)
    return img

def _img_draw_ellipse(img, left: int, top: int, right: int, bottom: int, color="red", width: int = 3, fill=None):
    """Draw an ellipse bounded by (left, top, right, bottom).
    Usage: img = img_draw_ellipse(img, 100, 50, 300, 200, color='green')"""
    from PIL import ImageDraw as _Draw
    draw = _Draw.Draw(img)
    draw.ellipse([left, top, right, bottom], outline=color, width=width, fill=fill)
    return img

def _img_draw_line(img, x1: int, y1: int, x2: int, y2: int, color="red", width: int = 3):
    """Draw a straight line from (x1,y1) to (x2,y2).
    Usage: img = img_draw_line(img, 0, 0, 500, 500, color='white', width=5)"""
    from PIL import ImageDraw as _Draw
    draw = _Draw.Draw(img)
    draw.line([(x1, y1), (x2, y2)], fill=color, width=width)
    return img

def _img_draw_arrow(img, x1: int, y1: int, x2: int, y2: int, color="red", width: int = 3, head_size: int = 15):
    """Draw a line with an arrowhead pointing from (x1,y1) to (x2,y2).
    Usage: img = img_draw_arrow(img, 100, 100, 300, 200, color='yellow')"""
    import math
    from PIL import ImageDraw as _Draw
    draw = _Draw.Draw(img)
    draw.line([(x1, y1), (x2, y2)], fill=color, width=width)
    angle = math.atan2(y2 - y1, x2 - x1)
    a1 = angle + math.pi * 0.85
    a2 = angle - math.pi * 0.85
    hx1 = x2 + int(head_size * math.cos(a1))
    hy1 = y2 + int(head_size * math.sin(a1))
    hx2 = x2 + int(head_size * math.cos(a2))
    hy2 = y2 + int(head_size * math.sin(a2))
    draw.polygon([(x2, y2), (hx1, hy1), (hx2, hy2)], fill=color)
    return img

def _img_draw_polygon(img, points, color="red", width: int = 3, fill=None):
    """Draw a polygon from a list of (x, y) points.
    Usage: img = img_draw_polygon(img, [(100,100),(200,50),(300,100),(250,200),(150,200)], color='blue', fill='lightblue')"""
    from PIL import ImageDraw as _Draw
    draw = _Draw.Draw(img)
    draw.polygon(points, outline=color, fill=fill)
    if width > 1 and fill is None:
        draw.polygon(points, outline=color)
    return img

def _img_draw_rounded_rect(img, left: int, top: int, right: int, bottom: int, radius: int = 10,
                           color="red", width: int = 3, fill=None):
    """Draw a rounded rectangle.
    Usage: img = img_draw_rounded_rect(img, 50, 50, 300, 200, radius=20, color='blue', fill='navy')"""
    from PIL import ImageDraw as _Draw
    draw = _Draw.Draw(img)
    draw.rounded_rectangle([left, top, right, bottom], radius=radius, outline=color, width=width, fill=fill)
    return img

def _img_draw_rich_text(img, x: int, y: int, text: str, color="white", size: int = 24,
                        font_name: str = None, align: str = 'left',
                        outline_color=None, outline_width: int = 0,
                        shadow: bool = False, max_width: int = None):
    """Draw text with advanced options: outline, shadow, alignment, word wrap.
    Usage: img = img_draw_rich_text(img, 50, 50, 'Hello World', size=48, outline_color='black', outline_width=2, shadow=True)"""
    from PIL import ImageDraw as _Draw, ImageFont as _Font
    draw = _Draw.Draw(img)
    try:
        fp = font_name or "/System/Library/Fonts/Helvetica.ttc"
        font = _Font.truetype(fp, size)
    except Exception:
        try:
            font = _Font.truetype("/System/Library/Fonts/SFNSMono.ttf", size)
        except Exception:
            font = _Font.load_default()
    # Word wrap if max_width specified
    if max_width and max_width > 0:
        words = text.split(' ')
        lines_out = []
        current_line = ""
        for word in words:
            test = (current_line + " " + word).strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_width and current_line:
                lines_out.append(current_line)
                current_line = word
            else:
                current_line = test
        if current_line:
            lines_out.append(current_line)
        text = "\n".join(lines_out)
    if shadow:
        draw.text((x + 2, y + 2), text, fill='black', font=font, align=align)
    if outline_color and outline_width > 0:
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), text, fill=outline_color, font=font, align=align)
    draw.text((x, y), text, fill=color, font=font, align=align)
    return img

def _img_watermark(img, text: str = "WATERMARK", position: str = "bottom-right",
                   opacity: float = 0.3, size: int = 24, color="white"):
    """Add a text watermark at a specified position.
    position: 'center', 'bottom-right', 'bottom-left', 'top-right', 'top-left'.
    Usage: img = img_watermark(img, '© 2025', position='bottom-right', opacity=0.5)"""
    from PIL import Image as _Img, ImageDraw as _Draw, ImageFont as _Font
    import numpy as _np
    overlay = _Img.new('RGBA', img.size, (0, 0, 0, 0))
    draw = _Draw.Draw(overlay)
    try:
        font = _Font.truetype("/System/Library/Fonts/Helvetica.ttc", size)
    except Exception:
        font = _Font.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    w, h = img.size
    margin = 20
    positions = {
        'center': ((w - tw) // 2, (h - th) // 2),
        'bottom-right': (w - tw - margin, h - th - margin),
        'bottom-left': (margin, h - th - margin),
        'top-right': (w - tw - margin, margin),
        'top-left': (margin, margin),
    }
    pos = positions.get(position, positions['bottom-right'])
    if isinstance(color, str):
        c = _resolve_color_name(color)
        color = c if c else (255, 255, 255)
    alpha = int(opacity * 255)
    draw.text(pos, text, fill=(*color, alpha), font=font)
    return _Img.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')

_BASE_GLOBALS['img_draw_circle'] = _img_draw_circle
_BASE_GLOBALS['img_draw_ellipse'] = _img_draw_ellipse
_BASE_GLOBALS['img_draw_line'] = _img_draw_line
_BASE_GLOBALS['img_draw_arrow'] = _img_draw_arrow
_BASE_GLOBALS['img_draw_polygon'] = _img_draw_polygon
_BASE_GLOBALS['img_draw_rounded_rect'] = _img_draw_rounded_rect
_BASE_GLOBALS['img_draw_rich_text'] = _img_draw_rich_text
_BASE_GLOBALS['img_watermark'] = _img_watermark


# ──────────────────────────────────────────
# PHASE 1C — MASKING & SELECTION (PIL-based)
# ──────────────────────────────────────────

def _img_mask_from_color(img, color, tolerance: int = 30):
    """Create a binary mask (white=match) from a color name or (R,G,B) tuple.
    Usage: mask = img_mask_from_color(img, 'blue', tolerance=40)
           mask = img_mask_from_color(img, (255, 0, 0), tolerance=30)"""
    import numpy as _np
    from PIL import Image as _Img
    if isinstance(color, str):
        # Use HSV-based matching for named colors
        c_key = color.lower().strip()
        if c_key in _COLOR_RANGES:
            hsv = _np.array(img.convert('HSV'))
            h_scaled = (hsv[:, :, 0].astype(_np.float32) / 255.0 * 180.0).astype(_np.uint8)
            s, v = hsv[:, :, 1], hsv[:, :, 2]
            lo1, hi1, lo2, hi2 = _COLOR_RANGES[c_key]
            s_tol = int(tolerance * 2.55)
            v_tol = int(tolerance * 2.55)
            mask = (
                (h_scaled >= max(lo1[0] - tolerance // 6, 0)) & (h_scaled <= min(hi1[0] + tolerance // 6, 180)) &
                (s >= max(lo1[1] - s_tol, 0)) & (s <= min(hi1[1] + s_tol, 255)) &
                (v >= max(lo1[2] - v_tol, 0)) & (v <= min(hi1[2] + v_tol, 255))
            )
            if lo2 is not None:
                mask2 = (
                    (h_scaled >= max(lo2[0] - tolerance // 6, 0)) & (h_scaled <= min(hi2[0] + tolerance // 6, 180)) &
                    (s >= max(lo2[1] - s_tol, 0)) & (s <= min(hi2[1] + s_tol, 255)) &
                    (v >= max(lo2[2] - v_tol, 0)) & (v <= min(hi2[2] + v_tol, 255))
                )
                mask = mask | mask2
            mask_arr = (mask.astype(_np.uint8) * 255)
            matched = int(_np.sum(mask))
            total = mask.shape[0] * mask.shape[1]
            print(f"Mask: {matched:,} pixels matched ({matched*100/total:.1f}%)")
            return _Img.fromarray(mask_arr, 'L')
        tc = _resolve_color_name(color)
        if tc is None:
            raise ValueError(f"Unknown color: '{color}'")
        color = tc
    arr = _np.array(img.convert('RGB'))
    fc = _np.array(color)
    mask = _np.all(_np.abs(arr.astype(int) - fc.astype(int)) <= tolerance, axis=-1)
    mask_arr = (mask.astype(_np.uint8) * 255)
    matched = int(_np.sum(mask))
    total = mask.shape[0] * mask.shape[1]
    print(f"Mask: {matched:,} pixels matched ({matched*100/total:.1f}%)")
    return _Img.fromarray(mask_arr, 'L')

def _img_mask_from_luminance(img, low: int = 0, high: int = 255):
    """Create a mask based on pixel brightness range (0-255).
    Usage: mask = img_mask_from_luminance(img, low=200, high=255)  — select highlights"""
    import numpy as _np
    from PIL import Image as _Img
    gray = _np.array(img.convert('L'))
    mask = ((gray >= low) & (gray <= high)).astype(_np.uint8) * 255
    matched = int(_np.sum(mask > 0))
    total = mask.shape[0] * mask.shape[1]
    print(f"Luminance mask: {matched:,} pixels in range [{low}, {high}] ({matched*100/total:.1f}%)")
    return _Img.fromarray(mask, 'L')

def _img_mask_invert(mask):
    """Invert a mask (swap white ↔ black).
    Usage: inverted = img_mask_invert(mask)"""
    from PIL import ImageOps as _Ops
    return _Ops.invert(mask.convert('L'))

def _img_mask_dilate(mask, radius: int = 3):
    """Grow/expand a mask by radius pixels.
    Usage: bigger_mask = img_mask_dilate(mask, 5)"""
    from PIL import ImageFilter as _Filt
    m = mask.convert('L')
    for _ in range(radius):
        m = m.filter(_Filt.MaxFilter(3))
    return m

def _img_mask_erode(mask, radius: int = 3):
    """Shrink a mask by radius pixels.
    Usage: smaller_mask = img_mask_erode(mask, 5)"""
    from PIL import ImageFilter as _Filt
    m = mask.convert('L')
    for _ in range(radius):
        m = m.filter(_Filt.MinFilter(3))
    return m

def _img_mask_feather(mask, radius: int = 5):
    """Soft-edge (feather) a mask by blurring its boundary.
    Usage: soft_mask = img_mask_feather(mask, 10)"""
    from PIL import ImageFilter as _Filt
    return mask.convert('L').filter(_Filt.GaussianBlur(radius=radius))

def _img_apply_to_region(img, mask, func, *args, **kwargs):
    """Apply any image editing function only to the masked region.
    White mask pixels are affected, black pixels are preserved.
    Usage: img = img_apply_to_region(img, mask, img_blur, radius=15)
           img = img_apply_to_region(img, mask, img_adjust, brightness=1.5)"""
    import numpy as _np
    from PIL import Image as _Img
    edited = func(img.copy(), *args, **kwargs)
    mask_l = mask.convert('L')
    mask_arr = _np.array(mask_l).astype(_np.float32) / 255.0
    mask3 = _np.stack([mask_arr]*3, axis=2)
    orig_arr = _np.array(img.convert('RGB')).astype(_np.float32)
    edit_arr = _np.array(edited.convert('RGB')).astype(_np.float32)
    result = orig_arr * (1.0 - mask3) + edit_arr * mask3
    return _Img.fromarray(_np.clip(result, 0, 255).astype(_np.uint8))

def _img_blur_region(img, mask, radius: int = 10):
    """Blur only the masked region of an image.
    Usage: img = img_blur_region(img, face_mask, radius=20)"""
    return _img_apply_to_region(img, mask, _img_blur, radius=radius)

def _img_fill_region(img, mask, color):
    """Fill the masked region with a solid color.
    Usage: img = img_fill_region(img, mask, 'red')
           img = img_fill_region(img, mask, (0, 255, 0))"""
    import numpy as _np
    from PIL import Image as _Img
    if isinstance(color, str):
        tc = _resolve_color_name(color)
        if tc is None:
            raise ValueError(f"Unknown color: '{color}'")
        color = tc
    arr = _np.array(img.convert('RGB')).copy()
    mask_arr = _np.array(mask.convert('L')) > 127
    arr[mask_arr] = _np.array(color, dtype=_np.uint8)
    return _Img.fromarray(arr)

_BASE_GLOBALS['img_mask_from_color'] = _img_mask_from_color
_BASE_GLOBALS['img_mask_from_luminance'] = _img_mask_from_luminance
_BASE_GLOBALS['img_mask_invert'] = _img_mask_invert
_BASE_GLOBALS['img_mask_dilate'] = _img_mask_dilate
_BASE_GLOBALS['img_mask_erode'] = _img_mask_erode
_BASE_GLOBALS['img_mask_feather'] = _img_mask_feather
_BASE_GLOBALS['img_apply_to_region'] = _img_apply_to_region
_BASE_GLOBALS['img_blur_region'] = _img_blur_region
_BASE_GLOBALS['img_fill_region'] = _img_fill_region


# ──────────────────────────────────────────
# PHASE 1E — UTILITY & INFO
# ──────────────────────────────────────────

def _img_histogram(img):
    """Display the RGB histogram of an image as a plot.
    Usage: img_histogram(img)"""
    import numpy as _np
    arr = _np.array(img.convert('RGB'))
    fig, ax = plt.subplots(figsize=(8, 4))
    for i, (ch, col) in enumerate(zip(['Red', 'Green', 'Blue'], ['#ff4444', '#44ff44', '#4444ff'])):
        ax.hist(arr[:, :, i].ravel(), bins=256, range=(0, 255), alpha=0.5, color=col, label=ch)
    ax.set_xlabel('Pixel Value')
    ax.set_ylabel('Count')
    ax.set_title('RGB Histogram')
    ax.legend()
    ax.set_xlim(0, 255)
    plt.tight_layout()

def _img_dominant_colors(img, n: int = 5):
    """Extract the N most dominant colors from an image as hex strings.
    Usage: colors = img_dominant_colors(img, 8)"""
    import numpy as _np
    from collections import Counter
    small = img.copy()
    small.thumbnail((150, 150))
    arr = _np.array(small.convert('RGB'))
    pixels = arr.reshape(-1, 3)
    # Quantize to reduce unique colors
    quantized = (pixels // 16) * 16
    counts = Counter(map(tuple, quantized))
    top = counts.most_common(n)
    result = []
    for color_rgb, count in top:
        hex_str = '#{:02x}{:02x}{:02x}'.format(*color_rgb)
        result.append(hex_str)
    print(f"Dominant colors: {', '.join(result)}")
    return result

def _img_color_palette(img, n: int = 8):
    """Generate a color palette visualization from the image.
    Usage: img_color_palette(img)"""
    import numpy as _np
    colors = _img_dominant_colors(img, n)
    swatch_w = 80
    swatch_h = 60
    fig, axes = plt.subplots(1, n, figsize=(n * 1.2, 1.5))
    if n == 1:
        axes = [axes]
    for ax, hex_col in zip(axes, colors):
        r, g, b = int(hex_col[1:3], 16), int(hex_col[3:5], 16), int(hex_col[5:7], 16)
        ax.imshow(_np.full((swatch_h, swatch_w, 3), [r, g, b], dtype=_np.uint8))
        ax.set_title(hex_col, fontsize=8)
        ax.axis('off')
    plt.suptitle('Color Palette', fontsize=11)
    plt.tight_layout()

def _img_exif(path: str):
    """Read EXIF metadata from an image file.
    Usage: data = img_exif('/path/to/photo.jpg')"""
    from PIL import Image as _Img
    from PIL.ExifTags import TAGS
    im = _Img.open(os.path.expanduser(path))
    exif_data = im.getexif()
    if not exif_data:
        print("No EXIF data found.")
        return {}
    result = {}
    for tag_id, value in exif_data.items():
        tag_name = TAGS.get(tag_id, tag_id)
        result[tag_name] = str(value)[:200]
    for k, v in result.items():
        print(f"  {k}: {v}")
    return result

def _img_compare(img1, img2):
    """Display two images side by side for comparison.
    Usage: img_compare(original, edited)"""
    import numpy as _np
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    ax1.imshow(img1)
    ax1.set_title('Before', fontsize=12)
    ax1.axis('off')
    ax2.imshow(img2)
    ax2.set_title('After', fontsize=12)
    ax2.axis('off')
    plt.tight_layout()

def _img_diff(img1, img2):
    """Show pixel-level difference between two images as a heatmap.
    Usage: img_diff(original, edited)"""
    import numpy as _np
    from PIL import Image as _Img
    a1 = _np.array(img1.convert('RGB')).astype(_np.float32)
    a2 = _np.array(img2.convert('RGB')).astype(_np.float32)
    if a1.shape != a2.shape:
        i2 = img2.resize(img1.size, _Img.LANCZOS)
        a2 = _np.array(i2.convert('RGB')).astype(_np.float32)
    diff = _np.abs(a1 - a2).mean(axis=2)
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(diff, cmap='hot', vmin=0, vmax=128)
    ax.set_title('Pixel Difference Heatmap')
    ax.axis('off')
    plt.colorbar(im, ax=ax, label='Mean Δ')
    plt.tight_layout()

def _img_trim(img, fuzz: int = 10):
    """Auto-crop whitespace or near-uniform borders from an image.
    Usage: img = img_trim(img)"""
    import numpy as _np
    from PIL import Image as _Img
    arr = _np.array(img.convert('RGB'))
    # Compare to the corner pixel
    ref = arr[0, 0].astype(int)
    mask = _np.any(_np.abs(arr.astype(int) - ref) > fuzz, axis=2)
    coords = _np.argwhere(mask)
    if coords.size == 0:
        return img
    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0) + 1
    result = img.crop((x0, y0, x1, y1))
    print(f"Trimmed: {img.size[0]}x{img.size[1]} → {result.size[0]}x{result.size[1]}")
    return result

def _img_pad(img, top: int = 0, right: int = 0, bottom: int = 0, left: int = 0, color="white"):
    """Add padding around an image.
    Usage: img = img_pad(img, 20, 20, 20, 20, 'black')"""
    from PIL import Image as _Img
    if isinstance(color, str):
        c = _resolve_color_name(color)
        color = c if c else color
    new_w = img.size[0] + left + right
    new_h = img.size[1] + top + bottom
    canvas = _Img.new('RGB', (new_w, new_h), color)
    canvas.paste(img.convert('RGB'), (left, top))
    return canvas

def _img_tile(img, cols: int, rows: int):
    """Tile an image into a cols×rows grid.
    Usage: img = img_tile(pattern, 3, 3)"""
    from PIL import Image as _Img
    w, h = img.size
    canvas = _Img.new('RGB', (w * cols, h * rows))
    for r in range(rows):
        for c in range(cols):
            canvas.paste(img.convert('RGB'), (c * w, r * h))
    return canvas

def _img_sample_color(img, x: int, y: int):
    """Sample the color at pixel (x, y) and return (R, G, B) + hex.
    Usage: color = img_sample_color(img, 100, 200)"""
    rgb = img.convert('RGB')
    if x < 0 or x >= rgb.size[0] or y < 0 or y >= rgb.size[1]:
        raise ValueError(f"Coordinates ({x}, {y}) out of bounds for {rgb.size[0]}x{rgb.size[1]} image.")
    r, g, b = rgb.getpixel((x, y))
    hex_str = '#{:02x}{:02x}{:02x}'.format(r, g, b)
    print(f"Color at ({x}, {y}): RGB({r}, {g}, {b}) = {hex_str}")
    return (r, g, b)

def _img_scale_to_fit(img, max_w: int, max_h: int):
    """Scale image to fit within max_w × max_h, preserving aspect ratio.
    Usage: img = img_scale_to_fit(img, 1920, 1080)"""
    from PIL import Image as _Img
    w, h = img.size
    ratio = min(max_w / w, max_h / h)
    if ratio >= 1.0:
        return img
    new_w = int(w * ratio)
    new_h = int(h * ratio)
    result = img.resize((new_w, new_h), _Img.LANCZOS)
    print(f"Scaled: {w}x{h} → {new_w}x{new_h}")
    return result

_BASE_GLOBALS['img_histogram'] = _img_histogram
_BASE_GLOBALS['img_dominant_colors'] = _img_dominant_colors
_BASE_GLOBALS['img_color_palette'] = _img_color_palette
_BASE_GLOBALS['img_exif'] = _img_exif
_BASE_GLOBALS['img_compare'] = _img_compare
_BASE_GLOBALS['img_diff'] = _img_diff
_BASE_GLOBALS['img_trim'] = _img_trim
_BASE_GLOBALS['img_pad'] = _img_pad
_BASE_GLOBALS['img_tile'] = _img_tile
_BASE_GLOBALS['img_sample_color'] = _img_sample_color
_BASE_GLOBALS['img_scale_to_fit'] = _img_scale_to_fit


# ──────────────────────────────────────────
# PHASE 1F — ADVANCED COLOR & EFFECTS
# ──────────────────────────────────────────

def _img_temperature(img, kelvin: float = 6500):
    """Adjust color temperature. 6500K=neutral, <6500=warm (yellow/orange), >6500=cool (blue).
    Usage: img = img_temperature(img, 4500)  — warmer
           img = img_temperature(img, 8500)  — cooler"""
    import numpy as _np
    from PIL import Image as _Img
    arr = _np.array(img.convert('RGB')).astype(_np.float32)
    # Simplified color temperature mapping
    if kelvin < 6500:
        # Warm: boost red, reduce blue
        t = (6500 - kelvin) / 6500
        arr[:, :, 0] = _np.clip(arr[:, :, 0] * (1 + 0.3 * t), 0, 255)
        arr[:, :, 1] = _np.clip(arr[:, :, 1] * (1 + 0.05 * t), 0, 255)
        arr[:, :, 2] = _np.clip(arr[:, :, 2] * (1 - 0.3 * t), 0, 255)
    else:
        # Cool: boost blue, reduce red
        t = (kelvin - 6500) / 6500
        arr[:, :, 0] = _np.clip(arr[:, :, 0] * (1 - 0.2 * t), 0, 255)
        arr[:, :, 2] = _np.clip(arr[:, :, 2] * (1 + 0.3 * t), 0, 255)
    return _Img.fromarray(arr.astype(_np.uint8))

def _img_vibrance(img, amount: float = 1.3):
    """Smart saturation — boosts under-saturated colors more than already saturated ones.
    amount: 1.0=no change, >1.0=more vibrant, <1.0=less vibrant.
    Usage: img = img_vibrance(img, 1.5)"""
    import numpy as _np
    from PIL import Image as _Img
    arr = _np.array(img.convert('RGB')).astype(_np.float32)
    gray = _np.mean(arr, axis=2, keepdims=True)
    sat = _np.max(arr, axis=2, keepdims=True) - _np.min(arr, axis=2, keepdims=True)
    max_sat = sat.max() + 1e-6
    # Lower saturation pixels get boosted more
    weight = 1.0 - (sat / max_sat)
    effective_amount = 1.0 + (amount - 1.0) * weight
    result = gray + (arr - gray) * effective_amount
    return _Img.fromarray(_np.clip(result, 0, 255).astype(_np.uint8))

def _img_clarity(img, amount: float = 1.5):
    """Enhance midtone contrast (clarity/punch). amount: 1.0=no change, >1.0=more clarity.
    Usage: img = img_clarity(img, 2.0)"""
    import numpy as _np
    from PIL import Image as _Img, ImageFilter as _Filt
    arr = _np.array(img.convert('RGB')).astype(_np.float32)
    blurred = img.filter(_Filt.GaussianBlur(radius=10))
    blur_arr = _np.array(blurred.convert('RGB')).astype(_np.float32)
    # Unsharp mask focused on midtones
    detail = arr - blur_arr
    result = arr + detail * (amount - 1.0)
    return _Img.fromarray(_np.clip(result, 0, 255).astype(_np.uint8))

def _img_dehaze(img, strength: float = 0.5):
    """Simple dehazing by boosting contrast and saturation.
    strength: 0.0-1.0. Usage: img = img_dehaze(img, 0.7)"""
    from PIL import ImageEnhance as _Enh
    strength = max(0.0, min(1.0, strength))
    result = img.copy()
    result = _Enh.Contrast(result).enhance(1.0 + 0.5 * strength)
    result = _Enh.Color(result).enhance(1.0 + 0.3 * strength)
    result = _Enh.Brightness(result).enhance(1.0 + 0.1 * strength)
    return result

def _img_curves(img, shadows: float = 1.0, midtones: float = 1.0, highlights: float = 1.0):
    """Approximate tone curves: adjust shadows, midtones, and highlights independently.
    Values: 1.0=no change, >1.0=brighten, <1.0=darken.
    Usage: img = img_curves(img, shadows=1.3, midtones=0.9, highlights=0.8)"""
    import numpy as _np
    from PIL import Image as _Img
    arr = _np.array(img.convert('RGB')).astype(_np.float32) / 255.0
    # Build a tone curve LUT
    lut = _np.zeros(256, dtype=_np.float32)
    for i in range(256):
        x = i / 255.0
        if x < 0.33:
            w = x / 0.33
            lut[i] = x * shadows
        elif x < 0.67:
            w = (x - 0.33) / 0.34
            lut[i] = x * midtones
        else:
            lut[i] = x * highlights
    lut = _np.clip(lut * 255, 0, 255).astype(_np.uint8)
    arr_u8 = _np.array(img.convert('RGB'))
    result = lut[arr_u8]
    return _Img.fromarray(result)

def _img_color_balance(img, cyan_red: float = 0, magenta_green: float = 0, yellow_blue: float = 0):
    """Adjust color balance. Each parameter ranges from -100 to +100.
    Negative = first color, Positive = second color.
    Usage: img = img_color_balance(img, cyan_red=20, yellow_blue=-15)"""
    import numpy as _np
    from PIL import Image as _Img
    arr = _np.array(img.convert('RGB')).astype(_np.float32)
    arr[:, :, 0] = _np.clip(arr[:, :, 0] + cyan_red * 1.28, 0, 255)   # red channel
    arr[:, :, 1] = _np.clip(arr[:, :, 1] + magenta_green * 1.28, 0, 255)  # green channel
    arr[:, :, 2] = _np.clip(arr[:, :, 2] + yellow_blue * 1.28, 0, 255)  # blue channel
    return _Img.fromarray(arr.astype(_np.uint8))

def _img_lens_blur(img, radius: int = 10, shape: str = 'circle'):
    """Bokeh-style lens blur. shape: 'circle' or 'hexagon'.
    Usage: img = img_lens_blur(img, radius=15, shape='hexagon')"""
    import numpy as _np
    from PIL import Image as _Img, ImageFilter as _Filt
    if shape == 'hexagon':
        # Approximate hexagonal bokeh with multiple directional blurs
        import math
        arr = _np.array(img.convert('RGB')).astype(_np.float32)
        result = _np.zeros_like(arr)
        for angle in range(0, 360, 60):
            blurred = img.filter(_Filt.GaussianBlur(radius=radius))
            result += _np.array(blurred.convert('RGB')).astype(_np.float32)
        result = result / 6.0
        return _Img.fromarray(_np.clip(result, 0, 255).astype(_np.uint8))
    else:
        return img.filter(_Filt.GaussianBlur(radius=radius))

def _img_motion_blur(img, size: int = 15, angle: float = 0):
    """Apply motion blur at a specified angle (degrees).
    Usage: img = img_motion_blur(img, size=20, angle=45)"""
    import numpy as _np
    from PIL import Image as _Img, ImageFilter as _Filt
    import math
    # Create a motion blur kernel
    kernel_size = max(3, size)
    kernel = _np.zeros((kernel_size, kernel_size), dtype=_np.float32)
    center = kernel_size // 2
    rad = math.radians(angle)
    for i in range(kernel_size):
        offset = i - center
        x = center + int(round(offset * math.cos(rad)))
        y = center + int(round(offset * math.sin(rad)))
        if 0 <= x < kernel_size and 0 <= y < kernel_size:
            kernel[y, x] = 1.0
    kernel /= kernel.sum() + 1e-8
    flat = kernel.flatten().tolist()
    filt = _Filt.Kernel((kernel_size, kernel_size), flat, scale=1, offset=0)
    return img.filter(filt)

def _img_radial_blur(img, cx: int = None, cy: int = None, strength: int = 10):
    """Radial (zoom) blur centered on (cx, cy).
    Usage: img = img_radial_blur(img, strength=15)"""
    import numpy as _np
    from PIL import Image as _Img
    w, h = img.size
    if cx is None: cx = w // 2
    if cy is None: cy = h // 2
    arr = _np.array(img.convert('RGB')).astype(_np.float32)
    result = arr.copy()
    for s in range(1, strength + 1):
        scale = 1.0 + s * 0.003
        offset_x = int(cx * (1 - scale))
        offset_y = int(cy * (1 - scale))
        new_w = int(w * scale)
        new_h = int(h * scale)
        scaled = img.resize((new_w, new_h), _Img.BILINEAR)
        cropped = scaled.crop((-offset_x, -offset_y, -offset_x + w, -offset_y + h))
        if cropped.size != (w, h):
            cropped = cropped.resize((w, h), _Img.BILINEAR)
        result += _np.array(cropped.convert('RGB')).astype(_np.float32)
    result /= (strength + 1)
    return _Img.fromarray(_np.clip(result, 0, 255).astype(_np.uint8))

_BASE_GLOBALS['img_temperature'] = _img_temperature
_BASE_GLOBALS['img_vibrance'] = _img_vibrance
_BASE_GLOBALS['img_clarity'] = _img_clarity
_BASE_GLOBALS['img_dehaze'] = _img_dehaze
_BASE_GLOBALS['img_curves'] = _img_curves
_BASE_GLOBALS['img_color_balance'] = _img_color_balance
_BASE_GLOBALS['img_lens_blur'] = _img_lens_blur
_BASE_GLOBALS['img_motion_blur'] = _img_motion_blur
_BASE_GLOBALS['img_radial_blur'] = _img_radial_blur


# ──────────────────────────────────────────
# PHASE 2 — LOCAL AI-POWERED TOOLS
# All models lazy-loaded on first call.
# ──────────────────────────────────────────

# Shared model cache so we only load once per process
_AI_MODEL_CACHE = {}

def _img_remove_bg(img):
    """Remove the background from an image. Returns an RGBA image with transparent background.
    Requires: pip install rembg onnxruntime
    Usage: img = img_remove_bg(img)"""
    try:
        from rembg import remove as _rembg_remove
    except ImportError:
        raise RuntimeError(
            "Background removal requires the 'rembg' package.\n"
            "Install it with: pip install rembg onnxruntime\n"
            "The model (~170 MB) will auto-download on first use."
        )
    print("Removing background (this may take a few seconds on first run)...")
    result = _rembg_remove(img)
    print(f"Background removed. Output mode: {result.mode}, size: {result.size[0]}x{result.size[1]}")
    return result

def _img_replace_bg(img, new_bg):
    """Remove background and composite onto a new background.
    new_bg: color name/tuple, or a PIL Image.
    Usage: img = img_replace_bg(img, 'white')
           img = img_replace_bg(img, beach_photo)"""
    from PIL import Image as _Img
    fg = _img_remove_bg(img)
    if isinstance(new_bg, str):
        c = _resolve_color_name(new_bg)
        if c is None:
            c = new_bg
        bg = _Img.new('RGBA', fg.size, (*c, 255) if isinstance(c, tuple) else c)
    elif isinstance(new_bg, tuple):
        bg = _Img.new('RGBA', fg.size, (*new_bg, 255))
    else:
        bg = new_bg.convert('RGBA').resize(fg.size, _Img.LANCZOS)
    bg.paste(fg, (0, 0), fg)
    return bg.convert('RGB')

def _img_detect_faces(img):
    """Detect faces in an image. Returns list of bounding box dicts.
    Each dict: {'x': int, 'y': int, 'w': int, 'h': int, 'confidence': float}
    Uses mediapipe Tasks API (new) → mediapipe Solutions (old) → OpenCV Haar cascade.
    Usage: faces = img_detect_faces(img)"""
    import numpy as _np
    arr = _np.array(img.convert('RGB'))
    h, w = arr.shape[:2]

    # ── Tier 1: MediaPipe Tasks API (>= 0.10.18) ──
    try:
        import mediapipe as _mp
        from mediapipe.tasks.python import vision as _mp_vision
        from mediapipe.tasks.python import BaseOptions as _BaseOpts

        # Auto-download the short-range face detection model to ~/.kasset/cache/
        _model_dir = os.path.join(os.path.expanduser("~"), ".kasset", "cache", "models")
        os.makedirs(_model_dir, exist_ok=True)
        _model_path = os.path.join(_model_dir, "blaze_face_short_range.tflite")
        if not os.path.exists(_model_path):
            print("Downloading face detection model (first run only, ~200 KB)...")
            import urllib.request
            _model_url = (
                "https://storage.googleapis.com/mediapipe-models/"
                "face_detector/blaze_face_short_range/float16/latest/"
                "blaze_face_short_range.tflite"
            )
            urllib.request.urlretrieve(_model_url, _model_path)
            print("Model downloaded.")

        _opts = _mp_vision.FaceDetectorOptions(
            base_options=_BaseOpts(model_asset_path=_model_path),
            min_detection_confidence=0.5,
        )
        _detector = _mp_vision.FaceDetector.create_from_options(_opts)
        _mp_img = _mp.Image(image_format=_mp.ImageFormat.SRGB, data=arr)
        _result = _detector.detect(_mp_img)

        faces = []
        if _result.detections:
            for det in _result.detections:
                bbox = det.bounding_box
                fx, fy, fw, fh = bbox.origin_x, bbox.origin_y, bbox.width, bbox.height
                conf = det.categories[0].score if det.categories else 0.0
                faces.append({'x': fx, 'y': fy, 'w': fw, 'h': fh, 'confidence': round(conf, 3)})
        _detector.close()
        print(f"Detected {len(faces)} face(s) (mediapipe Tasks API).")
        for i, f in enumerate(faces):
            print(f"  Face {i}: ({f['x']}, {f['y']}) {f['w']}x{f['h']} conf={f['confidence']}")
        return faces
    except Exception as _e1:
        _tier1_err = str(_e1)

    # ── Tier 2: MediaPipe Solutions (legacy, < 0.10.18) ──
    try:
        import mediapipe as _mp
        _mp_face = _mp.solutions.face_detection
        with _mp_face.FaceDetection(model_selection=1, min_detection_confidence=0.5) as detector:
            results = detector.process(arr)
        faces = []
        if results.detections:
            for det in results.detections:
                bbox = det.location_data.relative_bounding_box
                fx = int(bbox.xmin * w)
                fy = int(bbox.ymin * h)
                fw = int(bbox.width * w)
                fh = int(bbox.height * h)
                conf = det.score[0] if det.score else 0.0
                faces.append({'x': fx, 'y': fy, 'w': fw, 'h': fh, 'confidence': round(conf, 3)})
        print(f"Detected {len(faces)} face(s) (mediapipe Solutions).")
        for i, f in enumerate(faces):
            print(f"  Face {i}: ({f['x']}, {f['y']}) {f['w']}x{f['h']} conf={f['confidence']}")
        return faces
    except Exception as _e2:
        pass

    # ── Tier 3: OpenCV Haar Cascade (always available) ──
    try:
        import cv2 as _cv2
        _cascade_path = _cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        _cascade = _cv2.CascadeClassifier(_cascade_path)
        if _cascade.empty():
            raise RuntimeError("Haar cascade file not found")
        gray = _cv2.cvtColor(arr, _cv2.COLOR_RGB2GRAY)
        _cv2_faces = _cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
        )
        faces = []
        for (fx, fy, fw, fh) in _cv2_faces:
            faces.append({'x': int(fx), 'y': int(fy), 'w': int(fw), 'h': int(fh), 'confidence': 0.9})
        print(f"Detected {len(faces)} face(s) (OpenCV Haar cascade).")
        for i, f in enumerate(faces):
            print(f"  Face {i}: ({f['x']}, {f['y']}) {f['w']}x{f['h']} conf={f['confidence']}")
        return faces
    except Exception as _e3:
        pass

    raise RuntimeError(
        f"No face detection backend available.\n"
        f"  MediaPipe Tasks: {_tier1_err}\n"
        f"  Install mediapipe or opencv-python for face detection."
    )

def _img_blur_faces(img, radius: int = 20):
    """Auto-detect and blur all faces in an image.
    Usage: img = img_blur_faces(img, radius=25)"""
    import numpy as _np
    from PIL import Image as _Img, ImageFilter as _Filt
    faces = _img_detect_faces(img)
    if not faces:
        print("No faces detected — image unchanged.")
        return img
    result = img.copy()
    for f in faces:
        # Expand bbox slightly for better coverage
        margin = int(max(f['w'], f['h']) * 0.15)
        x1 = max(0, f['x'] - margin)
        y1 = max(0, f['y'] - margin)
        x2 = min(img.size[0], f['x'] + f['w'] + margin)
        y2 = min(img.size[1], f['y'] + f['h'] + margin)
        face_region = result.crop((x1, y1, x2, y2))
        blurred = face_region.filter(_Filt.GaussianBlur(radius=radius))
        result.paste(blurred, (x1, y1))
    print(f"Blurred {len(faces)} face(s).")
    return result

def _img_smooth_skin(img, strength: float = 0.5):
    """Face-aware skin smoothing. Detects faces, applies bilateral-style smoothing.
    strength: 0.0-1.0. Usage: img = img_smooth_skin(img, 0.7)"""
    import numpy as _np
    from PIL import Image as _Img, ImageFilter as _Filt
    faces = _img_detect_faces(img)
    if not faces:
        print("No faces detected — image unchanged.")
        return img
    result = img.copy()
    strength = max(0.0, min(1.0, strength))
    blur_r = int(3 + strength * 7)  # 3-10 pixel radius
    for f in faces:
        margin = int(max(f['w'], f['h']) * 0.2)
        x1 = max(0, f['x'] - margin)
        y1 = max(0, f['y'] - margin)
        x2 = min(img.size[0], f['x'] + f['w'] + margin)
        y2 = min(img.size[1], f['y'] + f['h'] + margin)
        region = result.crop((x1, y1, x2, y2))
        # Smooth while preserving edges: blend original with blurred
        smooth = region.filter(_Filt.GaussianBlur(radius=blur_r))
        arr_orig = _np.array(region).astype(_np.float32)
        arr_smooth = _np.array(smooth).astype(_np.float32)
        blended = arr_orig * (1.0 - strength) + arr_smooth * strength
        result.paste(_Img.fromarray(_np.clip(blended, 0, 255).astype(_np.uint8)), (x1, y1))
    print(f"Smoothed skin on {len(faces)} face(s).")
    return result

def _img_depth_map(img):
    """Estimate depth from a single image using MiDaS (local model).
    Returns a grayscale depth image (white=close, black=far).
    Requires: pip install timm torch torchvision
    Usage: depth = img_depth_map(img)"""
    try:
        import torch
    except ImportError:
        raise RuntimeError("Depth estimation requires 'torch'. Install with: pip install torch torchvision")
    import numpy as _np
    from PIL import Image as _Img

    print("Loading depth estimation model (first run downloads ~80 MB)...")
    if 'midas' not in _AI_MODEL_CACHE:
        model = torch.hub.load("intel-isl/MiDaS", "MiDaS_small", trust_repo=True)
        model.eval()
        transforms = torch.hub.load("intel-isl/MiDaS", "transforms", trust_repo=True)
        transform = transforms.small_transform
        # Use MPS if available (Apple Silicon)
        device = torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")
        model = model.to(device)
        _AI_MODEL_CACHE['midas'] = (model, transform, device)
    else:
        model, transform, device = _AI_MODEL_CACHE['midas']

    input_img = _np.array(img.convert('RGB'))
    input_batch = transform(input_img).to(device)

    with torch.no_grad():
        prediction = model(input_batch)
        prediction = torch.nn.functional.interpolate(
            prediction.unsqueeze(1),
            size=input_img.shape[:2],
            mode="bicubic",
            align_corners=False,
        ).squeeze()

    depth = prediction.cpu().numpy()
    # Normalize to 0-255
    depth = (depth - depth.min()) / (depth.max() - depth.min() + 1e-8) * 255
    depth_img = _Img.fromarray(depth.astype(_np.uint8), 'L')
    print(f"Depth map generated: {depth_img.size[0]}x{depth_img.size[1]}")
    return depth_img

def _img_bokeh(img, focus_point=None, aperture: float = 2.0):
    """Simulate depth-of-field bokeh using depth estimation.
    focus_point: (x, y) tuple — the point to keep in focus. Defaults to center.
    aperture: blur strength (1.0-5.0). Higher = more blur.
    Usage: img = img_bokeh(img, focus_point=(300, 200), aperture=3.0)"""
    import numpy as _np
    from PIL import Image as _Img, ImageFilter as _Filt

    w, h = img.size
    if focus_point is None:
        focus_point = (w // 2, h // 2)

    depth = _img_depth_map(img)
    depth_arr = _np.array(depth).astype(_np.float32) / 255.0

    # Get depth at focus point
    fx, fy = min(focus_point[0], w - 1), min(focus_point[1], h - 1)
    focus_depth = depth_arr[fy, fx]

    # Create blur mask: further from focus depth = more blur
    blur_mask = _np.abs(depth_arr - focus_depth)
    blur_mask = _np.clip(blur_mask * aperture * 3, 0, 1)

    # Apply progressive blur
    max_radius = int(aperture * 8)
    blurred = img.filter(_Filt.GaussianBlur(radius=max_radius))

    mask3 = _np.stack([blur_mask] * 3, axis=2)
    orig_arr = _np.array(img.convert('RGB')).astype(_np.float32)
    blur_arr = _np.array(blurred.convert('RGB')).astype(_np.float32)
    result = orig_arr * (1.0 - mask3) + blur_arr * mask3

    print(f"Bokeh applied. Focus point: {focus_point}, aperture: {aperture}")
    return _Img.fromarray(_np.clip(result, 0, 255).astype(_np.uint8))

def _img_depth_mask(img, near: float = 0.0, far: float = 0.5):
    """Create a mask based on estimated depth. near/far: 0.0-1.0 (0=closest, 1=farthest).
    Usage: mask = img_depth_mask(img, near=0.0, far=0.4)  — select foreground objects"""
    import numpy as _np
    from PIL import Image as _Img
    depth = _img_depth_map(img)
    depth_arr = _np.array(depth).astype(_np.float32) / 255.0
    mask = ((depth_arr >= near) & (depth_arr <= far)).astype(_np.uint8) * 255
    matched = int(_np.sum(mask > 0))
    total = mask.shape[0] * mask.shape[1]
    print(f"Depth mask: {matched:,} pixels in range [{near:.2f}, {far:.2f}] ({matched*100/total:.1f}%)")
    return _Img.fromarray(mask, 'L')

def _img_upscale(img, scale: int = 2):
    """Upscale an image using high-quality Lanczos resampling with sharpening.
    For ML-based upscaling, install realesrgan. Falls back to PIL Lanczos.
    scale: 2 or 4. Usage: img = img_upscale(img, 2)"""
    from PIL import Image as _Img
    if scale not in (2, 4):
        raise ValueError("Scale must be 2 or 4.")

    # Try Real-ESRGAN first for best quality
    try:
        from realesrgan import RealESRGANer
        from basicsr.archs.rrdbnet_arch import RRDBNet
        import torch
        import numpy as _np

        if 'realesrgan' not in _AI_MODEL_CACHE:
            print("Loading Real-ESRGAN model (first run downloads ~60 MB)...")
            model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
            device = 'mps' if torch.backends.mps.is_available() else 'cpu'
            upsampler = RealESRGANer(
                scale=4, model_path=None, model=model, device=device,
                half=False, tile=0, tile_pad=10, pre_pad=0
            )
            _AI_MODEL_CACHE['realesrgan'] = upsampler
        else:
            upsampler = _AI_MODEL_CACHE['realesrgan']

        import cv2
        arr = _np.array(img.convert('RGB'))[:, :, ::-1]  # RGB to BGR
        output, _ = upsampler.enhance(arr, outscale=scale)
        result = _Img.fromarray(output[:, :, ::-1])  # BGR to RGB
        print(f"Upscaled {scale}x with Real-ESRGAN: {img.size[0]}x{img.size[1]} → {result.size[0]}x{result.size[1]}")
        return result
    except ImportError:
        pass

    # Fallback: high-quality Lanczos + sharpening
    w, h = img.size
    new_w, new_h = w * scale, h * scale
    result = img.resize((new_w, new_h), _Img.LANCZOS)
    # Apply mild sharpening to compensate for interpolation softness
    from PIL import ImageFilter as _Filt
    result = result.filter(_Filt.UnsharpMask(radius=2, percent=50, threshold=2))
    print(f"Upscaled {scale}x with Lanczos+sharpen: {w}x{h} → {new_w}x{new_h}")
    print("(Install 'realesrgan' + 'basicsr' for ML-based upscaling)")
    return result

def _img_inpaint(img, mask):
    """Fill the masked region with context-aware content (inpainting).
    Uses OpenCV's Navier-Stokes inpainting. For best results feather the mask edges.
    Requires: pip install opencv-python-headless
    Usage: img = img_inpaint(img, mask)"""
    try:
        import cv2
    except ImportError:
        raise RuntimeError(
            "Inpainting requires OpenCV.\n"
            "Install with: pip install opencv-python-headless"
        )
    import numpy as _np
    from PIL import Image as _Img
    src = _np.array(img.convert('RGB'))
    mask_arr = _np.array(mask.convert('L'))
    # OpenCV inpaint expects 0=keep, 255=inpaint — which matches our mask convention
    result = cv2.inpaint(src, mask_arr, inpaintRadius=5, flags=cv2.INPAINT_NS)
    print(f"Inpainted {int(_np.sum(mask_arr > 127)):,} pixels.")
    return _Img.fromarray(result)

def _img_remove_object(img, mask):
    """Remove an object by inpainting the masked region.
    Usage: mask = img_mask_from_color(img, 'red', tolerance=40)
           img = img_remove_object(img, mask)"""
    # Dilate mask slightly for cleaner removal
    expanded = _img_mask_dilate(mask, radius=5)
    feathered = _img_mask_feather(expanded, radius=3)
    return _img_inpaint(img, feathered)

def _img_auto_enhance(img):
    """One-click auto-enhancement: auto contrast, vibrance boost, mild sharpening, and dehaze.
    Usage: img = img_auto_enhance(img)"""
    result = _img_auto_contrast(img, cutoff=0.5)
    result = _img_vibrance(result, amount=1.15)
    result = _img_clarity(result, amount=1.2)
    result = _img_dehaze(result, strength=0.2)
    from PIL import ImageFilter as _Filt
    result = result.filter(_Filt.UnsharpMask(radius=1, percent=30, threshold=2))
    print("Auto-enhanced: contrast, vibrance, clarity, dehaze, sharpen.")
    return result

_BASE_GLOBALS['img_remove_bg'] = _img_remove_bg
_BASE_GLOBALS['img_replace_bg'] = _img_replace_bg
_BASE_GLOBALS['img_detect_faces'] = _img_detect_faces
_BASE_GLOBALS['img_blur_faces'] = _img_blur_faces
_BASE_GLOBALS['img_smooth_skin'] = _img_smooth_skin
_BASE_GLOBALS['img_depth_map'] = _img_depth_map
_BASE_GLOBALS['img_bokeh'] = _img_bokeh
_BASE_GLOBALS['img_depth_mask'] = _img_depth_mask
_BASE_GLOBALS['img_upscale'] = _img_upscale
_BASE_GLOBALS['img_inpaint'] = _img_inpaint
_BASE_GLOBALS['img_remove_object'] = _img_remove_object
_BASE_GLOBALS['img_auto_enhance'] = _img_auto_enhance


# ──────────────────────────────────────────
# PHASE 8 — BATCH PROCESSING
# ──────────────────────────────────────────

def _img_batch_load(directory: str, extensions=None):
    """Load all images from a directory. Returns list of (path, PIL.Image) tuples.
    extensions: list of extensions to include, e.g. ['.jpg', '.png']. Default: all image types.
    Usage: images = img_batch_load('/path/to/folder')
           images = img_batch_load('/path', extensions=['.jpg'])"""
    from PIL import Image as _Img
    import glob as _glob
    if extensions is None:
        extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif']
    results = []
    for ext in extensions:
        pattern = os.path.join(directory, f'*{ext}')
        results.extend(_glob.glob(pattern))
        pattern_upper = os.path.join(directory, f'*{ext.upper()}')
        results.extend(_glob.glob(pattern_upper))
    results = sorted(set(results))
    images = []
    for p in results:
        try:
            img = _Img.open(p)
            img.load()
            images.append((p, img))
        except Exception as e:
            print(f"  Skipped {os.path.basename(p)}: {e}")
    print(f"Loaded {len(images)} images from {directory}")
    return images

def _img_batch_apply(images, func, *args, **kwargs):
    """Apply a function to a list of (path, image) tuples. Returns list of (path, result_image).
    func: any img_* function that takes an image as first argument.
    Usage: results = img_batch_apply(images, img_auto_enhance)
           results = img_batch_apply(images, img_resize, 800, 600)"""
    results = []
    total = len(images)
    for i, (path, img) in enumerate(images):
        try:
            result = func(img, *args, **kwargs)
            results.append((path, result))
            if (i + 1) % 5 == 0 or i == total - 1:
                print(f"  Processed {i + 1}/{total}")
        except Exception as e:
            print(f"  Failed {os.path.basename(path)}: {e}")
            results.append((path, img))  # keep original on failure
    print(f"Batch processing complete: {len(results)}/{total} succeeded")
    return results

def _img_batch_save(images, output_dir: str, format: str = 'png', prefix: str = '', suffix: str = '', quality: int = 95):
    """Save a list of (path, image) tuples to a directory.
    Usage: img_batch_save(results, '/path/to/output')
           img_batch_save(results, '/path/to/output', format='jpg', quality=85, prefix='edited_')"""
    os.makedirs(output_dir, exist_ok=True)
    saved = 0
    for path, img in images:
        basename = os.path.splitext(os.path.basename(path))[0]
        out_name = f"{prefix}{basename}{suffix}.{format}"
        out_path = os.path.join(output_dir, out_name)
        try:
            if format.lower() in ('jpg', 'jpeg'):
                img.convert('RGB').save(out_path, format='JPEG', quality=quality)
            else:
                img.save(out_path, format=format.upper())
            saved += 1
        except Exception as e:
            print(f"  Failed to save {out_name}: {e}")
    print(f"Saved {saved}/{len(images)} images to {output_dir}")
    return output_dir

def _img_batch_resize(images, width: int, height: int = None):
    """Batch resize all images. If height is None, maintains aspect ratio.
    Usage: results = img_batch_resize(images, 800)
           results = img_batch_resize(images, 1920, 1080)"""
    from PIL import Image as _Img
    results = []
    for path, img in images:
        w, h = img.size
        if height is None:
            ratio = width / w
            new_h = int(h * ratio)
            result = img.resize((width, new_h), _Img.LANCZOS)
        else:
            result = img.resize((width, height), _Img.LANCZOS)
        results.append((path, result))
    print(f"Resized {len(results)} images to {width}x{height or 'auto'}")
    return results

def _img_batch_convert(input_dir: str, output_dir: str, output_format: str = 'webp', quality: int = 85):
    """Convert all images in a directory to a different format.
    Usage: img_batch_convert('/path/input', '/path/output', 'webp', quality=80)"""
    images = _img_batch_load(input_dir)
    return _img_batch_save(images, output_dir, format=output_format, quality=quality)

def _img_batch_watermark(images, text: str, opacity: float = 0.3, position: str = 'br', font_size: int = 24):
    """Add watermark to a batch of images.
    Usage: results = img_batch_watermark(images, 'Copyright 2024', opacity=0.4)"""
    results = []
    for path, img in images:
        result = _img_watermark(img, text, opacity=opacity, position=position, font_size=font_size)
        results.append((path, result))
    print(f"Watermarked {len(results)} images with '{text}'")
    return results

def _img_contact_sheet(images, cols: int = 4, thumb_size: int = 200, padding: int = 10, bg_color='white'):
    """Create a contact sheet / thumbnail grid from a batch of images.
    Usage: sheet = img_contact_sheet(images, cols=5, thumb_size=150)"""
    from PIL import Image as _Img
    n = len(images)
    rows = (n + cols - 1) // cols
    sheet_w = cols * (thumb_size + padding) + padding
    sheet_h = rows * (thumb_size + padding) + padding
    c = _resolve_color_name(bg_color) if isinstance(bg_color, str) else bg_color
    sheet = _Img.new('RGB', (sheet_w, sheet_h), c if c else (255, 255, 255))
    for idx, (path, img) in enumerate(images):
        row, col = divmod(idx, cols)
        thumb = img.copy()
        thumb.thumbnail((thumb_size, thumb_size), _Img.LANCZOS)
        x = padding + col * (thumb_size + padding) + (thumb_size - thumb.size[0]) // 2
        y = padding + row * (thumb_size + padding) + (thumb_size - thumb.size[1]) // 2
        sheet.paste(thumb, (x, y))
    print(f"Contact sheet: {cols}×{rows} grid, {sheet_w}×{sheet_h}px, {n} images")
    return sheet

_BASE_GLOBALS['img_batch_load'] = _img_batch_load
_BASE_GLOBALS['img_batch_apply'] = _img_batch_apply
_BASE_GLOBALS['img_batch_save'] = _img_batch_save
_BASE_GLOBALS['img_batch_resize'] = _img_batch_resize
_BASE_GLOBALS['img_batch_convert'] = _img_batch_convert
_BASE_GLOBALS['img_batch_watermark'] = _img_batch_watermark
_BASE_GLOBALS['img_contact_sheet'] = _img_contact_sheet


# ──────────────────────────────────────────
# HTML ARTIFACT HELPER
# ──────────────────────────────────────────
# Thread-local storage for HTML artifacts produced during execution
_pending_html_artifact = {"html": ""}

def _html_preview(html_string: str):
    """Embed an interactive HTML artifact directly in the chat.
    Usage: html_preview('<html>...</html>')
    The HTML will be rendered as an interactive iframe in the conversation.
    Use this for buttons, interactive demos, mini-apps, etc."""
    if not isinstance(html_string, str) or not html_string.strip():
        print("html_preview: empty HTML string, nothing to display.")
        return
    _pending_html_artifact["html"] = html_string
    print(f"[HTML artifact queued — {len(html_string)} chars]")

_BASE_GLOBALS['html_preview'] = _html_preview

# Also update legacy alias
_SHARED_GLOBALS = _BASE_GLOBALS


# ──────────────────────────────────────────
# SESSION-SCOPED SANDBOX
# ──────────────────────────────────────────
import time as _time
import threading as _threading

class SandboxSession:
    """Isolated sandbox environment for a single chat session."""
    __slots__ = ('session_id', 'globals', 'created_at', 'last_used', 'pending_html')

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.globals = dict(_BASE_GLOBALS)  # shallow copy — libraries shared, user vars isolated
        self.globals['__name__'] = '__main__'
        self.created_at = _time.time()
        self.last_used = _time.time()
        self.pending_html = {"html": ""}

    def touch(self):
        self.last_used = _time.time()


_SESSION_REGISTRY: dict[str, SandboxSession] = {}
_SESSION_LOCK = _threading.Lock()
_SESSION_MAX_AGE = 6 * 3600  # 6 hours
_SESSION_MAX_COUNT = 50


def get_session(session_id: str | None = None) -> SandboxSession:
    """Get or create a sandbox session. None returns a default global session."""
    if not session_id:
        session_id = "__default__"
    with _SESSION_LOCK:
        if session_id in _SESSION_REGISTRY:
            sess = _SESSION_REGISTRY[session_id]
            sess.touch()
            return sess
        # Evict old sessions if at capacity
        if len(_SESSION_REGISTRY) >= _SESSION_MAX_COUNT:
            now = _time.time()
            expired = [k for k, v in _SESSION_REGISTRY.items()
                       if now - v.last_used > _SESSION_MAX_AGE]
            for k in expired:
                del _SESSION_REGISTRY[k]
            # If still at capacity, evict oldest
            if len(_SESSION_REGISTRY) >= _SESSION_MAX_COUNT:
                oldest_key = min(_SESSION_REGISTRY, key=lambda k: _SESSION_REGISTRY[k].last_used)
                del _SESSION_REGISTRY[oldest_key]
        sess = SandboxSession(session_id)
        _SESSION_REGISTRY[session_id] = sess
        return sess


def clear_session(session_id: str):
    """Remove a session's sandbox state."""
    with _SESSION_LOCK:
        _SESSION_REGISTRY.pop(session_id, None)


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
            'font.size': 11,
            'axes.titlesize': 14,
            'axes.titleweight': 'bold',
            'figure.dpi': 150,
            'figure.figsize': (10, 6),
            'figure.autolayout': True,
            'lines.linewidth': 2.5,
            'lines.color': '#58a6ff',
            'axes.prop_cycle': plt.cycler('color', ['#58a6ff', '#3fb950', '#f85149', '#a371f7', '#d29922', '#e3b341']),
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
    (r'(?<!\.)\bcompile\s*\(', 'compile() — not allowed in sandbox (use re.compile() for regex)'),
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


def execute_python_sandbox(code: str, session_id: str = None) -> dict:
    """
    Executes Python code safely, capturing stdout/stderr, matplotlib plots, and Plotly HTML.
    Returns a dict with 'output' (str), 'images' (list of base64 data URIs),
    and optionally 'html' (str) for interactive Plotly figures.
    Uses a session-scoped global environment so variables persist within a chat session.
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

    # ast.parse() pre-check: catch syntax errors before exec()
    import ast
    try:
        ast.parse(code)
    except SyntaxError as e:
        line_info = f" (line {e.lineno})" if e.lineno else ""
        return {
            "output": f"SyntaxError{line_info}: {e.msg}\nFix the syntax error and try again.",
            "images": [],
        }

    output_capture = io.StringIO()
    images = []
    html_artifact = ""

    # Get session-scoped globals
    session = get_session(session_id)
    session_globals = session.globals

    # Clear pending html_preview artifact from previous execution
    _pending_html_artifact["html"] = ""
    session.pending_html["html"] = ""

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
    session_globals['plt'] = plt
    plt.show = lambda *args, **kwargs: None

    # Snapshot existing Plotly figures before execution so we only capture NEW ones
    _pre_plotly_ids = set()
    try:
        import plotly.graph_objects as _go
        _pre_plotly_ids = {id(v) for v in session_globals.values() if isinstance(v, _go.Figure)}
    except ImportError:
        pass

    try:
        with contextlib.redirect_stdout(output_capture), contextlib.redirect_stderr(output_capture):
            exec(safe_code, session_globals)

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
                new_figs = [v for v in session_globals.values()
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

        # Also capture html_preview() artifacts (takes priority over Plotly if both present)
        if _pending_html_artifact["html"]:
            html_artifact = _pending_html_artifact["html"]
            _pending_html_artifact["html"] = ""
        elif session.pending_html["html"]:
            html_artifact = session.pending_html["html"]
            session.pending_html["html"] = ""

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

