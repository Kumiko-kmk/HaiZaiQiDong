"""pywebview desktop shell loading the HTML frontend."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import webview

from gui.app_service import (
    WINDOW_HEIGHT,
    WINDOW_MIN_HEIGHT,
    WINDOW_MIN_WIDTH,
    WINDOW_WIDTH,
    AppService,
)
from gui.web_api import WebApi

_SERVICE: AppService | None = None
_API: WebApi | None = None
_WINDOW: webview.Window | None = None


def _resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "web"
    return Path(__file__).resolve().parent.parent / "web"


def _notify_ui(state: dict) -> None:
    if _WINDOW is None:
        return
    payload = json.dumps(state, ensure_ascii=False)
    try:
        _WINDOW.evaluate_js(f"window.app && window.app.onStateUpdate({payload})")
    except Exception:
        pass


def _window_bounds():
    if _WINDOW is None:
        return None
    try:
        return (_WINDOW.x, _WINDOW.y, _WINDOW.width, _WINDOW.height)
    except Exception:
        return (0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)


def run_app() -> None:
    global _SERVICE, _API, _WINDOW

    index_html = _resource_dir() / "index.html"
    if not index_html.is_file():
        raise FileNotFoundError(f"Web UI not found: {index_html}")

    service = AppService()
    api = WebApi(service)
    _SERVICE = service
    _API = api

    service.set_ui_notifier(_notify_ui)
    service.set_window_bounds_provider(_window_bounds)

    window = webview.create_window(
        "HaiZaiQiDong",
        url=index_html.as_uri(),
        js_api=api,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT),
        resizable=True,
        frameless=True,
        easy_drag=False,
        shadow=True,
        on_top=True,
        background_color="#F4F2EE",
    )
    _WINDOW = window
    api.bind_window(window)

    def on_loaded() -> None:
        service.start()
        _notify_ui(service.get_state())

    def on_closing() -> None:
        service.shutdown()

    window.events.loaded += on_loaded
    window.events.closing += on_closing
    webview.start(debug=False)
