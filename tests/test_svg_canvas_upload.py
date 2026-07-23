from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock, patch

from gui.app_service import AppService, MAX_SVG_BYTES
from gui.web_api import WebApi
from presets.registry import MAX_CANVAS_STROKES, PresetRegistry
from presets.svg_import import extract_svg_strokes, svg_to_stroke_dicts


class SvgContourParserTests(unittest.TestCase):
    def test_common_shapes_curves_arcs_and_transforms_are_extracted(self) -> None:
        svg = """<svg xmlns="http://www.w3.org/2000/svg">
          <g transform="translate(4 6) scale(2)">
            <path d="M0 0 C2 0 3 2 5 2 Q7 2 8 4 A2 2 0 0 1 10 6" />
            <line x1="20" y1="0" x2="24" y2="4" />
            <polyline points="30,0 32,2 34,0" />
            <polygon points="40,0 44,0 42,4" />
            <circle cx="52" cy="2" r="2" />
            <ellipse cx="62" cy="2" rx="3" ry="2" />
            <rect x="70" y="0" width="5" height="4" />
          </g>
        </svg>"""

        raw_strokes = extract_svg_strokes(svg)
        strokes = svg_to_stroke_dicts(svg)
        segment_types = {
            segment["type"]
            for stroke in strokes
            for segment in stroke["segments"]
        }

        self.assertGreaterEqual(len(raw_strokes), 7)
        self.assertIn("cubicBezier", segment_types)
        self.assertIn("quadraticBezier", segment_types)
        self.assertIn("polyline", segment_types)
        self.assertTrue(any(stroke.closed for stroke in raw_strokes))
        transformed_start = tuple(raw_strokes[0].segments[0]["to"])
        self.assertEqual(transformed_start, (4.0, 6.0))

    def test_invalid_xml_and_empty_svg_are_rejected(self) -> None:
        with self.assertRaises(ET.ParseError):
            svg_to_stroke_dicts("<svg>")
        with self.assertRaisesRegex(ValueError, "no drawable strokes"):
            svg_to_stroke_dicts("<svg />")

    def test_repository_sample_fits_canvas_stroke_limit(self) -> None:
        sample = Path(__file__).resolve().parents[1] / "presets" / "data" / "lineart_star_scene.svg"
        strokes = svg_to_stroke_dicts(sample.read_text(encoding="utf-8"))

        self.assertEqual(len(strokes), 283)
        self.assertLessEqual(len(strokes), MAX_CANVAS_STROKES)


class SvgCanvasServiceTests(unittest.TestCase):
    def _make_service(self, registry: PresetRegistry) -> AppService:
        controller = Mock()
        controller.history.list_entries.return_value = []
        with (
            patch("gui.app_service.get_registry", return_value=registry),
            patch("gui.app_service.InputRouter", return_value=Mock()),
            patch("gui.app_service.DrawController", return_value=controller),
            patch("gui.app_service.OverlayBridge", return_value=Mock()),
        ):
            return AppService()

    def test_svg_is_loaded_as_draft_without_creating_preset_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            data_dir = root / "builtins"
            custom_dir = root / "custom"
            source = root / "fallback-name.svg"
            source.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><title>标题名称</title>'
                '<path d="M0 0 L10 10" /></svg>',
                encoding="utf-8",
            )
            registry = PresetRegistry(data_dir, custom_dir)
            service = self._make_service(registry)

            result = service.load_svg_to_canvas(source)

            self.assertEqual(result["status"], "loaded")
            self.assertEqual(result["suggestedName"], "标题名称")
            self.assertTrue(result["strokes"])
            self.assertEqual(list(custom_dir.rglob("*.json")), [])
            self.assertEqual(list(custom_dir.rglob("*.png")), [])
            self.assertEqual(registry.list_presets(), [])

    def test_filename_is_used_when_svg_has_no_title(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source = root / "轮廓文件.svg"
            source.write_text('<svg><path d="M0 0 L1 1" /></svg>', encoding="utf-8")
            service = self._make_service(PresetRegistry(root / "data", root / "custom"))

            result = service.load_svg_to_canvas(source)

            self.assertEqual(result["status"], "loaded")
            self.assertEqual(result["suggestedName"], "轮廓文件")

    def test_invalid_empty_oversized_and_overcomplex_svg_return_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            service = self._make_service(PresetRegistry(root / "data", root / "custom"))
            cases = {
                "invalid.svg": "<svg>",
                "empty.svg": "<svg />",
                "complex.svg": "<svg>" + "".join(
                    f'<circle cx="{index}" cy="0" r="1" />'
                    for index in range(MAX_CANVAS_STROKES + 1)
                ) + "</svg>",
            }
            for filename, content in cases.items():
                path = root / filename
                path.write_text(content, encoding="utf-8")
                with self.subTest(filename=filename):
                    self.assertEqual(service.load_svg_to_canvas(path)["status"], "error")

            oversized = root / "oversized.svg"
            oversized.write_bytes(b" " * (MAX_SVG_BYTES + 1))
            result = service.load_svg_to_canvas(oversized)
            self.assertEqual(result["status"], "error")
            self.assertIn("2 MB", result["message"])


class SvgCanvasWebApiTests(unittest.TestCase):
    def test_cancelled_dialog_returns_explicit_status_without_calling_service(self) -> None:
        service = Mock()
        api = WebApi(service)
        window = Mock()
        window.create_file_dialog.return_value = None
        api.bind_window(window)

        result = api.load_svg_to_canvas()

        self.assertEqual(result["status"], "cancelled")
        service.load_svg_to_canvas.assert_not_called()

    def test_selected_svg_is_delegated_to_service(self) -> None:
        service = Mock()
        service.load_svg_to_canvas.return_value = {"status": "loaded"}
        api = WebApi(service)
        window = Mock()
        window.create_file_dialog.return_value = [r"C:\drawing.svg"]
        api.bind_window(window)

        result = api.load_svg_to_canvas()

        self.assertEqual(result["status"], "loaded")
        service.load_svg_to_canvas.assert_called_once_with(Path(r"C:\drawing.svg"))


if __name__ == "__main__":
    unittest.main()
