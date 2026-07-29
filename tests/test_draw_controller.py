from __future__ import annotations

import threading
import unittest

from core.draw_controller import DrawController, DrawOutcome, DrawSession
from core.mouse_controller import InputInjectionError
from core.stroke_executor import DrawSettings
from core.transform import TransformState
from tests.support import RecordingMouse, make_preset


class FailingDrawer:
    def __init__(self) -> None:
        self._mouse = RecordingMouse()

    def draw_single_stroke(self, *_args, **_kwargs) -> int:
        raise InputInjectionError("test move", actual=0)


class DrawControllerTests(unittest.TestCase):
    def test_input_failure_is_returned_and_recorded(self) -> None:
        preset = make_preset()
        controller = DrawController(drawer=FailingDrawer())
        completed = threading.Event()
        results = []

        with self.assertLogs("core.draw_controller", level="ERROR"):
            self.assertTrue(
                controller.start(
                    DrawSession(preset, (0, 0), DrawSettings(TransformState())),
                    on_finish=lambda result: (results.append(result), completed.set()),
                )
            )
            self.assertTrue(completed.wait(1.0))

        self.assertEqual(results[0].outcome, DrawOutcome.FAILED)
        self.assertEqual(results[0].failure_code, "input_injection_failed")
        self.assertIn("权限", results[0].message)
        history = controller.history.list_entries()
        self.assertEqual(history[0].failure_code, "input_injection_failed")
        self.assertEqual(history[0].draw_button, "right")


if __name__ == "__main__":
    unittest.main()
