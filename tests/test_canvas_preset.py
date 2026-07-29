from __future__ import annotations

import json
import unittest

from gui.app_service import decode_png_data_url
from gui.state import AppState
from presets.registry import PNG_SIGNATURE, PresetRegistry
from tests.support import (
    WEB_ROOT,
    RegistryTestCase,
    make_app_service,
    png_data_url,
    write_preset,
)


class CanvasPresetRegistryTests(RegistryTestCase):
    def test_custom_preset_can_be_renamed_and_deleted_with_its_preview(self) -> None:
        preset = self.registry.create_canvas_preset(
            name="旧名称",
            strokes=[[[0.1, 0.1], [0.9, 0.9]]],
            canvas_width=400,
            canvas_height=200,
            preview_png=PNG_SIGNATURE + b"preview",
        )
        preset_path = self.root / f"{preset.id}.json"
        preview_path = self.registry.preview_path(preset.id)

        renamed = self.registry.rename_custom_preset(preset.id, "新名称")

        self.assertEqual(renamed.name, "新名称")
        self.assertEqual(
            json.loads(preset_path.read_text(encoding="utf-8"))["name"],
            "新名称",
        )
        self.assertTrue(preview_path.is_file())

        deleted = self.registry.delete_custom_preset(preset.id)

        self.assertEqual(deleted.name, "新名称")
        self.assertFalse(preset_path.exists())
        self.assertFalse(preview_path.exists())
        self.assertEqual(self.registry.list_presets(), [])

    def test_builtin_preset_cannot_be_managed(self) -> None:
        registry = self.make_registry(split=True)
        builtin_path = write_preset(self.builtin_dir, "builtin", tags=["其他"])
        registry.reload()

        with self.assertRaisesRegex(ValueError, "只能重命名"):
            registry.rename_custom_preset("builtin", "新名称")
        with self.assertRaisesRegex(ValueError, "只能删除"):
            registry.delete_custom_preset("builtin")
        with self.assertRaisesRegex(ValueError, "只能更改"):
            registry.update_canvas_preset(
                "builtin",
                name="更改",
                strokes=[[[0.0, 0.0], [1.0, 1.0]]],
                canvas_width=400,
                canvas_height=200,
                preview_png=PNG_SIGNATURE,
            )

        self.assertTrue(builtin_path.exists())

    def test_canvas_preset_is_saved_with_preview_and_other_tag(self) -> None:
        preset = self.registry.create_canvas_preset(
            name="我的图案",
            strokes=[[[0.1, 0.2], [0.5, 0.4], [0.9, 0.8]]],
            canvas_width=400,
            canvas_height=200,
            preview_png=PNG_SIGNATURE + b"preview",
        )

        saved = json.loads(
            (self.root / f"{preset.id}.json").read_text(encoding="utf-8")
        )
        preview_path = self.registry.preview_path(preset.id)

        self.assertEqual(preset.tags, ("其他", "自定义"))
        self.assertEqual(saved["tags"], ["其他", "自定义"])
        self.assertEqual(
            saved["strokes"][0]["segments"][0]["points"],
            [[-160.0, -60.0], [0.0, -20.0], [160.0, 60.0]],
        )
        self.assertIsNotNone(preview_path)
        self.assertEqual(preview_path.read_bytes(), PNG_SIGNATURE + b"preview")
        self.assertEqual(
            [item.id for item in PresetRegistry(self.root).list_presets()],
            [preset.id],
        )

    def test_canvas_preset_can_be_updated_in_place(self) -> None:
        original = self.registry.create_canvas_preset(
            name="修改前",
            strokes=[[[0.1, 0.1], [0.9, 0.9]]],
            canvas_width=400,
            canvas_height=200,
            preview_png=PNG_SIGNATURE + b"old",
        )
        preset_path = self.root / f"{original.id}.json"
        preview_path = self.registry.preview_path(original.id)

        updated = self.registry.update_canvas_preset(
            original.id,
            name="修改后",
            strokes=[[[0.2, 0.8], [0.5, 0.2], [0.8, 0.8]]],
            canvas_width=400,
            canvas_height=200,
            preview_png=PNG_SIGNATURE + b"new",
        )

        self.assertEqual(updated.id, original.id)
        self.assertEqual(updated.name, "修改后")
        self.assertEqual(preview_path.read_bytes(), PNG_SIGNATURE + b"new")
        self.assertEqual(len(list(self.root.glob("*.json"))), 1)
        saved = json.loads(preset_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["id"], original.id)
        self.assertEqual(saved["name"], "修改后")
        self.assertEqual(len(saved["strokes"][0]["segments"][0]["points"]), 3)
        self.assertEqual(PresetRegistry(self.root).list_presets()[0].name, "修改后")

    def test_invalid_canvas_data_leaves_no_partial_files(self) -> None:
        with self.assertRaisesRegex(ValueError, "预览图格式无效"):
            self.registry.create_canvas_preset(
                name="无效图案",
                strokes=[[[0.0, 0.0], [1.0, 1.0]]],
                canvas_width=400,
                canvas_height=200,
                preview_png=b"not-a-png",
            )

        self.assertEqual(list(self.root.rglob("*")), [])

    def test_stationary_point_is_saved_as_a_centered_dot(self) -> None:
        preset = self.registry.create_canvas_preset(
            name="只有一点",
            strokes=[[[0.5, 0.5], [0.5, 0.5], [2.0, 2.0]]],
            canvas_width=400,
            canvas_height=200,
            preview_png=PNG_SIGNATURE,
        )

        self.assertEqual(preset.strokes[0].points, [(0.0, 0.0)])


class CanvasPresetServiceTests(RegistryTestCase):
    def test_service_returns_selected_saved_preset_and_embedded_preview(self) -> None:
        harness = make_app_service(registry=self.registry, state=AppState.IDLE)
        service = harness.service
        service.selected_preset = None

        state = service.save_canvas_preset(
            {
                "name": "服务测试",
                "canvasWidth": 300,
                "canvasHeight": 150,
                "strokes": [[[0.1, 0.1], [0.9, 0.9]]],
                "previewDataUrl": png_data_url(b"preview"),
            }
        )

        self.assertEqual(state["savedPresetId"], state["selectedPresetId"])
        self.assertEqual(state["presets"][0]["tags"][:1], ["其他"])
        self.assertTrue(
            state["presets"][0]["previewUrl"].startswith("data:image/png;base64,")
        )
        self.assertIn("已保存到“其他”", state["message"])

        preset_id = state["savedPresetId"]
        edit_draft = service.load_custom_preset_for_edit(preset_id)
        self.assertEqual(edit_draft["status"], "loaded")
        self.assertEqual(edit_draft["presetId"], preset_id)
        self.assertEqual(edit_draft["suggestedName"], "服务测试")

        updated_state = service.update_canvas_preset(
            preset_id,
            {
                "name": "服务更改",
                "canvasWidth": 300,
                "canvasHeight": 150,
                "strokes": [[[0.2, 0.8], [0.5, 0.2], [0.8, 0.8]]],
                "previewDataUrl": png_data_url(b"updated"),
            },
        )
        self.assertEqual(updated_state["updatedPresetId"], preset_id)
        self.assertEqual(updated_state["selectedPresetId"], preset_id)
        self.assertEqual(
            next(
                item for item in updated_state["presets"] if item["id"] == preset_id
            )["name"],
            "服务更改",
        )
        self.assertIn("已更新", updated_state["message"])

        renamed_state = service.rename_custom_preset(preset_id, "服务重命名")
        self.assertEqual(renamed_state["renamedPresetId"], preset_id)
        self.assertEqual(
            next(
                item for item in renamed_state["presets"] if item["id"] == preset_id
            )["name"],
            "服务重命名",
        )

        deleted_state = service.delete_custom_preset(preset_id)
        self.assertEqual(deleted_state["deletedPresetId"], preset_id)
        self.assertNotIn(
            preset_id,
            [item["id"] for item in deleted_state["presets"]],
        )

    def test_png_data_url_decoder_rejects_non_png_data_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "预览图格式无效"):
            decode_png_data_url("data:image/jpeg;base64,AAAA")


class CanvasPageContractTests(unittest.TestCase):
    def test_navigation_and_canvas_controls_are_present(self) -> None:
        index_path = WEB_ROOT / "index.html"
        html = index_path.read_text(encoding="utf-8")

        self.assertIn('data-page="canvas"', html)
        self.assertIn('id="sketch-canvas"', html)
        self.assertIn('id="btn-canvas-upload-svg"', html)
        self.assertIn('id="btn-canvas-pencil"', html)
        self.assertIn('id="btn-canvas-eraser"', html)
        self.assertIn('id="btn-canvas-undo"', html)
        self.assertIn('id="btn-canvas-redo"', html)
        self.assertIn('id="btn-canvas-clear"', html)
        tool_order = [
            html.index('id="btn-canvas-pencil"'),
            html.index('id="btn-canvas-eraser"'),
            html.index('id="btn-canvas-undo"'),
            html.index('id="btn-canvas-redo"'),
            html.index('id="btn-canvas-clear"'),
        ]
        self.assertEqual(tool_order, sorted(tool_order))
        self.assertIn('id="btn-canvas-save"', html)
        self.assertIn('id="btn-manage-presets"', html)
        self.assertNotIn('>清空画布</button>', html)
        self.assertIn('class="canvas-toolbar__drag pywebview-drag-region"', html)
        self.assertIn('class="draw-drag-zone draw-drag-zone--left pywebview-drag-region"', html)
        self.assertIn('class="draw-drag-zone draw-drag-zone--bottom pywebview-drag-region"', html)
        self.assertIn('class="history-drag-rail pywebview-drag-region"', html)
        self.assertEqual(html.count('class="setting-row__drag pywebview-drag-region"'), 3)
        self.assertIn('class="settings-drag-fill pywebview-drag-region"', html)
        self.assertIn('id="save-preset-dialog"', html)
        self.assertIn('id="save-preset-title"', html)
        self.assertIn('id="manage-presets-dialog"', html)
        self.assertIn('id="manage-preset-list"', html)
        self.assertNotIn("拖动画笔创作自定义预设", html)
        self.assertNotIn('<span class="nav-btn__label">预设</span>', html)

        app_js = (index_path.parent / "js" / "app.js").read_text(encoding="utf-8")
        editor_js = (index_path.parent / "js" / "canvas-editor.js").read_text(encoding="utf-8")
        app_css = (index_path.parent / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn('callApi("load_svg_to_canvas")', app_js)
        self.assertIn('data-manage-action="edit"', app_js)
        self.assertIn('callApi("load_custom_preset_for_edit", presetId)', app_js)
        self.assertIn('callApi("update_canvas_preset", editingPresetId, payload)', app_js)
        self.assertIn('callApi("set_preview_color", accent)', app_js)
        self.assertIn('history-item pywebview-drag-region', app_js)
        self.assertIn("W/S 缩放 · A/D 旋转 · 右键取消", app_js)
        self.assertIn("canvasEditor.suggestedName", app_js)
        self.assertIn("loadPresetStrokes(strokes", editor_js)
        self.assertIn("if (resetHistory)", editor_js)
        self.assertIn("canvasEditor.setTool(tool)", app_js)
        self.assertIn("canvasEditor.undo()", app_js)
        self.assertIn("canvasEditor.redo()", app_js)
        self.assertIn('setTool(tool)', editor_js)
        self.assertIn('setHistoryChangeListener(listener)', editor_js)
        self.assertIn('this._eraseAt(', editor_js)
        self.assertIn("justify-content: space-between", app_css)
        clear_method = editor_js[
            editor_js.index("  clear() {") : editor_js.index("  loadPresetStrokes(", editor_js.index("  clear() {"))
        ]
        self.assertIn("this.undoStack = []", clear_method)
        self.assertIn("this.redoStack = []", clear_method)
        self.assertNotIn("this._recordHistory(", clear_method)


if __name__ == "__main__":
    unittest.main()
