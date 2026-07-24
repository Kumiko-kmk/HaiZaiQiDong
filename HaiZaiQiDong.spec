# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for HaiZaiQiDong (Windows)."""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
project_dir = Path(SPECPATH)


def _normalise_tcl_dir(value, marker):
    if not value:
        return None
    path = Path(value)
    if path.name.lower() == marker.lower():
        path = path.parent
    try:
        return path if (path / marker).is_file() else None
    except OSError:
        return None


# Some standalone Python distributions expose TCL_LIBRARY as init.tcl itself.
# PyInstaller expects directory paths when its tkinter hook probes the runtime.
python_base = Path(sys.base_prefix)
tcl_dir = _normalise_tcl_dir(str(python_base / "tcl" / "tcl8.6"), "init.tcl")
tk_dir = _normalise_tcl_dir(str(python_base / "tcl" / "tk8.6"), "tk.tcl")
if tcl_dir is None:
    tcl_dir = _normalise_tcl_dir(os.environ.get("TCL_LIBRARY"), "init.tcl")
if tk_dir is None:
    tk_dir = _normalise_tcl_dir(os.environ.get("TK_LIBRARY"), "tk.tcl")
if tcl_dir is not None and tk_dir is None:
    candidate = tcl_dir.parent / "tk8.6"
    try:
        if (candidate / "tk.tcl").is_file():
            tk_dir = candidate
    except OSError:
        pass
if tcl_dir is not None:
    os.environ["TCL_LIBRARY"] = str(tcl_dir)
if tk_dir is not None:
    os.environ["TK_LIBRARY"] = str(tk_dir)

hiddenimports = collect_submodules("pynput")
hiddenimports += [
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
    "webview",
    "clr_loader",
]

runtime_binaries = []
runtime_datas = []
if sys.platform == "win32":
    # Some embeddable/managed Python runtimes can import tkinter but cannot be
    # inspected by PyInstaller's isolated Tcl probe. Bundle the known runtime
    # files explicitly so a successful build can never silently omit overlays.
    dll_dir = python_base / "DLLs"
    tkinter_package = python_base / "Lib" / "tkinter"
    tcl_library = python_base / "tcl" / "tcl8.6"
    tk_library = python_base / "tcl" / "tk8.6"
    for filename in ("_tkinter.pyd", "tcl86t.dll", "tk86t.dll"):
        source = dll_dir / filename
        if source.is_file():
            runtime_binaries.append((str(source), "."))
    if tkinter_package.is_dir():
        runtime_datas.append((str(tkinter_package), "tkinter"))
    if tcl_library.is_dir():
        runtime_datas.append((str(tcl_library), "tcl/tcl8.6"))
    if tk_library.is_dir():
        runtime_datas.append((str(tk_library), "tcl/tk8.6"))

datas = [(str(project_dir / "web"), "web")]
datas += [(str(project_dir / "presets" / "data"), "presets/data")]
datas += [(str(project_dir / "pythonnet.runtime.config"), ".")]
datas += runtime_datas

a = Analysis(
    ["main.py"],
    pathex=[str(project_dir)],
    binaries=runtime_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HaiZaiQiDong",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_dir / "web" / "assets" / "HaiZaiQiDong.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="HaiZaiQiDong",
)
