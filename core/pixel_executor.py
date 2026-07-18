"""Stream screen-space points through checked absolute mouse input."""

from __future__ import annotations

import itertools
import math
from threading import Event
from typing import Iterable, Sequence

from core.mouse_controller import MouseButton, MouseController
from core.pacing import DeadlinePacer, wait_sec
from core.pixel_path import Pixel
from core.speed_tier import SpeedProfile
from core.transform import Point


def execute_point_stream(
    mouse: MouseController,
    points: Iterable[Point],
    button: MouseButton,
    profile: SpeedProfile,
    *,
    pen_up_gap_sec: float = 0.002,
    abort_event: Event | None = None,
) -> int:
    """Draw one stroke and return the number of absolute move events sent."""
    iterator = iter(points)
    try:
        first = next(iterator)
    except StopIteration:
        return 0
    try:
        second = next(iterator)
    except StopIteration:
        second = None

    if abort_event is not None and abort_event.is_set():
        return 0

    mouse.ensure_pen_up(gap_sec=pen_up_gap_sec)
    if abort_event is not None and abort_event.is_set():
        return 0
    mouse.move_absolute(first[0], first[1])
    event_count = 1
    if abort_event is not None and abort_event.is_set():
        return event_count

    mouse.press(button)
    previous = first
    pacer = DeadlinePacer(profile.draw_speed_px_s, profile.max_event_rate_hz)
    try:
        remaining_points = iterator if second is None else itertools.chain((second,), iterator)
        for point in remaining_points:
            if abort_event is not None and abort_event.is_set():
                break
            distance = math.dist(previous, point)
            if distance <= 1e-7:
                continue
            if not pacer.wait_for_distance(distance, abort_event=abort_event):
                break
            if abort_event is not None and abort_event.is_set():
                break
            mouse.move_absolute(point[0], point[1])
            event_count += 1
            previous = point
    finally:
        try:
            mouse.release(button)
        finally:
            mouse.best_effort_release_all()
            wait_sec(pen_up_gap_sec)
    return event_count


def execute_pixel_path(
    mouse: MouseController,
    pixels: Sequence[Pixel],
    button: MouseButton,
    profile: SpeedProfile,
    *,
    pen_up_gap_sec: float = 0.002,
    abort_event: Event | None = None,
) -> int:
    """Compatibility wrapper for legacy callers with an existing point list."""
    return execute_point_stream(
        mouse,
        pixels,
        button,
        profile,
        pen_up_gap_sec=pen_up_gap_sec,
        abort_event=abort_event,
    )
