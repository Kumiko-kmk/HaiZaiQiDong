"""2D transform for sketch presets centered at origin."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Tuple

from core.preset_fit import MAX_ZOOM, MIN_ZOOM, fit_scale_for_screen
from presets.models import Preset

Point = Tuple[float, float]

SCALE_STEP_FACTOR = 1.1
ROTATION_STEP_DEG = 5.0
SCALE_EPSILON = 1e-6


@dataclass
class TransformState:
    fit_scale: float = 1.0
    zoom: float = 1.0
    rotation_deg: float = 0.0
    flip_h: bool = False
    flip_v: bool = False

    @property
    def scale(self) -> float:
        return self.fit_scale * self.zoom

    def clamp_zoom(self) -> None:
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom))

    @classmethod
    def for_preset(cls, preset: Preset) -> TransformState:
        return cls(fit_scale=fit_scale_for_screen(preset), zoom=1.0)

    @classmethod
    def with_scale(cls, scale: float) -> TransformState:
        """Absolute scale at zoom=1 (tests and helpers)."""
        return cls(fit_scale=scale, zoom=1.0)

    def flip_label(self) -> str:
        if self.flip_h and self.flip_v:
            return "水平+垂直"
        if self.flip_h:
            return "水平"
        if self.flip_v:
            return "垂直"
        return "无"

    def cycle_flip(self) -> None:
        """Alternate: none -> horizontal -> vertical -> none."""
        if not self.flip_h and not self.flip_v:
            self.flip_h = True
            self.flip_v = False
        elif self.flip_h and not self.flip_v:
            self.flip_h = False
            self.flip_v = True
        else:
            self.flip_h = False
            self.flip_v = False


def transform_point(point: Point, state: TransformState) -> Point:
    x, y = point
    if state.flip_h:
        x = -x
    if state.flip_v:
        y = -y
    x *= state.scale
    y *= state.scale
    if state.rotation_deg:
        radians = math.radians(state.rotation_deg)
        cos_r = math.cos(radians)
        sin_r = math.sin(radians)
        x, y = x * cos_r - y * sin_r, x * sin_r + y * cos_r
    return x, y


def transform_points(points: Iterable[Point], state: TransformState) -> List[Point]:
    return [transform_point(point, state) for point in points]


def to_screen_points(
    relative_points: Iterable[Point],
    anchor: Point,
    state: TransformState,
) -> List[Point]:
    ax, ay = anchor
    return [
        (ax + transform_point(point, state)[0], ay + transform_point(point, state)[1])
        for point in relative_points
    ]
