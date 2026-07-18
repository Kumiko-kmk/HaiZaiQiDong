"""Tkinter overlay bridge — runs Tk on a dedicated thread."""

from __future__ import annotations

import queue
import threading
from typing import Callable, Optional

from gui.tk_env import ensure_tcl_tk_env

ensure_tcl_tk_env()

import tkinter as tk

from core.transform import TransformState
from gui.overlay_preview import OverlayPreview
from presets.models import Preset


class OverlayBridge:
    def __init__(self) -> None:
        self._ready = threading.Event()
        self._jobs: queue.Queue[Callable[[], None]] = queue.Queue()
        self.overlay: Optional[OverlayPreview] = None
        threading.Thread(target=self._tk_loop, daemon=True).start()
        self._ready.wait(timeout=5)

    def _tk_loop(self) -> None:
        root = tk.Tk()
        root.withdraw()
        self.overlay = OverlayPreview(root)
        self._ready.set()

        def pump() -> None:
            while True:
                try:
                    job = self._jobs.get_nowait()
                    job()
                except queue.Empty:
                    break
            try:
                root.update_idletasks()
                root.update()
            except tk.TclError:
                return
            root.after(33, pump)

        root.after(33, pump)
        root.mainloop()

    def _call(self, fn: Callable[[], None]) -> None:
        self._jobs.put(fn)

    def show(self, preset: Preset, transform: TransformState) -> None:
        if self.overlay is not None:
            self._call(lambda: self.overlay.show(preset, transform))  # type: ignore[union-attr]

    def hide(self) -> None:
        if self.overlay is not None:
            self._call(lambda: self.overlay.hide())  # type: ignore[union-attr]

    def update_position(self, anchor) -> None:
        if self.overlay is not None:
            self._call(lambda: self.overlay.update_position(anchor))  # type: ignore[union-attr]

    def set_transform(self, transform: TransformState) -> None:
        if self.overlay is not None:
            self._call(lambda: self.overlay.set_transform(transform))  # type: ignore[union-attr]

    def destroy(self) -> None:
        if self.overlay is not None:
            self._call(lambda: self.overlay.destroy())  # type: ignore[union-attr]
