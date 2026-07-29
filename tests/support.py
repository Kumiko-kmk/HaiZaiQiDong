"""Small, shared test fixtures for desktop workflow tests."""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock, patch

from core.curves.segments import LineSegment, MoveSegment
from core.mouse_controller import MouseButton
from core.stroke_executor import DrawSettings
from core.transform import TransformState
from gui.app_service import AppService
from gui.state import AppState
from presets.models import Preset, Stroke
from presets.registry import PNG_SIGNATURE, PresetRegistry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "web"


class RecordingMouse:
    """Mouse-controller substitute that records calls and can fail on a move."""

    def __init__(self, *, fail_after_moves: int | None = None) -> None:
        self.events: list[tuple] = []
        self.moves = 0
        self.fail_after_moves = fail_after_moves

    def ensure_pen_up(self, *, gap_sec: float = 0.0) -> None:
        self.events.append(("up", gap_sec))

    def move_absolute(self, x: float, y: float) -> None:
        self.moves += 1
        self.events.append(("move", x, y))
        if self.fail_after_moves is not None and self.moves >= self.fail_after_moves:
            raise RuntimeError("move failed")

    def press(self, button: MouseButton) -> None:
        self.events.append(("press", button))

    def release(self, button: MouseButton | None = None) -> None:
        self.events.append(("release", button))

    def best_effort_release_all(self) -> None:
        self.events.append(("release_all",))


def make_preset(
    *,
    preset_id: str = "test",
    name: str = "Test",
    points: tuple[tuple[float, float], ...] = ((0.0, 0.0), (10.0, 0.0)),
    button: MouseButton = MouseButton.RIGHT,
) -> Preset:
    """Build the smallest real preset suitable for drawing workflow tests."""

    if not points:
        raise ValueError("points must not be empty")
    segments = [MoveSegment(points[0])]
    segments.extend(LineSegment(point) for point in points[1:])
    return Preset(
        id=preset_id,
        name=name,
        version=3,
        strokes=[Stroke(tuple(segments))],
        draw_button=button,
    )


@dataclass(frozen=True)
class AppServiceHarness:
    service: AppService
    registry: object
    router: object
    controller: object
    overlay: object


def make_app_service(
    *,
    registry: object | None = None,
    router: object | None = None,
    controller: object | None = None,
    overlay: object | None = None,
    start_result: bool = True,
    state: AppState = AppState.READY,
    preset: Preset | None = None,
    stub_settings: bool = True,
) -> AppServiceHarness:
    """Construct AppService without starting hooks, overlays, or real input."""

    registry = registry if registry is not None else Mock()
    router = router if router is not None else Mock()
    overlay = overlay if overlay is not None else Mock()
    if controller is None:
        controller = Mock()
        controller.start.return_value = start_result
        controller.history.list_entries.return_value = []

    with (
        patch("gui.app_service.get_registry", return_value=registry),
        patch("gui.app_service.InputRouter", return_value=router),
        patch("gui.app_service.DrawController", return_value=controller),
        patch("gui.app_service.OverlayBridge", return_value=overlay),
        patch("gui.app_service.HistoryStore", return_value=Mock()),
    ):
        service = AppService()

    service.selected_preset = preset or make_preset()
    service.app_state = state
    if stub_settings:
        service._build_settings = Mock(
            return_value=DrawSettings(
                transform=TransformState(),
                button=MouseButton.RIGHT,
            )
        )
        service._reset_transform = Mock()
    return AppServiceHarness(service, registry, router, controller, overlay)


class RegistryTestCase(unittest.TestCase):
    """Test case with an isolated preset registry and automatic cleanup."""

    split_registry = False

    def setUp(self) -> None:
        super().setUp()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.registry = self.make_registry(split=self.split_registry)

    def make_registry(self, *, split: bool = False) -> PresetRegistry:
        if split:
            self.builtin_dir = self.root / "builtins"
            self.custom_dir = self.root / "custom"
            return PresetRegistry(self.builtin_dir, self.custom_dir)
        self.builtin_dir = self.root
        self.custom_dir = self.root
        return PresetRegistry(self.root)


def write_preset(
    directory: Path,
    preset_id: str,
    *,
    tags: list[str] | None = None,
    menu_order: int | None = None,
) -> Path:
    """Write a minimal preset JSON fixture and return its path."""

    data: dict[str, object] = {
        "id": preset_id,
        "name": preset_id,
        "strokes": [
            {
                "segments": [
                    {"type": "polyline", "points": [[0, 0], [10, 10]]}
                ]
            }
        ],
    }
    if tags is not None:
        data["tags"] = tags
    if menu_order is not None:
        data["menuOrder"] = menu_order
    path = directory / f"{preset_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def png_data_url(payload: bytes = b"preview") -> str:
    return "data:image/png;base64," + base64.b64encode(
        PNG_SIGNATURE + payload
    ).decode("ascii")
