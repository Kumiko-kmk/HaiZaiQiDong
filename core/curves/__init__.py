"""Unified curve flattening and segment models."""

from core.curves.flatten import flatten_stroke
from core.curves.segments import CurveSegment, segment_from_dict

__all__ = ["CurveSegment", "flatten_stroke", "segment_from_dict"]
