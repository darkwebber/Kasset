#!/usr/bin/env python3
"""
startup.py - Pre-flight checks for Qwen Studio.
Run this to verify your environment before starting the servers.
"""

import sys
import socket
from pathlib import Path


def check_files():
    required = ["app.py", "model_server.py", "utils.py", "requirements.txt"]
    missing = [f for f in required if not Path(f).exists()]
    if missing:
        print(f"  ✗ Missing files: {', '.join(missing)}")
        return False
    print(f"  ✓ Project files OK")
    return True


def check_python():
    v = sys.version_info
    if v.major < 3 or v.minor < 10:
        print(f"  ✗ Python 3.10+ required (found {v.major}.{v.minor})")
        return False
    print(f"  ✓ Python {v.major}.{v.minor}.{v.micro}")
    return True


def check_packages():
    packages = {
        "gradio": "gradio",
        "gradio_client": "gradio_client",
        "mlx_vlm": "mlx-vlm",
        "PIL": "Pillow",
    }
    missing = []
    for mod, pip_name in packages.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pip_name)
    if missing:
        print(f"  ✗ Missing packages: {', '.join(missing)}")
        print(f"    Fix: pip install {' '.join(missing)}")
        return False
    print(f"  ✓ All packages installed")
    return True


def check_ports():
    ok = True
    for port in (7860, 7861):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("localhost", port))
            s.close()
        except OSError:
            print(f"  ✗ Port {port} is in use (lsof -i :{port})")
            ok = False
    if ok:
        print(f"  ✓ Ports 7860, 7861 available")
    return ok


def main():
    print()
    print("  Qwen Studio - Pre-flight Check")
    print("  ═══════════════════════════════")
    print()

    checks = [check_files, check_python, check_packages, check_ports]
    all_ok = all(fn() for fn in checks)

    print()
    if all_ok:
        print("  ✅ All checks passed!")
        print()
        print("  Start:")
        print("    Terminal 1:  python model_server.py")
        print("    Terminal 2:  python app.py")
        print("    Browser:     http://localhost:7860")
    else:
        print("  ❌ Some checks failed. Fix the issues above and try again.")
        sys.exit(1)
    print()


if __name__ == "__main__":
    main()
