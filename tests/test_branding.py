from __future__ import annotations

import struct
import unittest
from pathlib import Path


class BrandingContractTests(unittest.TestCase):
    def test_application_name_and_icon_are_wired_into_desktop_build(self) -> None:
        root = Path(__file__).resolve().parents[1]
        png = root / "web" / "assets" / "HaiZaiQiDong.png"
        ico = root / "web" / "assets" / "HaiZaiQiDong.ico"
        spec = (root / "HaiZaiQiDong.spec").read_text(encoding="utf-8")
        build = (root / "scripts" / "build.ps1").read_text(encoding="utf-8")
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        shell = (root / "gui" / "webview_app.py").read_text(encoding="utf-8")

        self.assertTrue(png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        ico_header = ico.read_bytes()[:6]
        reserved, image_type, image_count = struct.unpack("<HHH", ico_header)
        self.assertEqual((reserved, image_type, image_count), (0, 1, 7))
        self.assertIn('name="HaiZaiQiDong"', spec)
        self.assertIn('"HaiZaiQiDong.ico"', spec)
        self.assertIn("HaiZaiQiDong.spec", build)
        self.assertIn("HaiZaiQiDong.exe", build)
        self.assertIn("<title>HaiZaiQiDong</title>", html)
        self.assertIn('href="assets/HaiZaiQiDong.png"', html)
        self.assertIn('"HaiZaiQiDong",', shell)


if __name__ == "__main__":
    unittest.main()
