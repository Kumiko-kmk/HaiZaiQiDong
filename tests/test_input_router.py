from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from pynput import mouse

from core.input_router import InputRouter


class InputRouterDrawingModeTests(unittest.TestCase):
    def test_injected_right_click_does_not_cancel(self) -> None:
        on_cancel = Mock()
        router = InputRouter()
        router.enable_drawing_mode(on_cancel=on_cancel)

        router._handle_click(10, 20, mouse.Button.right, True, True)
        router._handle_click(10, 20, mouse.Button.right, False, True)

        on_cancel.assert_not_called()

    def test_physical_right_press_cancels_only_once(self) -> None:
        on_cancel = Mock()
        router = InputRouter()
        router.enable_drawing_mode(on_cancel=on_cancel)

        router._handle_click(10, 20, mouse.Button.right, True, False)
        router._handle_click(10, 20, mouse.Button.right, True, False)
        router._handle_click(10, 20, mouse.Button.right, False, False)

        on_cancel.assert_called_once_with()

    def test_win32_filter_suppresses_press_and_pending_release(self) -> None:
        on_cancel = Mock()
        listener = Mock()
        router = InputRouter()
        router._listener = listener
        router.enable_drawing_mode(on_cancel=on_cancel)

        injected = SimpleNamespace(flags=0x00000001)
        physical = SimpleNamespace(flags=0)

        self.assertTrue(router._handle_win32_event(0x0204, injected))
        self.assertFalse(router._handle_win32_event(0x0204, physical))
        on_cancel.assert_called_once_with()
        listener.suppress_event.assert_called_once_with()

        router.disable_drawing_mode()
        self.assertFalse(router._handle_win32_event(0x0205, physical))
        self.assertEqual(listener.suppress_event.call_count, 2)
        self.assertTrue(router._handle_win32_event(0x0205, physical))


class InputRouterReadyModeTests(unittest.TestCase):
    def test_ready_controls_remain_available(self) -> None:
        on_anchor = Mock()
        on_scale = Mock()
        on_rotation = Mock()
        on_flip = Mock()
        router = InputRouter()
        router.enable_ready_mode(
            panel_hit_test=lambda _x, _y: False,
            on_anchor=on_anchor,
            on_scale=on_scale,
            on_rotation=on_rotation,
            on_flip=on_flip,
        )

        router._handle_click(30, 40, mouse.Button.left, False)
        router._handle_scroll(30, 40, 0, 1)
        router._handle_click(0, 0, mouse.Button.right, True)
        router._handle_move(0, 10)
        router._handle_click(0, 10, mouse.Button.right, False)
        router._handle_click(0, 10, mouse.Button.right, True)
        router._handle_click(0, 10, mouse.Button.right, False)

        on_anchor.assert_called_once_with((30.0, 40.0))
        on_scale.assert_called_once()
        on_rotation.assert_called()
        on_flip.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
