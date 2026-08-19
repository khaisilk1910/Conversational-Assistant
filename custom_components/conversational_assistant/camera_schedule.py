"""Deterministic parsing helpers for scheduled camera snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re

from .models import Recurrence
from .parser import ReminderParseError, parse_reminder_request
from .targeting import normalize_text


@dataclass(slots=True, frozen=True)
class CameraScheduleRequest:
    """Raw scheduled-camera command split into time and camera/destination text."""

    schedule_text: str
    camera_tail: str


@dataclass(slots=True, frozen=True)
class CameraScheduleSpec:
    """Resolved first run and recurrence for one camera snapshot schedule."""

    first_run: datetime
    recurrence: Recurrence
    interval_minutes: int | None = None

    @property
    def is_recurring(self) -> bool:
        """Return whether the schedule repeats."""
        return bool(self.interval_minutes) or self.recurrence.kind != "none"


_SCHEDULE_PREFIXES = (
    ("hen", "gio"),
    ("hen",),
    ("len", "lich"),
    ("dat", "lich"),
    ("schedule",),
)

_CAPTURE_PREFIXES = (
    ("chup", "anh", "camera"),
    ("chup", "anh", "cam"),
    ("chup", "hinh", "camera"),
    ("chup", "hinh", "cam"),
    ("chup", "camera"),
    ("chup", "cam"),
    ("chup", "may", "quay"),
    ("take", "a", "camera", "snapshot"),
    ("take", "camera", "snapshot"),
    ("capture", "camera", "image"),
    ("take", "a", "photo", "from", "camera"),
)


def camera_schedule_request(text: str) -> CameraScheduleRequest | None:
    """Return schedule/camera pieces only for an explicit scheduled snapshot command."""
    raw = str(text or "").strip()
    word_matches = list(re.finditer(r"[^\W_]+|\d+", raw, re.UNICODE))
    if not word_matches:
        return None
    words = [normalize_text(match.group(0)) for match in word_matches]
    start = 1 if words[0] in {"hay", "please"} else 0

    prefix_end: int | None = None
    for prefix in sorted(_SCHEDULE_PREFIXES, key=len, reverse=True):
        end = start + len(prefix)
        if tuple(words[start:end]) == prefix:
            prefix_end = end
            break
    if prefix_end is None:
        return None

    action_pos: int | None = None
    action_end: int | None = None
    for pos in range(prefix_end, len(words)):
        for prefix in sorted(_CAPTURE_PREFIXES, key=len, reverse=True):
            end = pos + len(prefix)
            if tuple(words[pos:end]) == prefix:
                action_pos = pos
                action_end = end
                break
        if action_pos is not None:
            break
    if action_pos is None or action_end is None:
        return None

    schedule_start = word_matches[prefix_end - 1].end()
    schedule_end = word_matches[action_pos].start()
    schedule_text = raw[schedule_start:schedule_end].strip(" \t\r\n,;:-–—")
    camera_tail = raw[word_matches[action_end - 1].end() :].strip(
        " \t\r\n,;:-–—"
    )
    if not schedule_text:
        return None
    return CameraScheduleRequest(
        schedule_text=schedule_text,
        camera_tail=camera_tail,
    )


def parse_camera_schedule_spec(
    schedule_text: str, now: datetime
) -> CameraScheduleSpec:
    """Resolve a scheduled snapshot time with deterministic local parsing."""
    normalized = normalize_text(schedule_text)

    interval = re.fullmatch(
        r"(?:(?:cu|lap)\s+)?(?:moi|cach)\s+(?P<n>\d+)\s*"
        r"(?P<u>phut|gio|tieng)(?:\s+(?:mot\s+lan|lan))?",
        normalized,
    )
    if interval is None:
        interval = re.fullmatch(
            r"every\s+(?P<n>\d+)\s*(?P<u>minutes?|mins?|hours?|hrs?)",
            normalized,
        )
    if interval is not None:
        amount = int(interval.group("n"))
        if amount <= 0:
            raise ReminderParseError("Chu kỳ chụp camera phải lớn hơn 0.")
        unit = interval.group("u")
        interval_minutes = amount * 60 if unit in {"gio", "tieng", "hour", "hours", "hr", "hrs"} else amount
        if interval_minutes < 1:
            raise ReminderParseError("Chu kỳ chụp camera tối thiểu là 1 phút.")
        return CameraScheduleSpec(
            first_run=now + timedelta(minutes=interval_minutes),
            recurrence=Recurrence(),
            interval_minutes=interval_minutes,
        )

    parsed = parse_reminder_request(
        f"{schedule_text.strip()} chụp camera",
        now=now,
    )
    return CameraScheduleSpec(
        first_run=parsed.first_run,
        recurrence=parsed.recurrence,
        interval_minutes=None,
    )


def is_camera_schedule_list_request(text: str) -> bool:
    """Return whether text asks to list camera snapshot schedules."""
    normalized = normalize_text(text)
    if not normalized:
        return False
    phrases = (
        "danh sach lich chup camera",
        "danh sach lich chup cam",
        "list lich chup camera",
        "list lich chup cam",
        "list danh sach lich chup camera",
        "list danh sach lich chup cam",
        "xem cac lich chup camera",
        "xem cac lich chup cam",
        "danh sach hen chup camera",
        "danh sach hen chup cam",
        "lich chup camera",
        "lich chup cam",
        "xem lich chup camera",
        "xem lich chup cam",
        "liet ke lich chup camera",
        "liet ke lich chup cam",
        "cho toi xem lich chup camera",
        "cho toi xem lich chup cam",
        "list camera snapshot schedules",
        "show camera snapshot schedules",
    )
    return normalized in phrases or normalized.startswith(
        (
            "xem danh sach lich chup camera",
            "xem danh sach lich chup cam",
            "liet ke danh sach lich chup camera",
            "liet ke danh sach lich chup cam",
            "list cac lich chup camera",
            "list cac lich chup cam",
        )
    )


def camera_schedule_delete_request(text: str) -> str | None:
    """Return optional text following an explicit camera-schedule delete command."""
    normalized = normalize_text(text)
    prefixes = (
        "xoa lich chup camera",
        "xoa lich chup cam",
        "huy lich chup camera",
        "huy lich chup cam",
        "xoa hen chup camera",
        "xoa hen chup cam",
        "huy hen chup camera",
        "huy hen chup cam",
        "delete camera snapshot schedule",
        "delete camera snapshot schedules",
        "cancel camera snapshot schedule",
    )
    for prefix in prefixes:
        if normalized == prefix:
            return ""
        if normalized.startswith(prefix + " "):
            return normalized[len(prefix) :].strip()
    return None


def camera_schedule_recurrence_label(
    recurrence: Recurrence, interval_minutes: int | None
) -> str:
    """Return a compact Vietnamese recurrence label for UI/sensor text."""
    if interval_minutes:
        if interval_minutes % 60 == 0:
            hours = interval_minutes // 60
            return f"mỗi {hours} giờ"
        return f"mỗi {interval_minutes} phút"
    if recurrence.kind == "daily":
        return "hằng ngày"
    if recurrence.kind == "weekdays":
        return "thứ Hai đến thứ Sáu"
    if recurrence.kind == "weekend":
        return "cuối tuần"
    if recurrence.kind == "weekly":
        weekdays = recurrence.weekdays or (
            [recurrence.weekday] if recurrence.weekday is not None else []
        )
        labels = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
        values = [labels[item] for item in weekdays if 0 <= item <= 6]
        return "hằng tuần " + ", ".join(values) if values else "hằng tuần"
    if recurrence.kind == "monthly":
        return f"hằng tháng ngày {recurrence.day_of_month or '?'}"
    if recurrence.kind == "yearly":
        return (
            "hằng năm ngày "
            f"{recurrence.day_of_month or '?'}/{recurrence.month or '?'}"
        )
    return "một lần"
