"""Transparent overlay preview following the cursor."""

from __future__ import annotations

import tkinter as tk
from typing import List, Optional, Tuple

from core.draw_path import build_stroke_screen_points, preview_max_half_extent
from core.geometry import FLATNESS_PX
from core.transform import TransformState
from presets.models import Preset

Point = Tuple[float, float]


class OverlayPreview:
    def __init__(self, root: tk.Misc) -> None:
        self._root = root
        self._window: Optional[tk.Toplevel] = None
        self._canvas: Optional[tk.Canvas] = None
        self._visible = False
        self._preset: Optional[Preset] = None
        self._transform = TransformState()
        self._half_extent = 120
        self._last_anchor: Point = (0.0, 0.0)
        self._flatness_px = FLATNESS_PX
        self._stroke_color = "#00AAFF"

    def show(self, preset: Preset, transform: TransformState) -> None:
        self._preset = preset
        self._transform = transform
        self._half_extent = preview_max_half_extent(preset, self._flatness_px)
        if self._window is None:
            self._create_window()
        else:
            self._apply_canvas_size()
        self._visible = True
        if self._window is not None:
            self._window.deiconify()

    def hide(self) -> None:
        self._visible = False
        if self._window is not None:
            self._window.withdraw()

    def set_transform(self, transform: TransformState) -> None:
        if not self._visible or self._preset is None:
            return
        self._transform = transform
        self._redraw(self._last_anchor)

    def set_color(self, color: str) -> None:
        self._stroke_color = color
        if self._visible and self._preset is not None and self._canvas is not None:
            self._redraw(self._last_anchor)

    def update_position(self, anchor: Point) -> None:
        if not self._visible or self._preset is None or self._window is None:
            return
        self._last_anchor = anchor
        size = self._half_extent * 2
        ax, ay = anchor
        self._window.geometry(
            f"{size}x{size}+{int(ax - self._half_extent)}+{int(ay - self._half_extent)}"
        )
        self._redraw(anchor)

    def destroy(self) -> None:
        if self._window is not None:
            self._window.destroy()
            self._window = None
            self._canvas = None

    def _create_window(self) -> None:
        self._window = tk.Toplevel(self._root)
        self._window.overrideredirect(True)
        self._window.attributes("-topmost", True)
        self._window.attributes("-transparentcolor", "magenta")
        self._window.configure(bg="magenta")
        self._canvas = tk.Canvas(
            self._window,
            width=self._half_extent * 2,
            height=self._half_extent * 2,
            bg="magenta",
            highlightthickness=0,
        )
        self._canvas.pack()

    def _apply_canvas_size(self) -> None:
        if self._canvas is None:
            return
        size = self._half_extent * 2
        if int(self._canvas["width"]) != size or int(self._canvas["height"]) != size:
            self._canvas.config(width=size, height=size)

    def _redraw(self, anchor: Point) -> None:
        assert self._canvas is not None and self._preset is not None
        self._canvas.delete("all")
        cx = self._half_extent
        cy = self._half_extent
        for stroke in self._preset.strokes:
            screen_points = build_stroke_screen_points(
                stroke.segments,
                anchor,
                self._transform,
                self._flatness_px,
            )
            local_points: List[Tuple[float, float]] = [
                (cx + (x - anchor[0]), cy + (y - anchor[1])) for x, y in screen_points
            ]
            if len(local_points) >= 2:
                flat = [coord for point in local_points for coord in point]
                self._canvas.create_line(*flat, fill=self._stroke_color, width=2, smooth=True)
            elif len(local_points) == 1:
                x, y = local_points[0]
                self._canvas.create_oval(
                    x - 2,
                    y - 2,
                    x + 2,
                    y + 2,
                    outline=self._stroke_color,
                )
