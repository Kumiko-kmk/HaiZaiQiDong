"""Cancellation-aware, deadline-based cursor pacing."""

from __future__ import annotations

import time
from threading import Event

def wait_sec(duration: float, abort_event: Event | None = None) -> bool:
    """Wait without busy-spinning; return ``False`` when cancelled."""
    if duration <= 0:
        return abort_event is None or not abort_event.is_set()
    if abort_event is not None:
        return not abort_event.wait(duration)
    time.sleep(duration)
    return True


class DeadlinePacer:
    """Schedule moves by travelled distance while correcting clock drift."""

    def __init__(
        self,
        speed_px_s: float,
        max_event_rate_hz: float,
        *,
        clock=time.perf_counter,
    ) -> None:
        if speed_px_s <= 0 or max_event_rate_hz <= 0:
            raise ValueError("pacing limits must be positive")
        self._speed_px_s = speed_px_s
        self._minimum_interval = 1.0 / max_event_rate_hz
        self._clock = clock
        self._deadline = clock()

    def wait_for_distance(
        self,
        distance_px: float,
        *,
        abort_event: Event | None = None,
    ) -> bool:
        interval = max(max(0.0, distance_px) / self._speed_px_s, self._minimum_interval)
        now = self._clock()
        if self._deadline < now - 0.25:
            self._deadline = now
        self._deadline += interval
        return wait_sec(max(0.0, self._deadline - now), abort_event)


def estimate_paced_sec(
    profile,
    *,
    path_length_px: float,
    event_count: int,
    stroke_count: int,
) -> float:
    """Estimate duration from distance and the event-rate ceiling."""
    from core.speed_tier import SpeedProfile

    if not isinstance(profile, SpeedProfile):
        raise TypeError("profile must be SpeedProfile")

    distance_sec = max(0.0, path_length_px) / profile.draw_speed_px_s
    rate_sec = max(0, event_count) / profile.max_event_rate_hz
    pen_gap = stroke_count * 2 * 0.002
    pause_sec = max(0, stroke_count - 1) * profile.stroke_pause_ms / 1000.0
    return max(distance_sec, rate_sec) + pen_gap + pause_sec
