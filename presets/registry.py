"""Load, import, and list sketch presets."""

from __future__ import annotations

import json
import math
import shutil
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from core.app_paths import custom_presets_dir, presets_data_dir
from presets.models import Preset
from presets.svg_import import preset_id_from_filename, svg_title, svg_to_preset_dict


OWNER_TAG_ORDER = ("战士", "猎手", "储君", "骨妹", "鸡煲", "其他")
_OWNER_TAG_RANK = {tag: index for index, tag in enumerate(OWNER_TAG_ORDER)}
MAX_CANVAS_STROKES = 256
MAX_CANVAS_POINTS = 50_000
MAX_PREVIEW_BYTES = 2 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _clean_preset_name(name: object) -> str:
    clean_name = str(name).strip()
    if not clean_name:
        raise ValueError("预设名称不能为空。")
    if len(clean_name) > 40:
        raise ValueError("预设名称不能超过 40 个字符。")
    return clean_name


def _preset_sort_key(preset: Preset) -> tuple[int, bool, int, str]:
    owner_tag = preset.tags[0] if preset.tags else ""
    owner_rank = _OWNER_TAG_RANK.get(owner_tag, len(OWNER_TAG_ORDER))
    missing_order = preset.menu_order is None
    menu_order = preset.menu_order if preset.menu_order is not None else 0
    return owner_rank, missing_order, menu_order, preset.id


class PresetRegistry:
    def __init__(
        self,
        data_dir: Optional[Path] = None,
        custom_data_dir: Optional[Path] = None,
    ) -> None:
        self._data_dir = data_dir or presets_data_dir()
        self._custom_data_dir = custom_data_dir or (
            self._data_dir if data_dir is not None else custom_presets_dir()
        )
        self._presets: Dict[str, Preset] = {}
        self.reload()

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def preview_dir(self) -> Path:
        return self._custom_data_dir / "_previews"

    def preview_path(self, preset_id: str) -> Optional[Path]:
        path = self.preview_dir / f"{preset_id}.png"
        return path if path.is_file() else None

    def reload(self) -> None:
        self._presets.clear()
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._custom_data_dir.mkdir(parents=True, exist_ok=True)

        directories = [self._data_dir]
        if self._custom_data_dir.resolve() != self._data_dir.resolve():
            directories.append(self._custom_data_dir)
        for directory in directories:
            for path in sorted(directory.glob("*.json")):
                try:
                    preset = self._load_file(path)
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    print(f"[preset] skip {path.name}: {exc}")
                    continue
                self._presets[preset.id] = preset

    def list_presets(self) -> List[Preset]:
        return sorted(self._presets.values(), key=_preset_sort_key)

    def import_json(self, source_path: Path) -> Preset:
        preset = self._load_file(source_path)
        target = self._custom_data_dir / f"{preset.id}.json"
        shutil.copy2(source_path, target)
        self._presets[preset.id] = preset
        return preset

    def import_svg(self, source_path: Path) -> Preset:
        svg_text = source_path.read_text(encoding="utf-8")
        preset_id = preset_id_from_filename(source_path.stem)
        name = svg_title(svg_text) or source_path.stem
        preset_dict = svg_to_preset_dict(
            svg_text,
            preset_id=preset_id,
            name=name,
            description="由 SVG 导入",
            tags=["导入", "SVG"],
        )
        preset = Preset.from_dict(preset_dict)
        target = self._custom_data_dir / f"{preset.id}.json"
        with target.open("w", encoding="utf-8") as handle:
            json.dump(preset_dict, handle, ensure_ascii=False, indent=2)
        self._presets[preset.id] = preset
        return preset

    def create_canvas_preset(
        self,
        *,
        name: str,
        strokes: object,
        canvas_width: float,
        canvas_height: float,
        preview_png: bytes,
    ) -> Preset:
        """Validate and persist a lightweight polyline preset drawn in the UI."""
        clean_name = _clean_preset_name(name)
        if not math.isfinite(canvas_width) or not math.isfinite(canvas_height):
            raise ValueError("画布尺寸无效。")
        if canvas_width <= 0 or canvas_height <= 0:
            raise ValueError("画布尺寸无效。")
        if not isinstance(strokes, list) or not strokes:
            raise ValueError("请先在画布上绘制图案。")
        if len(strokes) > MAX_CANVAS_STROKES:
            raise ValueError("笔画数量过多，请适当简化图案。")
        if not isinstance(preview_png, bytes) or not preview_png.startswith(PNG_SIGNATURE):
            raise ValueError("预览图格式无效。")
        if len(preview_png) > MAX_PREVIEW_BYTES:
            raise ValueError("预览图过大，请适当简化图案。")

        canvas_strokes: list[list[list[float]]] = []
        point_count = 0
        for raw_stroke in strokes:
            points = self._normalize_canvas_stroke(
                raw_stroke,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
            )
            if not points:
                continue
            point_count += len(points)
            if point_count > MAX_CANVAS_POINTS:
                raise ValueError("采样点过多，请适当简化图案。")
            canvas_strokes.append(points)

        if not canvas_strokes:
            raise ValueError("请先在画布上绘制图案。")

        all_points = [point for stroke in canvas_strokes for point in stroke]
        min_x = min(point[0] for point in all_points)
        max_x = max(point[0] for point in all_points)
        min_y = min(point[1] for point in all_points)
        max_y = max(point[1] for point in all_points)
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        normalized_strokes = [
            {
                "segments": [
                    {
                        "type": "polyline",
                        "points": [
                            [round(point[0] - center_x, 3), round(point[1] - center_y, 3)]
                            for point in stroke
                        ],
                    }
                ]
            }
            for stroke in canvas_strokes
        ]

        preset_id = f"custom_{uuid.uuid4().hex[:16]}"
        preset_dict = {
            "id": preset_id,
            "name": clean_name,
            "version": 1,
            "description": "由画布创建",
            "tags": ["其他", "自定义"],
            "strokes": normalized_strokes,
        }
        preset = Preset.from_dict(preset_dict)

        self._custom_data_dir.mkdir(parents=True, exist_ok=True)
        self.preview_dir.mkdir(parents=True, exist_ok=True)
        json_target = self._custom_data_dir / f"{preset_id}.json"
        preview_target = self.preview_dir / f"{preset_id}.png"
        json_temp = json_target.with_suffix(".json.tmp")
        preview_temp = preview_target.with_suffix(".png.tmp")
        try:
            preview_temp.write_bytes(preview_png)
            with json_temp.open("w", encoding="utf-8") as handle:
                json.dump(preset_dict, handle, ensure_ascii=False, indent=2)
            preview_temp.replace(preview_target)
            json_temp.replace(json_target)
        except Exception:
            for temporary in (json_temp, preview_temp):
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                preview_target.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        self._presets[preset.id] = preset
        return preset

    def rename_custom_preset(self, preset_id: str, name: object) -> Preset:
        path = self._managed_custom_path(preset_id)
        if path is None:
            raise ValueError("只能重命名由画布创建的自定义预设。")
        clean_name = _clean_preset_name(name)
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("预设文件格式无效。")
        data["name"] = clean_name
        preset = Preset.from_dict(data)
        if preset.id != str(preset_id):
            raise ValueError("预设标识不匹配。")

        temporary = path.with_suffix(".json.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            temporary.replace(path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        self._presets[preset.id] = preset
        return preset

    def delete_custom_preset(self, preset_id: str) -> Preset:
        path = self._managed_custom_path(preset_id)
        if path is None:
            raise ValueError("只能删除由画布创建的自定义预设。")
        preset = self._presets[str(preset_id)]
        path.unlink()
        preview = self.preview_dir / f"{preset.id}.png"
        try:
            preview.unlink(missing_ok=True)
        except OSError as exc:
            print(f"[preset] unable to remove preview {preview.name}: {exc}")
        self._presets.pop(preset.id, None)
        return preset

    def _managed_custom_path(self, preset_id: str) -> Optional[Path]:
        clean_id = str(preset_id).strip()
        preset = self._presets.get(clean_id)
        if preset is None or "自定义" not in preset.tags:
            return None
        custom_root = self._custom_data_dir.resolve()
        path = (custom_root / f"{clean_id}.json").resolve()
        if path.parent != custom_root or not path.is_file():
            return None
        return path

    @staticmethod
    def _normalize_canvas_stroke(
        raw_stroke: object,
        *,
        canvas_width: float,
        canvas_height: float,
    ) -> list[list[float]]:
        if not isinstance(raw_stroke, list):
            return []
        points: list[list[float]] = []
        last: tuple[float, float] | None = None
        for raw_point in raw_stroke:
            if not isinstance(raw_point, Sequence) or isinstance(raw_point, (str, bytes)):
                continue
            if len(raw_point) < 2:
                continue
            try:
                x = float(raw_point[0])
                y = float(raw_point[1])
            except (TypeError, ValueError):
                continue
            if not math.isfinite(x) or not math.isfinite(y):
                continue
            if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
                continue
            model_point = (x * canvas_width, y * canvas_height)
            if last is not None and math.dist(last, model_point) < 0.5:
                continue
            points.append([round(model_point[0], 3), round(model_point[1], 3)])
            last = model_point
        return points

    def _load_file(self, path: Path) -> Preset:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("Preset root must be an object")
        return Preset.from_dict(data)


_default_registry: Optional[PresetRegistry] = None


def get_registry() -> PresetRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = PresetRegistry()
    return _default_registry
