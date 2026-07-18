"""Ensure Tcl/Tk env vars point at a usable install for tkinter."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass))
        roots.append(Path(sys.executable).resolve().parent)
    roots.append(Path(sys.base_prefix))
    roots.append(Path(sys.prefix))

    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _find_lib(root: Path, names: tuple[str, ...], marker: str) -> Path | None:
    for name in names:
        for candidate in (root / "tcl" / name, root / "lib" / name):
            try:
                if (candidate / marker).is_file():
                    return candidate
            except OSError:
                continue
    return None


def _find_tcl_tk() -> tuple[Path | None, Path | None]:
    for root in _candidate_roots():
        tcl_dir = _find_lib(root, ("tcl8.6", "tcl8.5"), "init.tcl")
        if tcl_dir is None:
            continue
        tk_dir = _find_lib(root, ("tk8.6", "tk8.5"), "tk.tcl")
        return tcl_dir, tk_dir
    return None, None


def _env_points_to_usable_dir(var: str, marker: str) -> bool:
    raw = os.environ.get(var)
    if not raw:
        return False
    path = Path(raw)
    try:
        if path.is_file():
            # Common misconfig: pointing at init.tcl / tk.tcl instead of the directory.
            return False
        return path.is_dir() and (path / marker).is_file()
    except OSError:
        return False


def ensure_tcl_tk_env() -> None:
    """Repair broken TCL_LIBRARY / TK_LIBRARY before importing tkinter."""
    tcl_ok = _env_points_to_usable_dir("TCL_LIBRARY", "init.tcl")
    tk_ok = _env_points_to_usable_dir("TK_LIBRARY", "tk.tcl")
    if tcl_ok and tk_ok:
        return

    tcl_dir, tk_dir = _find_tcl_tk()
    if not tcl_ok and tcl_dir is not None:
        os.environ["TCL_LIBRARY"] = str(tcl_dir)
    if not tk_ok and tk_dir is not None:
        os.environ["TK_LIBRARY"] = str(tk_dir)
