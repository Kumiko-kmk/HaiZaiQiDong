"""Checked absolute mouse input for Windows and a pynput fallback elsewhere."""

from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes
from enum import Enum
from typing import Callable

from pynput.mouse import Button, Controller

from core.pacing import wait_sec


class MouseButton(Enum):
    LEFT = "left"
    RIGHT = "right"


class InputInjectionError(RuntimeError):
    """Raised when Windows refuses or only partially inserts an input event."""

    failure_code = "input_injection_failed"

    def __init__(self, operation: str, *, expected: int = 1, actual: int = 0) -> None:
        self.operation = operation
        self.expected = expected
        self.actual = actual
        self.winerror = ctypes.get_last_error() if sys.platform == "win32" else 0
        super().__init__(
            f"{operation} failed: inserted {actual}/{expected} input events "
            f"(Win32 error {self.winerror}); run the drawer at the same privilege level as the target"
        )


if sys.platform == "win32":
    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_void_p),
        ]


    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT)]


    class _INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("value", _INPUTUNION)]


    _SEND_INPUT = ctypes.WinDLL("user32", use_last_error=True).SendInput
    _SEND_INPUT.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
    _SEND_INPUT.restype = wintypes.UINT


_INPUT_MOUSE = 0
_MOVE = 0x0001
_LEFT_DOWN = 0x0002
_LEFT_UP = 0x0004
_RIGHT_DOWN = 0x0008
_RIGHT_UP = 0x0010
_VIRTUAL_DESK = 0x4000
_ABSOLUTE = 0x8000
# Identifies events emitted by this process even when a hook/driver fails to
# preserve Windows' generic LLMHF_INJECTED flag.
DRAW_INPUT_MARKER = 0x48415A51

_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79

VirtualDesktopProvider = Callable[[], tuple[int, int, int, int]]


def get_virtual_desktop() -> tuple[int, int, int, int]:
    """Return virtual desktop ``left, top, width, height`` in physical pixels."""
    if sys.platform != "win32":
        return 0, 0, 1, 1
    user32 = ctypes.windll.user32
    left = int(user32.GetSystemMetrics(_SM_XVIRTUALSCREEN))
    top = int(user32.GetSystemMetrics(_SM_YVIRTUALSCREEN))
    width = int(user32.GetSystemMetrics(_SM_CXVIRTUALSCREEN))
    height = int(user32.GetSystemMetrics(_SM_CYVIRTUALSCREEN))
    if width <= 0 or height <= 0:
        left = top = 0
        width = int(user32.GetSystemMetrics(0))
        height = int(user32.GetSystemMetrics(1))
    if width <= 0 or height <= 0:
        raise InputInjectionError("read virtual desktop metrics")
    return left, top, width, height


def normalize_absolute_coordinate(value: float, origin: int, extent: int) -> int:
    """Map a physical screen coordinate to the Win32 0..65535 range."""
    if extent <= 1:
        return 0
    normalized = round((float(value) - origin) * 65535.0 / (extent - 1))
    return max(0, min(65535, int(normalized)))


class MouseController:
    def __init__(
        self,
        *,
        virtual_desktop_provider: VirtualDesktopProvider = get_virtual_desktop,
    ) -> None:
        self._mouse = Controller()
        self._virtual_desktop_provider = virtual_desktop_provider
        self._pressed_button: MouseButton | None = None
        self._lock = threading.RLock()
        pos = self._read_cursor_position()
        self._cursor_x = float(pos[0])
        self._cursor_y = float(pos[1])

    def _read_cursor_position(self) -> tuple[int, int]:
        if sys.platform == "win32":
            point = wintypes.POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
                return int(point.x), int(point.y)
        try:
            position = self._mouse.position
            if position is not None:
                return int(position[0]), int(position[1])
        except Exception:
            pass
        return 0, 0

    def ensure_pen_up(self, *, gap_sec: float = 0.0) -> None:
        """Release both drawing buttons and optionally yield to the OS."""
        self._force_buttons_up()
        wait_sec(gap_sec)

    def move_absolute(self, x: float, y: float) -> None:
        """Move to a physical virtual-desktop coordinate with checked input."""
        target_x = int(round(x))
        target_y = int(round(y))
        with self._lock:
            if sys.platform == "win32":
                left, top, width, height = self._virtual_desktop_provider()
                nx = normalize_absolute_coordinate(target_x, left, width)
                ny = normalize_absolute_coordinate(target_y, top, height)
                self._send_win32(_MOVE | _ABSOLUTE | _VIRTUAL_DESK, dx=nx, dy=ny, operation="move mouse")
            else:
                self._mouse.position = (target_x, target_y)
            self._cursor_x = float(target_x)
            self._cursor_y = float(target_y)

    def travel_to(self, x: float, y: float) -> None:
        """Compatibility wrapper for pen-up absolute travel."""
        self._force_buttons_up()
        wait_sec(0.008)
        self.move_absolute(x, y)

    def drag_relative(self, dx: int, dy: int) -> None:
        """Compatibility wrapper; new drawing code uses ``move_absolute``."""
        if self._pressed_button is None or (dx == 0 and dy == 0):
            return
        self.move_absolute(self._cursor_x + dx, self._cursor_y + dy)

    def press(self, button: MouseButton) -> None:
        with self._lock:
            self._force_buttons_up()
            if sys.platform == "win32":
                self._send_win32(self._button_down_flag(button), operation=f"press {button.value} button")
            else:
                self._mouse.press(self._to_pynput_button(button))
            self._pressed_button = button

    def release(self, button: MouseButton | None = None) -> None:
        with self._lock:
            target = button or self._pressed_button
            if target is None:
                return
            if sys.platform == "win32":
                self._send_win32(self._button_up_flag(target), operation=f"release {target.value} button")
            else:
                self._mouse.release(self._to_pynput_button(target))
            if self._pressed_button == target:
                self._pressed_button = None

    def release_all(self) -> None:
        self._force_buttons_up()

    def best_effort_release_all(self) -> None:
        """Cleanup path that must never hide the original drawing failure."""
        try:
            self._force_buttons_up()
        except Exception:
            self._pressed_button = None

    def _force_buttons_up(self) -> None:
        with self._lock:
            if sys.platform == "win32":
                first_error: Exception | None = None
                for flag, name in ((_LEFT_UP, "release left button"), (_RIGHT_UP, "release right button")):
                    try:
                        self._send_win32(flag, operation=name)
                    except Exception as exc:
                        first_error = first_error or exc
                self._pressed_button = None
                if first_error is not None:
                    raise first_error
            elif self._pressed_button is not None:
                self._mouse.release(self._to_pynput_button(self._pressed_button))
                self._pressed_button = None

    @staticmethod
    def _send_win32(
        flags: int,
        *,
        dx: int = 0,
        dy: int = 0,
        operation: str,
    ) -> None:
        event = _INPUT(
            type=_INPUT_MOUSE,
            value=_INPUTUNION(
                mi=_MOUSEINPUT(
                    dx=dx,
                    dy=dy,
                    mouseData=0,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=DRAW_INPUT_MARKER,
                )
            ),
        )
        inserted = int(_SEND_INPUT(1, ctypes.byref(event), ctypes.sizeof(_INPUT)))
        if inserted != 1:
            raise InputInjectionError(operation, actual=inserted)

    @staticmethod
    def _button_down_flag(button: MouseButton) -> int:
        return _LEFT_DOWN if button is MouseButton.LEFT else _RIGHT_DOWN

    @staticmethod
    def _button_up_flag(button: MouseButton) -> int:
        return _LEFT_UP if button is MouseButton.LEFT else _RIGHT_UP

    @staticmethod
    def _to_pynput_button(button: MouseButton) -> Button:
        return Button.left if button is MouseButton.LEFT else Button.right
