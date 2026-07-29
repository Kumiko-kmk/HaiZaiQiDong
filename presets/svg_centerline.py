"""Pure-Python centerline extraction for SVG artwork stored as filled silhouettes."""

from __future__ import annotations

import math
from typing import Sequence

Point = tuple[float, float]
Polygon = Sequence[Point]
FilledShape = tuple[Sequence[Polygon], str]

RASTER_MAX_EXTENT = 560
RASTER_PADDING = 3
_NEIGHBOR_OFFSETS = (
    (0, -1),
    (1, -1),
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
)


def filled_shapes_to_centerlines(shapes: Sequence[FilledShape]) -> list[list[Point]]:
    """Rasterize filled vector shapes, thin them, and return editable centerline polylines."""
    points = [point for polygons, _fill_rule in shapes for polygon in polygons for point in polygon]
    if not points:
        return []

    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    width = max(max_x - min_x, 1e-6)
    height = max(max_y - min_y, 1e-6)
    scale = (RASTER_MAX_EXTENT - RASTER_PADDING * 2) / max(width, height)
    raster_width = max(1, int(math.ceil(width * scale)) + RASTER_PADDING * 2)
    raster_height = max(1, int(math.ceil(height * scale)) + RASTER_PADDING * 2)

    def to_raster(point: Point) -> Point:
        return (
            (point[0] - min_x) * scale + RASTER_PADDING,
            (point[1] - min_y) * scale + RASTER_PADDING,
        )

    raster_shapes: list[FilledShape] = [
        (
            [[to_raster(point) for point in polygon] for polygon in polygons],
            fill_rule,
        )
        for polygons, fill_rule in shapes
    ]
    filled = _rasterize_shapes(raster_shapes, raster_width, raster_height)
    if not filled:
        return []

    skeleton = _thin_zhang_suen(filled)
    pixel_strokes = _trace_skeleton(skeleton)

    def from_raster(point: Point) -> Point:
        return (
            (point[0] - RASTER_PADDING) / scale + min_x,
            (point[1] - RASTER_PADDING) / scale + min_y,
        )

    strokes: list[list[Point]] = []
    for stroke in pixel_strokes:
        simplified = _simplify_polyline(stroke, epsilon=0.72)
        if not simplified:
            continue
        strokes.append([from_raster(point) for point in simplified])
    return strokes


def _rasterize_shapes(
    shapes: Sequence[FilledShape],
    width: int,
    height: int,
) -> set[tuple[int, int]]:
    filled: set[tuple[int, int]] = set()
    for polygons, fill_rule in shapes:
        usable = [polygon for polygon in polygons if len(polygon) >= 3]
        if not usable:
            continue
        min_y = max(0, int(math.floor(min(point[1] for polygon in usable for point in polygon))))
        max_y = min(
            height - 1,
            int(math.ceil(max(point[1] for polygon in usable for point in polygon))),
        )
        for pixel_y in range(min_y, max_y + 1):
            scan_y = pixel_y + 0.5
            events: list[tuple[float, int]] = []
            for polygon in usable:
                for start, end in zip(polygon, polygon[1:] + polygon[:1]):
                    if abs(end[1] - start[1]) < 1e-12:
                        continue
                    low_y = min(start[1], end[1])
                    high_y = max(start[1], end[1])
                    if not (low_y <= scan_y < high_y):
                        continue
                    amount = (scan_y - start[1]) / (end[1] - start[1])
                    x = start[0] + (end[0] - start[0]) * amount
                    direction = 1 if end[1] > start[1] else -1
                    events.append((x, direction))
            if not events:
                continue
            events.sort(key=lambda event: event[0])
            intervals = (
                _evenodd_intervals(events)
                if fill_rule == "evenodd"
                else _nonzero_intervals(events)
            )
            for left, right in intervals:
                first = max(0, int(math.ceil(left - 0.5)))
                last = min(width - 1, int(math.floor(right - 0.5)))
                for pixel_x in range(first, last + 1):
                    filled.add((pixel_x, pixel_y))
    return filled


def _evenodd_intervals(events: Sequence[tuple[float, int]]) -> list[tuple[float, float]]:
    xs = [event[0] for event in events]
    return [
        (xs[index], xs[index + 1])
        for index in range(0, len(xs) - 1, 2)
        if xs[index + 1] > xs[index]
    ]


def _nonzero_intervals(events: Sequence[tuple[float, int]]) -> list[tuple[float, float]]:
    intervals: list[tuple[float, float]] = []
    winding = 0
    start_x: float | None = None
    index = 0
    while index < len(events):
        x = events[index][0]
        delta = 0
        while index < len(events) and abs(events[index][0] - x) < 1e-9:
            delta += events[index][1]
            index += 1
        was_inside = winding != 0
        winding += delta
        is_inside = winding != 0
        if not was_inside and is_inside:
            start_x = x
        elif was_inside and not is_inside and start_x is not None and x > start_x:
            intervals.append((start_x, x))
            start_x = None
    return intervals


def _neighbors(pixel: tuple[int, int], pixels: set[tuple[int, int]]) -> list[int]:
    x, y = pixel
    return [
        1 if (x + offset_x, y + offset_y) in pixels else 0
        for offset_x, offset_y in _NEIGHBOR_OFFSETS
    ]


def _transitions(neighbors: Sequence[int]) -> int:
    return sum(
        1
        for index, value in enumerate(neighbors)
        if value == 0 and neighbors[(index + 1) % len(neighbors)] == 1
    )


def _thin_zhang_suen(filled: set[tuple[int, int]]) -> set[tuple[int, int]]:
    pixels = set(filled)
    changed = True
    while changed:
        changed = False
        for first_step in (True, False):
            removable: list[tuple[int, int]] = []
            for pixel in pixels:
                neighbors = _neighbors(pixel, pixels)
                count = sum(neighbors)
                if count < 2 or count > 6 or _transitions(neighbors) != 1:
                    continue
                north, north_east, east, south_east, south, south_west, west, north_west = neighbors
                if first_step:
                    if north * east * south != 0 or east * south * west != 0:
                        continue
                elif north * east * west != 0 or north * south * west != 0:
                    continue
                removable.append(pixel)
            if removable:
                pixels.difference_update(removable)
                changed = True
    return pixels


def _pixel_neighbors(
    pixel: tuple[int, int],
    pixels: set[tuple[int, int]],
) -> list[tuple[int, int]]:
    x, y = pixel
    return [
        (x + offset_x, y + offset_y)
        for offset_x, offset_y in _NEIGHBOR_OFFSETS
        if (x + offset_x, y + offset_y) in pixels
    ]


def _edge_key(
    first: tuple[int, int],
    second: tuple[int, int],
) -> tuple[tuple[int, int], tuple[int, int]]:
    return (first, second) if first <= second else (second, first)


def _trace_skeleton(pixels: set[tuple[int, int]]) -> list[list[Point]]:
    if not pixels:
        return []
    adjacency = {pixel: _pixel_neighbors(pixel, pixels) for pixel in pixels}
    nodes = {pixel for pixel, neighbors in adjacency.items() if len(neighbors) != 2}
    visited: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    strokes: list[list[Point]] = []

    for node in sorted(nodes):
        if not adjacency[node]:
            strokes.append([(node[0] + 0.5, node[1] + 0.5)])
            continue
        for neighbor in adjacency[node]:
            edge = _edge_key(node, neighbor)
            if edge in visited:
                continue
            stroke = _trace_edge_chain(node, neighbor, adjacency, nodes, visited)
            if _is_meaningful_chain(stroke):
                strokes.append([(x + 0.5, y + 0.5) for x, y in stroke])

    for pixel in sorted(pixels):
        for neighbor in adjacency[pixel]:
            edge = _edge_key(pixel, neighbor)
            if edge in visited:
                continue
            stroke = _trace_edge_chain(pixel, neighbor, adjacency, nodes, visited)
            if _is_meaningful_chain(stroke):
                strokes.append([(x + 0.5, y + 0.5) for x, y in stroke])
    return strokes


def _is_meaningful_chain(stroke: Sequence[tuple[int, int]]) -> bool:
    if len(stroke) < 2:
        return False
    length = sum(
        math.hypot(end[0] - start[0], end[1] - start[1])
        for start, end in zip(stroke, stroke[1:])
    )
    # Adjacent junction pixels form tiny graph edges, not visible drawing branches.
    return length > math.sqrt(2.0) + 1e-6


def _trace_edge_chain(
    start: tuple[int, int],
    neighbor: tuple[int, int],
    adjacency: dict[tuple[int, int], list[tuple[int, int]]],
    nodes: set[tuple[int, int]],
    visited: set[tuple[tuple[int, int], tuple[int, int]]],
) -> list[tuple[int, int]]:
    stroke = [start, neighbor]
    visited.add(_edge_key(start, neighbor))
    previous = start
    current = neighbor
    while current not in nodes:
        candidates = [pixel for pixel in adjacency[current] if pixel != previous]
        if not candidates:
            break
        next_pixel = candidates[0]
        edge = _edge_key(current, next_pixel)
        if edge in visited:
            if next_pixel == start:
                stroke.append(next_pixel)
            break
        visited.add(edge)
        stroke.append(next_pixel)
        previous, current = current, next_pixel
    return stroke


def _simplify_polyline(points: Sequence[Point], epsilon: float) -> list[Point]:
    if len(points) <= 2:
        return list(points)
    closed = len(points) > 3 and points[0] == points[-1]
    source = list(points[:-1] if closed else points)
    if closed:
        source.append(source[0])
    simplified = _rdp(source, epsilon)
    if closed and simplified[0] != simplified[-1]:
        simplified.append(simplified[0])
    return simplified


def _rdp(points: Sequence[Point], epsilon: float) -> list[Point]:
    if len(points) <= 2:
        return list(points)
    start = points[0]
    end = points[-1]
    max_distance = -1.0
    split_index = 0
    for index, point in enumerate(points[1:-1], start=1):
        distance = _point_to_segment_distance(point, start, end)
        if distance > max_distance:
            max_distance = distance
            split_index = index
    if max_distance <= epsilon:
        return [start, end]
    left = _rdp(points[: split_index + 1], epsilon)
    right = _rdp(points[split_index:], epsilon)
    return left[:-1] + right


def _point_to_segment_distance(point: Point, start: Point, end: Point) -> float:
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    length_squared = delta_x * delta_x + delta_y * delta_y
    if length_squared <= 1e-12:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    amount = max(
        0.0,
        min(
            1.0,
            ((point[0] - start[0]) * delta_x + (point[1] - start[1]) * delta_y)
            / length_squared,
        ),
    )
    nearest_x = start[0] + delta_x * amount
    nearest_y = start[1] + delta_y * amount
    return math.hypot(point[0] - nearest_x, point[1] - nearest_y)
