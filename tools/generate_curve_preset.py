"""Generate parametric curve presets (arc, bezier, ellipse)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.app_paths import presets_data_dir


def circle_head_preset() -> dict:
    return {
        "id": "curve_circle_demo",
        "name": "曲线示例：圆",
        "description": "参数化圆弧，非折线近似",
        "tags": ["曲线", "示例"],
        "drawButton": "left",
        "version": 3,
        "strokes": [
            {
                "segments": [
                    {"type": "move", "to": [12, -45]},
                    {
                        "type": "arc",
                        "center": [0, -45],
                        "radius": 12,
                        "startAngle": 0,
                        "endAngle": 360,
                        "closed": True,
                    },
                ]
            }
        ],
    }


def bezier_wave_preset() -> dict:
    return {
        "id": "curve_bezier_demo",
        "name": "曲线示例：贝塞尔波",
        "description": "三次贝塞尔曲线",
        "tags": ["曲线", "示例"],
        "drawButton": "left",
        "version": 3,
        "strokes": [
            {
                "segments": [
                    {"type": "move", "to": [-40, 0]},
                    {"type": "cubicBezier", "c1": [-20, -30], "c2": [20, 30], "to": [40, 0]},
                    {"type": "cubicBezier", "c1": [60, -30], "c2": [80, 30], "to": [100, 0]},
                ]
            }
        ],
    }


def ellipse_arc_preset() -> dict:
    return {
        "id": "curve_ellipse_demo",
        "name": "曲线示例：椭圆弧",
        "description": "参数化椭圆弧",
        "tags": ["曲线", "示例"],
        "drawButton": "left",
        "version": 3,
        "strokes": [
            {
                "segments": [
                    {
                        "type": "ellipse",
                        "center": [0, 0],
                        "rx": 35,
                        "ry": 18,
                        "rotation": -20,
                        "startAngle": 200,
                        "endAngle": 340,
                    }
                ]
            }
        ],
    }


def contour_blob_preset() -> dict:
    return {
        "id": "contour_blob_demo",
        "name": "轮廓示例：卡通形",
        "description": "多笔画贝塞尔轮廓 + 圆弧，演示矢量存储",
        "tags": ["曲线", "轮廓", "示例"],
        "drawButton": "left",
        "version": 3,
        "strokes": [
            {
                "segments": [
                    {"type": "move", "to": [-30, -20]},
                    {"type": "cubicBezier", "c1": [-45, -50], "c2": [10, -55], "to": [35, -25]},
                    {"type": "cubicBezier", "c1": [55, -5], "c2": [40, 35], "to": [0, 45]},
                    {"type": "cubicBezier", "c1": [-40, 35], "c2": [-55, 0], "to": [-30, -20]},
                ]
            },
            {
                "segments": [
                    {"type": "move", "to": [-18, -5]},
                    {
                        "type": "arc",
                        "center": [-12, -5],
                        "radius": 6,
                        "startAngle": 0,
                        "endAngle": 360,
                        "closed": True,
                    },
                ]
            },
            {
                "segments": [
                    {"type": "move", "to": [8, -5]},
                    {
                        "type": "arc",
                        "center": [14, -5],
                        "radius": 6,
                        "startAngle": 0,
                        "endAngle": 360,
                        "closed": True,
                    },
                ]
            },
            {
                "segments": [
                    {"type": "move", "to": [-8, 12]},
                    {"type": "quadraticBezier", "c": [0, 22], "to": [8, 12]},
                ]
            },
        ],
    }


PRESETS = {
    "circle": circle_head_preset,
    "bezier": bezier_wave_preset,
    "ellipse": ellipse_arc_preset,
    "contour": contour_blob_preset,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate parametric curve preset JSON files.")
    parser.add_argument(
        "kind",
        choices=sorted(PRESETS.keys()),
        help="Preset template to generate",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (default: presets/data/<id>.json)",
    )
    args = parser.parse_args()

    preset = PRESETS[args.kind]()
    output = args.output or presets_data_dir() / f"{preset['id']}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        json.dump(preset, handle, ensure_ascii=False, indent=2)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
