"""Natural-language helpers for Home Assistant commands received from Zalo."""

from __future__ import annotations

import calendar as month_calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
import unicodedata
from typing import Any

from homeassistant.components.calendar.const import CalendarEntityFeature
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
    calendar_entity_id: str
    location: str
    description: str
    all_day: bool
    uid: str = ""
    recurrence_id: str = ""
    rrule: str = ""
    can_update: bool = False
    can_delete: bool = False


@dataclass(slots=True, frozen=True)
class CalendarCreateRequest:
    """One parsed calendar event waiting to be created."""

    summary: str
    start: datetime
    end: datetime
    all_day: bool
    description: str = ""
    location: str = ""


_VI_NUMBER_WORDS = {
    "khong": 0,
    "mot": 1,
    "hai": 2,
    "ba": 3,
    "bon": 4,
    "tu": 4,
    "nam": 5,
    "lam": 5,
    "sau": 6,
    "bay": 7,
    "tam": 8,
    "chin": 9,
}
_EN_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_EN_MONTH_NUMBERS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

_NUMBER_TOKEN = (
    r"(?:\d{1,4}|khong|mot|hai|ba|bon|tu|nam|lam|sau|bay|tam|chin|"
    r"muoi|tram|linh|le|zero|one|two|three|four|five|six|seven|"
    r"eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    r"seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|"
    r"seventy|eighty|ninety|hundred)(?=\b)"
)
_NUMBER_EXPRESSION = rf"{_NUMBER_TOKEN}(?:\s+{_NUMBER_TOKEN}){{0,4}}?"
_NUMBER_EXPRESSION_GREEDY = rf"{_NUMBER_TOKEN}(?:\s+{_NUMBER_TOKEN}){{0,5}}"


def _fold_calendar_text(value: str) -> str:
    """Normalize text while preserving date and clock separators."""
    value = unicodedata.normalize("NFD", str(value or "").casefold())
    value = "".join(
        character
        for character in value
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    value = re.sub(r"[^a-z0-9:/+.-]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def explicit_home_assistant_request_kind(text: str) -> str | None:
    """Classify explicit Home Assistant commands without catching free chat."""
    normalized = normalize_text(text)
    if not normalized:
        return None

    if _is_camera_analysis_request(normalized):
        return "camera_analysis"

    if _is_camera_image_request(normalized):
        return "camera"

    if _is_calendar_query(normalized):
        return "calendar"

    command_prefixes = (
        "turn on ",
        "turn off ",
        "turn ",
        "set ",
        "dim ",
        "brighten ",
        "activate ",
        "deactivate ",
        "switch on ",
        "switch off ",
        "open ",
        "close ",
        "lock ",
        "unlock ",
        "increase ",
        "decrease ",
        "raise ",
        "lower ",
        "set temperature ",
        "set thermostat ",
        "set air conditioner ",
        "change ",
        "stop ",
        "pause ",
        "resume ",
        "play ",
        "start ",
        "clean ",
        "check ",
        "show status ",
        "status of ",
        "tell me ",
        "report ",
        "weather ",
        "forecast ",
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
        "weather",
        "weather forecast",
        "temperature",
        "humidity",
        "home status",
        "house status",
        "check the house",
        "how is the house",
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
        "weather",
        "forecast",
        "status",
        "turned on",
        "turned off",
        "is on",
        "is off",
        "locked",
        "unlocked",
        "temperature",
        "humidity",
        "which room",
        "which area",
        "which floor",
        "which device",
        "which lights",
        "lights on",
        "lights off",
        "devices on",
        "devices off",
        "doors locked",
        "doors unlocked",
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


def calendar_request_action(text: str) -> str:
    """Return whether a calendar request reads or creates events."""
    normalized = normalize_text(text)
    create_patterns = (
        r"\b(?:tao|them|dat|len)\s+(?:mot\s+)?(?:su kien|event)\b",
        r"\b(?:tao|them|dat|len)\s+(?:mot\s+)?(?:cuoc hop|cuoc hen)\b",
        r"\b(?:tao|them|dat|len)\s+(?:mot\s+)?lich\s+(?!nhac)",
        r"\b(?:create|add|schedule|book)\s+(?:an?\s+)?(?:calendar\s+)?event\b",
        r"\b(?:create|add|schedule|book)\s+(?:an?\s+)?(?:meeting|appointment)\b",
        r"\badd\s+.+\s+to\s+(?:my\s+)?calendar\b",
    )
    if any(re.search(pattern, normalized) for pattern in create_patterns):
        return "create"
    return "query"


def calendar_has_time_reference(text: str) -> bool:
    """Return whether text contains an explicit calendar lookup horizon."""
    normalized = _fold_calendar_text(text)
    if not normalized:
        return False
    phrases = (
        "hom nay",
        "toi nay",
        "ngay mai",
        "ngay kia",
        "ngay mot",
        "tuan nay",
        "tuan toi",
        "tuan sau",
        "thang nay",
        "thang toi",
        "thang sau",
        "cuoi tuan",
        "cuoi tuan sau",
        "cuoi tuan toi",
        "dau tuan sau",
        "cuoi thang",
        "cuoi thang nay",
        "cuoi thang sau",
        "cuoi thang toi",
        "dau thang sau",
        "cuoi nam",
        "today",
        "tonight",
        "tomorrow",
        "day after tomorrow",
        "this week",
        "next week",
        "this month",
        "next month",
        "weekend",
        "next weekend",
        "end of this month",
        "end of next month",
        "end of this year",
    )
    if any(phrase in normalized for phrase in phrases):
        return True
    if re.search(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", normalized):
        return True
    if re.search(r"\bngay\s+.+\s+thang\s+.+", normalized):
        return True
    if re.search(
        rf"\bthang\s+{_NUMBER_EXPRESSION}(?:\s+nam\s+{_NUMBER_EXPRESSION})?\b",
        normalized,
    ):
        return True
    if re.search(
        r"\b(?:january|february|march|april|may|june|july|august|"
        r"september|october|november|december)(?:\s+\d{4})?\b",
        normalized,
    ):
        return True
    if re.search(
        rf"\b(?:sau\s+)?{_NUMBER_EXPRESSION}\s+"
        r"(?:ngay|hom|tuan|thang|nam|days?|weeks?|months?|years?)"
        r"(?:\s+(?:nua|toi|sap toi|sau|tiep theo|ke tu hom nay|"
        r"tinh tu hom nay|from now|from today|ahead))?\b",
        normalized,
    ):
        return True
    # Keep a dedicated digit path for long natural horizons such as
    # "sự kiện 75 ngày nữa" or "sự kiện 115 ngày nữa". This intentionally
    # accepts up to four digits and does not depend on the more complex
    # number-word expression above.
    if re.search(
        r"\b\d{1,4}\s*(?:ngay|hom|days?)\s*"
        r"(?:nua|sau|toi|sap toi|from now|from today|ahead)?\b",
        normalized,
    ):
        return True
    # Broader hints let the configured AI parser handle less deterministic
    # expressions such as "nửa tháng nữa" or "đến cuối quý sau" without
    # treating a truly generic "kiểm tra lịch" request as time-bounded.
    if re.search(
        r"\b(?:nua|vai|mot vai|half|couple of)\s+"
        r"(?:ngay|hom|tuan|thang|nam|days?|weeks?|months?|years?)\b",
        normalized,
    ):
        return True
    if re.search(
        r"\b(?:den|until|through|within|trong vong)\s+"
        r"(?:cuoi|dau|giua|het|end|start|middle|next|this|quy|quarter)\b",
        normalized,
    ):
        return True
    if re.search(r"\b(?:quy|quarter)\s+(?:nay|sau|toi|this|next)\b", normalized):
        return True
    return bool(
        re.search(
            r"\b(?:thu\s+(?:hai|ba|tu|nam|sau|bay)|chu nhat|"
            r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            normalized,
        )
    )


def calendar_text_has_clock_time(text: str) -> bool:
    """Return whether text contains an explicit clock time."""
    normalized = _fold_calendar_text(text)
    patterns = (
        r"\b(?:[01]?\d|2[0-3])\s*(?:h|gio|:)\s*[0-5]?\d\b",
        r"\b(?:[01]?\d|2[0-3])\s*(?:h|gio)\b",
        r"\b(?:at|luc|vao)\s+(?:[01]?\d|2[0-3])(?:\s*(?:am|pm))?\b",
        r"\b(?:sang|trua|chieu|toi|dem)\b",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def calendar_window_from_text(text: str, now: datetime) -> CalendarWindow | None:
    """Return a local range from now through the requested natural horizon."""
    raw_calendar_text = unicodedata.normalize(
        "NFC", str(text or "").casefold()
    )
    normalized = _fold_calendar_text(text)
    explicit_june_phrase = bool(
        re.search(r"\btháng\s+sáu\b", raw_calendar_text)
    )
    relative_next_month_phrase = bool(
        re.search(r"\b(?:tháng|thang)\s+sau\b", raw_calendar_text)
    )
    # Canonicalize "counting from today" so Vietnamese "từ" is not
    # misread as the number four followed by "hôm" (days).
    normalized = re.sub(
        r"\b(?:ke|tinh) tu hom nay\b", "nua", normalized
    )
    normalized = re.sub(r"\bfrom today\b", "from now", normalized)
    local_now = dt_util.as_local(now)
    tzinfo = local_now.tzinfo

    def end_of_day(target_date: date) -> datetime:
        return datetime.combine(
            target_date + timedelta(days=1), time.min, tzinfo=tzinfo
        )

    # Parse long digit-based day horizons before the generic grammar. This
    # makes requests such as "75 ngày nữa" and "115 ngày nữa" deterministic
    # even when an AI parser is unavailable or returns an unusable answer.
    long_day_horizon = re.search(
        r"\b(?P<n>\d{1,4})\s*(?:ngay|hom|days?)\s*"
        r"(?P<suffix>nua|sau|toi|sap toi|from now|from today|ahead)\b",
        normalized,
    )
    if long_day_horizon:
        amount = int(long_day_horizon.group("n"))
        if 0 < amount <= 3650:
            target = local_now + timedelta(days=amount)
            return CalendarWindow(
                local_now,
                end_of_day(target.date()),
                f"trong {amount} ngày tới",
            )

    duration_hint = bool(
        re.search(
            rf"\b{_NUMBER_EXPRESSION}\s*"
            r"(?:ngay|hom|tuan|thang|nam|days?|weeks?|months?|years?)\b",
            normalized,
        )
    )

    if not duration_hint and (
        "day after tomorrow" in normalized
        or "ngay kia" in normalized
        or "ngay mot" in normalized
    ):
        target = local_now.date() + timedelta(days=2)
        return CalendarWindow(local_now, end_of_day(target), "đến hết ngày kia")
    if not duration_hint and (
        "tomorrow" in normalized or "ngay mai" in normalized
    ):
        target = local_now.date() + timedelta(days=1)
        return CalendarWindow(local_now, end_of_day(target), "đến hết ngày mai")
    if not duration_hint and any(
        phrase in normalized
        for phrase in ("today", "tonight", "hom nay", "toi nay")
    ):
        return CalendarWindow(
            local_now, end_of_day(local_now.date()), "đến hết hôm nay"
        )

    relative_month_day = re.search(
        rf"\bngay\s+(?P<d>{_NUMBER_EXPRESSION_GREEDY})\s+thang\s+"
        r"(?P<which>nay|sau|toi)\b",
        normalized,
    )
    if relative_month_day:
        which = relative_month_day.group("which")
        is_relative_phrase = (
            which in {"nay", "toi"}
            or relative_next_month_phrase
            or not explicit_june_phrase
        )
        if is_relative_phrase:
            day = _parse_small_number(relative_month_day.group("d"))
            if day is None:
                return None
            month_value = local_now if which == "nay" else _add_months(local_now, 1)
            max_day = month_calendar.monthrange(
                month_value.year, month_value.month
            )[1]
            if not 1 <= day <= max_day:
                return None
            target = date(month_value.year, month_value.month, day)
            if target < local_now.date():
                return None
            return CalendarWindow(
                local_now,
                end_of_day(target),
                f"đến hết ngày {target.strftime('%d/%m/%Y')}",
            )

    # Parse a concrete date before duration expressions so "ngày 5 tháng 8"
    # is never mistaken for "5 tháng nữa".
    absolute = _absolute_date_from_text(normalized, local_now)
    if absolute is not None:
        if absolute < local_now.date():
            return None
        return CalendarWindow(
            local_now,
            end_of_day(absolute),
            f"đến hết ngày {absolute.strftime('%d/%m/%Y')}",
        )

    # Relative month phrases must be handled before named-month parsing.
    # After accent folding, "tháng sau" (next month) and "tháng sáu" (June)
    # both contain "thang sau".
    if re.search(
        r"\b(?:end of next month|cuoi thang (?:sau|toi))\b",
        normalized,
    ) and (not explicit_june_phrase or relative_next_month_phrase):
        next_month = _add_months(local_now, 1)
        last_day = month_calendar.monthrange(
            next_month.year, next_month.month
        )[1]
        target = date(next_month.year, next_month.month, last_day)
        return CalendarWindow(
            local_now, end_of_day(target), "đến hết tháng sau"
        )
    if re.search(
        r"\b(?:dau thang (?:sau|toi))\b", normalized
    ) and (not explicit_june_phrase or relative_next_month_phrase):
        next_month = _add_months(local_now, 1)
        target = date(next_month.year, next_month.month, 1)
        return CalendarWindow(
            local_now, end_of_day(target), "đến hết ngày đầu tháng sau"
        )
    bare_end_this_month = bool(
        re.search(
            rf"\bcuoi thang(?: nay)?\b(?!\s+{_NUMBER_TOKEN})",
            normalized,
        )
    )
    if (
        re.search(
            r"\b(?:this month|thang nay|end of this month)\b",
            normalized,
        )
        or bare_end_this_month
    ):
        last_day = month_calendar.monthrange(local_now.year, local_now.month)[1]
        target = date(local_now.year, local_now.month, last_day)
        return CalendarWindow(local_now, end_of_day(target), "đến hết tháng này")
    next_month_match = re.search(
        r"\b(?:next month|thang toi|thang sau)\b", normalized
    )
    numbered_next_month = bool(
        re.search(
            rf"\b{_NUMBER_EXPRESSION}\s+(?:thang|months?)\s+"
            r"(?:toi|sau|nua|from now|ahead)\b",
            normalized,
        )
    )
    if (
        next_month_match
        and not numbered_next_month
        and (not explicit_june_phrase or relative_next_month_phrase)
    ):
        target = _add_months(local_now, 1)
        return CalendarWindow(
            local_now, end_of_day(target.date()), "trong 1 tháng tới"
        )

    month_end = _absolute_month_end_from_text(normalized, local_now)
    if month_end is not None:
        target = month_end
        label = f"đến hết tháng {month_end.strftime('%m/%Y')}"
        if re.search(r"\bdau thang\b", normalized):
            target = date(month_end.year, month_end.month, 1)
            label = f"đến hết ngày đầu tháng {month_end.strftime('%m/%Y')}"
        elif re.search(r"\bgiua thang\b", normalized):
            target = date(month_end.year, month_end.month, 15)
            label = f"đến hết giữa tháng {month_end.strftime('%m/%Y')}"
        if target < local_now.date():
            return None
        return CalendarWindow(local_now, end_of_day(target), label)

    # Resolve named weekdays before duration parsing. Vietnamese weekday
    # names contain number words ("thứ hai", "thứ sáu") that must never be
    # interpreted as "2 weeks" or "6 weeks".
    weekday = _weekday_from_text(normalized)
    if weekday is not None:
        if re.search(r"\b(?:next week|tuan toi|tuan sau)\b", normalized):
            next_monday = local_now.date() + timedelta(
                days=7 - local_now.weekday()
            )
            target = next_monday + timedelta(days=weekday)
        elif re.search(r"\b(?:this week|tuan nay)\b", normalized):
            this_monday = local_now.date() - timedelta(
                days=local_now.weekday()
            )
            target = this_monday + timedelta(days=weekday)
            if target < local_now.date():
                return None
        else:
            offset = (weekday - local_now.weekday()) % 7
            if offset == 0:
                offset = 7
            target = local_now.date() + timedelta(days=offset)
        return CalendarWindow(
            local_now,
            end_of_day(target),
            f"đến hết {target.strftime('%d/%m/%Y')}",
        )

    composite_totals = _relative_component_totals(normalized)
    if composite_totals is not None:
        target = local_now
        if composite_totals["years"]:
            target = _add_years(target, composite_totals["years"])
        if composite_totals["months"]:
            target = _add_months(target, composite_totals["months"])
        target += timedelta(
            weeks=composite_totals["weeks"],
            days=composite_totals["days"],
        )
        label = _relative_totals_label(composite_totals)
        return CalendarWindow(
            local_now,
            end_of_day(target.date()),
            f"trong {label} tới",
        )

    relative_suffix = (
        r"(?:\s+(?:nua|toi|sap toi|sau|tiep theo|ke tu hom nay|"
        r"tinh tu hom nay|from now|from today|ahead))?\b"
    )
    relative_patterns = (
        (
            rf"\b(?:sau\s+)?(?P<n>{_NUMBER_EXPRESSION})\s*"
            rf"(?:ngay|hom|days?){relative_suffix}",
            "days",
        ),
        (
            rf"\b(?:sau\s+)?(?P<n>{_NUMBER_EXPRESSION})\s*"
            rf"(?:tuan|weeks?){relative_suffix}",
            "weeks",
        ),
        (
            rf"\b(?:sau\s+)?(?P<n>{_NUMBER_EXPRESSION})\s*"
            rf"(?:thang|months?){relative_suffix}",
            "months",
        ),
        (
            rf"\b(?:sau\s+)?(?P<n>{_NUMBER_EXPRESSION})\s*"
            rf"(?:nam|years?){relative_suffix}",
            "years",
        ),
    )
    for pattern, unit in relative_patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        amount = _parse_small_number(match.group("n"))
        if amount is None or amount <= 0:
            continue
        amount = min(amount, 3650)
        if unit == "days":
            target = local_now + timedelta(days=amount)
            label = f"trong {amount} ngày tới"
        elif unit == "weeks":
            target = local_now + timedelta(weeks=amount)
            label = f"trong {amount} tuần tới"
        elif unit == "months":
            target = _add_months(local_now, amount)
            label = f"trong {amount} tháng tới"
        else:
            target = _add_years(local_now, amount)
            label = f"trong {amount} năm tới"
        return CalendarWindow(local_now, end_of_day(target.date()), label)

    if re.search(
        r"\b(?:next weekend|cuoi tuan (?:sau|toi))\b", normalized
    ):
        days_until_sunday = (6 - local_now.weekday()) % 7
        target = local_now.date() + timedelta(days=days_until_sunday + 7)
        return CalendarWindow(
            local_now, end_of_day(target), "đến hết cuối tuần sau"
        )
    if re.search(r"\b(?:this week|tuan nay)\b", normalized):
        days_until_sunday = 6 - local_now.weekday()
        target = local_now.date() + timedelta(days=days_until_sunday)
        return CalendarWindow(local_now, end_of_day(target), "đến hết tuần này")
    if re.search(r"\b(?:next week|tuan toi|tuan sau)\b", normalized):
        target = local_now.date() + timedelta(days=7)
        return CalendarWindow(
            local_now, end_of_day(target), "trong 1 tuần tới"
        )
    if re.search(r"\b(?:weekend|cuoi tuan)\b", normalized):
        days_until_sunday = (6 - local_now.weekday()) % 7
        target = local_now.date() + timedelta(days=days_until_sunday)
        return CalendarWindow(local_now, end_of_day(target), "đến hết cuối tuần")

    if re.search(r"\b(?:cuoi nam|end of this year)\b", normalized):
        target = date(local_now.year, 12, 31)
        return CalendarWindow(local_now, end_of_day(target), "đến hết năm nay")

    return None


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
    supported_features: int = 0,
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
        event = _normalize_calendar_event(
            item,
            entity_id,
            calendar_name,
            supported_features=supported_features,
        )
        if event is not None:
            result.append(event)
    return result


def event_from_calendar_state(
    attributes: dict[str, Any], entity_id: str, calendar_name: str
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
        entity_id,
        calendar_name,
    )


def calendar_events_for_display(
    events: list[CalendarDisplayEvent],
    window: CalendarWindow,
    limit: int = 50,
) -> tuple[list[CalendarDisplayEvent], int]:
    """Return the exact ordered events shown to the user and skip count."""
    unique: dict[
        tuple[str, datetime, str, str, str], CalendarDisplayEvent
    ] = {}
    skipped_lunar = 0
    for event in events:
        if event.start >= window.end:
            continue
        if event.end is not None and event.end <= window.start:
            continue
        if event.end is None and event.start < window.start:
            continue
        if _should_skip_lunar_event(event):
            skipped_lunar += 1
            continue
        unique[
            (
                event.calendar_entity_id,
                event.start,
                event.summary,
                event.uid,
                event.recurrence_id,
            )
        ] = event

    ordered = sorted(
        unique.values(),
        key=lambda event: (
            event.calendar_name.casefold(),
            event.start,
            event.summary.casefold(),
        ),
    )
    return ordered[:limit], skipped_lunar


def format_calendar_events(
    events: list[CalendarDisplayEvent],
    window: CalendarWindow,
    now: datetime,
    limit: int = 50,
) -> str:
    """Format events by calendar with dates, contents, and days remaining."""
    ordered, skipped_lunar = calendar_events_for_display(
        events, window, limit=limit
    )
    if not ordered:
        message = f"📭 Không có sự kiện phù hợp {window.label}."
        if skipped_lunar:
            message += (
                "\nCác ngày âm lịch thông thường đã được tự động bỏ qua; "
                "chỉ giữ mùng 1, ngày rằm hoặc ngày có nội dung sự kiện."
            )
        return message

    local_now = dt_util.as_local(now)
    grouped: dict[str, list[CalendarDisplayEvent]] = {}
    for event in ordered:
        grouped.setdefault(event.calendar_name or "Lịch không tên", []).append(event)

    lines = [f"📅 **Kết quả lịch {window.label}**"]
    item_index = 0
    for calendar_name, calendar_events in grouped.items():
        lines.append(f"\n🗓️ **{calendar_name}**")
        for event in calendar_events:
            item_index += 1
            event_start = dt_util.as_local(event.start)
            days_remaining = max(0, (event_start.date() - local_now.date()).days)
            content = _display_event_summary(event)
            lines.append(f"{item_index}. 📌 **Nội dung:** {content}")
            lines.append(
                f"   🕒 **Thời gian:** {_format_event_time(event, local_now)}"
            )
            lines.append(
                f"   ⏳ **Còn:** {_days_remaining_text(days_remaining)}"
            )
            if event.location:
                lines.append(f"   📍 **Địa điểm:** {event.location}")
            if event.description and normalize_text(event.description) != normalize_text(content):
                lines.append(f"   📝 **Chi tiết:** {event.description}")

    return "\n".join(lines)


def calendar_create_request_from_ai_payload(
    payload: dict[str, Any], now: datetime
) -> CalendarCreateRequest | None:
    """Validate a strict AI-produced calendar event payload."""
    summary = str(payload.get("summary") or "").strip()
    if not summary:
        return None
    raw_all_day = payload.get("all_day", False)
    all_day = (
        raw_all_day
        if isinstance(raw_all_day, bool)
        else str(raw_all_day).strip().casefold() in {"true", "1", "yes"}
    )
    local_now = dt_util.as_local(now)
    if all_day:
        start_date = dt_util.parse_date(str(payload.get("start_date") or ""))
        end_date = dt_util.parse_date(str(payload.get("end_date") or ""))
        if start_date is None:
            return None
        if end_date is None or end_date <= start_date:
            end_date = start_date + timedelta(days=1)
        start = datetime.combine(start_date, time.min, tzinfo=local_now.tzinfo)
        end = datetime.combine(end_date, time.min, tzinfo=local_now.tzinfo)
    else:
        start = dt_util.parse_datetime(str(payload.get("start_date_time") or ""))
        end = dt_util.parse_datetime(str(payload.get("end_date_time") or ""))
        if start is None:
            return None
        if start.tzinfo is None:
            start = start.replace(tzinfo=local_now.tzinfo)
        start = dt_util.as_local(start)
        if end is None:
            end = start + timedelta(hours=1)
        elif end.tzinfo is None:
            end = end.replace(tzinfo=local_now.tzinfo)
        end = dt_util.as_local(end)
        if end <= start:
            end = start + timedelta(hours=1)
    if all_day:
        # An all-day event starts at midnight, which is naturally earlier than
        # "now" when the user creates it later the same day. It is valid as
        # long as its exclusive end has not passed.
        if end <= local_now:
            return None
    elif start < local_now - timedelta(minutes=1):
        return None
    return CalendarCreateRequest(
        summary=summary,
        start=start,
        end=end,
        all_day=all_day,
        description=str(payload.get("description") or "").strip(),
        location=str(payload.get("location") or "").strip(),
    )


def format_calendar_create_request(request: CalendarCreateRequest) -> str:
    """Return a compact confirmation line for a parsed calendar event."""
    start = dt_util.as_local(request.start)
    end = dt_util.as_local(request.end)
    if request.all_day:
        when = start.strftime("cả ngày %d/%m/%Y")
        if end.date() > start.date() + timedelta(days=1):
            inclusive_end = end.date() - timedelta(days=1)
            when = f"từ {start.strftime('%d/%m/%Y')} đến {inclusive_end.strftime('%d/%m/%Y')}"
    else:
        when = (
            f"{start.strftime('%H:%M ngày %d/%m/%Y')} đến "
            f"{end.strftime('%H:%M ngày %d/%m/%Y')}"
        )
    return f"**{request.summary}** — {when}"


def _parse_small_number(value: str) -> int | None:
    value = normalize_text(value)
    if value.isdigit():
        return int(value)
    tokens = value.split()
    if not tokens:
        return None
    if all(token in _EN_NUMBER_WORDS or token == "hundred" for token in tokens):
        current = 0
        for token in tokens:
            if token == "hundred":
                current = max(1, current) * 100
            else:
                current += _EN_NUMBER_WORDS[token]
        return current
    allowed_vi = set(_VI_NUMBER_WORDS) | {"muoi", "tram", "linh", "le"}
    if any(token not in allowed_vi for token in tokens):
        return None
    if len(tokens) > 1 and all(token in _VI_NUMBER_WORDS for token in tokens):
        return int("".join(str(_VI_NUMBER_WORDS[token]) for token in tokens))
    total = 0
    if "tram" in tokens:
        index = tokens.index("tram")
        hundred = _VI_NUMBER_WORDS.get(tokens[index - 1], 1) if index else 1
        total += hundred * 100
        tokens = tokens[index + 1 :]
    tokens = [token for token in tokens if token not in {"linh", "le"}]
    if not tokens:
        return total
    if tokens[0] == "muoi":
        total += 10
        tokens = tokens[1:]
    elif len(tokens) >= 2 and tokens[1] == "muoi":
        total += _VI_NUMBER_WORDS.get(tokens[0], 0) * 10
        tokens = tokens[2:]
    if tokens:
        total += _VI_NUMBER_WORDS.get(tokens[-1], 0)
    return total


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.year * 12 + (value.month - 1) + months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(value.day, month_calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _add_years(value: datetime, years: int) -> datetime:
    year = value.year + years
    day = min(value.day, month_calendar.monthrange(year, value.month)[1])
    return value.replace(year=year, day=day)


def _relative_component_totals(normalized: str) -> dict[str, int] | None:
    """Return totals for a clearly relative multi-unit date expression."""
    has_relative_marker = bool(
        re.search(r"\b(?:sau|trong|after|in)\b", normalized)
        or re.search(
            r"\b(?:nua|sap toi|tiep theo|ke tu hom nay|tinh tu hom nay|"
            r"from now|from today|ahead)\b",
            normalized,
        )
    )
    if not has_relative_marker:
        return None

    # Remove the relative marker before parsing amounts. Without this,
    # accent-folded Vietnamese "sau" (after) can be mistaken for "sáu" (6),
    # turning "sau hai tuần" into 62 weeks.
    core = re.sub(
        r"\b(?:trong|after|in)\s+",
        " ",
        normalized,
        count=1,
    )
    core = re.sub(
        rf"\bsau\s+(?={_NUMBER_TOKEN}\b)",
        " ",
        core,
        count=1,
    )
    core = re.sub(
        r"\s+(?:nua|sap toi|tiep theo|ke tu hom nay|tinh tu hom nay|"
        r"from now|from today|ahead|sau)\s*$",
        " ",
        core,
        count=1,
    )
    component_pattern = re.compile(
        rf"(?P<n>{_NUMBER_EXPRESSION_GREEDY})\s*"
        r"(?P<u>ngay|hom|tuan|thang|nam|days?|weeks?|months?|years?)\b"
    )
    matches = list(component_pattern.finditer(core))
    if len(matches) < 2:
        return None

    totals = {"days": 0, "weeks": 0, "months": 0, "years": 0}
    for match in matches:
        amount = _parse_small_number(match.group("n"))
        if amount is None or amount <= 0:
            return None
        unit = match.group("u")
        if unit in {"ngay", "hom", "day", "days"}:
            totals["days"] += amount
        elif unit in {"tuan", "week", "weeks"}:
            totals["weeks"] += amount
        elif unit in {"thang", "month", "months"}:
            totals["months"] += amount
        else:
            totals["years"] += amount

    if (
        totals["days"] > 3650
        or totals["weeks"] > 520
        or totals["months"] > 120
        or totals["years"] > 10
    ):
        return None
    return totals


def _relative_totals_label(totals: dict[str, int]) -> str:
    parts: list[str] = []
    labels = (
        ("years", "năm"),
        ("months", "tháng"),
        ("weeks", "tuần"),
        ("days", "ngày"),
    )
    for key, label in labels:
        amount = totals[key]
        if amount:
            parts.append(f"{amount} {label}")
    return " ".join(parts)


def _absolute_date_from_text(normalized: str, now: datetime) -> date | None:
    numeric = re.search(
        r"\b(?P<d>\d{1,2})[/-](?P<m>\d{1,2})(?:[/-](?P<y>\d{2,4}))?\b",
        normalized,
    )
    if numeric:
        year = int(numeric.group("y") or now.year)
        if year < 100:
            year += 2000
        try:
            candidate = date(year, int(numeric.group("m")), int(numeric.group("d")))
        except ValueError:
            return None
        if numeric.group("y") is None and candidate < now.date():
            try:
                candidate = candidate.replace(year=year + 1)
            except ValueError:
                return None
        return candidate

    # Parse the explicit-year form first. The year group must be greedy:
    # a non-greedy number expression would read "hai không hai sáu" as only
    # "hai" and silently turn 2026 into 2002.
    words = re.search(
        rf"\bngay\s+(?P<d>{_NUMBER_EXPRESSION_GREEDY})\s+thang\s+"
        rf"(?P<m>{_NUMBER_EXPRESSION_GREEDY})\s+nam\s+"
        rf"(?P<y>{_NUMBER_EXPRESSION_GREEDY})",
        normalized,
    )
    has_explicit_year = words is not None
    if words is None:
        words = re.search(
            rf"\bngay\s+(?P<d>{_NUMBER_EXPRESSION_GREEDY})\s+thang\s+"
            rf"(?P<m>{_NUMBER_EXPRESSION_GREEDY})",
            normalized,
        )
    if words:
        day = _parse_small_number(words.group("d"))
        month = _parse_small_number(words.group("m"))
        year = _parse_small_number(words.group("y")) if has_explicit_year else now.year
        if day is None or month is None or year is None:
            return None
        if year < 100:
            year += 2000
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if not has_explicit_year and candidate < now.date():
            try:
                candidate = candidate.replace(year=year + 1)
            except ValueError:
                return None
        return candidate
    return None


def _absolute_month_end_from_text(
    normalized: str, now: datetime
) -> date | None:
    """Return the last day of a named month horizon."""
    month: int | None = None
    year: int | None = None
    explicit_year = False

    with_year = re.search(
        rf"\bthang\s+(?P<m>{_NUMBER_EXPRESSION_GREEDY})\s+nam\s+"
        rf"(?P<y>{_NUMBER_EXPRESSION_GREEDY})",
        normalized,
    )
    if with_year:
        month = _parse_small_number(with_year.group("m"))
        year = _parse_small_number(with_year.group("y"))
        explicit_year = True
    else:
        without_year = re.search(
            rf"\bthang\s+(?P<m>{_NUMBER_EXPRESSION_GREEDY})",
            normalized,
        )
        if without_year:
            month = _parse_small_number(without_year.group("m"))
            year = now.year
        else:
            english = re.search(
                r"\b(?P<m>january|february|march|april|may|june|july|"
                r"august|september|october|november|december)"
                r"(?:\s+(?P<y>\d{4}))?\b",
                normalized,
            )
            if english:
                month = _EN_MONTH_NUMBERS[english.group("m")]
                year = int(english.group("y") or now.year)
                explicit_year = english.group("y") is not None

    if month is None or year is None or not 1 <= month <= 12:
        return None
    if year < 100:
        year += 2000
    last_day = month_calendar.monthrange(year, month)[1]
    target = date(year, month, last_day)
    if not explicit_year and target < now.date():
        year += 1
        target = date(year, month, month_calendar.monthrange(year, month)[1])
    return target


def _weekday_from_text(normalized: str) -> int | None:
    mapping = {
        "thu hai": 0,
        "monday": 0,
        "thu ba": 1,
        "tuesday": 1,
        "thu tu": 2,
        "wednesday": 2,
        "thu nam": 3,
        "thursday": 3,
        "thu sau": 4,
        "friday": 4,
        "thu bay": 5,
        "saturday": 5,
        "chu nhat": 6,
        "sunday": 6,
    }
    for phrase, weekday in mapping.items():
        if phrase in normalized:
            return weekday
    return None


def _days_remaining_text(days: int) -> str:
    if days == 0:
        return "0 ngày (hôm nay)"
    if days == 1:
        return "1 ngày (ngày mai)"
    return f"{days} ngày"


def _is_lunar_calendar(event: CalendarDisplayEvent) -> bool:
    text = normalize_text(f"{event.calendar_name} {event.calendar_entity_id}")
    return any(term in text for term in ("lich am", "am lich", "lunar"))


def _lunar_day_from_summary(summary: str) -> int | None:
    normalized = normalize_text(summary)
    if "ram" in normalized:
        return 15
    if re.search(r"\bmung\s+1\b", normalized):
        return 1
    match = re.search(r"\b(\d{1,2})\s*[/.-]\s*\d{1,2}\b", summary)
    if match:
        return int(match.group(1))
    match = re.search(r"\bngay\s+(\d{1,2})\b", normalized)
    return int(match.group(1)) if match else None


def _lunar_summary_has_content(summary: str) -> bool:
    normalized = normalize_text(summary)
    normalized = re.sub(r"\b\d{1,2}\s*\d{1,2}(?:\s*\d{2,4})?\b", " ", normalized)
    normalized = re.sub(r"\b(?:lich am|am lich|ngay am|am|lunar|ngay|thang)\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return len(normalized) >= 3


def calendar_event_should_be_skipped(event: CalendarDisplayEvent) -> bool:
    """Return whether a plain, ordinary lunar-calendar date should be hidden."""
    if not _is_lunar_calendar(event):
        return False
    lunar_day = _lunar_day_from_summary(event.summary)
    if lunar_day in {1, 15}:
        return False
    if event.description.strip() or _lunar_summary_has_content(event.summary):
        return False
    return True


def calendar_event_display_summary(event: CalendarDisplayEvent) -> str:
    """Return the same user-facing lunar summary used by calendar lookup."""
    if not _is_lunar_calendar(event):
        return event.summary
    lunar_day = _lunar_day_from_summary(event.summary)
    if lunar_day == 1 and not _lunar_summary_has_content(event.summary):
        return f"Mùng 1 âm lịch ({event.summary})"
    if lunar_day == 15 and not _lunar_summary_has_content(event.summary):
        return f"Ngày rằm, 15 âm lịch ({event.summary})"
    return event.summary


# Backward-compatible private aliases used inside older call sites.
_should_skip_lunar_event = calendar_event_should_be_skipped
_display_event_summary = calendar_event_display_summary


def _is_camera_image_request(normalized: str) -> bool:
    """Return whether a Zalo message requests a still image from a camera."""
    if not normalized:
        return False

    direct_image_prefixes = (
        "take a photo",
        "take a picture",
        "take an image",
        "capture a photo",
        "capture a picture",
        "capture an image",
        "get a photo",
        "get a picture",
        "get an image",
        "send a photo",
        "send a picture",
        "send an image",
        "camera snapshot",
        "chup anh",
        "chup hinh",
        "lay anh",
        "lay hinh",
        "gui anh",
        "gui hinh",
    )
    if normalized.startswith(direct_image_prefixes):
        return True

    mentions_camera = (
        normalized == "camera"
        or "camera" in normalized
        or "may quay" in normalized
        or normalized.startswith("cam ")
        or "cctv" in normalized
    )
    if not mentions_camera:
        return False

    image_phrases = (
        "take photo",
        "take a photo",
        "take picture",
        "take a picture",
        "capture photo",
        "capture image",
        "capture picture",
        "camera photo",
        "camera picture",
        "camera image",
        "camera snapshot",
        "view camera",
        "check camera",
        "show camera",
        "send camera image",
        "chup anh",
        "chup hinh",
        "lay anh",
        "lay hinh",
        "xem anh",
        "xem hinh",
        "gui anh",
        "gui hinh",
        "anh camera",
        "hinh camera",
        "kiem tra camera",
        "xem camera",
        "mo camera",
    )
    return normalized == "camera" or any(
        phrase in normalized for phrase in image_phrases
    )


def _is_camera_analysis_request(normalized: str) -> bool:
    """Return whether text requests AI analysis of one or more cameras."""
    if not normalized:
        return False
    for polite_prefix in ("hay ", "please "):
        if normalized.startswith(polite_prefix):
            normalized = normalized[len(polite_prefix) :].strip()
            break
    phrases = {
        "analyze camera",
        "analyze cameras",
        "analyse camera",
        "analyse cameras",
        "camera analysis",
        "check camera",
        "check cameras",
        "inspect camera",
        "inspect cameras",
        "phan tich cam",
        "phan tich camera",
        "phan tich cac cam",
        "phan tich cac camera",
        "kiem tra cam",
        "kiem tra camera",
        "kiem tra cac cam",
        "kiem tra cac camera",
        "xem va phan tich cam",
        "xem va phan tich camera",
    }
    prefixes = tuple(f"{phrase} " for phrase in phrases)
    return normalized in phrases or normalized.startswith(prefixes)


def _is_calendar_query(normalized: str) -> bool:
    """Return whether normalized text asks about or creates calendar events."""
    reminder_terms = (
        "reminder",
        "reminders",
        "timer",
        "lich nhac",
        "nhac hen",
        "nhac nho",
        "hen gio",
    )
    if any(term in normalized for term in reminder_terms):
        return False
    if "event" in normalized or "events" in normalized or "su kien" in normalized:
        return True
    calendar_phrases = {
        "calendar",
        "show calendar",
        "check calendar",
        "my calendar",
        "calendar today",
        "calendar tomorrow",
        "upcoming calendar",
        "calendar this week",
        "calendar next week",
        "what is on my calendar",
        "whats on my calendar",
        "what s on my calendar",
        "what is on my calendar today",
        "whats on my calendar today",
        "what s on my calendar today",
        "what is on my calendar tomorrow",
        "whats on my calendar tomorrow",
        "what s on my calendar tomorrow",
        "do i have any events",
        "lich",
        "xem lich",
        "kiem tra lich",
        "tra lich",
        "tra cuu lich",
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
        or normalized.startswith("show calendar ")
        or normalized.startswith("check calendar ")
        or normalized.startswith("calendar ")
        or normalized.startswith("what is on my calendar ")
        or normalized.startswith("whats on my calendar ")
        or normalized.startswith("what s on my calendar ")
        or normalized.startswith("xem lich ")
        or normalized.startswith("kiem tra lich ")
        or normalized.startswith("tra lich ")
        or normalized.startswith("tra cuu lich ")
        or normalized.startswith("lich ")
        or normalized.startswith("tao lich ")
        or normalized.startswith("them lich ")
        or normalized.startswith("dat lich ")
        or normalized.startswith("len lich ")
        or normalized.startswith("tao cuoc hop ")
        or normalized.startswith("them cuoc hop ")
        or normalized.startswith("tao cuoc hen ")
        or normalized.startswith("dat cuoc hen ")
        or normalized.startswith("schedule meeting ")
        or normalized.startswith("book appointment ")
    )


def _parse_event_datetime(value: Any) -> tuple[datetime | None, bool]:
    """Parse a calendar date/datetime value and flag all-day values."""
    if isinstance(value, datetime):
        parsed = value
        all_day = False
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min, tzinfo=dt_util.now().tzinfo)
        all_day = True
    elif isinstance(value, dict):
        raw = value.get("dateTime") or value.get("date")
        return _parse_event_datetime(raw)
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
    item: dict[str, Any],
    entity_id: str,
    calendar_name: str,
    *,
    supported_features: int = 0,
) -> CalendarDisplayEvent | None:
    """Normalize one raw calendar event."""
    start, inferred_start_all_day = _parse_event_datetime(item.get("start"))
    if start is None:
        return None
    end, inferred_end_all_day = _parse_event_datetime(item.get("end"))
    summary = str(
        item.get("summary") or item.get("message") or "Sự kiện không có tên"
    ).strip()
    explicit_all_day = bool(item.get("all_day"))
    midnight_span = bool(
        end is not None
        and start.time() == time.min
        and end.time() == time.min
        and end > start
        and (end - start).total_seconds() % 86400 == 0
    )
    lunar_name = normalize_text(f"{calendar_name} {entity_id}")
    lunar_midnight = bool(
        start.time() == time.min
        and any(term in lunar_name for term in ("lich am", "am lich", "lunar"))
    )
    all_day = bool(
        explicit_all_day
        or inferred_start_all_day
        or inferred_end_all_day
        or midnight_span
        or lunar_midnight
    )
    return CalendarDisplayEvent(
        start=start,
        end=end,
        summary=summary,
        calendar_name=calendar_name,
        calendar_entity_id=entity_id,
        location=str(item.get("location") or "").strip(),
        description=str(item.get("description") or "").strip(),
        all_day=all_day,
        uid=str(item.get("uid") or "").strip(),
        recurrence_id=str(item.get("recurrence_id") or "").strip(),
        rrule=str(item.get("rrule") or "").strip(),
        can_update=bool(supported_features & int(CalendarEntityFeature.UPDATE_EVENT)),
        can_delete=bool(supported_features & int(CalendarEntityFeature.DELETE_EVENT)),
    )


def _format_event_time(
    event: CalendarDisplayEvent, local_now: datetime
) -> str:
    """Return a natural local timestamp for one event."""
    event_start = dt_util.as_local(event.start)
    day = event_start.date()
    if day == local_now.date():
        day_label = f"Hôm nay, {event_start.strftime('%d/%m/%Y')}"
    elif day == local_now.date() + timedelta(days=1):
        day_label = f"Ngày mai, {event_start.strftime('%d/%m/%Y')}"
    else:
        day_label = event_start.strftime("%d/%m/%Y")
    if event.all_day:
        return f"{day_label}, cả ngày"
    if event.end is not None:
        event_end = dt_util.as_local(event.end)
        if event_end.date() == event_start.date():
            return (
                f"{day_label}, {event_start.strftime('%H:%M')}–"
                f"{event_end.strftime('%H:%M')}"
            )
    return f"{day_label}, lúc {event_start.strftime('%H:%M')}"
