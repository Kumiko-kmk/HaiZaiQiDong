from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from presets.registry import PresetRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRESET_DIR = PROJECT_ROOT / "presets" / "data"
PREVIEW_DIR = PROJECT_ROOT / "web" / "assets" / "preset-previews"

EXPECTED_PRESETS = (
    ("sts2_fear_no_pain", "战士"),
    ("sts2_hell_berserker", "战士"),
    ("sts2_omnidirectional_slash", "战士"),
    ("sts2_shrug", "战士"),
    ("sts2_grand_finale", "猎手"),
    ("sts2_snake_bite", "猎手"),
    ("sts2_escort", "储君"),
    ("sts2_rally_forward", "储君"),
    ("sts2_honed_blade", "储君"),
    ("sts2_victory_in_hand", "储君"),
    ("sts2_protector", "骨妹"),
    ("sts2_soul_storm", "骨妹"),
    ("sts2_calm_mind", "鸡煲"),
    ("sts2_hailstorm", "鸡煲"),
    ("sts2_iteration", "鸡煲"),
    ("sts2_synchronize", "鸡煲"),
    ("sts2_strict_red_father", "鸡煲"),
    ("sts2_under_pressure", "鸡煲"),
    ("sts2_believe_in_you", "其他"),
    ("sts2_group_huddle", "其他"),
)


class BuiltinPresetLibraryTests(unittest.TestCase):
    def test_library_contains_only_the_twenty_sts2_presets(self) -> None:
        preset_paths = sorted(PRESET_DIR.glob("*.json"))

        self.assertEqual(len(preset_paths), 20)
        self.assertTrue(all(path.stem.startswith("sts2_") for path in preset_paths))

    def test_every_preset_has_exactly_one_matching_card_preview(self) -> None:
        preset_paths = sorted(PRESET_DIR.glob("*.json"))
        preview_paths = sorted(PREVIEW_DIR.glob("*.png"))
        preset_ids = set()
        for path in preset_paths:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["id"], path.stem)
            preset_ids.add(data["id"])

        self.assertEqual({path.stem for path in preview_paths}, preset_ids)

    def test_presets_have_the_expected_owner_tags_and_menu_order(self) -> None:
        expected_by_id = {
            preset_id: (owner_tag, menu_order)
            for menu_order, (preset_id, owner_tag) in enumerate(EXPECTED_PRESETS, start=1)
        }
        for path in PRESET_DIR.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            owner_tag, menu_order = expected_by_id[data["id"]]
            self.assertEqual(data["tags"], [owner_tag], path.name)
            self.assertEqual(data["menuOrder"], menu_order, path.name)

    def test_registry_lists_presets_in_owner_and_menu_order(self) -> None:
        registry = PresetRegistry(PRESET_DIR)
        actual = [(preset.id, preset.tags[0]) for preset in registry.list_presets()]
        self.assertEqual(actual, list(EXPECTED_PRESETS))

    def test_presets_do_not_reintroduce_dense_tiny_strokes(self) -> None:
        for path in PRESET_DIR.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            stroke_limit = 320 if path.stem == "sts2_protector" else 240
            self.assertLessEqual(len(data["strokes"]), stroke_limit, path.name)
            for stroke in data["strokes"]:
                points = stroke["segments"][0]["points"]
                length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
                self.assertGreaterEqual(length, 8.5, path.name)


if __name__ == "__main__":
    unittest.main()
