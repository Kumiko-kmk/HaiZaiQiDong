"""Data models for sketch presets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from core.curves.segments import (
    ArcSegment,
    CubicBezierSegment,
    CurveSegment,
    EllipseSegment,
    LineSegment,
    MoveSegment,
    PolylineSegment,
    QuadraticBezierSegment,
    segment_from_dict,
    segment_to_dict,
)
from core.mouse_controller import MouseButton

Point = Tuple[float, float]


@dataclass(frozen=True)
class Stroke:
    segments: Tuple[CurveSegment, ...]

    @property
    def points(self) -> List[Point]:
        """Compatibility: approximate polyline vertices from segments."""
        vertices: List[Point] = []
        pen: Point | None = None
        for segment in self.segments:
            if isinstance(segment, MoveSegment):
                if pen is None:
                    vertices.append(segment.to)
                elif vertices[-1] != segment.to:
                    vertices.append(segment.to)
                pen = segment.to
            elif isinstance(segment, LineSegment):
                if not vertices or vertices[-1] != segment.to:
                    vertices.append(segment.to)
                pen = segment.to
            elif isinstance(segment, PolylineSegment):
                for point in segment.points:
                    if not vertices or vertices[-1] != point:
                        vertices.append(point)
                if segment.points:
                    pen = segment.points[-1]
            elif isinstance(segment, (ArcSegment, EllipseSegment)):
                if not vertices:
                    vertices.append(segment.center)
                pen = segment.center
            elif isinstance(segment, (CubicBezierSegment, QuadraticBezierSegment)):
                if not vertices or vertices[-1] != segment.to:
                    vertices.append(segment.to)
                pen = segment.to
        return vertices

    def to_dict(self) -> dict:
        return {"segments": [segment_to_dict(segment) for segment in self.segments]}

    @classmethod
    def from_dict(cls, data: dict) -> Stroke:
        if "segments" in data:
            raw_segments = data.get("segments", [])
            if not isinstance(raw_segments, list) or not raw_segments:
                raise ValueError("Stroke segments must be a non-empty list")
            segments = tuple(segment_from_dict(item) for item in raw_segments)
            return cls(segments=segments)

        raw_points = data.get("points", [])
        if not isinstance(raw_points, list) or not raw_points:
            raise ValueError("Stroke must contain segments or points")
        points: List[Point] = []
        for item in raw_points:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            points.append((float(item[0]), float(item[1])))
        if not points:
            raise ValueError("Stroke must contain at least one point")
        return cls(segments=(PolylineSegment(points=tuple(points)),))


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    version: int
    strokes: List[Stroke]
    description: str = ""
    tags: Tuple[str, ...] = ()
    menu_order: int | None = None
    draw_button: MouseButton = MouseButton.RIGHT

    @classmethod
    def from_dict(cls, data: dict) -> Preset:
        preset_id = str(data.get("id", "")).strip()
        name = str(data.get("name", preset_id)).strip()
        if not preset_id:
            raise ValueError("Preset id is required")
        if not name:
            raise ValueError("Preset name is required")

        raw_strokes = data.get("strokes", [])
        if not isinstance(raw_strokes, list) or not raw_strokes:
            raise ValueError("Preset must contain at least one stroke")

        strokes = [Stroke.from_dict(stroke) for stroke in raw_strokes]
        version = int(data.get("version", 1))
        description = str(data.get("description", "")).strip()

        raw_tags = data.get("tags", [])
        tags: Tuple[str, ...] = tuple(
            str(tag).strip() for tag in raw_tags if str(tag).strip()
        ) if isinstance(raw_tags, list) else ()

        raw_menu_order = data.get("menuOrder")
        menu_order = int(raw_menu_order) if raw_menu_order is not None else None

        button_raw = str(data.get("drawButton", "right")).strip().lower()
        draw_button = MouseButton.RIGHT if button_raw == "right" else MouseButton.LEFT

        return cls(
            id=preset_id,
            name=name,
            version=version,
            strokes=strokes,
            description=description,
            tags=tags,
            menu_order=menu_order,
            draw_button=draw_button,
        )
