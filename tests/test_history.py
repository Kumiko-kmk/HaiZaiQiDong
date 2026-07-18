from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from core.history import HistoryEntry, HistoryStore


def make_entry(index: int) -> HistoryEntry:
    return HistoryEntry(
        timestamp=datetime(2026, 7, 18, 9, index, 5),
        preset_name=f"预设 {index}",
        anchor=(100.0 + index, 200.0),
        scale=1.25,
        rotation_deg=15.0,
        flip_label="水平",
        status="成功",
        duration_sec=2.4,
        draw_button="left",
        message="绘制完成。",
        event_count=128 + index,
    )


class PersistentHistoryTests(unittest.TestCase):
    def test_entries_survive_store_recreation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "logs" / "drawing-history.jsonl"
            first_run = HistoryStore(log_path=path)
            first_run.add(make_entry(1))
            first_run.add(make_entry(2))

            second_run = HistoryStore(log_path=path)
            entries = second_run.list_entries()

            self.assertEqual([entry.preset_name for entry in entries], ["预设 2", "预设 1"])
            self.assertEqual(entries[0].draw_button, "left")
            self.assertEqual(entries[0].event_count, 130)

    def test_invalid_rows_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "drawing-history.jsonl"
            path.write_text(
                "not json\n"
                + json.dumps({"timestamp": "invalid"})
                + "\n"
                + json.dumps(
                    {"timestamp": "2026-07-18T09:00:00", "presetName": "不完整记录"}
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertLogs("core.history", level="WARNING"):
                store = HistoryStore(log_path=path)

            self.assertEqual(store.list_entries(), [])
            store.add(make_entry(3))
            self.assertEqual(HistoryStore(log_path=path).list_entries()[0].preset_name, "预设 3")

    def test_memory_and_log_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "drawing-history.jsonl"
            store = HistoryStore(max_entries=3, log_path=path)
            for index in range(8):
                store.add(make_entry(index))

            reloaded = HistoryStore(max_entries=3, log_path=path)

            self.assertEqual(
                [entry.preset_name for entry in reloaded.list_entries()],
                ["预设 7", "预设 6", "预设 5"],
            )
            self.assertLessEqual(len(path.read_text(encoding="utf-8").splitlines()), 6)


if __name__ == "__main__":
    unittest.main()
