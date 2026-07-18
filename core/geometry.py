"""Shared geometry precision constants (independent of speed tier)."""

from __future__ import annotations

# Screen-space chord-height tolerance for curve flattening.
FLATNESS_PX = 0.75

# Maximum distance between consecutive flattened points on near-straight spans.
MAX_FLATTEN_STEP_PX = 8.0
