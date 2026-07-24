"""Configure pythonnet for a frozen Windows application."""

from __future__ import annotations

import os
import sys
from pathlib import Path

RUNTIME_CONFIG_NAME = "pythonnet.runtime.config"


def _unblock_bundled_dotnet(root: Path) -> None:
    """Remove browser download markers from bundled managed assemblies."""
    candidates = [root / "pythonnet" / "runtime" / "Python.Runtime.dll"]
    webview_lib = root / "webview" / "lib"
    if webview_lib.is_dir():
        candidates.extend(webview_lib.rglob("*.dll"))

    for assembly in candidates:
        if not assembly.is_file():
            continue
        try:
            os.remove(f"{assembly}:Zone.Identifier")
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise RuntimeError(f"Unable to unblock bundled assembly: {assembly}") from exc


def configure_frozen_pythonnet() -> None:
    """Allow marked .NET assemblies from a downloaded release to load."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return

    bundle_root = Path(sys._MEIPASS)
    _unblock_bundled_dotnet(bundle_root)

    config_path = bundle_root / RUNTIME_CONFIG_NAME
    if not config_path.is_file():
        raise RuntimeError(f"Missing bundled pythonnet config: {config_path}")

    from pythonnet import set_runtime

    set_runtime(
        "netfx",
        domain="HaiZaiQiDong",
        config_file=str(config_path),
    )
