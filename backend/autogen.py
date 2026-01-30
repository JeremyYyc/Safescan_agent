"""
Proxy module to forward to the real pyautogen package.

This file exists only to prevent shadowing when this repository is on sys.path.
It re-imports the external `autogen` package and exposes its symbols.
"""

from __future__ import annotations

import importlib
import os
import sys

_this_dir = os.path.dirname(__file__)
_project_root = os.path.dirname(_this_dir)
_blocked = {os.path.normcase(_this_dir), os.path.normcase(_project_root)}

_original_sys_path = list(sys.path)
sys.path = [p for p in sys.path if os.path.normcase(p) not in _blocked]
sys.modules.pop(__name__, None)

try:
    _real_autogen = importlib.import_module("autogen")
finally:
    sys.path = _original_sys_path

sys.modules[__name__] = _real_autogen
globals().update(_real_autogen.__dict__)
