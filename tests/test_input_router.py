from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pynput import keyboard, mouse

from core.input_router import InputRouter
from core.transform import ROTATION_STEP_DEG, SCALE_STEP_FACTOR


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
        router._mouse_listener = listener
        router.enable_drawing_mode(on_cancel=on_cancel)

        injected = SimpleNamespace(flags=0x00000001)
        physical = SimpleNamespace(flags=0)

        self.assertTrue(router._handle_win32_mouse_event(0x0204, injected))
        self.assertFalse(router._handle_win32_mouse_event(0x0204, physical))
        on_cancel.assert_called_once_with()
        listener.suppress_event.assert_called_once_with()

        router.disable_drawing_mode()
        self.assertFalse(router._handle_win32_mouse_event(0x0205, physical))
        self.assertEqual(listener.suppress_event.call_count, 2)
        self.assertTrue(router._handle_win32_mouse_event(0x0205, physical))


class InputRouterReadyModeTests(unittest.TestCase):
    def _enable_ready(self, router: InputRouter, **overrides):
        callbacks = {
            "panel_hit_test": lambda _x, _y: False,
            "on_anchor": Mock(),
            "on_scale": Mock(),
            "on_rotation": Mock(),
            "on_cancel": Mock(),
        }
        callbacks.update(overrides)
        router.enable_ready_mode(**callbacks)
        return callbacks

    def test_wasd_controls_and_left_anchor(self) -> None:
        router = InputRouter()
        callbacks = self._enable_ready(router)

        router._handle_click(30, 40, mouse.Button.left, False)
        for char in "wsadq":
            router._handle_key_press(keyboard.KeyCode.from_char(char))

        callbacks["on_anchor"].assert_called_once_with((30.0, 40.0))
        self.assertEqual(
            [call.args[0] for call in callbacks["on_scale"].call_args_list],
            [SCALE_STEP_FACTOR, 1.0 / SCALE_STEP_FACTOR],
        )
        self.assertEqual(
            [call.args[0] for call in callbacks["on_rotation"].call_args_list],
            [-ROTATION_STEP_DEG, ROTATION_STEP_DEG],
        )

    def test_right_click_cancels_globally_only_once(self) -> None:
        router = InputRouter()
        callbacks = self._enable_ready(router, panel_hit_test=lambda _x, _y: True)

        router._handle_click(10, 20, mouse.Button.right, True)
        router._handle_click(10, 20, mouse.Button.right, True)
        router._handle_click(10, 20, mouse.Button.right, False)

        callbacks["on_cancel"].assert_called_once_with()
        callbacks["on_anchor"].assert_not_called()

    def test_win32_right_click_suppresses_press_and_release(self) -> None:
        router = InputRouter()
        listener = Mock()
        router._mouse_listener = listener
        callbacks = self._enable_ready(router, panel_hit_test=lambda _x, _y: True)
        physical = SimpleNamespace(flags=0)

        self.assertFalse(router._handle_win32_mouse_event(0x0204, physical))
        callbacks["on_cancel"].assert_called_once_with()
        router.disable_ready_mode()
        self.assertFalse(router._handle_win32_mouse_event(0x0205, physical))
        self.assertEqual(listener.suppress_event.call_count, 2)

    def test_win32_wasd_is_repeated_and_suppressed_but_other_keys_pass(self) -> None:
        router = InputRouter()
        listener = Mock()
        router._keyboard_listener = listener
        callbacks = self._enable_ready(router)
        w_key = SimpleNamespace(flags=0, vkCode=ord("W"))
        q_key = SimpleNamespace(flags=0, vkCode=ord("Q"))
        injected_w = SimpleNamespace(flags=0x10, vkCode=ord("W"))

        self.assertTrue(router._handle_win32_keyboard_event(0x0100, q_key))
        self.assertTrue(router._handle_win32_keyboard_event(0x0100, injected_w))
        self.assertFalse(router._handle_win32_keyboard_event(0x0100, w_key))
        self.assertFalse(router._handle_win32_keyboard_event(0x0100, w_key))
        self.assertEqual(callbacks["on_scale"].call_count, 2)

        router.disable_ready_mode()
        self.assertFalse(router._handle_win32_keyboard_event(0x0101, w_key))
        self.assertTrue(router._handle_win32_keyboard_event(0x0101, w_key))
        self.assertEqual(listener.suppress_event.call_count, 3)

    def test_start_and_stop_manage_mouse_and_keyboard_listeners(self) -> None:
        mouse_listener = Mock()
        keyboard_listener = Mock()
        with (
            patch("core.input_router.mouse.Listener", return_value=mouse_listener),
            patch("core.input_router.keyboard.Listener", return_value=keyboard_listener),
        ):
            router = InputRouter()
            router.start_base()
            router.stop()

        mouse_listener.start.assert_called_once_with()
        keyboard_listener.start.assert_called_once_with()
        mouse_listener.stop.assert_called_once_with()
        keyboard_listener.stop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
