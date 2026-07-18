from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.draw_controller import DrawOutcome, DrawResult
from core.mouse_controller import MouseButton
from core.stroke_executor import DrawSettings
from core.transform import TransformState
from gui.app_service import AppService
from gui.state import AppState


class AppServiceTerminationTests(unittest.TestCase):
    def _make_service(self, *, start_result: bool = True):
        registry = Mock()
        router = Mock()
        controller = Mock()
        controller.start.return_value = start_result
        controller.history.list_entries.return_value = []
        overlay = Mock()

        with (
            patch("gui.app_service.get_registry", return_value=registry),
            patch("gui.app_service.InputRouter", return_value=router),
            patch("gui.app_service.DrawController", return_value=controller),
            patch("gui.app_service.OverlayBridge", return_value=overlay),
        ):
            service = AppService()

        preset = Mock()
        preset.id = "test"
        preset.name = "Test"
        service.selected_preset = preset
        service._build_settings = Mock(
            return_value=DrawSettings(
                transform=TransformState(),
                button=MouseButton.RIGHT,
            )
        )
        service._reset_transform = Mock()
        service.app_state = AppState.READY
        return service, router, controller

    def test_physical_cancel_waits_for_draw_finish_before_idle(self) -> None:
        service, router, controller = self._make_service()
        observed_states = []
        service.set_ui_notifier(lambda state: observed_states.append(state["appState"]))

        service._start_draw((10.0, 20.0))
        cancel_callback = router.enable_drawing_mode.call_args.kwargs["on_cancel"]
        finish_callback = controller.start.call_args.kwargs["on_finish"]

        cancel_callback()
        cancel_callback()

        self.assertEqual(service.app_state, AppState.TERMINATING)
        controller.cancel.assert_called_once_with()
        self.assertEqual(observed_states, ["drawing", "terminating"])

        finish_callback(DrawResult(DrawOutcome.CANCELLED, 0.1, message="绘制已取消。"))

        self.assertEqual(service.app_state, AppState.IDLE)
        router.disable_drawing_mode.assert_called_once_with()
        self.assertEqual(observed_states, ["drawing", "terminating", "idle"])

    def test_normal_finish_returns_directly_to_idle(self) -> None:
        service, router, controller = self._make_service()
        observed_states = []
        service.set_ui_notifier(lambda state: observed_states.append(state["appState"]))

        service._start_draw((10.0, 20.0))
        finish_callback = controller.start.call_args.kwargs["on_finish"]
        finish_callback(DrawResult(DrawOutcome.SUCCESS, 0.1, message="绘制完成。"))

        self.assertEqual(service.app_state, AppState.IDLE)
        controller.cancel.assert_not_called()
        self.assertEqual(observed_states, ["drawing", "idle"])

    def test_failure_returns_to_idle_and_notifies_message(self) -> None:
        service, _router, controller = self._make_service()
        states = []
        service.set_ui_notifier(lambda state: states.append(state))

        service._start_draw((10.0, 20.0))
        finish_callback = controller.start.call_args.kwargs["on_finish"]
        finish_callback(
            DrawResult(
                DrawOutcome.FAILED,
                0.1,
                failure_code="input_injection_failed",
                message="鼠标输入注入失败。",
            )
        )

        self.assertEqual(service.app_state, AppState.IDLE)
        self.assertEqual(states[-1]["message"], "鼠标输入注入失败。")

    def test_start_failure_rolls_back_to_idle(self) -> None:
        service, router, _controller = self._make_service(start_result=False)

        service._start_draw((10.0, 20.0))

        self.assertEqual(service.app_state, AppState.IDLE)
        router.disable_drawing_mode.assert_called_once_with()

    def test_terminating_state_disables_cards(self) -> None:
        service, _router, _controller = self._make_service()
        service.app_state = AppState.TERMINATING

        state = service.get_state()

        self.assertEqual(state["appState"], "terminating")
        self.assertFalse(state["cardsEnabled"])

    def test_draw_button_setting_controls_next_draw_session(self) -> None:
        service, _router, _controller = self._make_service()
        service._build_settings = AppService._build_settings.__get__(service, AppService)

        state = service.set_draw_button("left")
        settings = service._build_settings()

        self.assertEqual(state["drawButton"], "left")
        self.assertEqual(settings.button, MouseButton.LEFT)

    def test_invalid_draw_button_is_rejected(self) -> None:
        service, _router, _controller = self._make_service()

        state = service.set_draw_button("middle")

        self.assertEqual(state["drawButton"], "right")
        self.assertEqual(state["message"], "无效的绘制方式。")

    def test_history_state_includes_button_and_event_details(self) -> None:
        service, _router, controller = self._make_service()
        controller.history.list_entries.return_value = [
            SimpleNamespace(
                timestamp=datetime(2026, 7, 14, 10, 30, 15),
                preset_name="Test",
                anchor=(320.0, 240.0),
                scale=1.25,
                rotation_deg=15.0,
                flip_label="水平",
                draw_button="left",
                status="完成",
                duration_sec=2.4,
                failure_code=None,
                message="绘制完成。",
                event_count=128,
            )
        ]

        entry = service.get_state()["history"][0]

        self.assertNotIn("anchor", entry)
        self.assertNotIn("rotation", entry)
        self.assertNotIn("flip", entry)
        self.assertEqual(entry["drawButton"], "left")
        self.assertEqual(entry["eventCount"], 128)
        self.assertEqual(entry["time"], "07-14 10:30")
        self.assertEqual(entry["timestamp"], "2026-07-14T10:30:15")


if __name__ == "__main__":
    unittest.main()
