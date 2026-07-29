"""Natural-language helpers for Home Assistant commands received from Zalo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
from typing import Any

from homeassistant.util import dt as dt_util

from .targeting import normalize_text


@dataclass(slots=True, frozen=True)
class CalendarWindow:
    """Time window requested by a Zalo calendar query."""

    start: datetime
    end: datetime
    label: str


@dataclass(slots=True, frozen=True)
class CalendarDisplayEvent:
    """One normalized event ready for sorting and display."""

    start: datetime
    end: datetime | None
    summary: str
    calendar_name: str
    location: str
    all_day: bool


def explicit_home_assistant_request_kind(text: str) -> str | None:
    """Classify explicit Home Assistant commands without catching free chat."""
    normalized = normalize_text(text)
    if not normalized:
        return None

    if _is_calendar_query(normalized):
        return "calendar"

    command_prefixes = (
        "bat ",
        "tat ",
        "mo ",
        "dong ",
        "khoa ",
        "mo khoa ",
        "tang ",
        "giam ",
        "dat nhiet do ",
        "dat dieu hoa ",
        "chuyen ",
        "dung ",
        "tam dung ",
        "tiep tuc ",
        "phat ",
        "quet ",
        "don dep ",
        "lam sach ",
        "kiem tra ",
        "xem trang thai ",
        "trang thai ",
        "cho toi biet ",
        "bao cao ",
        "thoi tiet ",
        "du bao ",
    )
    exact_queries = {
        "thoi tiet",
        "du bao thoi tiet",
        "nhiet do",
        "do am",
        "trang thai nha",
        "kiem tra nha",
        "nha dang the nao",
    }
    if normalized in exact_queries or normalized.startswith(command_prefixes):
        return "conversation"

    query_terms = (
        "thoi tiet",
        "du bao",
        "trang thai",
        "dang bat",
        "dang tat",
        "da khoa",
        "dang khoa",
        "khoa chua",
        "da mo khoa",
        "nhiet do",
        "do am",
        "phong nao",
        "khu vuc nao",
        "tang nao",
        "thiet bi nao",
    )
    if any(term in normalized for term in query_terms):
        return "conversation"
    return None


def calendar_window_from_text(text: str, now: datetime) -> CalendarWindow:
    """Return a useful local time range for a Vietnamese calendar query."""
    normalized = normalize_text(text)
    local_now = dt_util.as_local(now)
    tzinfo = local_now.tzinfo

    today_start = datetime.combine(local_now.date(), time.min, tzinfo=tzinfo)
    tomorrow_start = today_start + timedelta(days=1)

    if "ngay mai" in normalized:
        return CalendarWindow(
            start=tomorrow_start,
            end=tomorrow_start + timedelta(days=1),
            label="ngày mai",
        )
    if "hom nay" in normalized:
        return CalendarWindow(
            start=local_now,
            end=tomorrow_start,
            label="hôm nay",
        )
    if "tuan nay" in normalized:
        end = today_start + timedelta(days=7 - local_now.weekday())
        return CalendarWindow(local_now, end, "tuần này")
    if "tuan toi" in normalized or "7 ngay" in normalized:
        return CalendarWindow(
            local_now,
            local_now + timedelta(days=7),
            "7 ngày tới",
        )

    match = re.search(r"\b(\d{1,2})\s*ngay(?:\s*(?:toi|sap toi))?\b", normalized)
    if match:
        days = max(1, min(31, int(match.group(1))))
        return CalendarWindow(
            local_now,
            local_now + timedelta(days=days),
            f"{days} ngày tới",
        )

    return CalendarWindow(
        local_now,
        local_now + timedelta(days=7),
        "7 ngày tới",
    )


def calendar_matches_query(
    text: str, entity_id: str, friendly_name: str
) -> bool:
    """Return whether a query explicitly names a calendar entity."""
    normalized = normalize_text(text)
    names = {
        normalize_text(friendly_name),
        normalize_text(entity_id.split(".", 1)[-1].replace("_", " ")),
    }
    return any(name and len(name) >= 3 and name in normalized for name in names)


def extract_calendar_events(
    response: Any,
    entity_id: str,
    calendar_name: str,
) -> list[CalendarDisplayEvent]:
    """Normalize calendar.get_events response shapes across HA releases."""
    payload = response
    if isinstance(response, dict) and entity_id in response:
        payload = response[entity_id]
    if isinstance(payload, dict):
        raw_events = payload.get("events", [])
    elif isinstance(payload, list):
        raw_events = payload
    else:
        raw_events = []

    result: list[CalendarDisplayEvent] = []
    for item in raw_events:
        if not isinstance(item, dict):
            continue
        event = _normalize_calendar_event(item, calendar_name)
        if event is not None:
            result.append(event)
    return result


def event_from_calendar_state(
    attributes: dict[str, Any], calendar_name: str
) -> CalendarDisplayEvent | None:
    """Build a fallback event from a calendar entity's current attributes."""
    if not attributes.get("start_time"):
        return None
    return _normalize_calendar_event(
        {
            "summary": attributes.get("message") or attributes.get("summary"),
            "start": attributes.get("start_time"),
            "end": attributes.get("end_time"),
            "location": attributes.get("location"),
            "description": attributes.get("description"),
            "all_day": attributes.get("all_day"),
        },
        calendar_name,
    )


def format_calendar_events(
    events: list[CalendarDisplayEvent],
    window: CalendarWindow,
    now: datetime,
    limit: int = 10,
) -> str:
    """Format sorted calendar events as a compact Vietnamese Zalo reply."""
    unique: dict[tuple[str, datetime, str], CalendarDisplayEvent] = {}
    for event in events:
        if event.start >= window.end:
            continue
        if event.end is not None and event.end <= window.start:
            continue
        if event.end is None and event.start < window.start:
            continue
        unique[(event.calendar_name, event.start, event.summary)] = event

    ordered = sorted(unique.values(), key=lambda event: event.start)
    if not ordered:
        return f"Không có sự kiện nào trong {window.label}."

    local_now = dt_util.as_local(now)
    lines = [f"Lịch {window.label}:"]
    for index, event in enumerate(ordered[:limit], start=1):
        when = _format_event_time(event, local_now)
        calendar_label = (
            f" [{event.calendar_name}]" if event.calendar_name else ""
        )
        location = f" — {event.location}" if event.location else ""
        lines.append(
            f"{index}. {when}: {event.summary}{calendar_label}{location}"
        )
    remaining = len(ordered) - limit
    if remaining > 0:
        lines.append(f"Còn {remaining} sự kiện khác.")
    return "\n".join(lines)


def _is_calendar_query(normalized: str) -> bool:
    """Return whether normalized text asks about calendar events."""
    reminder_terms = ("lich nhac", "nhac hen", "nhac nho", "hen gio")
    if any(term in normalized for term in reminder_terms):
        return False
    if "su kien" in normalized:
        return True
    calendar_phrases = {
        "lich",
        "xem lich",
        "kiem tra lich",
        "lich cua toi",
        "lich hom nay",
        "lich ngay mai",
        "lich sap toi",
        "lich tuan nay",
        "lich tuan toi",
        "toi co lich gi",
        "hom nay co lich gi",
        "ngay mai co lich gi",
    }
    return (
        normalized in calendar_phrases
        or normalized.startswith("xem lich ")
        or normalized.startswith("lich ")
    )


def _parse_event_datetime(value: Any) -> tuple[datetime | None, bool]:
    """Parse a calendar date/datetime value and flag all-day values."""
    if isinstance(value, datetime):
        parsed = value
        all_day = False
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min, tzinfo=dt_util.now().tzinfo)
        all_day = True
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None, False
        parsed = dt_util.parse_datetime(raw)
        all_day = parsed is None
        if parsed is None:
            parsed_date = dt_util.parse_date(raw)
            if parsed_date is None:
                return None, False
            parsed = datetime.combine(
                parsed_date, time.min, tzinfo=dt_util.now().tzinfo
            )
    else:
        return None, False

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.now().tzinfo)
    return dt_util.as_local(parsed), all_day


def _normalize_calendar_event(
    item: dict[str, Any], calendar_name: str
) -> CalendarDisplayEvent | None:
    """Normalize one raw calendar event."""
    start, inferred_all_day = _parse_event_datetime(item.get("start"))
    if start is None:
        return None
    end, _ = _parse_event_datetime(item.get("end"))
    summary = str(
        item.get("summary") or item.get("message") or "Sự kiện không có tên"
    ).strip()
    return CalendarDisplayEvent(
        start=start,
        end=end,
        summary=summary,
        calendar_name=calendar_name,
        location=str(item.get("location") or "").strip(),
        all_day=bool(item.get("all_day", inferred_all_day)),
    )


def _format_event_time(
    event: CalendarDisplayEvent, local_now: datetime
) -> str:
    """Return a natural local timestamp for one event."""
    event_start = dt_util.as_local(event.start)
    day = event_start.date()
    if day == local_now.date():
        day_label = "Hôm nay"
    elif day == local_now.date() + timedelta(days=1):
        day_label = "Ngày mai"
    else:
        day_label = event_start.strftime("Ngày %d/%m/%Y")
    if event.all_day:
        return f"{day_label}, cả ngày"
    return f"{day_label} lúc {event_start.strftime('%H:%M')}"
