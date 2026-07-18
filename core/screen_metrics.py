"""Primary display size for layout and preset fitting."""

from __future__ import annotations

import ctypes

ScreenSize = tuple[int, int]


def get_screen_size() -> ScreenSize:
    width = int(ctypes.windll.user32.GetSystemMetrics(0))
    height = int(ctypes.windll.user32.GetSystemMetrics(1))
    return width, height
