from __future__ import annotations

import unittest

from core.preset_fit import fit_scale_for_preset
from presets.models import Preset


def rectangle_preset(preset_id: str, width: float, height: float) -> Preset:
    half_w = width / 2.0
    half_h = height / 2.0
    return Preset.from_dict(
        {
            "id": preset_id,
            "name": preset_id,
            "version": 3,
            "strokes": [
                {
                    "segments": [
                        {
                            "type": "polyline",
                            "points": [
                                [-half_w, -half_h],
                                [half_w, -half_h],
                                [half_w, half_h],
                                [-half_w, half_h],
                            ],
                        }
                    ]
                }
            ],
        }
    )


class PresetFitTests(unittest.TestCase):
    def test_landscape_preset_uses_landscape_target(self) -> None:
        preset = rectangle_preset("landscape", 400, 200)

        self.assertAlmostEqual(fit_scale_for_preset(preset, 1920, 1080), 1.2)

    def test_portrait_preset_uses_portrait_target(self) -> None:
        preset = rectangle_preset("portrait", 200, 400)

        self.assertAlmostEqual(fit_scale_for_preset(preset, 1920, 1080), 1.2)


if __name__ == "__main__":
    unittest.main()
