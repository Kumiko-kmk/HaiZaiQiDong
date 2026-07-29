"""Windows administrator bootstrap used before loading the desktop UI."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path
from typing import Tuple

_SW_SHOWNORMAL = 1
_SHELLEXECUTE_SUCCESS = 32
_ERROR_ICON = 0x00000010


class ElevationError(RuntimeError):
    """Raised when Windows cannot launch the elevated replacement process."""


def is_administrator() -> bool:
    if sys.platform != "win32":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def elevated_launch_command() -> Tuple[str, str, str]:
    """Build the executable, parameters and working directory for relaunch."""
    executable = str(Path(sys.executable).resolve())
    arguments = list(sys.argv[1:])
    if not getattr(sys, "frozen", False):
        arguments.insert(0, str(Path(sys.argv[0]).resolve()))
    return executable, subprocess.list2cmdline(arguments), os.getcwd()


def _shell_execute_runas(
    executable: str, parameters: str, working_directory: str
) -> int:
    shell_execute = ctypes.windll.shell32.ShellExecuteW
    shell_execute.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_int,
    ]
    shell_execute.restype = ctypes.c_void_p
    result = shell_execute(
        None,
        "runas",
        executable,
        parameters or None,
        working_directory,
        _SW_SHOWNORMAL,
    )
    return int(result or 0)


def ensure_administrator() -> bool:
    """Return True in the process that should continue running.

    An unelevated Windows process launches an elevated replacement and returns
    False so the original process can exit immediately.
    """
    if sys.platform != "win32" or is_administrator():
        return True
    executable, parameters, working_directory = elevated_launch_command()
    result = _shell_execute_runas(executable, parameters, working_directory)
    if result <= _SHELLEXECUTE_SUCCESS:
        raise ElevationError(f"管理员权限请求失败，Windows 错误代码：{result}")
    return False


def show_elevation_error(message: str) -> None:
    text = f"{message}\n\nHaiZaiQiDong 需要管理员权限才能控制以管理员身份运行的游戏。"
    try:
        ctypes.windll.user32.MessageBoxW(None, text, "HaiZaiQiDong", _ERROR_ICON)
    except (AttributeError, OSError):
        print(text, file=sys.stderr)
