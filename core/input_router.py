"""Global input routing for preview controls and physical-button cancellation."""

from __future__ import annotations

import logging
import sys
import threading
from typing import Callable, Optional, Tuple

from pynput import keyboard, mouse

from core.mouse_controller import DRAW_INPUT_MARKER
from core.transform import ROTATION_STEP_DEG, SCALE_STEP_FACTOR

Point = Tuple[float, float]
VoidCallback = Callable[[], None]
AnchorCallback = Callable[[Point], None]
ScaleCallback = Callable[[float], None]
RotationCallback = Callable[[float], None]
PanelHitTest = Callable[[float, float], bool]

_WM_KEYDOWN = 0x0100
_WM_KEYUP = 0x0101
_WM_SYSKEYDOWN = 0x0104
_WM_SYSKEYUP = 0x0105
_WM_RBUTTONDOWN = 0x0204
_WM_RBUTTONUP = 0x0205
_MOUSE_INJECTED_MASK = 0x00000001 | 0x00000002
_KEYBOARD_INJECTED_MASK = 0x00000010 | 0x00000002
_READY_KEYS = {ord("W"), ord("A"), ord("S"), ord("D")}
_LOG = logging.getLogger(__name__)


class InputRouter:
    def __init__(self) -> None:
        self._mouse_listener: Optional[mouse.Listener] = None
        self._keyboard_listener: Optional[keyboard.Listener] = None
        self._ready_enabled = False
        self._drawing_enabled = False
        self._panel_hit_test: Optional[PanelHitTest] = None
        self._on_anchor: Optional[AnchorCallback] = None
        self._on_scale: Optional[ScaleCallback] = None
        self._on_rotation: Optional[RotationCallback] = None
        self._on_ready_cancel: Optional[VoidCallback] = None
        self._on_draw_cancel: Optional[VoidCallback] = None
        self._ready_cancel_requested = False
        self._draw_cancel_requested = False
        self._suppress_physical_right_release = False
        self._suppressed_ready_keys: set[int] = set()
        self._position_lock = threading.Lock()
        self._mode_lock = threading.Lock()
        self._latest_position: Point = (0.0, 0.0)

    @property
    def position(self) -> Point:
        with self._position_lock:
            return self._latest_position

    def start_base(self) -> None:
        if self._mouse_listener is None:
            options = {}
            if sys.platform == "win32":
                options["win32_event_filter"] = self._handle_win32_mouse_event
            self._mouse_listener = mouse.Listener(
                on_move=self._handle_move,
                on_click=self._handle_click,
                **options,
            )
            self._mouse_listener.start()
            _LOG.info("Global mouse listener started")

        if self._keyboard_listener is None:
            options = {}
            if sys.platform == "win32":
                options["win32_event_filter"] = self._handle_win32_keyboard_event
            self._keyboard_listener = keyboard.Listener(
                on_press=self._handle_key_press,
                **options,
            )
            self._keyboard_listener.start()
            _LOG.info("Global keyboard listener started")

    def stop(self) -> None:
        self.disable_ready_mode()
        self.disable_drawing_mode()
        if self._mouse_listener is not None:
            self._mouse_listener.stop()
            self._mouse_listener = None
        if self._keyboard_listener is not None:
            self._keyboard_listener.stop()
            self._keyboard_listener = None
        with self._mode_lock:
            self._suppress_physical_right_release = False
            self._suppressed_ready_keys.clear()

    def enable_ready_mode(
        self,
        *,
        panel_hit_test: PanelHitTest,
        on_anchor: AnchorCallback,
        on_scale: ScaleCallback,
        on_rotation: RotationCallback,
        on_cancel: VoidCallback,
    ) -> None:
        self.disable_drawing_mode()
        with self._mode_lock:
            self._panel_hit_test = panel_hit_test
            self._on_anchor = on_anchor
            self._on_scale = on_scale
            self._on_rotation = on_rotation
            self._on_ready_cancel = on_cancel
            self._ready_cancel_requested = False
            self._ready_enabled = True

    def disable_ready_mode(self) -> None:
        with self._mode_lock:
            self._ready_enabled = False
            self._panel_hit_test = None
            self._on_anchor = None
            self._on_scale = None
            self._on_rotation = None
            self._on_ready_cancel = None
            self._ready_cancel_requested = False

    def enable_drawing_mode(self, *, on_cancel: VoidCallback) -> None:
        """Listen for one physical right-button press while drawing."""
        self.disable_ready_mode()
        with self._mode_lock:
            self._on_draw_cancel = on_cancel
            self._draw_cancel_requested = False
            self._drawing_enabled = True

    def disable_drawing_mode(self) -> None:
        """Stop accepting cancel requests but keep pending releases suppressed."""
        with self._mode_lock:
            self._drawing_enabled = False
            self._on_draw_cancel = None
            self._draw_cancel_requested = False

    def _handle_move(self, x: float, y: float) -> None:
        with self._position_lock:
            self._latest_position = (float(x), float(y))

    def _handle_click(
        self,
        x: float,
        y: float,
        button: mouse.Button,
        pressed: bool,
        injected: bool = False,
    ) -> None:
        with self._mode_lock:
            drawing_enabled = self._drawing_enabled
            ready_enabled = self._ready_enabled
            panel_hit_test = self._panel_hit_test
            on_anchor = self._on_anchor

        if drawing_enabled:
            if button is mouse.Button.right and pressed and not injected:
                self._request_draw_cancel_once(source="mouse_callback")
            return
        if not ready_enabled:
            return
        if button is mouse.Button.right and pressed and not injected:
            self._request_ready_cancel_once()
            return
        in_panel = panel_hit_test is not None and panel_hit_test(x, y)
        if button is mouse.Button.left and not pressed:
            _LOG.info(
                "ready left release x=%.1f y=%.1f panel_hit=%s injected=%s",
                x,
                y,
                in_panel,
                injected,
            )
        if in_panel:
            return
        if button is mouse.Button.left and not pressed and on_anchor is not None:
            on_anchor((float(x), float(y)))

    def _handle_key_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        char = getattr(key, "char", None)
        if isinstance(char, str) and len(char) == 1:
            self._dispatch_ready_key(char.upper())

    def _dispatch_ready_key(self, char: str) -> bool:
        with self._mode_lock:
            if not self._ready_enabled:
                return False
            on_scale = self._on_scale
            on_rotation = self._on_rotation

        if char == "W" and on_scale is not None:
            on_scale(SCALE_STEP_FACTOR)
        elif char == "S" and on_scale is not None:
            on_scale(1.0 / SCALE_STEP_FACTOR)
        elif char == "A" and on_rotation is not None:
            on_rotation(-ROTATION_STEP_DEG)
        elif char == "D" and on_rotation is not None:
            on_rotation(ROTATION_STEP_DEG)
        else:
            return False
        return True

    def _request_ready_cancel_once(self) -> None:
        with self._mode_lock:
            if not self._ready_enabled or self._ready_cancel_requested:
                return
            self._ready_cancel_requested = True
            callback = self._on_ready_cancel
        if callback is not None:
            callback()

    def _request_draw_cancel_once(self, *, source: str = "unknown") -> None:
        with self._mode_lock:
            if not self._drawing_enabled or self._draw_cancel_requested:
                return
            self._draw_cancel_requested = True
            callback = self._on_draw_cancel
        _LOG.info("Draw cancellation requested source=%s", source)
        if callback is not None:
            callback()

    def _handle_win32_mouse_event(self, msg: int, data) -> bool:
        """Suppress physical right-click cancellation while allowing injected drawing."""
        if msg not in (_WM_RBUTTONDOWN, _WM_RBUTTONUP):
            return True
        if int(getattr(data, "dwExtraInfo", 0) or 0) == DRAW_INPUT_MARKER:
            # Do not forward our tagged right-button events to ``on_click``;
            # they must reach the target application but must never cancel
            # their own drawing session.
            return False
        if int(data.flags) & _MOUSE_INJECTED_MASK:
            return True

        if msg == _WM_RBUTTONDOWN:
            with self._mode_lock:
                drawing_enabled = self._drawing_enabled
                ready_enabled = self._ready_enabled
                if not drawing_enabled and not ready_enabled:
                    return True
                self._suppress_physical_right_release = True
            if drawing_enabled:
                self._request_draw_cancel_once(source="win32_physical_right")
            else:
                self._request_ready_cancel_once()
            self._suppress_mouse_event()
            return False

        with self._mode_lock:
            should_suppress = self._suppress_physical_right_release
            self._suppress_physical_right_release = False
        if should_suppress:
            self._suppress_mouse_event()
            return False
        return True

    def _handle_win32_keyboard_event(self, msg: int, data) -> bool:
        """Handle and suppress physical WASD preview controls on Windows."""
        if msg not in (_WM_KEYDOWN, _WM_KEYUP, _WM_SYSKEYDOWN, _WM_SYSKEYUP):
            return True
        if int(data.flags) & _KEYBOARD_INJECTED_MASK:
            return True
        vk_code = int(data.vkCode)
        if vk_code not in _READY_KEYS:
            return True

        if msg in (_WM_KEYDOWN, _WM_SYSKEYDOWN):
            with self._mode_lock:
                ready_enabled = self._ready_enabled
                if ready_enabled:
                    self._suppressed_ready_keys.add(vk_code)
            if not ready_enabled:
                return True
            self._dispatch_ready_key(chr(vk_code))
            self._suppress_keyboard_event()
            return False

        with self._mode_lock:
            should_suppress = vk_code in self._suppressed_ready_keys
            self._suppressed_ready_keys.discard(vk_code)
        if should_suppress:
            self._suppress_keyboard_event()
            return False
        return True

    def _suppress_mouse_event(self) -> None:
        if self._mouse_listener is not None:
            self._mouse_listener.suppress_event()

    def _suppress_keyboard_event(self) -> None:
        if self._keyboard_listener is not None:
            self._keyboard_listener.suppress_event()
