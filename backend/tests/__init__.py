"""
Backend tests package
Ensures project root and backend folder are in sys.path when running tests via unittest
"""

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TESTS_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for path_str in [str(PROJECT_ROOT), str(BACKEND_DIR)]:
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
