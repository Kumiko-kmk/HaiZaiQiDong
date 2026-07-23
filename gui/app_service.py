"""UI-agnostic application service — core draw workflow without a UI toolkit."""

from __future__ import annotations

import base64
import binascii
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.draw_controller import DrawController, DrawOutcome, DrawResult, DrawSession
from core.input_router import InputRouter
from core.app_paths import bundle_root, history_log_path
from core.history import HistoryStore
from core.mouse_controller import MouseButton
from core.stroke_executor import DrawSettings
from core.preset_fit import MAX_ZOOM, MIN_ZOOM
from core.transform import TransformState
from gui.overlay_bridge import OverlayBridge
from gui.state import AppState
from presets.models import Preset
from presets.registry import MAX_CANVAS_POINTS, MAX_CANVAS_STROKES, get_registry
from presets.svg_import import svg_title, svg_to_stroke_dicts

WINDOW_WIDTH = 480
WINDOW_HEIGHT = 297  # 1 : 0.618 golden ratio
WINDOW_MIN_WIDTH = 384
WINDOW_MIN_HEIGHT = 237  # keep 1 : 0.618 at minimum size

WindowBounds = Tuple[int, int, int, int]
UiNotifier = Callable[[Dict[str, Any]], None]
WindowBoundsProvider = Callable[[], Optional[WindowBounds]]
PRESET_PREVIEW_DIR = Path("web") / "assets" / "preset-previews"
MAX_SVG_BYTES = 2 * 1024 * 1024
PREVIEW_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def preset_preview_url(preset_id: str, custom_preview_path: Optional[Path] = None) -> str:
    filename = f"{preset_id}.png"
    if (bundle_root() / PRESET_PREVIEW_DIR / filename).is_file():
        return f"assets/preset-previews/{filename}"
    if isinstance(custom_preview_path, Path) and custom_preview_path.is_file():
        try:
            encoded = base64.b64encode(custom_preview_path.read_bytes()).decode("ascii")
        except OSError:
            return ""
        return f"data:image/png;base64,{encoded}"
    return ""


def preset_to_dict(
    preset: Preset,
    custom_preview_path: Optional[Path] = None,
) -> Dict[str, Any]:
    return {
        "id": preset.id,
        "name": preset.name,
        "description": preset.description or "简笔画预设",
        "tags": list(getattr(preset, "tags", ())),
        "strokes": [stroke.to_dict() for stroke in preset.strokes],
        "previewUrl": preset_preview_url(preset.id, custom_preview_path),
    }


def decode_png_data_url(value: object) -> bytes:
    prefix = "data:image/png;base64,"
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValueError("预览图格式无效。")
    encoded = value[len(prefix):]
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("预览图格式无效。") from exc


class AppService:
    def __init__(self) -> None:
        self.registry = get_registry()
        self.router = InputRouter()
        self.draw_controller = DrawController(
            history=HistoryStore(log_path=history_log_path())
        )
        self.overlay_bridge = OverlayBridge()
        self.transform = TransformState()
        self.app_state = AppState.IDLE
        self._state_lock = threading.RLock()
        self.selected_preset: Optional[Preset] = None
        self.filtered_presets: List[Preset] = []
        self.topmost = True
        self.draw_button = MouseButton.RIGHT
        self._running = False
        self._ui_notifier: Optional[UiNotifier] = None
        self._window_bounds: Optional[WindowBoundsProvider] = None
        self._tick_thread: Optional[threading.Thread] = None

    def set_ui_notifier(self, notifier: UiNotifier) -> None:
        self._ui_notifier = notifier

    def set_window_bounds_provider(self, provider: WindowBoundsProvider) -> None:
        self._window_bounds = provider

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.router.start_base()
        self.refresh_presets()
        self._tick_thread = threading.Thread(target=self._tick_loop, daemon=True)
        self._tick_thread.start()
        self._notify_ui()

    def shutdown(self) -> None:
        self._running = False
        self.draw_controller.cancel()
        self._exit_ready()
        self.overlay_bridge.destroy()
        self.router.stop()

    def get_state(self) -> Dict[str, Any]:
        return self._build_state()

    def select_preset(self, preset_id: str) -> Dict[str, Any]:
        if self.app_state is not AppState.IDLE:
            return self._build_state(message="绘制中无法切换预设。")
        for preset in self.filtered_presets:
            if preset.id == preset_id:
                self._apply_preset(preset)
                break
        return self._build_state()

    def confirm_card(self) -> Dict[str, Any]:
        if self.app_state is AppState.IDLE:
            return self._enter_ready()
        if self.app_state is AppState.READY:
            self._cancel_ready()
        return self._build_state()

    def refresh_presets(self) -> Dict[str, Any]:
        self.registry.reload()
        self.filtered_presets = self.registry.list_presets()
        if self.selected_preset is None and self.filtered_presets:
            self._apply_preset(self.filtered_presets[0])
        elif self.selected_preset is not None:
            still_exists = any(p.id == self.selected_preset.id for p in self.filtered_presets)
            if not still_exists and self.filtered_presets:
                self._apply_preset(self.filtered_presets[0])
        return self._build_state()

    def import_json(self, path: Path) -> Dict[str, Any]:
        try:
            self.registry.import_json(path)
            self.refresh_presets()
            return self._build_state(message="预设已导入。")
        except Exception as exc:
            return self._build_state(message=f"导入失败: {exc}")

    def load_svg_to_canvas(self, path: Path) -> Dict[str, Any]:
        """Parse an SVG into an editable canvas draft without persisting it."""
        if self.app_state is not AppState.IDLE:
            return {
                "status": "error",
                "suggestedName": "",
                "strokes": [],
                "message": "请先结束当前绘制状态，再上传 SVG。",
            }
        try:
            if path.suffix.lower() != ".svg":
                raise ValueError("请选择 SVG 文件。")
            raw = path.read_bytes()
            if len(raw) > MAX_SVG_BYTES:
                raise ValueError("SVG 文件过大，不能超过 2 MB。")
            try:
                svg_text = raw.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValueError("SVG 必须使用 UTF-8 编码。") from exc

            suggested_name = svg_title(svg_text) or path.stem
            strokes = svg_to_stroke_dicts(svg_text)
            if len(strokes) > MAX_CANVAS_STROKES:
                raise ValueError(f"SVG 轮廓数量过多，不能超过 {MAX_CANVAS_STROKES} 笔。")
            segment_count = sum(len(stroke.get("segments", [])) for stroke in strokes)
            if segment_count > MAX_CANVAS_POINTS:
                raise ValueError("SVG 路径过于复杂，请适当简化后重试。")
            return {
                "status": "loaded",
                "suggestedName": suggested_name[:40],
                "strokes": strokes,
                "message": f"SVG“{suggested_name}”已载入画布。",
            }
        except Exception as exc:
            return {
                "status": "error",
                "suggestedName": "",
                "strokes": [],
                "message": f"SVG 加载失败: {exc}",
            }

    def save_canvas_preset(self, payload: object) -> Dict[str, Any]:
        if self.app_state is not AppState.IDLE:
            return self._build_state(message="请先结束当前绘制状态，再保存画布。")
        if not isinstance(payload, dict):
            return self._build_state(message="保存失败: 画布数据无效。")
        try:
            preview_png = decode_png_data_url(payload.get("previewDataUrl"))
            preset = self.registry.create_canvas_preset(
                name=str(payload.get("name", "")),
                strokes=payload.get("strokes"),
                canvas_width=float(payload.get("canvasWidth", 0)),
                canvas_height=float(payload.get("canvasHeight", 0)),
                preview_png=preview_png,
            )
            self.filtered_presets = self.registry.list_presets()
            self._apply_preset(preset)
            state = self._build_state(message=f"预设「{preset.name}」已保存到“其他”。")
            state["savedPresetId"] = preset.id
            return state
        except Exception as exc:
            return self._build_state(message=f"保存失败: {exc}")

    def rename_custom_preset(self, preset_id: str, name: str) -> Dict[str, Any]:
        if self.app_state is not AppState.IDLE:
            return self._build_state(message="请先结束当前绘制状态，再管理预设。")
        try:
            preset = self.registry.rename_custom_preset(preset_id, name)
            self.filtered_presets = self.registry.list_presets()
            if self.selected_preset is not None and self.selected_preset.id == preset.id:
                self._apply_preset(preset)
            state = self._build_state(message=f"预设已重命名为「{preset.name}」。")
            state["renamedPresetId"] = preset.id
            return state
        except Exception as exc:
            return self._build_state(message=f"重命名失败: {exc}")

    def delete_custom_preset(self, preset_id: str) -> Dict[str, Any]:
        if self.app_state is not AppState.IDLE:
            return self._build_state(message="请先结束当前绘制状态，再管理预设。")
        try:
            preset = self.registry.delete_custom_preset(preset_id)
            if self.selected_preset is not None and self.selected_preset.id == preset.id:
                self.selected_preset = None
            self.filtered_presets = self.registry.list_presets()
            if self.selected_preset is None:
                if self.filtered_presets:
                    self._apply_preset(self.filtered_presets[0])
                else:
                    self.transform = TransformState()
            state = self._build_state(message=f"预设「{preset.name}」已删除。")
            state["deletedPresetId"] = preset.id
            return state
        except Exception as exc:
            return self._build_state(message=f"删除失败: {exc}")

    def set_topmost(self, enabled: bool) -> Dict[str, Any]:
        self.topmost = enabled
        return self._build_state()

    def set_draw_button(self, button: str) -> Dict[str, Any]:
        try:
            self.draw_button = MouseButton(str(button).strip().lower())
        except ValueError:
            return self._build_state(message="无效的绘制方式。")
        return self._build_state()

    def set_preview_color(self, color: str) -> Dict[str, Any]:
        clean_color = str(color).strip()
        if PREVIEW_COLOR_RE.fullmatch(clean_color) is None:
            return self._build_state(message="无效的预览颜色。")
        self.overlay_bridge.set_color(clean_color.upper())
        return self._build_state()

    def _tick_loop(self) -> None:
        while self._running:
            x, y = self.router.position
            if self.app_state is AppState.READY and self.selected_preset is not None:
                self.overlay_bridge.update_position((x, y))
            time.sleep(0.033)

    def _apply_preset(self, preset: Preset) -> None:
        if self.app_state in (AppState.DRAWING, AppState.TERMINATING):
            return
        self.selected_preset = preset
        self.transform = TransformState.for_preset(preset)

    def _reset_transform(self) -> None:
        if self.selected_preset is not None:
            self.transform = TransformState.for_preset(self.selected_preset)
        else:
            self.transform = TransformState()

    def _panel_hit_test(self, x: float, y: float) -> bool:
        if self._window_bounds is None:
            return False
        bounds = self._window_bounds()
        if bounds is None:
            return False
        left, top, width, height = bounds
        return left <= x <= left + width and top <= y <= top + height

    def _enter_ready(self) -> Dict[str, Any]:
        if self.selected_preset is None:
            return self._build_state(message="请先选择简笔画预设。")
        self.app_state = AppState.READY
        self.overlay_bridge.show(self.selected_preset, self.transform)
        self.router.enable_ready_mode(
            panel_hit_test=self._panel_hit_test,
            on_anchor=self._on_anchor,
            on_scale=self._on_scale,
            on_rotation=self._on_rotation,
            on_cancel=self._cancel_ready,
        )
        self._notify_ui()
        return self._build_state()

    def _exit_ready(self) -> None:
        self.router.disable_ready_mode()
        self.overlay_bridge.hide()

    def _cancel_ready(self) -> None:
        if self.app_state is not AppState.READY:
            return
        self._exit_ready()
        self.app_state = AppState.IDLE
        self._reset_transform()
        self._notify_ui()

    def _on_anchor(self, anchor) -> None:
        if self.app_state is not AppState.READY or self.selected_preset is None:
            return
        self._exit_ready()
        self._start_draw(anchor)

    def _build_settings(self) -> DrawSettings:
        preset = self.selected_preset
        assert preset is not None
        return DrawSettings(
            transform=self.transform,
            button=self.draw_button,
        )

    def _start_draw(self, anchor) -> None:
        preset = self.selected_preset
        if preset is None:
            return
        session = DrawSession(preset=preset, anchor=anchor, settings=self._build_settings())
        with self._state_lock:
            self.app_state = AppState.DRAWING
            self.router.enable_drawing_mode(on_cancel=self._request_termination)
            started = self.draw_controller.start(session, on_finish=self._on_draw_finish)
            if not started:
                self.router.disable_drawing_mode()
                self.app_state = AppState.IDLE
        self._notify_ui()

    def _on_draw_finish(self, result: DrawResult) -> None:
        with self._state_lock:
            self.router.disable_drawing_mode()
            self.app_state = AppState.IDLE
        self._reset_transform()
        message = result.message if result.outcome is DrawOutcome.FAILED else None
        self._notify_ui(message=message)

    def _request_termination(self) -> None:
        with self._state_lock:
            if self.app_state is not AppState.DRAWING:
                return
            self.app_state = AppState.TERMINATING
        self._notify_ui()
        self.draw_controller.cancel()

    def _on_scale(self, factor: float) -> None:
        if self.app_state is not AppState.READY:
            return
        self.transform.zoom *= factor
        self.transform.clamp_zoom()
        if self.selected_preset is not None:
            self.overlay_bridge.set_transform(self.transform)
        self._notify_ui()

    def _on_rotation(self, delta_deg: float) -> None:
        if self.app_state is not AppState.READY:
            return
        self.transform.rotation_deg += delta_deg
        if self.selected_preset is not None:
            self.overlay_bridge.set_transform(self.transform)

    def _build_state(self, *, message: Optional[str] = None) -> Dict[str, Any]:
        history = []
        for entry in self.draw_controller.history.list_entries():
            history.append(
                {
                    "presetName": entry.preset_name,
                    "status": entry.status,
                    "time": entry.timestamp.strftime("%m-%d %H:%M"),
                    "timestamp": entry.timestamp.isoformat(timespec="seconds"),
                    "scale": round(entry.scale, 1),
                    "drawButton": entry.draw_button,
                    "durationSec": round(entry.duration_sec, 1),
                    "failureCode": entry.failure_code,
                    "message": entry.message,
                    "eventCount": entry.event_count,
                }
            )
        return {
            "appState": self.app_state.name.lower(),
            "presets": [
                preset_to_dict(p, self.registry.preview_path(p.id))
                for p in self.filtered_presets
            ],
            "selectedPresetId": self.selected_preset.id if self.selected_preset else None,
            "libraryCount": len(self.filtered_presets),
            "history": history,
            "topmost": self.topmost,
            "drawButton": self.draw_button.value,
            "cardsEnabled": self.app_state is AppState.IDLE,
            "message": message,
            "transform": {
                "zoom": round(self.transform.zoom, 2),
                "minZoom": MIN_ZOOM,
                "maxZoom": MAX_ZOOM,
                "effectiveScale": round(self.transform.scale, 2),
            },
        }

    def _notify_ui(self, *, message: Optional[str] = None) -> None:
        if self._ui_notifier is not None:
            self._ui_notifier(self._build_state(message=message))
