from __future__ import annotations

import unittest
from unittest.mock import patch
import sys

from core.mouse_controller import InputInjectionError, MouseController, normalize_absolute_coordinate


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


if __name__ == "__main__":
    unittest.main()
