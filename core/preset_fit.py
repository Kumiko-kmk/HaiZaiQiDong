"""Fit presets to an orientation-aware, screen-relative default size."""

from __future__ import annotations

from core.curves import flatten_stroke
from core.geometry import FLATNESS_PX, MAX_FLATTEN_STEP_PX
from core.screen_metrics import ScreenSize, get_screen_size
from presets.models import Preset

FIT_SCREEN_FRACTION = 1.0 / 4.0
MIN_ZOOM = 0.5
MAX_ZOOM = 2.0


def landscape_target_box(screen_w: int, screen_h: int) -> tuple[float, float]:
    """Target bounding box: one-quarter of screen with width greater than height."""
    long_side = max(screen_w, screen_h)
    short_side = min(screen_w, screen_h)
    return long_side * FIT_SCREEN_FRACTION, short_side * FIT_SCREEN_FRACTION


def preset_model_half_extents(preset: Preset) -> tuple[float, float]:
    """Axis-aligned half-extents of the preset in model space."""
    max_x = 0.0
    max_y = 0.0
    for stroke in preset.strokes:
        points = flatten_stroke(
            stroke.segments,
            FLATNESS_PX,
            max_step_px=MAX_FLATTEN_STEP_PX,
        )
        for x, y in points:
            max_x = max(max_x, abs(x))
            max_y = max(max_y, abs(y))
    return max(max_x, 1e-6), max(max_y, 1e-6)


def fit_scale_for_preset(
    preset: Preset,
    screen_w: int,
    screen_h: int,
) -> float:
    """Uniform scale into a landscape or portrait quarter-screen target box."""
    half_w, half_h = preset_model_half_extents(preset)
    target_w, target_h = landscape_target_box(screen_w, screen_h)
    if half_h > half_w:
        target_w, target_h = target_h, target_w
    return min(target_w / (2.0 * half_w), target_h / (2.0 * half_h))


def fit_scale_for_screen(preset: Preset, screen_size: ScreenSize | None = None) -> float:
    width, height = screen_size or get_screen_size()
    return fit_scale_for_preset(preset, width, height)
