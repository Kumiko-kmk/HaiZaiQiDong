from __future__ import annotations

import sys
import types
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from gui import pythonnet_runtime


class PythonnetRuntimeTests(unittest.TestCase):
    def test_source_run_does_not_configure_pythonnet(self) -> None:
        fake_pythonnet = types.SimpleNamespace(set_runtime=Mock())
        with (
            patch.object(pythonnet_runtime.sys, "platform", "win32"),
            patch.object(pythonnet_runtime.sys, "frozen", False, create=True),
            patch.dict(sys.modules, {"pythonnet": fake_pythonnet}),
        ):
            pythonnet_runtime.configure_frozen_pythonnet()

        fake_pythonnet.set_runtime.assert_not_called()

    def test_frozen_windows_run_uses_download_safe_appdomain(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / pythonnet_runtime.RUNTIME_CONFIG_NAME
            config.write_text("<configuration />", encoding="utf-8")
            python_runtime = root / "pythonnet" / "runtime" / "Python.Runtime.dll"
            webview_runtime = (
                root / "webview" / "lib" / "Microsoft.Web.WebView2.Core.dll"
            )
            python_runtime.parent.mkdir(parents=True)
            webview_runtime.parent.mkdir(parents=True)
            python_runtime.write_bytes(b"managed")
            webview_runtime.write_bytes(b"managed")
            set_runtime = Mock()
            remove = Mock()
            fake_pythonnet = types.SimpleNamespace(set_runtime=set_runtime)

            with (
                patch.object(pythonnet_runtime.sys, "platform", "win32"),
                patch.object(pythonnet_runtime.sys, "frozen", True, create=True),
                patch.object(pythonnet_runtime.sys, "_MEIPASS", str(root), create=True),
                patch.object(pythonnet_runtime.os, "remove", remove),
                patch.dict(sys.modules, {"pythonnet": fake_pythonnet}),
            ):
                pythonnet_runtime.configure_frozen_pythonnet()

            set_runtime.assert_called_once_with(
                "netfx",
                domain="HaiZaiQiDong",
                config_file=str(config),
            )
            remove.assert_any_call(f"{python_runtime}:Zone.Identifier")
            remove.assert_any_call(f"{webview_runtime}:Zone.Identifier")

    def test_runtime_config_allows_internet_marked_assemblies(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = root / pythonnet_runtime.RUNTIME_CONFIG_NAME
        runtime = ElementTree.parse(config).getroot().find("runtime")
        self.assertIsNotNone(runtime)
        setting = runtime.find("loadFromRemoteSources")
        self.assertIsNotNone(setting)
        self.assertEqual(setting.attrib.get("enabled"), "true")


if __name__ == "__main__":
    unittest.main()
