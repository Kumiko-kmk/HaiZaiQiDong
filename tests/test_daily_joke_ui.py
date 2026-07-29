from __future__ import annotations

import unittest
from pathlib import Path


class DailyJokeUiContractTests(unittest.TestCase):
    def test_settings_page_wires_daily_joke_dialog_before_about(self) -> None:
        root = Path(__file__).resolve().parents[1]
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        app = (root / "web" / "js" / "app.js").read_text(encoding="utf-8")
        daily_joke = (root / "web" / "js" / "daily-joke.js").read_text(
            encoding="utf-8"
        )

        self.assertLess(html.index('id="btn-daily-joke"'), html.index('id="btn-about"'))
        self.assertIn('id="daily-joke-dialog"', html)
        self.assertNotIn('id="daily-joke-number"', html)
        self.assertIn('id="daily-joke-text"', html)
        self.assertIn('src="js/daily-joke.js"', html)
        self.assertIn("window.DailyJoke.getToday()", app)
        self.assertNotIn("joke.number", app)
        self.assertIn("new Date()", daily_joke)
        self.assertIn("window.localStorage", daily_joke)
        self.assertIn("Math.random()", daily_joke)
        self.assertEqual(daily_joke.count("].join(\"\\n\")"), 10)

    def test_about_and_daily_joke_confirm_buttons_use_right_aligned_actions(self) -> None:
        root = Path(__file__).resolve().parents[1]
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        css = (root / "web" / "css" / "app.css").read_text(encoding="utf-8")

        daily_dialog = html[
            html.index('id="daily-joke-dialog"') : html.index("</dialog>", html.index('id="daily-joke-dialog"'))
        ]
        about_dialog = html[
            html.index('id="about-dialog"') : html.index("</dialog>", html.index('id="about-dialog"'))
        ]
        self.assertIn('class="dialog-actions"', daily_dialog)
        self.assertIn('class="dialog-actions"', about_dialog)
        self.assertIn("justify-content: flex-end", css)

    def test_daily_joke_is_fixed_size_static_text_without_scrollbar(self) -> None:
        root = Path(__file__).resolve().parents[1]
        css = (root / "web" / "css" / "app.css").read_text(encoding="utf-8")
        dialog_start = css.index(".daily-joke-dialog {")
        dialog_end = css.index("}", dialog_start)
        dialog_rule = css[dialog_start:dialog_end]
        content_start = css.index(".daily-joke-content {")
        content_end = css.index("}", content_start)
        content_rule = css[content_start:content_end]

        self.assertIn("width: 440px", dialog_rule)
        self.assertIn("height: 286px", dialog_rule)
        self.assertIn("max-width: calc(100vw - 16px)", dialog_rule)
        self.assertIn("max-height: calc(100vh - 16px)", dialog_rule)
        self.assertIn("overflow: hidden", content_rule)
        self.assertNotIn("overflow-y: auto", content_rule)
        self.assertNotIn(".daily-joke-content::-webkit-scrollbar", css)

    def test_daily_joke_title_has_a_light_divider(self) -> None:
        root = Path(__file__).resolve().parents[1]
        css = (root / "web" / "css" / "app.css").read_text(encoding="utf-8")
        heading_start = css.index(".daily-joke-heading {")
        heading_end = css.index("}", heading_start)
        heading_rule = css[heading_start:heading_end]

        self.assertIn("border-bottom: 1px solid var(--divider)", heading_rule)


if __name__ == "__main__":
    unittest.main()
