from __future__ import annotations

import ctypes
import unittest
from unittest.mock import patch
import sys

from core import mouse_controller
from core.mouse_controller import (
    DRAW_INPUT_MARKER,
    InputInjectionError,
    MouseController,
    normalize_absolute_coordinate,
)


class MouseCoordinateTests(unittest.TestCase):
    def test_virtual_desktop_endpoints(self) -> None:
        self.assertEqual(normalize_absolute_coordinate(-1920, -1920, 3840), 0)
        self.assertEqual(normalize_absolute_coordinate(1919, -1920, 3840), 65535)

    def test_coordinates_are_clamped(self) -> None:
        self.assertEqual(normalize_absolute_coordinate(-3000, -1920, 3840), 0)
        self.assertEqual(normalize_absolute_coordinate(3000, -1920, 3840), 65535)

    @unittest.skipUnless(sys.platform == "win32", "Win32 SendInput test")
    @patch("core.mouse_controller._SEND_INPUT", return_value=0)
    def test_partial_send_input_raises_diagnostic_error(self, _send_input) -> None:
        with self.assertRaises(InputInjectionError) as raised:
            MouseController._send_win32(0x0001, operation="test move")
        self.assertEqual(raised.exception.failure_code, "input_injection_failed")

    @unittest.skipUnless(sys.platform == "win32", "Win32 SendInput test")
    def test_send_input_tags_events_for_router_filter(self) -> None:
        markers = []

        def capture(_count, pointer, _size):
            event = ctypes.cast(
                pointer,
                ctypes.POINTER(mouse_controller._INPUT),
            ).contents
            markers.append(event.value.mi.dwExtraInfo)
            return 1

        with patch("core.mouse_controller._SEND_INPUT", side_effect=capture):
            MouseController._send_win32(0x0008, operation="test right press")

        self.assertEqual(markers, [DRAW_INPUT_MARKER])


if __name__ == "__main__":
    unittest.main()
