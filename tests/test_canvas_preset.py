from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from gui.app_service import AppService, decode_png_data_url
from presets.registry import PNG_SIGNATURE, PresetRegistry


class CanvasPresetRegistryTests(unittest.TestCase):
    def test_custom_preset_can_be_renamed_and_deleted_with_its_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            registry = PresetRegistry(Path(temporary_dir))
            preset = registry.create_canvas_preset(
                name="旧名称",
                strokes=[[[0.1, 0.1], [0.9, 0.9]]],
                canvas_width=400,
                canvas_height=200,
                preview_png=PNG_SIGNATURE + b"preview",
            )
            preset_path = Path(temporary_dir) / f"{preset.id}.json"
            preview_path = registry.preview_path(preset.id)

            renamed = registry.rename_custom_preset(preset.id, "新名称")

            self.assertEqual(renamed.name, "新名称")
            self.assertEqual(
                json.loads(preset_path.read_text(encoding="utf-8"))["name"],
                "新名称",
            )
            self.assertTrue(preview_path.is_file())

            deleted = registry.delete_custom_preset(preset.id)

            self.assertEqual(deleted.name, "新名称")
            self.assertFalse(preset_path.exists())
            self.assertFalse(preview_path.exists())
            self.assertEqual(registry.list_presets(), [])

    def test_builtin_preset_cannot_be_managed(self) -> None:
        with (
            tempfile.TemporaryDirectory() as builtin_dir,
            tempfile.TemporaryDirectory() as custom_dir,
        ):
            builtin_path = Path(builtin_dir) / "builtin.json"
            builtin_path.write_text(
                json.dumps(
                    {
                        "id": "builtin",
                        "name": "内置",
                        "version": 1,
                        "tags": ["其他"],
                        "strokes": [{"points": [[0, 0], [1, 1]]}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry = PresetRegistry(Path(builtin_dir), Path(custom_dir))

            with self.assertRaisesRegex(ValueError, "只能重命名"):
                registry.rename_custom_preset("builtin", "新名称")
            with self.assertRaisesRegex(ValueError, "只能删除"):
                registry.delete_custom_preset("builtin")

            self.assertTrue(builtin_path.exists())

    def test_canvas_preset_is_saved_with_preview_and_other_tag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            registry = PresetRegistry(Path(temporary_dir))

            preset = registry.create_canvas_preset(
                name="我的图案",
                strokes=[[[0.1, 0.2], [0.5, 0.4], [0.9, 0.8]]],
                canvas_width=400,
                canvas_height=200,
                preview_png=PNG_SIGNATURE + b"preview",
            )

            preset_path = Path(temporary_dir) / f"{preset.id}.json"
            saved = json.loads(preset_path.read_text(encoding="utf-8"))
            preview_path = registry.preview_path(preset.id)

            self.assertEqual(preset.tags, ("其他", "自定义"))
            self.assertEqual(saved["tags"], ["其他", "自定义"])
            self.assertEqual(
                saved["strokes"][0]["segments"][0]["points"],
                [[-160.0, -60.0], [0.0, -20.0], [160.0, 60.0]],
            )
            self.assertIsNotNone(preview_path)
            self.assertEqual(preview_path.read_bytes(), PNG_SIGNATURE + b"preview")

            reloaded = PresetRegistry(Path(temporary_dir))
            self.assertEqual([item.id for item in reloaded.list_presets()], [preset.id])

    def test_invalid_canvas_data_leaves_no_partial_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            registry = PresetRegistry(Path(temporary_dir))

            with self.assertRaisesRegex(ValueError, "预览图格式无效"):
                registry.create_canvas_preset(
                    name="无效图案",
                    strokes=[[[0.0, 0.0], [1.0, 1.0]]],
                    canvas_width=400,
                    canvas_height=200,
                    preview_png=b"not-a-png",
                )

            self.assertEqual(list(Path(temporary_dir).rglob("*")), [])

    def test_stationary_point_is_saved_as_a_centered_dot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            registry = PresetRegistry(Path(temporary_dir))

            preset = registry.create_canvas_preset(
                name="只有一点",
                strokes=[[[0.5, 0.5], [0.5, 0.5], [2.0, 2.0]]],
                canvas_width=400,
                canvas_height=200,
                preview_png=PNG_SIGNATURE,
            )

            self.assertEqual(preset.strokes[0].points, [(0.0, 0.0)])


class CanvasPresetServiceTests(unittest.TestCase):
    def test_service_returns_selected_saved_preset_and_embedded_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            registry = PresetRegistry(Path(temporary_dir))
            controller = Mock()
            controller.history.list_entries.return_value = []
            with (
                patch("gui.app_service.get_registry", return_value=registry),
                patch("gui.app_service.InputRouter", return_value=Mock()),
                patch("gui.app_service.DrawController", return_value=controller),
                patch("gui.app_service.OverlayBridge", return_value=Mock()),
            ):
                service = AppService()

            preview = PNG_SIGNATURE + b"preview"
            state = service.save_canvas_preset(
                {
                    "name": "服务测试",
                    "canvasWidth": 300,
                    "canvasHeight": 150,
                    "strokes": [[[0.1, 0.1], [0.9, 0.9]]],
                    "previewDataUrl": "data:image/png;base64,"
                    + base64.b64encode(preview).decode("ascii"),
                }
            )

            self.assertEqual(state["savedPresetId"], state["selectedPresetId"])
            self.assertEqual(state["presets"][0]["tags"][:1], ["其他"])
            self.assertTrue(state["presets"][0]["previewUrl"].startswith("data:image/png;base64,"))
            self.assertIn("已保存到“其他”", state["message"])

            preset_id = state["savedPresetId"]
            renamed_state = service.rename_custom_preset(preset_id, "服务重命名")
            self.assertEqual(renamed_state["renamedPresetId"], preset_id)
            self.assertEqual(
                next(item for item in renamed_state["presets"] if item["id"] == preset_id)["name"],
                "服务重命名",
            )

            deleted_state = service.delete_custom_preset(preset_id)
            self.assertEqual(deleted_state["deletedPresetId"], preset_id)
            self.assertNotIn(preset_id, [item["id"] for item in deleted_state["presets"]])

    def test_png_data_url_decoder_rejects_non_png_data_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "预览图格式无效"):
            decode_png_data_url("data:image/jpeg;base64,AAAA")


class CanvasPageContractTests(unittest.TestCase):
    def test_navigation_and_canvas_controls_are_present(self) -> None:
        index_path = Path(__file__).resolve().parents[1] / "web" / "index.html"
        html = index_path.read_text(encoding="utf-8")

        self.assertIn('data-page="canvas"', html)
        self.assertIn('id="sketch-canvas"', html)
        self.assertIn('id="btn-canvas-clear"', html)
        self.assertIn('id="btn-canvas-save"', html)
        self.assertIn('id="btn-manage-presets"', html)
        self.assertIn('class="canvas-toolbar__drag pywebview-drag-region"', html)
        self.assertIn('id="save-preset-dialog"', html)
        self.assertIn('id="manage-presets-dialog"', html)
        self.assertIn('id="manage-preset-list"', html)
        self.assertNotIn("拖动画笔创作自定义预设", html)
        self.assertNotIn('<span class="nav-btn__label">预设</span>', html)


if __name__ == "__main__":
    unittest.main()
