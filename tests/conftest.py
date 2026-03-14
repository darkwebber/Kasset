"""
Shared fixtures and configuration for the Kasset Studio test suite.
"""
import sys
from pathlib import Path

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
