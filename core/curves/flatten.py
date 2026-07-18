"""Adaptive flatness-based flattening of curve segments into polylines."""

from __future__ import annotations

import math
from typing import Callable, List, Optional, Sequence

from core.curves.segments import (
    ArcSegment,
    CubicBezierSegment,
    CurveSegment,
    EllipseSegment,
    LineSegment,
    MoveSegment,
    PolylineSegment,
    QuadraticBezierSegment,
)

Point = tuple[float, float]
_EPS = 1e-9
_MAX_DEPTH = 24


def _distance(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _lerp(a: Point, b: Point, t: float) -> Point:
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t


def _chord_height(point: Point, start: Point, end: Point) -> float:
    chord = _distance(start, end)
    if chord < _EPS:
        return _distance(point, start)
    cross = abs(
        (end[0] - start[0]) * (start[1] - point[1])
        - (start[0] - point[0]) * (end[1] - start[1])
    )
    return cross / chord


def _append_points(target: List[Point], points: Sequence[Point]) -> None:
    for point in points:
        if not target or _distance(target[-1], point) > _EPS:
            target.append(point)


def _subdivide_line(start: Point, end: Point, max_step_px: float) -> List[Point]:
    length = _distance(start, end)
    if length <= max_step_px + _EPS:
        return [start, end]
    steps = max(1, int(math.ceil(length / max_step_px)))
    return [_lerp(start, end, index / steps) for index in range(steps + 1)]


def _cubic_at(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    u = 1.0 - t
    return (
        u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
    )


def _quadratic_at(p0: Point, p1: Point, p2: Point, t: float) -> Point:
    u = 1.0 - t
    return (
        u**2 * p0[0] + 2 * u * t * p1[0] + t**2 * p2[0],
        u**2 * p0[1] + 2 * u * t * p1[1] + t**2 * p2[1],
    )


def _flatten_cubic(
    p0: Point,
    p1: Point,
    p2: Point,
    p3: Point,
    *,
    flatness_px: float,
    max_step_px: float,
    depth: int = 0,
) -> List[Point]:
    mid = _cubic_at(p0, p1, p2, p3, 0.5)
    sagitta = _chord_height(mid, p0, p3)
    span = _distance(p0, p3)
    if depth >= _MAX_DEPTH or (sagitta <= flatness_px and span <= max_step_px):
        return [p0, p3]
    p01 = _lerp(p0, p1, 0.5)
    p12 = _lerp(p1, p2, 0.5)
    p23 = _lerp(p2, p3, 0.5)
    p012 = _lerp(p01, p12, 0.5)
    p123 = _lerp(p12, p23, 0.5)
    mid_split = _lerp(p012, p123, 0.5)
    left = _flatten_cubic(
        p0, p01, p012, mid_split, flatness_px=flatness_px, max_step_px=max_step_px, depth=depth + 1
    )
    right = _flatten_cubic(
        mid_split, p123, p23, p3, flatness_px=flatness_px, max_step_px=max_step_px, depth=depth + 1
    )
    return left[:-1] + right


def _flatten_quadratic(
    p0: Point,
    p1: Point,
    p2: Point,
    *,
    flatness_px: float,
    max_step_px: float,
    depth: int = 0,
) -> List[Point]:
    mid = _quadratic_at(p0, p1, p2, 0.5)
    sagitta = _chord_height(mid, p0, p2)
    span = _distance(p0, p2)
    if depth >= _MAX_DEPTH or (sagitta <= flatness_px and span <= max_step_px):
        return [p0, p2]
    p01 = _lerp(p0, p1, 0.5)
    p12 = _lerp(p1, p2, 0.5)
    mid_split = _lerp(p01, p12, 0.5)
    left = _flatten_quadratic(
        p0, p01, mid_split, flatness_px=flatness_px, max_step_px=max_step_px, depth=depth + 1
    )
    right = _flatten_quadratic(
        mid_split, p12, p2, flatness_px=flatness_px, max_step_px=max_step_px, depth=depth + 1
    )
    return left[:-1] + right


def _flatten_parametric(
    evaluate: Callable[[float], Point],
    t_start: float,
    t_end: float,
    *,
    flatness_px: float,
    max_step_px: float,
    depth: int = 0,
) -> List[Point]:
    start = evaluate(t_start)
    end = evaluate(t_end)
    mid_t = (t_start + t_end) * 0.5
    mid = evaluate(mid_t)
    sagitta = _chord_height(mid, start, end)
    span = _distance(start, end)
    if depth >= _MAX_DEPTH or (sagitta <= flatness_px and span <= max_step_px):
        return [start, end]
    left = _flatten_parametric(
        evaluate, t_start, mid_t, flatness_px=flatness_px, max_step_px=max_step_px, depth=depth + 1
    )
    right = _flatten_parametric(
        evaluate, mid_t, t_end, flatness_px=flatness_px, max_step_px=max_step_px, depth=depth + 1
    )
    return left[:-1] + right


def _arc_angles(segment: ArcSegment) -> tuple[float, float]:
    start_rad = math.radians(segment.start_angle)
    end_rad = math.radians(segment.end_angle)
    if segment.closed and abs(segment.end_angle - segment.start_angle) >= 359.9:
        end_rad = start_rad + 2.0 * math.pi
    elif end_rad < start_rad:
        end_rad += 2.0 * math.pi
    return start_rad, end_rad


def _flatten_arc(
    segment: ArcSegment,
    *,
    flatness_px: float,
    max_step_px: float,
) -> List[Point]:
    cx, cy = segment.center
    r = segment.radius
    start_rad, end_rad = _arc_angles(segment)

    def evaluate(angle: float) -> Point:
        return cx + r * math.cos(angle), cy + r * math.sin(angle)

    return _flatten_parametric(
        evaluate,
        start_rad,
        end_rad,
        flatness_px=flatness_px,
        max_step_px=max_step_px,
    )


def _flatten_ellipse(
    segment: EllipseSegment,
    *,
    flatness_px: float,
    max_step_px: float,
) -> List[Point]:
    cx, cy = segment.center
    rot = math.radians(segment.rotation)
    cos_r = math.cos(rot)
    sin_r = math.sin(rot)
    start_rad = math.radians(segment.start_angle)
    end_rad = math.radians(segment.end_angle)
    if end_rad < start_rad:
        end_rad += 2.0 * math.pi

    def evaluate(angle: float) -> Point:
        lx = segment.rx * math.cos(angle)
        ly = segment.ry * math.sin(angle)
        x = cx + lx * cos_r - ly * sin_r
        y = cy + lx * sin_r + ly * cos_r
        return x, y

    return _flatten_parametric(
        evaluate,
        start_rad,
        end_rad,
        flatness_px=flatness_px,
        max_step_px=max_step_px,
    )


def flatten_segment(
    segment: CurveSegment,
    pen: Optional[Point],
    *,
    flatness_px: float,
    max_step_px: float,
    include_start: bool,
) -> List[Point]:
    if isinstance(segment, MoveSegment):
        return [segment.to]

    if isinstance(segment, LineSegment):
        if pen is None:
            raise ValueError("line segment requires a starting pen position")
        subdivided = _subdivide_line(pen, segment.to, max_step_px)
        if include_start:
            return subdivided
        return subdivided[1:] if subdivided else []

    if isinstance(segment, PolylineSegment):
        if not segment.points:
            return []
        vertices: List[Point] = list(segment.points)
        if pen is not None and _distance(pen, vertices[0]) > _EPS:
            vertices.insert(0, pen)
        elif pen is not None:
            vertices[0] = pen
        if pen is None and not vertices:
            return []
        out: List[Point] = []
        if include_start:
            out.append(vertices[0])
        for start, end in zip(vertices[:-1], vertices[1:]):
            if _distance(start, end) < _EPS:
                continue
            edge = _subdivide_line(start, end, max_step_px)
            _append_points(out, edge[1:])
        return out

    if isinstance(segment, ArcSegment):
        flattened = _flatten_arc(segment, flatness_px=flatness_px, max_step_px=max_step_px)
        return flattened if include_start else flattened[1:]

    if isinstance(segment, CubicBezierSegment):
        if pen is None:
            raise ValueError("cubicBezier segment requires a starting pen position")
        flattened = _flatten_cubic(
            pen,
            segment.c1,
            segment.c2,
            segment.to,
            flatness_px=flatness_px,
            max_step_px=max_step_px,
        )
        return flattened if include_start else flattened[1:]

    if isinstance(segment, QuadraticBezierSegment):
        if pen is None:
            raise ValueError("quadraticBezier segment requires a starting pen position")
        flattened = _flatten_quadratic(
            pen,
            segment.c,
            segment.to,
            flatness_px=flatness_px,
            max_step_px=max_step_px,
        )
        return flattened if include_start else flattened[1:]

    if isinstance(segment, EllipseSegment):
        flattened = _flatten_ellipse(segment, flatness_px=flatness_px, max_step_px=max_step_px)
        return flattened if include_start else flattened[1:]

    raise TypeError(f"Unsupported segment: {type(segment)!r}")


def flatten_stroke(
    segments: Sequence[CurveSegment],
    flatness_px: float,
    *,
    max_step_px: float,
) -> List[Point]:
    if flatness_px <= 0:
        raise ValueError("flatness_px must be positive")
    if max_step_px <= 0:
        raise ValueError("max_step_px must be positive")
    if not segments:
        return []

    dense: List[Point] = []
    pen: Optional[Point] = None

    for segment in segments:
        include_start = not dense
        if isinstance(segment, MoveSegment):
            pen = segment.to
            if include_start:
                dense.append(segment.to)
            continue

        points = flatten_segment(
            segment,
            pen,
            flatness_px=flatness_px,
            max_step_px=max_step_px,
            include_start=include_start,
        )
        if not points:
            continue

        if dense and _distance(dense[-1], points[0]) < _EPS:
            dense.extend(points[1:])
        else:
            dense.extend(points)
        pen = dense[-1]

    return dense
