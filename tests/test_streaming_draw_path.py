from __future__ import annotations

import math
import unittest

from core.curves.segments import (
    CubicBezierSegment,
    LineSegment,
    MoveSegment,
    QuadraticBezierSegment,
)
from core.draw_path import _point_to_chord_distance, iter_resampled_points, iter_stroke_points
from core.transform import TransformState


class StreamingDrawPathTests(unittest.TestCase):
    def test_line_is_resampled_by_arc_length_and_keeps_endpoints(self) -> None:
        points = list(
            iter_stroke_points(
                (MoveSegment((0, 0)), LineSegment((10, 0))),
                (0, 0),
                TransformState(),
                0.75,
                sample_spacing_px=3.0,
            )
        )

        self.assertEqual(points[0], (0.0, 0.0))
        self.assertEqual(points[-1], (10.0, 0.0))
        self.assertLessEqual(max(math.dist(a, b) for a, b in zip(points, points[1:])), 3.000001)

    def test_quadratic_and_cubic_keep_final_endpoint_with_bounded_gaps(self) -> None:
        segments = (
            MoveSegment((0, 0)),
            QuadraticBezierSegment((20, 30), (40, 0)),
            CubicBezierSegment((50, -20), (70, 20), (80, 0)),
        )
        points = list(
            iter_stroke_points(
                segments,
                (100, 200),
                TransformState(),
                0.75,
                sample_spacing_px=3.0,
            )
        )

        self.assertEqual(points[0], (100.0, 200.0))
        self.assertEqual(points[-1], (180.0, 200.0))
        self.assertLessEqual(max(math.dist(a, b) for a, b in zip(points, points[1:])), 3.000001)

    def test_rotation_scale_and_negative_virtual_desktop_coordinates(self) -> None:
        transform = TransformState.with_scale(2.0)
        transform.rotation_deg = 90.0
        points = list(
            iter_stroke_points(
                (MoveSegment((0, 0)), LineSegment((10, 0))),
                (-100, -50),
                transform,
                0.75,
                sample_spacing_px=3.0,
            )
        )

        self.assertAlmostEqual(points[0][0], -100.0)
        self.assertAlmostEqual(points[0][1], -50.0)
        self.assertAlmostEqual(points[-1][0], -100.0)
        self.assertAlmostEqual(points[-1][1], -30.0)

    def test_resampler_removes_duplicates(self) -> None:
        points = list(iter_resampled_points([(0, 0), (0, 0), (2, 0), (2, 0)], 3.0))
        self.assertEqual(points, [(0, 0), (2, 0)])

    def test_resampler_keeps_corner_error_within_one_pixel(self) -> None:
        points = list(iter_resampled_points([(0, 0), (1.5, 1.5), (3, 0)], 3.0))
        error = min(
            _point_to_chord_distance((1.5, 1.5), start, end)
            for start, end in zip(points, points[1:])
        )
        self.assertLessEqual(error, 1.0)


if __name__ == "__main__":
    unittest.main()
