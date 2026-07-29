"""Import SVG line art into mouse-sketch-drawer preset JSON."""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable, List, Sequence, Tuple

from core.curves.flatten import flatten_stroke
from core.curves.segments import segment_from_dict
from core.geometry import FLATNESS_PX
from presets.svg_centerline import FilledShape, filled_shapes_to_centerlines

Point = Tuple[float, float]
StrokePoints = List[Point]
SegmentDict = dict
Affine = Tuple[float, float, float, float, float, float]
IDENTITY: Affine = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

_TOKEN_RE = re.compile(
    r"([MmLlHhVvCcSsQqTtAaZz])|(-?\d*\.?\d+(?:[eE][-+]?\d+)?)",
)
_TRANSFORM_RE = re.compile(
    r"(matrix|translate|scale)\(([^)]+)\)",
    re.IGNORECASE,
)
BRIDGE_GAP_FACTOR = 1.0
MIN_BRIDGE_GAP = 0.5
_EPS = 1e-6


@dataclass
class _StrokeRaw:
    segments: List[SegmentDict]
    closed: bool


@dataclass
class _ParseContext:
    bridge_gap: float
    strokes: List[_StrokeRaw]
    open_stroke: _StrokeRaw | None = None


def svg_title(svg_text: str) -> str | None:
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError:
        return None
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "title":
            text = (element.text or "").strip()
            if text:
                return text
    return None


def svg_to_stroke_dicts(
    svg_text: str,
    *,
    target_half_extent: float = 60.0,
    bridge_gap_factor: float = BRIDGE_GAP_FACTOR,
) -> List[dict]:
    """Extract and normalize SVG contours without preset metadata."""
    root = ET.fromstring(svg_text)
    centerlines = _extract_filled_centerlines(root)
    if centerlines is None:
        strokes_raw = extract_svg_strokes(svg_text, bridge_gap_factor=bridge_gap_factor)
    else:
        strokes_raw = [
            _StrokeRaw(segments=_points_to_polyline_segment(points), closed=False)
            for points in centerlines
            if points
        ]
    if not strokes_raw:
        raise ValueError("SVG contains no drawable strokes")

    valid = [stroke for stroke in strokes_raw if _is_valid_stroke(stroke.segments)]
    if not valid:
        raise ValueError("SVG contains no valid strokes")

    segment_groups = [stroke.segments for stroke in valid]
    normalized = _normalize_segment_strokes(segment_groups, target_half_extent=target_half_extent)

    strokes: List[dict] = []
    for segments in normalized:
        if not _is_valid_stroke(segments):
            continue
        strokes.append({"segments": [_round_segment_dict(seg) for seg in segments]})

    if not strokes:
        raise ValueError("SVG contains no valid strokes after normalization")

    return strokes


def extract_svg_strokes(
    svg_text: str,
    *,
    bridge_gap_factor: float = BRIDGE_GAP_FACTOR,
) -> List[_StrokeRaw]:
    root = ET.fromstring(svg_text)
    bridge_gap = _resolve_bridge_gap(root, bridge_gap_factor=bridge_gap_factor)
    context = _ParseContext(bridge_gap=bridge_gap, strokes=[])
    _walk_svg_element(root, IDENTITY, context)
    _flush_open_stroke(context)
    return context.strokes


def _extract_filled_centerlines(root: ET.Element) -> list[StrokePoints] | None:
    """Return centerlines only when the SVG clearly stores paths as filled silhouettes."""
    shapes: list[FilledShape] = []
    eligible = True
    found_filled_path = False

    initial_style = {
        "fill": "black",
        "stroke": "none",
        "fill-rule": "nonzero",
        "display": "inline",
        "visibility": "visible",
        "opacity": "1",
        "fill-opacity": "1",
        "stroke-opacity": "1",
    }

    def walk(
        element: ET.Element,
        parent_matrix: Affine,
        inherited_style: dict[str, str],
        inherited_fill_explicit: bool,
    ) -> None:
        nonlocal eligible, found_filled_path
        if not eligible:
            return
        matrix = _compose_affine(parent_matrix, _parse_transform_matrix(element.get("transform")))
        style, fill_explicit = _resolve_element_style(
            element,
            inherited_style,
            inherited_fill_explicit,
        )
        if style["display"].strip().lower() == "none":
            return
        if style["visibility"].strip().lower() in {"hidden", "collapse"}:
            return
        if _style_number(style.get("opacity"), 1.0) <= 0:
            return

        tag = element.tag.rsplit("}", 1)[-1]
        if tag in {"line", "polyline"}:
            if _element_has_geometry(element, tag):
                eligible = False
                return
        elif tag in {"path", "polygon", "rect", "circle", "ellipse"} and _element_has_geometry(element, tag):
            visible_fill = _paint_is_visible(style["fill"]) and _style_number(
                style.get("fill-opacity"),
                1.0,
            ) > 0
            visible_stroke = _paint_is_visible(style["stroke"]) and _style_number(
                style.get("stroke-opacity"),
                1.0,
            ) > 0
            if visible_stroke or not visible_fill or not fill_explicit:
                eligible = False
                return
            polygons = _filled_element_polygons(element, tag, matrix)
            if not polygons:
                eligible = False
                return
            if tag == "path":
                found_filled_path = True
            fill_rule = style.get("fill-rule", "nonzero").strip().lower()
            shapes.append((polygons, "evenodd" if fill_rule == "evenodd" else "nonzero"))

        for child in element:
            walk(child, matrix, style, fill_explicit)

    walk(root, IDENTITY, initial_style, False)
    if not eligible or not found_filled_path or not shapes:
        return None
    return filled_shapes_to_centerlines(shapes)


def _resolve_element_style(
    element: ET.Element,
    inherited: dict[str, str],
    inherited_fill_explicit: bool,
) -> tuple[dict[str, str], bool]:
    style = dict(inherited)
    fill_explicit = inherited_fill_explicit
    names = {
        "fill",
        "stroke",
        "fill-rule",
        "display",
        "visibility",
        "opacity",
        "fill-opacity",
        "stroke-opacity",
    }
    for name in names:
        raw = element.get(name)
        if raw is not None:
            style[name] = raw
            if name == "fill":
                fill_explicit = True
    inline: dict[str, str] = {}
    for declaration in (element.get("style") or "").split(";"):
        if ":" not in declaration:
            continue
        name, value = declaration.split(":", 1)
        inline[name.strip().lower()] = value.strip()
    for name in names:
        if name in inline:
            style[name] = inline[name]
            if name == "fill":
                fill_explicit = True
    return style, fill_explicit


def _style_number(raw: str | None, fallback: float) -> float:
    try:
        return float(raw) if raw is not None else fallback
    except ValueError:
        return fallback


def _paint_is_visible(raw: str | None) -> bool:
    value = (raw or "").strip().lower().replace(" ", "")
    return value not in {"", "none", "transparent", "rgba(0,0,0,0)"}


def _element_has_geometry(element: ET.Element, tag: str) -> bool:
    if tag == "path":
        return bool((element.get("d") or "").strip())
    if tag in {"line", "polyline", "polygon"}:
        return bool((element.get("points") or "").strip()) if tag != "line" else True
    if tag == "rect":
        return _style_number(element.get("width"), 0) > 0 and _style_number(element.get("height"), 0) > 0
    if tag == "circle":
        return _style_number(element.get("r"), 0) > 0
    if tag == "ellipse":
        return _style_number(element.get("rx"), 0) > 0 and _style_number(element.get("ry"), 0) > 0
    return False


def _filled_element_polygons(
    element: ET.Element,
    tag: str,
    matrix: Affine,
) -> list[StrokePoints]:
    polygons: list[StrokePoints] = []
    if tag == "path":
        for subpath in _parse_path_segments(element.get("d", ""), bridge_gap=0.0):
            if not subpath.closed:
                return []
            transformed = _apply_affine_to_segments(subpath.segments, matrix)
            points = _flatten_raw_segments(transformed)
            if len(points) >= 3:
                polygons.append(points)
        return polygons
    if tag == "polygon":
        points = _apply_affine(_parse_points_attr(element.get("points", "")), matrix)
        return [points] if len(points) >= 3 else []
    if tag == "rect":
        x = _style_number(element.get("x"), 0)
        y = _style_number(element.get("y"), 0)
        width = _style_number(element.get("width"), 0)
        height = _style_number(element.get("height"), 0)
        return [_apply_affine(
            [(x, y), (x + width, y), (x + width, y + height), (x, y + height)],
            matrix,
        )]
    if tag == "circle":
        points = _circle_points(
            _style_number(element.get("cx"), 0),
            _style_number(element.get("cy"), 0),
            _style_number(element.get("r"), 0),
            segments=64,
        )
        return [_apply_affine(points, matrix)]
    if tag == "ellipse":
        points = _ellipse_points(
            _style_number(element.get("cx"), 0),
            _style_number(element.get("cy"), 0),
            _style_number(element.get("rx"), 0),
            _style_number(element.get("ry"), 0),
            segments=64,
        )
        return [_apply_affine(points, matrix)]
    return []


def _flatten_raw_segments(segments: Sequence[SegmentDict]) -> StrokePoints:
    typed = [segment_from_dict(segment) for segment in segments]
    return flatten_stroke(
        typed,
        flatness_px=max(FLATNESS_PX, 0.75),
        max_step_px=4.0,
    )


def _walk_svg_element(
    element: ET.Element,
    parent_matrix: Affine,
    context: _ParseContext,
    *,
    inherited_stroke_width: float | None = None,
) -> None:
    matrix = _compose_affine(parent_matrix, _parse_transform_matrix(element.get("transform")))
    raw_stroke_width = element.get("stroke-width")
    stroke_width = inherited_stroke_width
    if raw_stroke_width is not None:
        try:
            stroke_width = float(raw_stroke_width)
        except ValueError:
            pass

    tag = element.tag.rsplit("}", 1)[-1]
    if tag == "path":
        d = element.get("d", "")
        scale = _affine_scale_factor(matrix)
        local_bridge_gap = context.bridge_gap / max(scale, _EPS)
        for subpath in _parse_path_segments(d, bridge_gap=local_bridge_gap):
            segments = _apply_affine_to_segments(subpath.segments, matrix)
            _ingest_stroke(context, _StrokeRaw(segments=segments, closed=subpath.closed))
    elif tag == "line":
        x1 = float(element.get("x1", 0))
        y1 = float(element.get("y1", 0))
        x2 = float(element.get("x2", 0))
        y2 = float(element.get("y2", 0))
        points = _apply_affine([(x1, y1), (x2, y2)], matrix)
        segments = _points_to_line_segments(points)
        _ingest_stroke(context, _StrokeRaw(segments=segments, closed=False))
    elif tag == "polyline":
        raw = _parse_points_attr(element.get("points", ""))
        points = _apply_affine(raw, matrix)
        segments = _points_to_line_segments(points)
        _ingest_stroke(context, _StrokeRaw(segments=segments, closed=False))
    elif tag == "polygon":
        raw = _parse_points_attr(element.get("points", ""))
        points = _apply_affine(raw, matrix)
        segments = _points_to_line_segments(points, closed=True)
        _ingest_stroke(context, _StrokeRaw(segments=segments, closed=True))
    elif tag == "circle":
        cx = float(element.get("cx", 0))
        cy = float(element.get("cy", 0))
        r = float(element.get("r", 0))
        if r > 0:
            points = _apply_affine(_circle_points(cx, cy, r), matrix)
            segments = _points_to_polyline_segment(points)
            _ingest_stroke(context, _StrokeRaw(segments=segments, closed=True))
    elif tag == "ellipse":
        cx = float(element.get("cx", 0))
        cy = float(element.get("cy", 0))
        rx = float(element.get("rx", 0))
        ry = float(element.get("ry", 0))
        if rx > 0 and ry > 0:
            points = _apply_affine(_ellipse_points(cx, cy, rx, ry), matrix)
            segments = _points_to_polyline_segment(points)
            _ingest_stroke(context, _StrokeRaw(segments=segments, closed=True))
    elif tag == "rect":
        x = float(element.get("x", 0))
        y = float(element.get("y", 0))
        w = float(element.get("width", 0))
        h = float(element.get("height", 0))
        if w > 0 and h > 0:
            points = _apply_affine(
                [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)],
                matrix,
            )
            segments = _points_to_polyline_segment(points)
            _ingest_stroke(context, _StrokeRaw(segments=segments, closed=True))

    for child in element:
        _walk_svg_element(child, matrix, context, inherited_stroke_width=stroke_width)

    if tag == "g":
        _flush_open_stroke(context)


def _is_valid_stroke(segments: Sequence[SegmentDict]) -> bool:
    if not segments:
        return False
    return any(seg.get("type") != "move" for seg in segments)


def _distance(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _stroke_endpoints(segments: Sequence[SegmentDict]) -> Tuple[Point, Point]:
    start = tuple(segments[0]["to"])
    pen: Point = start
    for segment in segments[1:]:
        seg_type = segment["type"]
        if seg_type == "move":
            pen = tuple(segment["to"])
        elif seg_type in {"line", "cubicBezier", "quadraticBezier"}:
            pen = tuple(segment["to"])
        elif seg_type == "polyline":
            points = segment.get("points") or []
            if points:
                pen = tuple(points[-1])
    return start, pen


def _flush_open_stroke(context: _ParseContext) -> None:
    if context.open_stroke is not None and _is_valid_stroke(context.open_stroke.segments):
        context.strokes.append(context.open_stroke)
    context.open_stroke = None


def _bridge_segments(
    left: Sequence[SegmentDict],
    right: Sequence[SegmentDict],
    *,
    bridge_gap: float,
) -> List[SegmentDict] | None:
    if not left or not right:
        return None
    _, end_left = _stroke_endpoints(left)
    start_right, _ = _stroke_endpoints(right)
    gap = _distance(end_left, start_right)
    if gap > bridge_gap:
        return None
    merged = list(left)
    if gap > _EPS:
        merged.append({"type": "line", "to": list(start_right)})
    merged.extend(right[1:] if right and right[0].get("type") == "move" else list(right))
    return merged


def _ingest_stroke(context: _ParseContext, stroke: _StrokeRaw) -> None:
    if not _is_valid_stroke(stroke.segments):
        return

    if context.open_stroke is None:
        if stroke.closed:
            context.strokes.append(stroke)
            return
        context.open_stroke = stroke
        return

    if stroke.closed:
        _flush_open_stroke(context)
        context.strokes.append(stroke)
        return

    if context.open_stroke.closed:
        _flush_open_stroke(context)
        context.open_stroke = stroke
        return

    merged = _bridge_segments(
        context.open_stroke.segments,
        stroke.segments,
        bridge_gap=context.bridge_gap,
    )
    if merged is not None:
        context.open_stroke = _StrokeRaw(segments=merged, closed=False)
        return

    _flush_open_stroke(context)
    context.open_stroke = stroke


def _affine_scale_factor(matrix: Affine) -> float:
    a, b, c, d, _, _ = matrix
    return (math.hypot(a, b) + math.hypot(c, d)) / 2.0


def _iter_subpath_gaps(d: str) -> List[float]:
    """Distances between consecutive subpath starts (M after prior geometry)."""
    tokens = [m.group(0) for m in _TOKEN_RE.finditer(d) if m.group(0)]
    gaps: List[float] = []
    index = 0
    current = (0.0, 0.0)
    start = (0.0, 0.0)
    cmd = "M"
    has_geometry = False

    def read_number() -> float:
        nonlocal index
        value = float(tokens[index])
        index += 1
        return value

    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            cmd = token
            index += 1
            if cmd in {"M", "m"}:
                x = read_number()
                y = read_number()
                new_start = (current[0] + x, current[1] + y) if cmd == "m" else (x, y)
                if has_geometry:
                    gaps.append(_distance(current, new_start))
                current = new_start
                start = current
                has_geometry = False
                cmd = "L" if cmd == "M" else "l"
                continue
            if cmd in {"Z", "z"}:
                current = start
                continue
            continue

        relative = cmd.islower()
        upper = cmd.upper()
        if upper == "L":
            x = read_number()
            y = read_number()
            current = (current[0] + x, current[1] + y) if relative else (x, y)
            has_geometry = True
        elif upper == "H":
            x = read_number()
            current = (current[0] + x, current[1]) if relative else (x, current[1])
            has_geometry = True
        elif upper == "V":
            y = read_number()
            current = (current[0], current[1] + y) if relative else (current[0], y)
            has_geometry = True
        elif upper == "C":
            read_number()
            read_number()
            read_number()
            read_number()
            x = read_number()
            y = read_number()
            current = (current[0] + x, current[1] + y) if relative else (x, y)
            has_geometry = True
        elif upper in {"S", "Q", "T"}:
            if upper == "S":
                read_number()
                read_number()
            elif upper == "Q":
                read_number()
                read_number()
            x = read_number()
            y = read_number()
            current = (current[0] + x, current[1] + y) if relative else (x, y)
            has_geometry = True
        elif upper == "A":
            read_number()
            read_number()
            read_number()
            read_number()
            read_number()
            x = read_number()
            y = read_number()
            current = (current[0] + x, current[1] + y) if relative else (x, y)
            has_geometry = True

    return gaps


def _resolve_bridge_gap(root: ET.Element, *, bridge_gap_factor: float) -> float:
    stroke_widths: List[float] = []
    subpath_gaps: List[float] = []
    bbox_points: List[Point] = []

    def walk(element: ET.Element, matrix: Affine, inherited_stroke_width: float | None) -> None:
        local_matrix = _compose_affine(matrix, _parse_transform_matrix(element.get("transform")))
        scale = _affine_scale_factor(local_matrix)
        stroke_width = inherited_stroke_width
        raw_stroke_width = element.get("stroke-width")
        if raw_stroke_width is not None:
            try:
                stroke_width = float(raw_stroke_width)
            except ValueError:
                pass
        if stroke_width is not None:
            stroke_widths.append(stroke_width * scale)

        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "path":
            d = element.get("d", "")
            for point in _iter_path_points(d):
                bbox_points.append(_apply_affine_point(point, local_matrix))
            for gap in _iter_subpath_gaps(d):
                subpath_gaps.append(gap * scale)

        for child in element:
            walk(child, local_matrix, stroke_width)

    walk(root, IDENTITY, None)

    if bbox_points:
        width, height = _bbox_size(bbox_points)
        bbox_diag = math.hypot(width, height)
    else:
        bbox_diag = 0.0

    if stroke_widths:
        stroke_width = sum(stroke_widths) / len(stroke_widths)
    elif subpath_gaps:
        positive = sorted(gap for gap in subpath_gaps if gap > _EPS)
        if positive:
            min_gap = positive[0]
            p10 = positive[min(len(positive) - 1, max(1, len(positive) // 10))]
            p25 = positive[len(positive) // 4]
            # Fine voids sit in the low end of the gap distribution, not the median.
            stroke_width = min(p25, max(min_gap * 2.5, p10 * 1.5))
        else:
            stroke_width = 0.0
    else:
        stroke_width = 0.0

    if bbox_diag > 0:
        stroke_width = max(stroke_width, bbox_diag * 0.006)

    return max(stroke_width * bridge_gap_factor, MIN_BRIDGE_GAP)


def _iter_path_points(d: str) -> List[Point]:
    tokens = [m.group(0) for m in _TOKEN_RE.finditer(d) if m.group(0)]
    points: List[Point] = []
    index = 0
    current = (0.0, 0.0)
    start = (0.0, 0.0)
    cmd = "M"

    def read_number() -> float:
        nonlocal index
        value = float(tokens[index])
        index += 1
        return value

    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            cmd = token
            index += 1
            if cmd in {"M", "m"}:
                x = read_number()
                y = read_number()
                current = (current[0] + x, current[1] + y) if cmd == "m" else (x, y)
                start = current
                points.append(current)
                cmd = "L" if cmd == "M" else "l"
                continue
            if cmd in {"Z", "z"}:
                current = start
                continue
            continue

        relative = cmd.islower()
        upper = cmd.upper()
        if upper == "L":
            x = read_number()
            y = read_number()
            current = (current[0] + x, current[1] + y) if relative else (x, y)
            points.append(current)
        elif upper == "H":
            x = read_number()
            current = (current[0] + x, current[1]) if relative else (x, current[1])
            points.append(current)
        elif upper == "V":
            y = read_number()
            current = (current[0], current[1] + y) if relative else (current[0], y)
            points.append(current)
        elif upper == "C":
            read_number()
            read_number()
            read_number()
            read_number()
            x = read_number()
            y = read_number()
            current = (current[0] + x, current[1] + y) if relative else (x, y)
            points.append(current)
        elif upper in {"S", "Q", "T"}:
            if upper == "S":
                read_number()
                read_number()
            elif upper == "Q":
                read_number()
                read_number()
            x = read_number()
            y = read_number()
            current = (current[0] + x, current[1] + y) if relative else (x, y)
            points.append(current)
        elif upper == "A":
            read_number()
            read_number()
            read_number()
            read_number()
            read_number()
            x = read_number()
            y = read_number()
            current = (current[0] + x, current[1] + y) if relative else (x, y)
            points.append(current)

    return points


def _points_to_line_segments(points: StrokePoints, *, closed: bool = False) -> List[SegmentDict]:
    if len(points) < 2:
        return []
    segments: List[SegmentDict] = [{"type": "move", "to": list(points[0])}]
    for point in points[1:]:
        segments.append({"type": "line", "to": list(point)})
    if closed and points[0] != points[-1]:
        segments.append({"type": "line", "to": list(points[0])})
    return segments


def _points_to_polyline_segment(points: StrokePoints) -> List[SegmentDict]:
    if len(points) < 2:
        return []
    return [{"type": "polyline", "points": [list(point) for point in points]}]


def _parse_points_attr(raw: str) -> StrokePoints:
    numbers = [float(value) for value in re.findall(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?", raw)]
    points: StrokePoints = []
    for index in range(0, len(numbers) - 1, 2):
        points.append((numbers[index], numbers[index + 1]))
    return points


def _circle_points(cx: float, cy: float, radius: float, segments: int = 32) -> StrokePoints:
    return [
        (
            cx + radius * math.cos(2 * math.pi * index / segments),
            cy + radius * math.sin(2 * math.pi * index / segments),
        )
        for index in range(segments + 1)
    ]


def _ellipse_points(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    segments: int = 48,
) -> StrokePoints:
    return [
        (
            cx + rx * math.cos(2 * math.pi * index / segments),
            cy + ry * math.sin(2 * math.pi * index / segments),
        )
        for index in range(segments + 1)
    ]


def _parse_transform_matrix(raw: str | None) -> Affine:
    matrix = IDENTITY
    if not raw:
        return matrix
    for match in _TRANSFORM_RE.finditer(raw):
        kind = match.group(1).lower()
        parts = [float(item) for item in re.findall(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?", match.group(2))]
        if kind == "translate":
            tx = parts[0]
            ty = parts[1] if len(parts) > 1 else 0.0
            matrix = _compose_affine(matrix, (1.0, 0.0, 0.0, 1.0, tx, ty))
        elif kind == "scale":
            sx = parts[0]
            sy = parts[1] if len(parts) > 1 else parts[0]
            matrix = _compose_affine(matrix, (sx, 0.0, 0.0, sy, 0.0, 0.0))
        elif kind == "matrix" and len(parts) == 6:
            matrix = _compose_affine(matrix, tuple(parts))  # type: ignore[arg-type]
    return matrix


def _compose_affine(outer: Affine, inner: Affine) -> Affine:
    a1, b1, c1, d1, e1, f1 = inner
    a2, b2, c2, d2, e2, f2 = outer
    return (
        a2 * a1 + c2 * b1,
        b2 * a1 + d2 * b1,
        a2 * c1 + c2 * d1,
        b2 * c1 + d2 * d1,
        a2 * e1 + c2 * f1 + e2,
        b2 * e1 + d2 * f1 + f2,
    )


def _apply_affine_point(point: Point, matrix: Affine) -> Point:
    a, b, c, d, e, f = matrix
    x, y = point
    return a * x + c * y + e, b * x + d * y + f


def _apply_affine(points: Sequence[Point], matrix: Affine) -> StrokePoints:
    return [_apply_affine_point(point, matrix) for point in points]


def _apply_affine_to_segments(segments: Sequence[SegmentDict], matrix: Affine) -> List[SegmentDict]:
    return [_transform_segment_dict(segment, lambda p: _apply_affine_point(p, matrix)) for segment in segments]


def _transform_segment_dict(segment: SegmentDict, transform: Callable[[Point], Point]) -> SegmentDict:
    seg_type = segment["type"]
    if seg_type == "move":
        return {"type": "move", "to": list(transform(tuple(segment["to"])))}
    if seg_type == "line":
        return {"type": "line", "to": list(transform(tuple(segment["to"])))}
    if seg_type == "cubicBezier":
        return {
            "type": "cubicBezier",
            "c1": list(transform(tuple(segment["c1"]))),
            "c2": list(transform(tuple(segment["c2"]))),
            "to": list(transform(tuple(segment["to"]))),
        }
    if seg_type == "quadraticBezier":
        return {
            "type": "quadraticBezier",
            "c": list(transform(tuple(segment["c"]))),
            "to": list(transform(tuple(segment["to"]))),
        }
    if seg_type == "polyline":
        return {
            "type": "polyline",
            "points": [list(transform(tuple(point))) for point in segment["points"]],
        }
    raise ValueError(f"Unsupported segment type for transform: {seg_type!r}")


def _segment_control_points(segment: SegmentDict) -> List[Point]:
    seg_type = segment["type"]
    if seg_type == "move":
        return [tuple(segment["to"])]
    if seg_type == "line":
        return [tuple(segment["to"])]
    if seg_type == "cubicBezier":
        return [tuple(segment["c1"]), tuple(segment["c2"]), tuple(segment["to"])]
    if seg_type == "quadraticBezier":
        return [tuple(segment["c"]), tuple(segment["to"])]
    if seg_type == "polyline":
        return [tuple(point) for point in segment["points"]]
    raise ValueError(f"Unsupported segment type for bbox: {seg_type!r}")


def _parse_path_segments(d: str, *, bridge_gap: float = MIN_BRIDGE_GAP) -> List[_StrokeRaw]:
    tokens = [m.group(0) for m in _TOKEN_RE.finditer(d) if m.group(0)]
    subpaths: List[_StrokeRaw] = []
    current_segments: List[SegmentDict] = []
    closed = False
    index = 0
    current = (0.0, 0.0)
    start = (0.0, 0.0)
    z_anchor: Point | None = None
    cmd = "M"
    prev_cmd = ""
    prev_control: Point | None = None

    def read_number() -> float:
        nonlocal index
        value = float(tokens[index])
        index += 1
        return value

    def flush_subpath(is_closed: bool) -> None:
        nonlocal current_segments, closed
        if _is_valid_stroke(current_segments):
            subpaths.append(_StrokeRaw(segments=list(current_segments), closed=is_closed))
        current_segments = []
        closed = False

    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            cmd = token
            index += 1
            if cmd in {"M", "m"}:
                x = read_number()
                y = read_number()
                if cmd == "m":
                    new_start = (current[0] + x, current[1] + y)
                else:
                    new_start = (x, y)
                if (
                    not current_segments
                    and z_anchor is not None
                    and subpaths
                    and subpaths[-1].closed
                    and _distance(z_anchor, new_start) <= bridge_gap
                ):
                    previous = subpaths.pop()
                    current_segments = list(previous.segments)
                    if _distance(z_anchor, new_start) > _EPS:
                        current_segments.append({"type": "line", "to": list(new_start)})
                    current = new_start
                    start = tuple(current_segments[0]["to"])
                    closed = False
                    z_anchor = None
                    prev_control = None
                    cmd = "L" if cmd == "M" else "l"
                    prev_cmd = "M"
                    continue
                if (
                    current_segments
                    and _is_valid_stroke(current_segments)
                    and not closed
                    and _distance(current, new_start) <= bridge_gap
                ):
                    if _distance(current, new_start) > _EPS:
                        current_segments.append({"type": "line", "to": list(new_start)})
                    current = new_start
                    z_anchor = None
                    prev_control = None
                    cmd = "L" if cmd == "M" else "l"
                    prev_cmd = "M"
                    continue
                if current_segments:
                    flush_subpath(closed)
                z_anchor = None
                current = new_start
                start = current
                current_segments = [{"type": "move", "to": list(current)}]
                prev_control = None
                cmd = "L" if cmd == "M" else "l"
                prev_cmd = "M"
                continue
            if cmd in {"Z", "z"}:
                if current != start:
                    current_segments.append({"type": "line", "to": list(start)})
                    current = start
                z_anchor = start
                closed = True
                flush_subpath(True)
                current = start
                prev_control = None
                prev_cmd = "Z"
                continue
            prev_cmd = cmd
            continue

        relative = cmd.islower()
        upper = cmd.upper()

        if upper == "L":
            x = read_number()
            y = read_number()
            point = (current[0] + x, current[1] + y) if relative else (x, y)
            current_segments.append({"type": "line", "to": list(point)})
            current = point
            prev_control = None
        elif upper == "H":
            x = read_number()
            point = (current[0] + x, current[1]) if relative else (x, current[1])
            current_segments.append({"type": "line", "to": list(point)})
            current = point
            prev_control = None
        elif upper == "V":
            y = read_number()
            point = (current[0], current[1] + y) if relative else (current[0], y)
            current_segments.append({"type": "line", "to": list(point)})
            current = point
            prev_control = None
        elif upper == "C":
            c1x = read_number()
            c1y = read_number()
            c2x = read_number()
            c2y = read_number()
            x = read_number()
            y = read_number()
            if relative:
                p1 = (current[0] + c1x, current[1] + c1y)
                p2 = (current[0] + c2x, current[1] + c2y)
                end = (current[0] + x, current[1] + y)
            else:
                p1 = (c1x, c1y)
                p2 = (c2x, c2y)
                end = (x, y)
            current_segments.append(
                {"type": "cubicBezier", "c1": list(p1), "c2": list(p2), "to": list(end)}
            )
            current = end
            prev_control = p2
        elif upper == "S":
            c2x = read_number()
            c2y = read_number()
            x = read_number()
            y = read_number()
            if prev_cmd.upper() in {"C", "S"} and prev_control is not None:
                p1 = _reflect_control(current, prev_control)
            else:
                p1 = current
            if relative:
                p2 = (current[0] + c2x, current[1] + c2y)
                end = (current[0] + x, current[1] + y)
            else:
                p2 = (c2x, c2y)
                end = (x, y)
            current_segments.append(
                {"type": "cubicBezier", "c1": list(p1), "c2": list(p2), "to": list(end)}
            )
            current = end
            prev_control = p2
        elif upper == "Q":
            c1x = read_number()
            c1y = read_number()
            x = read_number()
            y = read_number()
            if relative:
                p1 = (current[0] + c1x, current[1] + c1y)
                end = (current[0] + x, current[1] + y)
            else:
                p1 = (c1x, c1y)
                end = (x, y)
            current_segments.append({"type": "quadraticBezier", "c": list(p1), "to": list(end)})
            current = end
            prev_control = p1
        elif upper == "T":
            x = read_number()
            y = read_number()
            if prev_cmd.upper() in {"Q", "T"} and prev_control is not None:
                p1 = _reflect_control(current, prev_control)
            else:
                p1 = current
            end = (current[0] + x, current[1] + y) if relative else (x, y)
            current_segments.append({"type": "quadraticBezier", "c": list(p1), "to": list(end)})
            current = end
            prev_control = p1
        elif upper == "A":
            rx = read_number()
            ry = read_number()
            rotation = read_number()
            large_arc = int(read_number())
            sweep = int(read_number())
            x = read_number()
            y = read_number()
            end = (current[0] + x, current[1] + y) if relative else (x, y)
            arc_points = _flatten_arc(current, end, rx, ry, rotation, large_arc, sweep, FLATNESS_PX)
            if len(arc_points) >= 2:
                current_segments.append(
                    {"type": "polyline", "points": [list(point) for point in arc_points]}
                )
                current = arc_points[-1]
            prev_control = None
        else:
            raise ValueError(f"Unsupported SVG path command: {cmd}")

        prev_cmd = cmd

    if current_segments:
        flush_subpath(closed)
    return subpaths


def _reflect_control(current: Point, control: Point) -> Point:
    return (2 * current[0] - control[0], 2 * current[1] - control[1])


def _flatten_arc(
    start: Point,
    end: Point,
    rx: float,
    ry: float,
    rotation_deg: float,
    large_arc: int,
    sweep: int,
    tolerance: float,
) -> StrokePoints:
    if start == end:
        return [start]
    if rx == 0 or ry == 0:
        return [start, end]

    rx = abs(rx)
    ry = abs(ry)
    phi = math.radians(rotation_deg % 360)
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)

    dx = (start[0] - end[0]) / 2.0
    dy = (start[1] - end[1]) / 2.0
    x1 = cos_phi * dx + sin_phi * dy
    y1 = -sin_phi * dx + cos_phi * dy

    rx_sq = rx * rx
    ry_sq = ry * ry
    x1_sq = x1 * x1
    y1_sq = y1 * y1
    radii_scale = x1_sq / rx_sq + y1_sq / ry_sq
    if radii_scale > 1:
        scale = math.sqrt(radii_scale)
        rx *= scale
        ry *= scale
        rx_sq = rx * rx
        ry_sq = ry * ry

    numerator = rx_sq * ry_sq - rx_sq * y1_sq - ry_sq * x1_sq
    denominator = rx_sq * y1_sq + ry_sq * x1_sq
    coef = 0.0 if denominator == 0 else math.sqrt(max(0.0, numerator / denominator))
    if large_arc == sweep:
        coef = -coef

    cx1 = coef * ((rx * y1) / ry)
    cy1 = coef * (-(ry * x1) / rx)
    center = (
        cos_phi * cx1 - sin_phi * cy1 + (start[0] + end[0]) / 2.0,
        sin_phi * cx1 + cos_phi * cy1 + (start[1] + end[1]) / 2.0,
    )

    def angle(u: Point, v: Point) -> float:
        dot = u[0] * v[0] + u[1] * v[1]
        det = u[0] * v[1] - u[1] * v[0]
        return math.atan2(det, dot)

    v1 = ((x1 - cx1) / rx, (y1 - cy1) / ry)
    v2 = ((-x1 - cx1) / rx, (-y1 - cy1) / ry)
    theta1 = angle((1.0, 0.0), v1)
    delta = angle(v1, v2)
    if sweep == 0 and delta > 0:
        delta -= 2 * math.pi
    elif sweep == 1 and delta < 0:
        delta += 2 * math.pi

    arc_length = abs(delta) * max(rx, ry)
    segments = max(4, int(math.ceil(arc_length / max(tolerance, 0.1))))
    points: StrokePoints = [start]
    for step in range(1, segments + 1):
        t = step / segments
        arc_angle = theta1 + delta * t
        local = (rx * math.cos(arc_angle), ry * math.sin(arc_angle))
        point = (
            cos_phi * local[0] - sin_phi * local[1] + center[0],
            sin_phi * local[0] + cos_phi * local[1] + center[1],
        )
        points.append(point)
    return points


def _round_point(point: Point) -> Point:
    return round(point[0], 2), round(point[1], 2)


def _round_segment_dict(segment: SegmentDict) -> SegmentDict:
    seg_type = segment["type"]
    if seg_type == "move":
        return {"type": "move", "to": list(_round_point(tuple(segment["to"])))}
    if seg_type == "line":
        return {"type": "line", "to": list(_round_point(tuple(segment["to"])))}
    if seg_type == "cubicBezier":
        return {
            "type": "cubicBezier",
            "c1": list(_round_point(tuple(segment["c1"]))),
            "c2": list(_round_point(tuple(segment["c2"]))),
            "to": list(_round_point(tuple(segment["to"]))),
        }
    if seg_type == "quadraticBezier":
        return {
            "type": "quadraticBezier",
            "c": list(_round_point(tuple(segment["c"]))),
            "to": list(_round_point(tuple(segment["to"]))),
        }
    if seg_type == "polyline":
        return {
            "type": "polyline",
            "points": [list(_round_point(tuple(point))) for point in segment["points"]],
        }
    raise ValueError(f"Unsupported segment type for rounding: {seg_type!r}")


def _bbox_center(points: Sequence[Point]) -> Point:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def _bbox_size(points: Sequence[Point]) -> Tuple[float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def _normalize_segment_strokes(
    strokes: Sequence[Sequence[SegmentDict]],
    *,
    target_half_extent: float = 60.0,
) -> List[List[SegmentDict]]:
    all_points = [
        point
        for stroke in strokes
        for segment in stroke
        for point in _segment_control_points(segment)
    ]
    if not all_points:
        return [list(stroke) for stroke in strokes]

    cx, cy = _bbox_center(all_points)

    def center_and_scale(point: Point) -> Point:
        x = point[0] - cx
        y = point[1] - cy
        return x, y

    centered = [
        [_transform_segment_dict(segment, center_and_scale) for segment in stroke]
        for stroke in strokes
    ]
    flat = [
        point
        for stroke in centered
        for segment in stroke
        for point in _segment_control_points(segment)
    ]
    width, height = _bbox_size(flat)
    max_half = max(width, height) / 2.0
    if max_half <= 1e-6:
        return centered

    scale = target_half_extent / max_half

    def apply_scale(point: Point) -> Point:
        return point[0] * scale, point[1] * scale

    return [
        [_transform_segment_dict(segment, apply_scale) for segment in stroke]
        for stroke in centered
    ]
