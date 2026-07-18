from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from gui.app_service import preset_to_dict


class PresetPreviewTests(unittest.TestCase):
    def test_card_uses_bundled_preview_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            preview = root / "web" / "assets" / "preset-previews" / "sts2_test.png"
            preview.parent.mkdir(parents=True)
            preview.write_bytes(b"png")
            preset = SimpleNamespace(
                id="sts2_test",
                name="测试",
                description="预览测试",
                tags=("战士",),
                strokes=(),
            )

            with patch("gui.app_service.bundle_root", return_value=root):
                card = preset_to_dict(preset)

        self.assertEqual(card["previewUrl"], "assets/preset-previews/sts2_test.png")
        self.assertEqual(card["tags"], ["战士"])

    def test_missing_preview_keeps_vector_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            preset = SimpleNamespace(
                id="missing",
                name="缺失",
                description="",
                strokes=(),
            )
            with patch("gui.app_service.bundle_root", return_value=Path(temporary_dir)):
                card = preset_to_dict(preset)

        self.assertEqual(card["previewUrl"], "")
        self.assertEqual(card["tags"], [])


if __name__ == "__main__":
    unittest.main()
