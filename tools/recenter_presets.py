"""Recenter preset stroke coordinates to bounding-box center."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable, List, Tuple

Point = Tuple[float, float]


def _shift_point(point: Point, cx: float, cy: float) -> List[float]:
    return [round(point[0] - cx, 2), round(point[1] - cy, 2)]


def _collect_segment_points(segment: dict) -> List[Point]:
    seg_type = str(segment.get("type", ""))
    if seg_type in {"move", "line"}:
        to = segment.get("to")
        return [(float(to[0]), float(to[1]))] if to else []
    if seg_type == "polyline":
        return [(float(p[0]), float(p[1])) for p in segment.get("points", [])]
    if seg_type == "arc":
        center = segment.get("center")
        points = [(float(center[0]), float(center[1]))] if center else []
        radius = float(segment.get("radius", 0))
        start = math.radians(float(segment.get("startAngle", 0)))
        end = math.radians(float(segment.get("endAngle", 360)))
        if segment.get("closed"):
            end = start + 2 * math.pi
        points.append(
            (
                float(center[0]) + radius * math.cos(start),
                float(center[1]) + radius * math.sin(start),
            )
        )
        points.append(
            (
                float(center[0]) + radius * math.cos(end),
                float(center[1]) + radius * math.sin(end),
            )
        )
        return points
    if seg_type == "cubicBezier":
        pts = []
        for key in ("c1", "c2", "to"):
            raw = segment.get(key)
            if raw:
                pts.append((float(raw[0]), float(raw[1])))
        return pts
    if seg_type == "quadraticBezier":
        pts = []
        for key in ("c", "to"):
            raw = segment.get(key)
            if raw:
                pts.append((float(raw[0]), float(raw[1])))
        return pts
    if seg_type == "ellipse":
        center = segment.get("center")
        return [(float(center[0]), float(center[1]))] if center else []
    return []


def _collect_points(strokes: Iterable[dict]) -> List[Point]:
    points: List[Point] = []
    for stroke in strokes:
        if "segments" in stroke:
            for segment in stroke.get("segments", []):
                points.extend(_collect_segment_points(segment))
        for item in stroke.get("points", []):
            points.append((float(item[0]), float(item[1])))
    return points


def _recenter_segment(segment: dict, cx: float, cy: float) -> None:
    seg_type = str(segment.get("type", ""))
    if seg_type in {"move", "line"}:
        to = segment.get("to")
        if to:
            segment["to"] = _shift_point((float(to[0]), float(to[1])), cx, cy)
    elif seg_type == "polyline":
        segment["points"] = [
            _shift_point((float(p[0]), float(p[1])), cx, cy)
            for p in segment.get("points", [])
        ]
    elif seg_type == "arc":
        center = segment.get("center")
        if center:
            segment["center"] = _shift_point((float(center[0]), float(center[1])), cx, cy)
    elif seg_type == "cubicBezier":
        for key in ("c1", "c2", "to"):
            raw = segment.get(key)
            if raw:
                segment[key] = _shift_point((float(raw[0]), float(raw[1])), cx, cy)
    elif seg_type == "quadraticBezier":
        for key in ("c", "to"):
            raw = segment.get(key)
            if raw:
                segment[key] = _shift_point((float(raw[0]), float(raw[1])), cx, cy)
    elif seg_type == "ellipse":
        center = segment.get("center")
        if center:
            segment["center"] = _shift_point((float(center[0]), float(center[1])), cx, cy)


def recenter_preset(data: dict) -> dict:
    strokes = data.get("strokes", [])
    points = _collect_points(strokes)
    if not points:
        return data
    cx, cy = _bbox_center(points)
    for stroke in strokes:
        if "segments" in stroke:
            for segment in stroke.get("segments", []):
                _recenter_segment(segment, cx, cy)
        if "points" in stroke:
            stroke["points"] = [
                _shift_point((float(point[0]), float(point[1])), cx, cy)
                for point in stroke["points"]
            ]
    data["version"] = max(int(data.get("version", 1)), 2)
    return data


def _bbox_center(points: List[Point]) -> Point:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def main() -> None:
    data_dir = Path(__file__).resolve().parent.parent / "presets" / "data"
    for path in sorted(data_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        updated = recenter_preset(data)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(updated, handle, ensure_ascii=False, indent=2)
        print(f"recentered {path.name}")


if __name__ == "__main__":
    main()
