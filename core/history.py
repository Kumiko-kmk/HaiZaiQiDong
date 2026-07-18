"""Bounded, optionally persistent draw history."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, List, Mapping, Tuple

Point = Tuple[float, float]
_LOG = logging.getLogger(__name__)
_SCHEMA_VERSION = 1


@dataclass
class HistoryEntry:
    timestamp: datetime
    preset_name: str
    anchor: Point
    scale: float
    rotation_deg: float
    flip_label: str
    status: str
    duration_sec: float
    draw_button: str = "right"
    failure_code: str | None = None
    message: str = ""
    event_count: int = 0


class HistoryStore:
    def __init__(
        self,
        max_entries: int = 200,
        *,
        log_path: Path | None = None,
    ) -> None:
        self._max_entries = max(1, int(max_entries))
        self._log_path = Path(log_path) if log_path is not None else None
        self._entries: List[HistoryEntry] = []
        self._lock = threading.RLock()
        self._persisted_line_count = 0
        self._load()

    def add(self, entry: HistoryEntry) -> None:
        with self._lock:
            self._entries.insert(0, entry)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[: self._max_entries]
            if self._append(entry):
                self._persisted_line_count += 1
                if self._persisted_line_count > self._max_entries * 2:
                    self._compact()

    def list_entries(self) -> List[HistoryEntry]:
        with self._lock:
            return list(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._persisted_line_count = 0
            if self._log_path is None:
                return
            try:
                self._log_path.unlink(missing_ok=True)
            except OSError:
                _LOG.warning("Unable to clear draw history log: %s", self._log_path, exc_info=True)

    def _load(self) -> None:
        if self._log_path is None or not self._log_path.is_file():
            return
        try:
            lines = self._log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            _LOG.warning("Unable to read draw history log: %s", self._log_path, exc_info=True)
            return

        loaded: List[HistoryEntry] = []
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                if not isinstance(payload, Mapping):
                    raise ValueError("history row must be an object")
                loaded.append(_entry_from_dict(payload))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                _LOG.warning(
                    "Ignoring invalid draw history row %d in %s",
                    line_number,
                    self._log_path,
                )

        self._persisted_line_count = len(lines)
        self._entries = list(reversed(loaded[-self._max_entries :]))
        if self._persisted_line_count > self._max_entries * 2:
            self._compact()

    def _append(self, entry: HistoryEntry) -> bool:
        if self._log_path is None:
            return False
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8", newline="\n") as handle:
                json.dump(_entry_to_dict(entry), handle, ensure_ascii=False, separators=(",", ":"))
                handle.write("\n")
            return True
        except OSError:
            # History persistence must never prevent the drawing thread from finishing.
            _LOG.warning("Unable to append draw history log: %s", self._log_path, exc_info=True)
            return False

    def _compact(self) -> None:
        if self._log_path is None:
            return
        temporary = self._log_path.with_suffix(self._log_path.suffix + ".tmp")
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                for entry in reversed(self._entries):
                    json.dump(_entry_to_dict(entry), handle, ensure_ascii=False, separators=(",", ":"))
                    handle.write("\n")
            temporary.replace(self._log_path)
            self._persisted_line_count = len(self._entries)
        except OSError:
            _LOG.warning("Unable to compact draw history log: %s", self._log_path, exc_info=True)
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _entry_to_dict(entry: HistoryEntry) -> dict[str, Any]:
    return {
        "schemaVersion": _SCHEMA_VERSION,
        "timestamp": entry.timestamp.isoformat(timespec="milliseconds"),
        "presetName": entry.preset_name,
        "anchor": [float(entry.anchor[0]), float(entry.anchor[1])],
        "scale": float(entry.scale),
        "rotationDeg": float(entry.rotation_deg),
        "flipLabel": entry.flip_label,
        "status": entry.status,
        "durationSec": float(entry.duration_sec),
        "drawButton": entry.draw_button,
        "failureCode": entry.failure_code,
        "message": entry.message,
        "eventCount": int(entry.event_count),
    }


def _entry_from_dict(payload: Mapping[str, Any]) -> HistoryEntry:
    anchor = payload.get("anchor", (0.0, 0.0))
    if not isinstance(anchor, (list, tuple)) or len(anchor) != 2:
        raise ValueError("invalid anchor")
    return HistoryEntry(
        timestamp=datetime.fromisoformat(str(payload["timestamp"])),
        preset_name=str(payload["presetName"]),
        anchor=(float(anchor[0]), float(anchor[1])),
        scale=float(payload.get("scale", 1.0)),
        rotation_deg=float(payload.get("rotationDeg", 0.0)),
        flip_label=str(payload.get("flipLabel", "无")),
        status=str(payload["status"]),
        duration_sec=float(payload.get("durationSec", 0.0)),
        draw_button=str(payload.get("drawButton", "right")),
        failure_code=(
            str(payload["failureCode"])
            if payload.get("failureCode") is not None
            else None
        ),
        message=str(payload.get("message", "")),
        event_count=int(payload.get("eventCount", 0)),
    )
