"""Scale-invariant stroke path building in screen space."""

from __future__ import annotations

import math
from threading import Event
from typing import Iterable, Iterator, List, Sequence

from core.curves import flatten_stroke
from core.curves.flatten import flatten_segment
from core.curves.segments import CurveSegment, MoveSegment
from core.geometry import FLATNESS_PX, MAX_FLATTEN_STEP_PX
from core.pixel_path import Pixel, build_pixel_path
from core.preset_fit import MAX_ZOOM, fit_scale_for_screen
from core.transform import (
    SCALE_EPSILON,
    Point,
    TransformState,
    to_screen_points,
    transform_point,
)
from presets.models import Preset

MAX_PIXEL_GAP = math.sqrt(2) + 1e-6
PREVIEW_MIN_HALF_EXTENT = 60.0
PREVIEW_MARGIN_PX = 16.0
_POINT_EPSILON = 1e-7


def model_flatness_for_screen(flatness_px: float, transform: TransformState) -> float:
    """Convert screen-space flatness tolerance to model-space for flattening."""
    return flatness_px / max(transform.scale, SCALE_EPSILON)


def model_max_step_for_screen(max_step_px: float, transform: TransformState) -> float:
    return max_step_px / max(transform.scale, SCALE_EPSILON)


def build_stroke_screen_points(
    segments: Sequence[CurveSegment],
    anchor: Point,
    transform: TransformState,
    flatness_px: float,
    *,
    max_step_px: float = MAX_FLATTEN_STEP_PX,
) -> List[Point]:
    """Flatten and transform a stroke into screen-space float points."""
    model_flatness = model_flatness_for_screen(flatness_px, transform)
    model_max_step = model_max_step_for_screen(max_step_px, transform)
    dense = flatten_stroke(
        segments,
        model_flatness,
        max_step_px=model_max_step,
    )
    return to_screen_points(dense, anchor, transform)


def iter_stroke_screen_points(
    segments: Sequence[CurveSegment],
    anchor: Point,
    transform: TransformState,
    flatness_px: float,
    *,
    max_step_px: float = MAX_FLATTEN_STEP_PX,
    abort_event: Event | None = None,
) -> Iterator[Point]:
    """Flatten one curve segment at a time and yield screen-space points."""
    if flatness_px <= 0 or max_step_px <= 0:
        raise ValueError("flattening tolerances must be positive")

    model_flatness = model_flatness_for_screen(flatness_px, transform)
    model_max_step = model_max_step_for_screen(max_step_px, transform)
    pen: Point | None = None
    emitted = False
    last_screen: Point | None = None
    ax, ay = anchor

    for segment in segments:
        if abort_event is not None and abort_event.is_set():
            return
        if isinstance(segment, MoveSegment):
            pen = segment.to
            if emitted:
                continue
            model_points = [segment.to]
        else:
            model_points = flatten_segment(
                segment,
                pen,
                flatness_px=model_flatness,
                max_step_px=model_max_step,
                include_start=not emitted,
            )
            if model_points:
                pen = model_points[-1]

        for point in model_points:
            if abort_event is not None and abort_event.is_set():
                return
            tx, ty = transform_point(point, transform)
            screen = (ax + tx, ay + ty)
            if last_screen is not None and math.dist(last_screen, screen) <= _POINT_EPSILON:
                continue
            yield screen
            emitted = True
            last_screen = screen


def iter_resampled_points(
    points: Iterable[Point],
    spacing_px: float,
    *,
    max_error_px: float = 1.0,
) -> Iterator[Point]:
    """Yield global arc-length samples, adding corners only when needed."""
    if spacing_px <= 0:
        raise ValueError("spacing_px must be positive")
    if max_error_px <= 0:
        raise ValueError("max_error_px must be positive")

    iterator = iter(points)
    try:
        first = next(iterator)
    except StopIteration:
        return

    yield first
    last_emitted = first
    segment_start = first
    distance_since_emit = 0.0
    buffered_vertices: List[Point] = []

    for segment_end in iterator:
        remaining = math.dist(segment_start, segment_end)
        if remaining <= _POINT_EPSILON:
            segment_start = segment_end
            continue

        while distance_since_emit + remaining >= spacing_px - _POINT_EPSILON:
            needed = spacing_px - distance_since_emit
            ratio = min(1.0, max(0.0, needed / remaining))
            candidate = (
                segment_start[0] + (segment_end[0] - segment_start[0]) * ratio,
                segment_start[1] + (segment_end[1] - segment_start[1]) * ratio,
            )
            interval = _simplify_interval(
                [last_emitted, *buffered_vertices, candidate],
                max_error_px,
            )
            for point in interval[1:]:
                if math.dist(last_emitted, point) > _POINT_EPSILON:
                    yield point
                    last_emitted = point
            buffered_vertices.clear()
            segment_start = candidate
            remaining = math.dist(segment_start, segment_end)
            distance_since_emit = 0.0
            if remaining <= _POINT_EPSILON:
                break

        distance_since_emit += remaining
        buffered_vertices.append(segment_end)
        segment_start = segment_end

    if buffered_vertices:
        interval = _simplify_interval([last_emitted, *buffered_vertices], max_error_px)
        for point in interval[1:]:
            if math.dist(last_emitted, point) > _POINT_EPSILON:
                yield point
                last_emitted = point


def _point_to_chord_distance(point: Point, start: Point, end: Point) -> float:
    chord = math.dist(start, end)
    if chord <= _POINT_EPSILON:
        return math.dist(point, start)
    cross = abs(
        (end[0] - start[0]) * (start[1] - point[1])
        - (start[0] - point[0]) * (end[1] - start[1])
    )
    return cross / chord


def _simplify_interval(points: Sequence[Point], tolerance_px: float) -> List[Point]:
    """Small-window RDP: preserve corners without materialising a full stroke."""
    if len(points) <= 2:
        return list(points)
    distances = [
        _point_to_chord_distance(point, points[0], points[-1])
        for point in points[1:-1]
    ]
    if not distances:
        return [points[0], points[-1]]
    max_distance = max(distances)
    if max_distance <= tolerance_px:
        return [points[0], points[-1]]
    split = distances.index(max_distance) + 1
    left = _simplify_interval(points[: split + 1], tolerance_px)
    right = _simplify_interval(points[split:], tolerance_px)
    return left[:-1] + right


def iter_stroke_points(
    segments: Sequence[CurveSegment],
    anchor: Point,
    transform: TransformState,
    flatness_px: float,
    *,
    sample_spacing_px: float = 3.0,
    max_step_px: float = MAX_FLATTEN_STEP_PX,
    abort_event: Event | None = None,
) -> Iterator[Point]:
    """Stream an adaptively flattened, arc-length-resampled stroke."""
    screen_points = iter_stroke_screen_points(
        segments,
        anchor,
        transform,
        flatness_px,
        max_step_px=max_step_px,
        abort_event=abort_event,
    )
    yield from iter_resampled_points(screen_points, sample_spacing_px)


def build_stroke_path(
    segments: Sequence[CurveSegment],
    anchor: Point,
    transform: TransformState,
    flatness_px: float,
    *,
    max_step_px: float = MAX_FLATTEN_STEP_PX,
) -> List[Pixel]:
    """Build a continuous integer pixel path with scale-invariant flatness."""
    screen_points = build_stroke_screen_points(
        segments,
        anchor,
        transform,
        flatness_px,
        max_step_px=max_step_px,
    )
    return build_pixel_path(screen_points)


def max_screen_gap(screen_points: Sequence[Point]) -> float:
    if len(screen_points) < 2:
        return 0.0
    return max(
        math.hypot(b[0] - a[0], b[1] - a[1])
        for a, b in zip(screen_points, screen_points[1:])
    )


def max_pixel_gap(pixels: Sequence[Pixel]) -> float:
    if len(pixels) < 2:
        return 0.0
    return max(
        math.hypot(b[0] - a[0], b[1] - a[1])
        for a, b in zip(pixels, pixels[1:])
    )


def validate_pixel_path(
    pixels: Sequence[Pixel],
    *,
    max_gap: float = MAX_PIXEL_GAP,
) -> None:
    gap = max_pixel_gap(pixels)
    if gap > max_gap:
        raise ValueError(f"pixel path gap {gap:.3f} exceeds max {max_gap:.3f}")


def preview_max_half_extent(
    preset: Preset,
    flatness_px: float,
    *,
    margin_px: float = PREVIEW_MARGIN_PX,
    min_half_extent: float = PREVIEW_MIN_HALF_EXTENT,
) -> int:
    """Fixed preview half-size large enough for the preset at maximum zoom."""
    transform = TransformState(
        fit_scale=fit_scale_for_screen(preset),
        zoom=MAX_ZOOM,
    )
    return preview_half_extent(
        preset,
        (0.0, 0.0),
        transform,
        flatness_px,
        margin_px=margin_px,
        min_half_extent=min_half_extent,
    )


def preview_half_extent(
    preset: Preset,
    anchor: Point,
    transform: TransformState,
    flatness_px: float,
    *,
    margin_px: float = PREVIEW_MARGIN_PX,
    min_half_extent: float = PREVIEW_MIN_HALF_EXTENT,
) -> int:
    """Half-size of a square preview window that fully contains the preset."""
    ax, ay = anchor
    half_extent = 0.0
    for stroke in preset.strokes:
        for x, y in build_stroke_screen_points(
            stroke.segments,
            anchor,
            transform,
            flatness_px,
        ):
            half_extent = max(half_extent, abs(x - ax), abs(y - ay))
    return int(math.ceil(max(min_half_extent, half_extent + margin_px)))
