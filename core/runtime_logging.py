"""Bounded runtime logging for failures hidden by the windowed executable."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from core.app_paths import runtime_log_path


def configure_runtime_logging() -> None:
    root = logging.getLogger()
    if any(getattr(handler, "_haizai_runtime", False) for handler in root.handlers):
        return

    path = runtime_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path,
        maxBytes=512 * 1024,
        backupCount=1,
        encoding="utf-8",
    )
    handler._haizai_runtime = True  # type: ignore[attr-defined]
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(logging.INFO)
