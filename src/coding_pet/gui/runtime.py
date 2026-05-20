from __future__ import annotations

import os
import sys


def has_graphical_session() -> bool:
    if not sys.platform.startswith("linux"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def gui_runtime_status() -> str:
    if not has_graphical_session():
        return "unavailable:no_display"
    try:
        from PySide6.QtWidgets import QApplication  # noqa: F401
    except Exception:
        return "unavailable"
    return "available"
