from __future__ import annotations

import threading
import time
import unittest

from core.mouse_controller import MouseButton
from core.pixel_executor import execute_point_stream
from core.speed_tier import SpeedProfile


FAST_PROFILE = SpeedProfile(
    draw_speed_px_s=1_000_000,
    sample_spacing_px=3.0,
    max_event_rate_hz=1_000_000,
)


class FakeMouse:
    def __init__(self, *, fail_after_moves: int | None = None) -> None:
        self.events = []
        self.moves = 0
        self.fail_after_moves = fail_after_moves

    def ensure_pen_up(self, *, gap_sec: float = 0.0) -> None:
        self.events.append(("up", gap_sec))

    def move_absolute(self, x: float, y: float) -> None:
        self.moves += 1
        self.events.append(("move", x, y))
        if self.fail_after_moves is not None and self.moves >= self.fail_after_moves:
            raise RuntimeError("move failed")

    def press(self, button: MouseButton) -> None:
        self.events.append(("press", button))

    def release(self, button: MouseButton | None = None) -> None:
        self.events.append(("release", button))

    def best_effort_release_all(self) -> None:
        self.events.append(("release_all",))


class PointExecutorTests(unittest.TestCase):
    def test_single_point_is_drawn_as_a_click(self) -> None:
        mouse = FakeMouse()

        count = execute_point_stream(
            mouse,
            [(12, 34)],
            MouseButton.LEFT,
            FAST_PROFILE,
            pen_up_gap_sec=0,
        )

        self.assertEqual(count, 1)
        self.assertEqual(
            [event[0] for event in mouse.events],
            ["up", "move", "press", "release", "release_all"],
        )

    def test_draw_order_and_event_count(self) -> None:
        mouse = FakeMouse()
        count = execute_point_stream(
            mouse,
            [(0, 0), (3, 0), (6, 0)],
            MouseButton.LEFT,
            FAST_PROFILE,
            pen_up_gap_sec=0,
        )

        self.assertEqual(count, 3)
        self.assertEqual(
            [event[0] for event in mouse.events],
            ["up", "move", "press", "move", "move", "release", "release_all"],
        )

    def test_failure_always_releases_button(self) -> None:
        mouse = FakeMouse(fail_after_moves=2)
        with self.assertRaisesRegex(RuntimeError, "move failed"):
            execute_point_stream(
                mouse,
                [(0, 0), (3, 0), (6, 0)],
                MouseButton.RIGHT,
                FAST_PROFILE,
                pen_up_gap_sec=0,
            )

        self.assertIn(("release", MouseButton.RIGHT), mouse.events)
        self.assertIn(("release_all",), mouse.events)

    def test_cancel_interrupts_a_long_pacing_wait(self) -> None:
        mouse = FakeMouse()
        abort = threading.Event()
        slow_profile = SpeedProfile(1.0, 3.0, 240.0)
        worker = threading.Thread(
            target=execute_point_stream,
            args=(mouse, [(0, 0), (100, 0)], MouseButton.LEFT, slow_profile),
            kwargs={"pen_up_gap_sec": 0, "abort_event": abort},
        )
        worker.start()
        time.sleep(0.01)
        started = time.perf_counter()
        abort.set()
        worker.join(0.2)

        self.assertFalse(worker.is_alive())
        self.assertLess(time.perf_counter() - started, 0.1)
        self.assertIn(("release", MouseButton.LEFT), mouse.events)


if __name__ == "__main__":
    unittest.main()
