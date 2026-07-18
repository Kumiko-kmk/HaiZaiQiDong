"""Convert clean black-on-white line art into lightweight preset JSON files.

This is an offline preparation tool.  Pillow and NumPy are intentionally not
runtime dependencies of the drawing application.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
from PIL import Image, ImageDraw


Point = tuple[int, int]
FloatPoint = tuple[float, float]
NEIGHBOURS: tuple[Point, ...] = (
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
)


@dataclass(frozen=True)
class PresetSpec:
    source_name: str
    preset_id: str
    display_name: str
    owner_tag: str
    menu_order: int


PRESETS: tuple[PresetSpec, ...] = (
    PresetSpec("无惧疼痛.png", "sts2_fear_no_pain", "无惧疼痛", "战士", 1),
    PresetSpec("地狱狂徒.png", "sts2_hell_berserker", "地狱狂徒", "战士", 2),
    PresetSpec("万向斩.png", "sts2_omnidirectional_slash", "万向斩", "战士", 3),
    PresetSpec("耸肩无视.png", "sts2_shrug", "耸肩无视", "战士", 4),
    PresetSpec("华丽收场.png", "sts2_grand_finale", "华丽收场", "猎手", 5),
    PresetSpec("蛇咬.png", "sts2_snake_bite", "蛇咬", "猎手", 6),
    PresetSpec("护驾.png", "sts2_escort", "护驾", "储君", 7),
    PresetSpec("征召上前.png", "sts2_rally_forward", "征召上前", "储君", 8),
    PresetSpec("淬炼刀刃.png", "sts2_honed_blade", "淬炼刀刃", "储君", 9),
    PresetSpec("胜券在王.png", "sts2_victory_in_hand", "胜券在王", "储君", 10),
    PresetSpec("保护者.png", "sts2_protector", "保护者", "骨妹", 11),
    PresetSpec("灵魂风暴.png", "sts2_soul_storm", "灵魂风暴", "骨妹", 12),
    PresetSpec("冷静头脑.png", "sts2_calm_mind", "冷静头脑", "鸡煲", 13),
    PresetSpec("冰雹风暴.png", "sts2_hailstorm", "冰雹风暴", "鸡煲", 14),
    PresetSpec("迭代.png", "sts2_iteration", "迭代", "鸡煲", 15),
    PresetSpec("同步.png", "sts2_synchronize", "同步", "鸡煲", 16),
    PresetSpec("小红严父.png", "sts2_strict_red_father", "小红严父", "鸡煲", 17),
    PresetSpec("抗压.png", "sts2_under_pressure", "抗压", "鸡煲", 18),
    PresetSpec("相信着你.png", "sts2_believe_in_you", "相信着你", "其他", 19),
    PresetSpec("抱团.png", "sts2_group_huddle", "抱团", "其他", 20),
)


def _shift(mask: np.ndarray, dy: int, dx: int) -> np.ndarray:
    shifted = np.zeros_like(mask)
    src_y = slice(max(0, -dy), mask.shape[0] - max(0, dy))
    src_x = slice(max(0, -dx), mask.shape[1] - max(0, dx))
    dst_y = slice(max(0, dy), mask.shape[0] - max(0, -dy))
    dst_x = slice(max(0, dx), mask.shape[1] - max(0, -dx))
    shifted[dst_y, dst_x] = mask[src_y, src_x]
    return shifted


def zhang_suen_thinning(mask: np.ndarray, max_iterations: int = 100) -> np.ndarray:
    """Return a one-pixel centreline using vectorised Zhang-Suen thinning."""
    image = mask.astype(bool, copy=True)
    for _ in range(max_iterations):
        changed = False
        for first_step in (True, False):
            p2 = _shift(image, 1, 0)
            p3 = _shift(image, 1, -1)
            p4 = _shift(image, 0, -1)
            p5 = _shift(image, -1, -1)
            p6 = _shift(image, -1, 0)
            p7 = _shift(image, -1, 1)
            p8 = _shift(image, 0, 1)
            p9 = _shift(image, 1, 1)
            neighbours = (p2, p3, p4, p5, p6, p7, p8, p9)
            count = sum(neighbour.astype(np.uint8) for neighbour in neighbours)
            transitions = sum(
                ((~neighbours[index]) & neighbours[(index + 1) % 8]).astype(np.uint8)
                for index in range(8)
            )
            if first_step:
                side_a = ~(p2 & p4 & p6)
                side_b = ~(p4 & p6 & p8)
            else:
                side_a = ~(p2 & p4 & p8)
                side_b = ~(p2 & p6 & p8)
            remove = image & (count >= 2) & (count <= 6) & (transitions == 1) & side_a & side_b
            if remove.any():
                image[remove] = False
                changed = True
        if not changed:
            break
    return image


def remove_small_components(mask: np.ndarray, minimum_pixels: int) -> set[Point]:
    remaining = {(int(x), int(y)) for y, x in np.argwhere(mask)}
    kept: set[Point] = set()
    while remaining:
        seed = remaining.pop()
        component = {seed}
        stack = [seed]
        while stack:
            x, y = stack.pop()
            for dx, dy in NEIGHBOURS:
                neighbour = (x + dx, y + dy)
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    component.add(neighbour)
                    stack.append(neighbour)
        if len(component) >= minimum_pixels:
            kept.update(component)
    return kept


def _neighbours(point: Point, pixels: set[Point]) -> list[Point]:
    x, y = point
    linked: list[Point] = []
    for dx, dy in NEIGHBOURS:
        neighbour = (x + dx, y + dy)
        if neighbour not in pixels:
            continue
        # A diagonal next to an orthogonal connection creates a redundant
        # triangle in an 8-connected skeleton and fragments paths at corners.
        if dx and dy and ((x + dx, y) in pixels or (x, y + dy) in pixels):
            continue
        linked.append(neighbour)
    return linked


def _edge(a: Point, b: Point) -> frozenset[Point]:
    return frozenset((a, b))


def trace_skeleton(pixels: set[Point]) -> list[list[Point]]:
    adjacency = {point: _neighbours(point, pixels) for point in pixels}
    visited: set[frozenset[Point]] = set()
    paths: list[list[Point]] = []

    def walk(start: Point) -> list[Point]:
        path = [start]
        previous: Point | None = None
        current = start
        while True:
            candidates = [point for point in adjacency[current] if _edge(current, point) not in visited]
            if not candidates:
                break
            if previous is None:
                following = min(candidates)
            else:
                incoming = (current[0] - previous[0], current[1] - previous[1])
                # Continue as straight as possible through a junction.  This
                # preserves the visual stroke and avoids needless pen lifts.
                following = max(
                    candidates,
                    key=lambda point: (
                        incoming[0] * (point[0] - current[0])
                        + incoming[1] * (point[1] - current[1]),
                        point,
                    ),
                )
            visited.add(_edge(current, following))
            path.append(following)
            previous, current = current, following
        return path

    # Odd-degree points are natural trail endpoints.  Remaining even-degree
    # components are closed loops and are handled by the second pass.
    starts = sorted(point for point, linked in adjacency.items() if len(linked) % 2 == 1)
    starts.extend(sorted(pixels))
    for start in starts:
        while any(_edge(start, point) not in visited for point in adjacency[start]):
            path = walk(start)
            if len(path) >= 2:
                paths.append(path)
    return paths


def path_length(points: Sequence[FloatPoint]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def rdp(points: Sequence[FloatPoint], tolerance: float) -> list[FloatPoint]:
    if len(points) <= 2:
        return list(points)
    start, end = points[0], points[-1]
    dx, dy = end[0] - start[0], end[1] - start[1]
    denominator = math.hypot(dx, dy)
    best_distance = -1.0
    best_index = 0
    for index, point in enumerate(points[1:-1], 1):
        if denominator == 0:
            distance = math.dist(start, point)
        else:
            distance = abs(dy * point[0] - dx * point[1] + end[0] * start[1] - end[1] * start[0]) / denominator
        if distance > best_distance:
            best_distance = distance
            best_index = index
    if best_distance <= tolerance:
        return [start, end]
    return rdp(points[: best_index + 1], tolerance)[:-1] + rdp(points[best_index:], tolerance)


def chaikin_smooth(points: Sequence[FloatPoint], iterations: int) -> list[FloatPoint]:
    """Round polyline corners without changing the path's overall topology."""
    result = list(points)
    for _ in range(iterations):
        if len(result) < 3:
            break
        closed = result[0] == result[-1]
        source = result[:-1] if closed else result
        smoothed: list[FloatPoint] = [] if closed else [source[0]]
        pairs = zip(source, source[1:] + ([source[0]] if closed else []))
        for first, second in pairs:
            smoothed.append((0.75 * first[0] + 0.25 * second[0], 0.75 * first[1] + 0.25 * second[1]))
            smoothed.append((0.25 * first[0] + 0.75 * second[0], 0.25 * first[1] + 0.75 * second[1]))
        if closed:
            smoothed.append(smoothed[0])
        else:
            smoothed.append(source[-1])
        result = smoothed
    return result


def load_line_mask(path: Path, max_dimension: int, threshold: int) -> np.ndarray:
    with Image.open(path) as source:
        image = source.convert("L")
        scale = min(1.0, max_dimension / max(image.size))
        if scale < 1.0:
            size = tuple(max(1, round(value * scale)) for value in image.size)
            image = image.resize(size, Image.Resampling.LANCZOS)
        array = np.asarray(image)
    return array < threshold


def centre_paths(paths: Iterable[Sequence[FloatPoint]]) -> list[list[FloatPoint]]:
    materialised = [list(path) for path in paths]
    xs = [point[0] for path in materialised for point in path]
    ys = [point[1] for path in materialised for point in path]
    centre_x = (min(xs) + max(xs)) / 2.0
    centre_y = (min(ys) + max(ys)) / 2.0
    return [[(round(x - centre_x, 2), round(y - centre_y, 2)) for x, y in path] for path in materialised]


def convert_image(
    path: Path,
    *,
    max_dimension: int,
    threshold: int,
    minimum_component: int,
    minimum_path_length: float,
    simplify_tolerance: float,
    smooth_iterations: int = 0,
) -> list[list[FloatPoint]]:
    skeleton = zhang_suen_thinning(load_line_mask(path, max_dimension, threshold))
    pixels = remove_small_components(skeleton, minimum_component)
    raw_paths = trace_skeleton(pixels)
    paths: list[list[FloatPoint]] = []
    for raw_path in raw_paths:
        float_path = [(float(x), float(y)) for x, y in raw_path]
        if path_length(float_path) < minimum_path_length:
            continue
        simplified = rdp(float_path, simplify_tolerance)
        # RDP shortens zig-zag paths.  Apply the brush-aware threshold to the
        # final geometry as well so tiny remnants cannot re-enter the preset.
        if len(simplified) >= 2 and path_length(simplified) >= minimum_path_length:
            smoothed = chaikin_smooth(simplified, smooth_iterations)
            if path_length(smoothed) >= minimum_path_length:
                paths.append(smoothed)
    if not paths:
        raise ValueError(f"No drawable paths found in {path}")
    return centre_paths(paths)


def preset_dict(spec: PresetSpec, paths: Sequence[Sequence[FloatPoint]]) -> dict:
    return {
        "id": spec.preset_id,
        "name": spec.display_name,
        "description": "由《杀戮尖塔2》图片提炼并适度清理短线的轻量黑白线稿预设",
        "tags": [spec.owner_tag],
        "menuOrder": spec.menu_order,
        "drawButton": "right",
        "version": 3,
        "strokes": [
            {"segments": [{"type": "polyline", "points": [[x, y] for x, y in path]}]}
            for path in paths
        ],
    }


def render_preview(
    paths: Sequence[Sequence[FloatPoint]],
    output: Path,
    *,
    line_width: int = 1,
) -> None:
    xs = [point[0] for path in paths for point in path]
    ys = [point[1] for path in paths for point in path]
    margin = 12
    width = math.ceil(max(xs) - min(xs)) + margin * 2 + 1
    height = math.ceil(max(ys) - min(ys)) + margin * 2 + 1
    offset_x = margin - min(xs)
    offset_y = margin - min(ys)
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    for path in paths:
        draw.line(
            [(x + offset_x, y + offset_y) for x, y in path],
            fill=0,
            width=line_width,
            joint="curve",
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path, help="Directory containing cleaned PNG line art")
    parser.add_argument("output_dir", type=Path, help="Destination for preset JSON files")
    parser.add_argument("--max-dimension", type=int, default=420)
    parser.add_argument("--threshold", type=int, default=205)
    parser.add_argument("--minimum-component", type=int, default=7)
    parser.add_argument("--minimum-path-length", type=float, default=9.0)
    parser.add_argument("--simplify", type=float, default=1.15)
    parser.add_argument(
        "--smooth-iterations",
        type=int,
        default=0,
        help="Optional Chaikin passes for artwork that needs softer curves",
    )
    parser.add_argument("--preview-dir", type=Path, default=None, help="Optional rendered-vector QA previews")
    parser.add_argument(
        "--preview-line-width",
        type=int,
        default=1,
        help="Preview stroke width used to simulate the target brush",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="ID_OR_NAME",
        help="Generate only the matching preset id or display name; repeat as needed",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    requested = set(args.only)
    selected = [
        spec
        for spec in PRESETS
        if not requested or spec.preset_id in requested or spec.display_name in requested
    ]
    matched = {spec.preset_id for spec in selected} | {spec.display_name for spec in selected}
    unknown = requested - matched
    if unknown:
        parser.error(f"unknown preset selector(s): {', '.join(sorted(unknown))}")

    for spec in selected:
        source = args.source_dir / spec.source_name
        if not source.is_file():
            raise FileNotFoundError(source)
        paths = convert_image(
            source,
            max_dimension=args.max_dimension,
            threshold=args.threshold,
            minimum_component=args.minimum_component,
            minimum_path_length=args.minimum_path_length,
            simplify_tolerance=args.simplify,
            smooth_iterations=max(0, args.smooth_iterations),
        )
        preset = preset_dict(spec, paths)
        output = args.output_dir / f"{spec.preset_id}.json"
        output.write_text(json.dumps(preset, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        if args.preview_dir is not None:
            render_preview(
                paths,
                args.preview_dir / spec.source_name,
                line_width=max(1, args.preview_line_width),
            )
        points = sum(len(path) for path in paths)
        length = sum(path_length(path) for path in paths)
        print(f"{spec.display_name}: {len(paths)} strokes, {points} points, {length:.0f} px -> {output.name}")


if __name__ == "__main__":
    main()
