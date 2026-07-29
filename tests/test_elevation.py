from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import main
from core import elevation


class ElevationTests(unittest.TestCase):
    def test_non_windows_process_continues_without_relaunch(self) -> None:
        with (
            patch.object(elevation.sys, "platform", "linux"),
            patch.object(elevation, "_shell_execute_runas") as launch,
        ):
            self.assertTrue(elevation.ensure_administrator())

        launch.assert_not_called()

    def test_existing_administrator_process_continues_without_relaunch(self) -> None:
        with (
            patch.object(elevation.sys, "platform", "win32"),
            patch.object(elevation, "is_administrator", return_value=True),
            patch.object(elevation, "_shell_execute_runas") as launch,
        ):
            self.assertTrue(elevation.ensure_administrator())

        launch.assert_not_called()

    def test_source_process_relaunches_python_with_script_and_arguments(self) -> None:
        executable = str(Path("C:/Python/python.exe"))
        script = str(Path("E:/Hai Zai/main.py"))
        argv = [script, "--sample", "value with spaces"]
        launch = Mock(return_value=42)

        with (
            patch.object(elevation.sys, "platform", "win32"),
            patch.object(elevation.sys, "executable", executable),
            patch.object(elevation.sys, "argv", argv),
            patch.object(elevation.sys, "frozen", False, create=True),
            patch.object(elevation, "is_administrator", return_value=False),
            patch.object(elevation, "_shell_execute_runas", launch),
        ):
            self.assertFalse(elevation.ensure_administrator())

        expected_parameters = subprocess.list2cmdline(
            [str(Path(script).resolve()), *argv[1:]]
        )
        launch.assert_called_once_with(
            str(Path(executable).resolve()),
            expected_parameters,
            os.getcwd(),
        )

    def test_frozen_process_relaunches_executable_without_script_argument(self) -> None:
        executable = str(Path("E:/HaiZaiQiDong/HaiZaiQiDong.exe"))
        argv = [executable, "--sample"]
        launch = Mock(return_value=42)

        with (
            patch.object(elevation.sys, "platform", "win32"),
            patch.object(elevation.sys, "executable", executable),
            patch.object(elevation.sys, "argv", argv),
            patch.object(elevation.sys, "frozen", True, create=True),
            patch.object(elevation, "is_administrator", return_value=False),
            patch.object(elevation, "_shell_execute_runas", launch),
        ):
            self.assertFalse(elevation.ensure_administrator())

        launch.assert_called_once_with(
            str(Path(executable).resolve()),
            subprocess.list2cmdline(argv[1:]),
            os.getcwd(),
        )

    def test_failed_or_cancelled_request_is_reported(self) -> None:
        with (
            patch.object(elevation.sys, "platform", "win32"),
            patch.object(elevation, "is_administrator", return_value=False),
            patch.object(elevation, "_shell_execute_runas", return_value=5),
            self.assertRaises(elevation.ElevationError),
        ):
            elevation.ensure_administrator()

    def test_unelevated_parent_exits_without_loading_ui(self) -> None:
        with patch.object(main, "ensure_administrator", return_value=False):
            self.assertEqual(main.main(), 0)

    def test_elevation_failure_is_shown_and_returns_error(self) -> None:
        error = elevation.ElevationError("cancelled")
        with (
            patch.object(main, "ensure_administrator", side_effect=error),
            patch.object(main, "show_elevation_error") as show_error,
        ):
            self.assertEqual(main.main(), 1)

        show_error.assert_called_once_with("cancelled")


if __name__ == "__main__":
    unittest.main()
