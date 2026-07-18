from __future__ import annotations

import json
import time
import unittest
from pathlib import Path

from core.draw_path import build_stroke_path, iter_stroke_points
from core.geometry import FLATNESS_PX, MAX_FLATTEN_STEP_PX
from core.transform import TransformState
from presets.models import Preset


class PresetPathPerformanceTests(unittest.TestCase):
    def test_all_presets_stream_immediately_and_reduce_events(self) -> None:
        data_dir = Path(__file__).resolve().parents[1] / "presets" / "data"
        old_event_count = 0
        new_event_count = 0
        worst_first_point_sec = 0.0

        for path in sorted(data_dir.glob("*.json")):
            preset = Preset.from_dict(json.loads(path.read_text(encoding="utf-8")))
            for stroke in preset.strokes:
                started = time.perf_counter()
                stream = iter_stroke_points(
                    stroke.segments,
                    (0, 0),
                    TransformState(),
                    FLATNESS_PX,
                    sample_spacing_px=3.0,
                    max_step_px=MAX_FLATTEN_STEP_PX,
                )
                first = next(stream, None)
                worst_first_point_sec = max(worst_first_point_sec, time.perf_counter() - started)
                new_event_count += int(first is not None) + sum(1 for _ in stream)
                old_event_count += len(
                    build_stroke_path(
                        stroke.segments,
                        (0, 0),
                        TransformState(),
                        FLATNESS_PX,
                        max_step_px=MAX_FLATTEN_STEP_PX,
                    )
                )

        self.assertGreater(old_event_count, 0)
        self.assertLess(worst_first_point_sec, 0.1)
        reduction = 1.0 - new_event_count / old_event_count
        self.assertGreaterEqual(reduction, 0.60)


if __name__ == "__main__":
    unittest.main()
