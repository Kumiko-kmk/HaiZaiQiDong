"""Global input routing for preview controls and physical-button cancellation."""

from __future__ import annotations

import math
import sys
import threading
import time
from typing import Callable, Optional, Tuple

from core.transform import SCALE_WHEEL_FACTOR

from pynput import mouse

Point = Tuple[float, float]
VoidCallback = Callable[[], None]
AnchorCallback = Callable[[Point], None]
ScaleCallback = Callable[[float], None]
RotationCallback = Callable[[float], None]
FlipCallback = Callable[[], None]
PanelHitTest = Callable[[float, float], bool]

_WM_RBUTTONDOWN = 0x0204
_WM_RBUTTONUP = 0x0205
_LLMHF_INJECTED_MASK = 0x00000001 | 0x00000002


class InputRouter:
    def __init__(self) -> None:
        self._listener: Optional[mouse.Listener] = None
        self._ready_enabled = False
        self._drawing_enabled = False
        self._panel_hit_test: Optional[PanelHitTest] = None
        self._on_anchor: Optional[AnchorCallback] = None
        self._on_scale: Optional[ScaleCallback] = None
        self._on_rotation: Optional[RotationCallback] = None
        self._on_flip: Optional[FlipCallback] = None
        self._on_cancel: Optional[VoidCallback] = None
        self._cancel_requested = False
        self._suppress_physical_right_release = False
        self._right_dragging = False
        self._rotation_pivot: Optional[Point] = None
        self._last_angle_deg = 0.0
        self._last_right_release_time = 0.0
        self._double_click_interval = 0.35
        self._lock = threading.Lock()
        self._mode_lock = threading.Lock()
        self._latest_position: Point = (0.0, 0.0)

    @property
    def position(self) -> Point:
        with self._lock:
            return self._latest_position

    def start_base(self) -> None:
        if self._listener is None:
            platform_options = {}
            if sys.platform == "win32":
                platform_options["win32_event_filter"] = self._handle_win32_event
            self._listener = mouse.Listener(
                on_move=self._handle_move,
                on_click=self._handle_click,
                on_scroll=self._handle_scroll,
                **platform_options,
            )
            self._listener.start()

    def stop(self) -> None:
        self.disable_ready_mode()
        self.disable_drawing_mode()
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        with self._mode_lock:
            self._suppress_physical_right_release = False

    def enable_ready_mode(
        self,
        *,
        panel_hit_test: PanelHitTest,
        on_anchor: AnchorCallback,
        on_scale: ScaleCallback,
        on_rotation: RotationCallback,
        on_flip: FlipCallback,
    ) -> None:
        self.disable_drawing_mode()
        self._panel_hit_test = panel_hit_test
        self._on_anchor = on_anchor
        self._on_scale = on_scale
        self._on_rotation = on_rotation
        self._on_flip = on_flip
        self._ready_enabled = True

    def disable_ready_mode(self) -> None:
        self._ready_enabled = False
        self._right_dragging = False
        self._rotation_pivot = None

    def enable_drawing_mode(self, *, on_cancel: VoidCallback) -> None:
        """Listen for one physical right-button press while drawing."""
        self.disable_ready_mode()
        with self._mode_lock:
            self._on_cancel = on_cancel
            self._cancel_requested = False
            self._drawing_enabled = True

    def disable_drawing_mode(self) -> None:
        """Stop accepting cancel requests but keep a pending release suppressed."""
        with self._mode_lock:
            self._drawing_enabled = False
            self._on_cancel = None
            self._cancel_requested = False

    def _handle_move(self, x: float, y: float) -> None:
        with self._lock:
            self._latest_position = (float(x), float(y))
        if not self._ready_enabled or not self._right_dragging or self._rotation_pivot is None:
            return
        px, py = self._rotation_pivot
        angle = math.degrees(math.atan2(y - py, x - px))
        delta = angle - self._last_angle_deg
        if delta > 180:
            delta -= 360
        elif delta < -180:
            delta += 360
        if abs(delta) > 0.05 and self._on_rotation is not None:
            self._on_rotation(delta)
        self._last_angle_deg = angle

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
        if drawing_enabled:
            if button is mouse.Button.right and pressed and not injected:
                self._request_cancel_once()
            return

        if not self._ready_enabled:
            return
        if self._panel_hit_test is not None and self._panel_hit_test(x, y):
            return

        if button is mouse.Button.right:
            if pressed:
                self._right_dragging = True
                with self._lock:
                    self._rotation_pivot = self._latest_position
                px, py = self._rotation_pivot
                self._last_angle_deg = math.degrees(math.atan2(y - py, x - px))
            else:
                now = time.time()
                if now - self._last_right_release_time <= self._double_click_interval:
                    if self._on_flip is not None:
                        self._on_flip()
                self._last_right_release_time = now
                self._right_dragging = False
                self._rotation_pivot = None
            return

        if button is mouse.Button.left and not pressed:
            if self._on_anchor is not None:
                self._on_anchor((float(x), float(y)))

    def _handle_scroll(self, x: float, y: float, _dx: float, dy: float) -> None:
        if not self._ready_enabled or self._on_scale is None:
            return
        if self._panel_hit_test is not None and self._panel_hit_test(x, y):
            return
        factor = SCALE_WHEEL_FACTOR if dy > 0 else 1.0 / SCALE_WHEEL_FACTOR
        self._on_scale(factor)

    def _request_cancel_once(self) -> None:
        callback: Optional[VoidCallback]
        with self._mode_lock:
            if not self._drawing_enabled or self._cancel_requested:
                return
            self._cancel_requested = True
            callback = self._on_cancel
        if callback is not None:
            callback()

    def _handle_win32_event(self, msg: int, data) -> bool:
        """Suppress a physical cancel click while allowing injected drawing input."""
        if msg not in (_WM_RBUTTONDOWN, _WM_RBUTTONUP):
            return True
        if int(data.flags) & _LLMHF_INJECTED_MASK:
            return True

        if msg == _WM_RBUTTONDOWN:
            with self._mode_lock:
                if not self._drawing_enabled:
                    return True
                self._suppress_physical_right_release = True
            self._request_cancel_once()
            self._suppress_current_event()
            return False

        with self._mode_lock:
            should_suppress = self._suppress_physical_right_release
            self._suppress_physical_right_release = False
        if should_suppress:
            self._suppress_current_event()
            return False
        return True

    def _suppress_current_event(self) -> None:
        listener = self._listener
        if listener is not None:
            listener.suppress_event()
