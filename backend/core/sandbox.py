import sys
import io
import contextlib
import base64
import traceback
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def execute_python_sandbox(code: str) -> dict:
    """
    Executes Python code safely, capturing stdout/stderr and matplotlib plots.
    Returns a dict with 'output' (str) and 'images' (list of base64 data URIs).
    """
    output_capture = io.StringIO()
    images = []

    exec_globals = {
        'plt': plt,
        'pd': None,  # lazy-loaded if needed
        'np': None,
        '__name__': '__main__',
    }

    # Try to make common data libs available
    try:
        import pandas as pd
        exec_globals['pd'] = pd
    except ImportError:
        pass
    try:
        import numpy as np
        exec_globals['np'] = np
    except ImportError:
        pass

    try:
        with contextlib.redirect_stdout(output_capture), contextlib.redirect_stderr(output_capture):
            exec(code, exec_globals)

            if len(plt.get_fignums()) > 0:
                for i in plt.get_fignums():
                    fig = plt.figure(i)
                    buf = io.BytesIO()
                    fig.savefig(buf, format='png', bbox_inches='tight', facecolor='#0a0a0a', edgecolor='none')
                    buf.seek(0)
                    img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                    images.append(f"data:image/png;base64,{img_b64}")
                plt.close('all')

        output = output_capture.getvalue()
        if not output and not images:
            output = "Code executed successfully (no output)."

    except Exception as e:
        output = output_capture.getvalue() + "\n" + traceback.format_exc()

    return {
        "output": output.strip(),
        "images": images,
    }
