"""Execute preset strokes through the streaming path engine."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Tuple

from core.draw_path import iter_stroke_points
from core.geometry import FLATNESS_PX, MAX_FLATTEN_STEP_PX
from core.mouse_controller import MouseButton, MouseController
from core.pixel_executor import execute_point_stream
from core.speed_tier import (
    DEFAULT_SPEED_PROFILE,
    PEN_UP_GAP_SEC,
    SpeedProfile,
)
from core.transform import TransformState
from presets.models import Preset

ScreenPoint = Tuple[float, float]


@dataclass
class DrawSettings:
    transform: TransformState
    button: MouseButton = MouseButton.RIGHT
    profile: SpeedProfile = DEFAULT_SPEED_PROFILE

    @property
    def stroke_pause_ms(self) -> int:
        return self.profile.stroke_pause_ms

    @property
    def flatness_px(self) -> float:
        return FLATNESS_PX

    @property
    def max_flatten_step_px(self) -> float:
        return MAX_FLATTEN_STEP_PX

    @property
    def pen_up_gap_sec(self) -> float:
        return PEN_UP_GAP_SEC


class PathDrawer:
    def __init__(self, mouse: MouseController | None = None) -> None:
        self._mouse = mouse or MouseController()

    def draw_single_stroke(
        self,
        preset: Preset,
        anchor: ScreenPoint,
        settings: DrawSettings,
        stroke_index: int,
        *,
        abort_event: Event | None = None,
    ) -> int:
        return self.draw_preset(
            preset,
            anchor,
            settings,
            abort_event=abort_event,
            start_stroke_index=stroke_index,
            end_stroke_index=stroke_index + 1,
        )

    def draw_preset(
        self,
        preset: Preset,
        anchor: ScreenPoint,
        settings: DrawSettings,
        *,
        abort_event: Event | None = None,
        start_stroke_index: int = 0,
        end_stroke_index: int | None = None,
    ) -> int:
        total = len(preset.strokes)
        event_count = 0
        if end_stroke_index is None:
            end_stroke_index = total
        for index, stroke in enumerate(preset.strokes):
            if index < start_stroke_index:
                continue
            if index >= end_stroke_index:
                break
            if abort_event is not None and abort_event.is_set():
                self._mouse.best_effort_release_all()
                return event_count

            points = iter_stroke_points(
                stroke.segments,
                anchor,
                settings.transform,
                settings.flatness_px,
                sample_spacing_px=settings.profile.sample_spacing_px,
                max_step_px=settings.max_flatten_step_px,
                abort_event=abort_event,
            )
            event_count += execute_point_stream(
                self._mouse,
                points,
                settings.button,
                settings.profile,
                pen_up_gap_sec=settings.pen_up_gap_sec,
                abort_event=abort_event,
            )

            if abort_event is not None and abort_event.is_set():
                self._mouse.best_effort_release_all()
                return event_count

        return event_count
