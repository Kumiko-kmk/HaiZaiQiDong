from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from presets.registry import PresetRegistry


class PresetRegistryOrderingTests(unittest.TestCase):
    def _write_preset(
        self,
        directory: Path,
        preset_id: str,
        *,
        tags: list[str] | None = None,
        menu_order: int | None = None,
    ) -> None:
        data = {
            "id": preset_id,
            "name": preset_id,
            "strokes": [
                {
                    "segments": [
                        {"type": "polyline", "points": [[0, 0], [10, 10]]}
                    ]
                }
            ],
        }
        if tags is not None:
            data["tags"] = tags
        if menu_order is not None:
            data["menuOrder"] = menu_order
        (directory / f"{preset_id}.json").write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_untagged_and_unknown_imports_follow_the_other_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            directory = Path(temporary_dir)
            self._write_preset(directory, "known-warrior", tags=["战士"], menu_order=1)
            self._write_preset(directory, "known-other", tags=["其他"], menu_order=18)
            self._write_preset(directory, "imported-a", tags=["导入", "SVG"])
            self._write_preset(directory, "untagged-z")

            registry = PresetRegistry(directory)

        self.assertEqual(
            [preset.id for preset in registry.list_presets()],
            ["known-warrior", "known-other", "imported-a", "untagged-z"],
        )


if __name__ == "__main__":
    unittest.main()
