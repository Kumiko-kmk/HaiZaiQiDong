"""Typed curve segment models for preset strokes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Union

Point = Tuple[float, float]


def _parse_point(raw: object) -> Point:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        raise ValueError("Point must be [x, y]")
    return float(raw[0]), float(raw[1])


@dataclass(frozen=True)
class MoveSegment:
    to: Point


@dataclass(frozen=True)
class LineSegment:
    to: Point


@dataclass(frozen=True)
class PolylineSegment:
    points: Tuple[Point, ...]


@dataclass(frozen=True)
class ArcSegment:
    center: Point
    radius: float
    start_angle: float
    end_angle: float
    closed: bool = False


@dataclass(frozen=True)
class CubicBezierSegment:
    c1: Point
    c2: Point
    to: Point


@dataclass(frozen=True)
class QuadraticBezierSegment:
    c: Point
    to: Point


@dataclass(frozen=True)
class EllipseSegment:
    center: Point
    rx: float
    ry: float
    rotation: float
    start_angle: float
    end_angle: float


CurveSegment = Union[
    MoveSegment,
    LineSegment,
    PolylineSegment,
    ArcSegment,
    CubicBezierSegment,
    QuadraticBezierSegment,
    EllipseSegment,
]


def segment_from_dict(data: dict) -> CurveSegment:
    seg_type = str(data.get("type", "")).strip()
    if seg_type == "move":
        return MoveSegment(to=_parse_point(data["to"]))
    if seg_type == "line":
        return LineSegment(to=_parse_point(data["to"]))
    if seg_type == "polyline":
        raw_points = data.get("points", [])
        if not isinstance(raw_points, list) or not raw_points:
            raise ValueError("polyline segment requires non-empty points")
        return PolylineSegment(points=tuple(_parse_point(p) for p in raw_points))
    if seg_type == "arc":
        return ArcSegment(
            center=_parse_point(data["center"]),
            radius=float(data["radius"]),
            start_angle=float(data.get("startAngle", data.get("start_angle", 0))),
            end_angle=float(data.get("endAngle", data.get("end_angle", 360))),
            closed=bool(data.get("closed", False)),
        )
    if seg_type == "cubicBezier":
        return CubicBezierSegment(
            c1=_parse_point(data["c1"]),
            c2=_parse_point(data["c2"]),
            to=_parse_point(data["to"]),
        )
    if seg_type == "quadraticBezier":
        return QuadraticBezierSegment(
            c=_parse_point(data["c"]),
            to=_parse_point(data["to"]),
        )
    if seg_type == "ellipse":
        return EllipseSegment(
            center=_parse_point(data["center"]),
            rx=float(data["rx"]),
            ry=float(data["ry"]),
            rotation=float(data.get("rotation", 0)),
            start_angle=float(data.get("startAngle", data.get("start_angle", 0))),
            end_angle=float(data.get("endAngle", data.get("end_angle", 360))),
        )
    raise ValueError(f"Unknown segment type: {seg_type!r}")


def segment_to_dict(segment: CurveSegment) -> dict:
    if isinstance(segment, MoveSegment):
        return {"type": "move", "to": list(segment.to)}
    if isinstance(segment, LineSegment):
        return {"type": "line", "to": list(segment.to)}
    if isinstance(segment, PolylineSegment):
        return {"type": "polyline", "points": [list(p) for p in segment.points]}
    if isinstance(segment, ArcSegment):
        return {
            "type": "arc",
            "center": list(segment.center),
            "radius": segment.radius,
            "startAngle": segment.start_angle,
            "endAngle": segment.end_angle,
            "closed": segment.closed,
        }
    if isinstance(segment, CubicBezierSegment):
        return {
            "type": "cubicBezier",
            "c1": list(segment.c1),
            "c2": list(segment.c2),
            "to": list(segment.to),
        }
    if isinstance(segment, QuadraticBezierSegment):
        return {"type": "quadraticBezier", "c": list(segment.c), "to": list(segment.to)}
    if isinstance(segment, EllipseSegment):
        return {
            "type": "ellipse",
            "center": list(segment.center),
            "rx": segment.rx,
            "ry": segment.ry,
            "rotation": segment.rotation,
            "startAngle": segment.start_angle,
            "endAngle": segment.end_angle,
        }
    raise TypeError(f"Unsupported segment: {type(segment)!r}")
