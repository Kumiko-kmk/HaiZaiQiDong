"""Build continuous integer pixel paths for mouse drag drawing."""

from __future__ import annotations

from typing import Iterator, List, Sequence, Tuple

Point = Tuple[float, float]
Pixel = Tuple[int, int]


def iter_bresenham(x0: int, y0: int, x1: int, y1: int) -> Iterator[Pixel]:
    """Yield each pixel from (x0, y0) to (x1, y1), including the end pixel."""
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        if x == x1 and y == y1:
            yield x, y
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
        yield x, y


def build_pixel_path(points: Sequence[Point]) -> List[Pixel]:
    """Chain Bresenham segments into a continuous pixel path without duplicates."""
    if not points:
        return []

    pixels: List[Pixel] = []
    start_x = int(round(points[0][0]))
    start_y = int(round(points[0][1]))
    pixels.append((start_x, start_y))

    for point in points[1:]:
        end_x = int(round(point[0]))
        end_y = int(round(point[1]))
        last_x, last_y = pixels[-1]
        if end_x == last_x and end_y == last_y:
            continue
        for px, py in iter_bresenham(last_x, last_y, end_x, end_y):
            if pixels[-1] != (px, py):
                pixels.append((px, py))

    return pixels
