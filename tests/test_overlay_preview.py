from __future__ import annotations

import unittest
from unittest.mock import Mock

from gui.overlay_preview import OverlayPreview


class OverlayPreviewColorTests(unittest.TestCase):
    def test_visible_preview_redraws_when_color_changes(self) -> None:
        preview = object.__new__(OverlayPreview)
        preview._visible = True
        preview._preset = Mock()
        preview._canvas = Mock()
        preview._last_anchor = (12.0, 34.0)
        preview._redraw = Mock()

        preview.set_color("#55B979")

        self.assertEqual(preview._stroke_color, "#55B979")
        preview._redraw.assert_called_once_with((12.0, 34.0))

    def test_hidden_preview_only_stores_new_color(self) -> None:
        preview = object.__new__(OverlayPreview)
        preview._visible = False
        preview._preset = None
        preview._canvas = None
        preview._last_anchor = (0.0, 0.0)
        preview._redraw = Mock()

        preview.set_color("#E05252")

        self.assertEqual(preview._stroke_color, "#E05252")
        preview._redraw.assert_not_called()


if __name__ == "__main__":
    unittest.main()
