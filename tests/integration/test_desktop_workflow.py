from __future__ import annotations

import threading
import unittest
from unittest.mock import Mock, patch

from pynput import mouse as pynput_mouse

from core.draw_controller import DrawController
from core.history import HistoryStore
from core.input_router import InputRouter
from core.mouse_controller import MouseButton
from core.stroke_executor import PathDrawer
from gui.app_service import AppService
from gui.state import AppState
from tests.support import RecordingMouse, RegistryTestCase, make_preset


class DesktopWorkflowIntegrationTests(RegistryTestCase):
    def test_ready_click_draws_and_records_history_without_native_hooks(self) -> None:
        preset = make_preset(points=((0.0, 0.0), (6.0, 0.0)))
        registry = Mock()
        registry.list_presets.return_value = [preset]
        registry.preview_path.return_value = None
        router = InputRouter()
        overlay = Mock()
        recording_mouse = RecordingMouse()
        history = HistoryStore(log_path=self.root / "history.jsonl")
        controller = DrawController(
            drawer=PathDrawer(recording_mouse),
            history=history,
        )

        with (
            patch("gui.app_service.get_registry", return_value=registry),
            patch("gui.app_service.InputRouter", return_value=router),
            patch("gui.app_service.DrawController", return_value=controller),
            patch("gui.app_service.OverlayBridge", return_value=overlay),
            patch(
                "gui.app_service.history_log_path",
                return_value=self.root / "unused-history.jsonl",
            ),
        ):
            service = AppService()

        completed = threading.Event()
        observed_states: list[str] = []

        def observe(state: dict) -> None:
            observed_states.append(state["appState"])
            if state["appState"] == "idle" and state["history"]:
                completed.set()

        service.set_window_bounds_provider(lambda: (0, 0, 100, 100))
        service.set_ui_notifier(observe)
        service.refresh_presets()
        service.select_preset(preset.id)

        ready_state = service.confirm_card()
        self.assertEqual(ready_state["appState"], "ready")

        router._handle_click(
            320.0,
            240.0,
            pynput_mouse.Button.left,
            False,
        )

        self.assertTrue(completed.wait(1.0), "drawing workflow did not finish")
        self.assertEqual(service.app_state, AppState.IDLE)
        self.assertIn("ready", observed_states)
        self.assertIn("drawing", observed_states)
        self.assertEqual(observed_states[-1], "idle")
        overlay.show.assert_called_once()
        overlay.hide.assert_called_once()

        entries = history.list_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].preset_name, preset.name)
        self.assertEqual(entries[0].anchor, (320.0, 240.0))
        self.assertGreater(entries[0].event_count, 0)
        self.assertIn(("press", MouseButton.RIGHT), recording_mouse.events)
        self.assertIn(("release", MouseButton.RIGHT), recording_mouse.events)
        self.assertTrue((self.root / "history.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
