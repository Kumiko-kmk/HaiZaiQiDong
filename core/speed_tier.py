"""Distance-based draw pacing configuration."""

from __future__ import annotations

from dataclasses import dataclass

PEN_UP_GAP_SEC = 0.01


@dataclass(frozen=True)
class SpeedProfile:
    """Geometry-independent limits for smooth, predictable cursor motion."""

    draw_speed_px_s: float
    sample_spacing_px: float
    max_event_rate_hz: float
    stroke_pause_ms: int = 0

    def __post_init__(self) -> None:
        if self.draw_speed_px_s <= 0:
            raise ValueError("draw_speed_px_s must be positive")
        if self.sample_spacing_px <= 0:
            raise ValueError("sample_spacing_px must be positive")
        if self.max_event_rate_hz <= 0:
            raise ValueError("max_event_rate_hz must be positive")
        if self.stroke_pause_ms < 0:
            raise ValueError("stroke_pause_ms cannot be negative")


DEFAULT_SPEED_PROFILE = SpeedProfile(
    draw_speed_px_s=720.0,
    sample_spacing_px=3.0,
    max_event_rate_hz=240.0,
    stroke_pause_ms=0,
)
