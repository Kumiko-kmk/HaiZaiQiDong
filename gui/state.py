"""Application state for the control panel."""

from __future__ import annotations

from enum import Enum, auto


class AppState(Enum):
    IDLE = auto()
    READY = auto()
    DRAWING = auto()
    TERMINATING = auto()
