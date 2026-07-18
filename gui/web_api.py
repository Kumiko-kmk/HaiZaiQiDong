"""pywebview JavaScript API bridge."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import webview

from gui.app_service import AppService


class WebApi:
    def __init__(self, service: AppService) -> None:
        self._service = service
        self._window: Optional[webview.Window] = None

    def bind_window(self, window: webview.Window) -> None:
        self._window = window

    def get_state(self) -> Dict[str, Any]:
        return self._service.get_state()

    def select_preset(self, preset_id: str) -> Dict[str, Any]:
        return self._service.select_preset(preset_id)

    def confirm_card(self) -> Dict[str, Any]:
        return self._service.confirm_card()

    def refresh_presets(self) -> Dict[str, Any]:
        return self._service.refresh_presets()

    def save_canvas_preset(self, payload: object) -> Dict[str, Any]:
        return self._service.save_canvas_preset(payload)

    def rename_custom_preset(self, preset_id: str, name: str) -> Dict[str, Any]:
        return self._service.rename_custom_preset(preset_id, name)

    def delete_custom_preset(self, preset_id: str) -> Dict[str, Any]:
        return self._service.delete_custom_preset(preset_id)

    def import_preset(self) -> Dict[str, Any]:
        if self._window is None:
            return self._service.get_state()
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("JSON files (*.json)", "All files (*.*)"),
        )
        if not result:
            return self._service.get_state()
        return self._service.import_json(Path(result[0]))

    def import_svg(self) -> Dict[str, Any]:
        if self._window is None:
            return self._service.get_state()
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("SVG files (*.svg)", "All files (*.*)"),
        )
        if not result:
            return self._service.get_state()
        return self._service.import_svg(Path(result[0]))

    def set_topmost(self, enabled: bool) -> Dict[str, Any]:
        state = self._service.set_topmost(enabled)
        if self._window is not None:
            self._window.on_top = enabled
        return state

    def set_draw_button(self, button: str) -> Dict[str, Any]:
        return self._service.set_draw_button(button)

    def close_window(self) -> None:
        """Close the desktop window; the closing event owns application cleanup."""
        if self._window is not None:
            self._window.destroy()
