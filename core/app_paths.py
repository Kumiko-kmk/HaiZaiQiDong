"""Resolve bundle and user-writable paths for dev and frozen (PyInstaller) runs."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


APP_NAME = "MouseSketchDrawer"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundle_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", project_root()))
    return project_root()


def user_data_root() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        root = Path(appdata) / APP_NAME
    else:
        root = Path.home() / f".{APP_NAME}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def bundled_presets_dir() -> Path:
    return bundle_root() / "presets" / "data"


def presets_data_dir() -> Path:
    """Writable built-in preset mirror, kept in sync with the frozen bundle."""
    if not is_frozen():
        dev_dir = project_root() / "presets" / "data"
        dev_dir.mkdir(parents=True, exist_ok=True)
        return dev_dir

    user_dir = user_data_root() / "presets" / "data"
    user_dir.mkdir(parents=True, exist_ok=True)
    _sync_bundled_presets(user_dir)
    return user_dir


def custom_presets_dir() -> Path:
    """User-created/imported presets, kept separate from bundled source data."""
    directory = user_data_root() / "presets" / "custom"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def history_log_path() -> Path:
    """Persistent draw history shared by development and packaged runs."""
    return user_data_root() / "logs" / "drawing-history.jsonl"


def _sync_bundled_presets(user_dir: Path) -> None:
    """Refresh managed built-ins without touching legacy/custom JSON files."""
    bundled = bundled_presets_dir()
    if not bundled.is_dir():
        return

    bundled_files = {path.name: path for path in bundled.glob("*.json")}

    # Built-ins use the sts2_ prefix. Remove retired entries (for example a
    # preset deleted in a newer release), but preserve unrelated legacy files.
    for path in user_dir.glob("sts2_*.json"):
        if path.name not in bundled_files:
            path.unlink()

    for filename, source in bundled_files.items():
        target = user_dir / filename
        try:
            if target.is_file() and target.read_bytes() == source.read_bytes():
                continue
        except OSError:
            # Replacing the file below will surface a useful error if the
            # destination is genuinely inaccessible.
            pass

        temporary = target.with_suffix(".json.tmp")
        try:
            shutil.copyfile(source, temporary)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
