"""Draw session controller with progress, diagnostics, and cancellation."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Optional, Tuple

from core.history import HistoryEntry, HistoryStore
from core.mouse_controller import InputInjectionError, MouseController
from core.speed_tier import PEN_UP_GAP_SEC
from core.stroke_executor import DrawSettings, PathDrawer
from presets.models import Preset

Point = Tuple[float, float]
ProgressCallback = Callable[[int, int], None]
_LOG = logging.getLogger(__name__)


class DrawOutcome(str, Enum):
    SUCCESS = "成功"
    CANCELLED = "已取消"
    FAILED = "失败"


@dataclass(frozen=True)
class DrawResult:
    outcome: DrawOutcome
    duration_sec: float
    failure_code: str | None = None
    message: str = ""
    event_count: int = 0


FinishCallback = Callable[[DrawResult], None]


@dataclass
class DrawSession:
    preset: Preset
    anchor: Point
    settings: DrawSettings


class DrawController:
    def __init__(
        self,
        drawer: PathDrawer | None = None,
        history: HistoryStore | None = None,
    ) -> None:
        self._drawer = drawer or PathDrawer(MouseController())
        self._mouse = self._drawer._mouse
        self._history = history or HistoryStore()
        self._cancel_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._session: Optional[DrawSession] = None
        self._stroke_index = 0
        self._on_progress: Optional[ProgressCallback] = None
        self._on_finish: Optional[FinishCallback] = None
        self._started_at = 0.0

    @property
    def history(self) -> HistoryStore:
        return self._history

    @property
    def is_active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        session: DrawSession,
        *,
        on_progress: Optional[ProgressCallback] = None,
        on_finish: Optional[FinishCallback] = None,
        start_stroke_index: int = 0,
    ) -> bool:
        if self.is_active:
            return False
        self._session = session
        self._stroke_index = start_stroke_index
        self._on_progress = on_progress
        self._on_finish = on_finish
        self._cancel_event.clear()
        self._started_at = time.perf_counter()
        self._thread = threading.Thread(target=self._run, daemon=True, name="stroke-drawer")
        self._thread.start()
        return True

    def cancel(self) -> None:
        self._cancel_event.set()
        self._mouse.best_effort_release_all()

    def _run(self) -> None:
        outcome = DrawOutcome.FAILED
        failure_code: str | None = None
        message = ""
        event_count = 0
        session = self._session
        try:
            if session is None:
                failure_code = "missing_session"
                message = "绘制会话不存在。"
                return

            total = len(session.preset.strokes)
            self._mouse.ensure_pen_up(gap_sec=PEN_UP_GAP_SEC)
            while self._stroke_index < total:
                if self._cancel_event.is_set():
                    outcome = DrawOutcome.CANCELLED
                    message = "绘制已取消。"
                    return

                if self._on_progress is not None:
                    self._on_progress(self._stroke_index + 1, total)

                event_count += self._drawer.draw_single_stroke(
                    session.preset,
                    session.anchor,
                    session.settings,
                    self._stroke_index,
                    abort_event=self._cancel_event,
                )
                self._stroke_index += 1

                if self._cancel_event.is_set():
                    outcome = DrawOutcome.CANCELLED
                    message = "绘制已取消。"
                    return
                if self._stroke_index < total and session.settings.stroke_pause_ms > 0:
                    if self._cancel_event.wait(session.settings.stroke_pause_ms / 1000.0):
                        outcome = DrawOutcome.CANCELLED
                        message = "绘制已取消。"
                        return

            outcome = DrawOutcome.SUCCESS
            message = "绘制完成。"
        except InputInjectionError as exc:
            failure_code = exc.failure_code
            message = (
                "鼠标输入注入失败。请确保本程序与游戏使用相同权限级别；"
                "如果游戏以管理员身份运行，请同样以管理员身份运行本程序。"
                f"详情：{exc}"
            )
            _LOG.exception("Mouse input injection failed")
        except Exception as exc:
            failure_code = "draw_error"
            message = f"绘制失败：{exc}"
            _LOG.exception("Unhandled drawing failure")
        finally:
            self._mouse.best_effort_release_all()
            duration = max(0.0, time.perf_counter() - self._started_at)
            result = DrawResult(
                outcome=outcome,
                duration_sec=duration,
                failure_code=failure_code,
                message=message,
                event_count=event_count,
            )
            self._thread = None
            self._cancel_event.clear()

            if session is not None:
                self._history.add(
                    HistoryEntry(
                        timestamp=datetime.now(),
                        preset_name=session.preset.name,
                        anchor=session.anchor,
                        scale=session.settings.transform.scale,
                        rotation_deg=session.settings.transform.rotation_deg,
                        flip_label=session.settings.transform.flip_label(),
                        status=outcome.value,
                        duration_sec=duration,
                        draw_button=session.settings.button.value,
                        failure_code=failure_code,
                        message=message,
                        event_count=event_count,
                    )
                )

            on_finish = self._on_finish
            if on_finish is not None:
                try:
                    on_finish(result)
                except Exception:
                    _LOG.exception("Draw finish callback failed")

            self._session = None
            self._stroke_index = 0
