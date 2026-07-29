"""Natural Vietnamese reminder request parser."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta
import re
import unicodedata

from homeassistant.util import dt as dt_util

from .models import Recurrence


class ReminderParseError(ValueError):
    """Raised when a reminder request cannot be parsed."""


@dataclass(slots=True)
class ParsedReminder:
    """Parsed reminder request."""

    message: str
    first_run: datetime
    recurrence: Recurrence
    confirmation: str


DIGITS = {
    "không": 0,
    "một": 1,
    "mốt": 1,
    "hai": 2,
    "ba": 3,
    "bốn": 4,
    "tư": 4,
    "năm": 5,
    "lăm": 5,
    "sáu": 6,
    "bảy": 7,
    "tám": 8,
    "chín": 9,
}

# Home Assistant speech-to-text commonly converts values such as ``18h30``
# to ``mười tám giờ ba mươi``. Keep the vocabulary deliberately limited to
# number words so reminder content is not accidentally consumed as a date/time.
NUMBER_WORD_TOKEN_PATTERN = (
    r"(?:không|một|mốt|hai|ba|bốn|tư|năm|lăm|sáu|bảy|tám|chín|"
    r"mười|mươi|trăm|nghìn|ngàn|linh|lẻ)"
)
SMALL_NUMBER_WORD_PATTERN = (
    rf"{NUMBER_WORD_TOKEN_PATTERN}(?:\s+{NUMBER_WORD_TOKEN_PATTERN}){{0,2}}"
)
YEAR_NUMBER_WORD_PATTERN = (
    rf"{NUMBER_WORD_TOKEN_PATTERN}(?:\s+{NUMBER_WORD_TOKEN_PATTERN}){{0,11}}"
)
SMALL_NUMBER_PATTERN = rf"(?:\d{{1,2}}|{SMALL_NUMBER_WORD_PATTERN})"
YEAR_NUMBER_PATTERN = rf"(?:\d{{2,4}}|{YEAR_NUMBER_WORD_PATTERN})"

WEEKDAY_LABELS = {
    0: "thứ hai",
    1: "thứ ba",
    2: "thứ tư",
    3: "thứ năm",
    4: "thứ sáu",
    5: "thứ bảy",
    6: "chủ nhật",
}

WEEKDAY_TOKEN_RE = re.compile(
    r"(?<!\w)(?:"
    r"t\s*[2-7]|cn|"
    r"thứ\s*(?:hai|2|ba|3|tư|4|năm|5|sáu|6|bảy|7)|"
    r"chủ\s*nhật"
    r")(?!\w)",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    """Normalize input while preserving time/date separators."""
    text = unicodedata.normalize("NFC", text).lower().strip()
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"[,!?;]+", " ", text)
    return re.sub(r"\s+", " ", text).strip(" .")


def _fold(text: str) -> str:
    """Return accent-free lowercase text for tolerant comparisons."""
    normalized = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _strip_command_prefix(text: str) -> str:
    """Allow the parser to be called with or without a command prefix."""
    text = re.sub(r"^(?:tôi|cho\s+tôi)\s+", "", text)
    text = re.sub(
        r"^(?:nhắc\s+hẹn|nhắc\s+nhở|lịch\s+nhắc|hẹn\s+giờ)\s+",
        "",
        text,
    )
    patterns = (
        r"^(?:hãy\s+)?hẹn\s+giờ\s+nhắc\s+tôi\s+",
        r"^(?:hãy\s+)?tạo\s+hẹn\s+giờ\s+nhắc\s+tôi\s+",
        r"^(?:hãy\s+)?(?:tạo|đặt|thêm)\s+(?:nhắc\s+hẹn|nhắc\s+nhở|lịch\s+nhắc|hẹn\s+giờ)\s+",
        r"^(?:hãy\s+)?(?:nhắc|hẹn|thêm|tạo|đặt)(?:\s+(?:tôi|cho\s+tôi))?\s+",
    )
    for pattern in patterns:
        stripped = re.sub(pattern, "", text, count=1)
        if stripped != text:
            return stripped.strip()
    return text


def _parse_under_thousand(tokens: list[str]) -> int:
    """Parse one Vietnamese number group below 1000."""
    tokens = [token for token in tokens if token not in ("linh", "lẻ", "và")]
    if not tokens:
        return 0

    # Speech engines sometimes dictate each digit separately, for example
    # ``hai không hai sáu`` for 2026 or ``không sáu`` for 06.
    if all(token in DIGITS for token in tokens) and len(tokens) > 1:
        return int("".join(str(DIGITS[token]) for token in tokens))

    value = 0
    if "trăm" in tokens:
        index = tokens.index("trăm")
        if index == 0 or tokens[index - 1] not in DIGITS:
            raise ReminderParseError("Thiếu hàng trăm.")
        value += DIGITS[tokens[index - 1]] * 100
        tokens = tokens[index + 1 :]
        if not tokens:
            return value

    if not tokens:
        return value
    if tokens[0] == "mười":
        value += 10
        tokens = tokens[1:]
    elif len(tokens) >= 2 and tokens[0] in DIGITS and tokens[1] == "mươi":
        value += DIGITS[tokens[0]] * 10
        tokens = tokens[2:]
    elif len(tokens) == 1 and tokens[0] in DIGITS:
        return value + DIGITS[tokens[0]]
    elif all(token in DIGITS for token in tokens):
        return value + int("".join(str(DIGITS[token]) for token in tokens))
    else:
        raise ReminderParseError("Không hiểu cấu trúc số.")

    if tokens:
        if len(tokens) != 1 or tokens[0] not in DIGITS:
            raise ReminderParseError("Không hiểu phần đơn vị của số.")
        value += DIGITS[tokens[0]]
    return value


def _parse_number(text: str) -> int:
    """Parse Vietnamese cardinal or digit-by-digit numbers up to 999999."""
    text = _clean(text)
    if text.isdigit():
        return int(text)
    tokens = text.split()
    if not tokens:
        raise ReminderParseError("Thiếu số.")

    allowed = set(DIGITS) | {
        "mười",
        "mươi",
        "trăm",
        "nghìn",
        "ngàn",
        "linh",
        "lẻ",
        "và",
    }
    if any(token not in allowed for token in tokens):
        raise ReminderParseError(f"Không hiểu số {text}.")

    # Pure digit dictation: ``một tám`` -> 18, ``hai không hai sáu`` -> 2026.
    if len(tokens) > 1 and all(token in DIGITS for token in tokens):
        return int("".join(str(DIGITS[token]) for token in tokens))

    thousand_indexes = [
        index for index, token in enumerate(tokens) if token in ("nghìn", "ngàn")
    ]
    if len(thousand_indexes) > 1:
        raise ReminderParseError(f"Không hiểu số {text}.")
    if thousand_indexes:
        index = thousand_indexes[0]
        left = tokens[:index] or ["một"]
        right = tokens[index + 1 :]
        return _parse_under_thousand(left) * 1000 + _parse_under_thousand(right)

    return _parse_under_thousand(tokens)


def _apply_period(hour: int, period: str | None) -> int:
    if not period:
        return hour
    period = _fold(period)
    if period in ("chieu", "toi") and hour < 12:
        return hour + 12
    if period == "dem" and hour == 12:
        return 0
    if period == "sang" and hour == 12:
        return 0
    return hour


def _remove_span(text: str, start: int, end: int) -> str:
    return re.sub(r"\s+", " ", f"{text[:start]} {text[end:]}").strip()


def _extract_time(
    text: str, *, required: bool = True
) -> tuple[int, int, str] | None:
    """Extract one natural time expression from text.

    When ``required`` is false, return ``None`` if the request contains no
    recognizable clock time. Invalid clock values still raise an error.
    """
    text = _clean(text)
    patterns: tuple[re.Pattern[str], ...] = (
        # 18h30, 18 h 30, 18:30
        re.compile(
            r"(?<!\d)(?P<h>\d{1,2})\s*(?:h|:)\s*(?P<m>\d{1,2})"
            r"(?:\s*(?P<p>sáng|chiều|tối|đêm))?(?!\d)"
        ),
        # 1830
        re.compile(
            r"(?<!\d)(?P<h>[01]\d|2[0-3])(?P<m>[0-5]\d)"
            r"(?:\s*(?P<p>sáng|chiều|tối|đêm))?(?!\d)"
        ),
        # 18 giờ 30 phút, 18 giờ ba mươi, 18 giờ rưỡi, 18 giờ
        re.compile(
            rf"(?<!\d)(?P<h>\d{{1,2}})\s*giờ"
            rf"(?:\s*(?P<m>\d{{1,2}}|rưỡi|{SMALL_NUMBER_WORD_PATTERN})"
            rf"\s*(?:phút)?)?"
            rf"(?:\s*(?P<p>sáng|chiều|tối|đêm))?(?!\w)"
        ),
        # 18h (hour only)
        re.compile(
            r"(?<!\d)(?P<h>\d{1,2})\s*h"
            r"(?:\s*(?P<p>sáng|chiều|tối|đêm))?(?!\w)"
        ),
    )

    match: re.Match[str] | None = None
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            break

    # Natural spaced form: 18 30 đi tắm. Limit it to the beginning after
    # optional fillers to avoid interpreting numbers inside reminder content.
    if match is None:
        spaced = re.compile(
            r"^(?:vào\s+|lúc\s+)?(?P<h>\d{1,2})\s+(?P<m>\d{1,2})"
            r"(?:\s*(?P<p>sáng|chiều|tối|đêm))?(?=\s|$)"
        )
        match = spaced.search(text)

    # Word form produced by speech-to-text, for example:
    # ``mười tám giờ ba mươi uống thuốc`` or
    # ``lúc sáu giờ không năm phút sáng``. The word ``phút`` is optional
    # because many STT engines omit it after converting 18h30.
    if match is None:
        word_match = re.search(
            rf"(?<!\w)(?:vào\s+|lúc\s+)?"
            rf"(?P<h>{SMALL_NUMBER_WORD_PATTERN})\s+giờ"
            rf"(?:\s+(?P<m>rưỡi|\d{{1,2}}|{SMALL_NUMBER_WORD_PATTERN})"
            rf"(?:\s+phút)?)?"
            rf"(?:\s+(?P<p>sáng|chiều|tối|đêm))?(?=\s|$)",
            text,
        )
        if word_match:
            hour = _apply_period(
                _parse_number(word_match.group("h")), word_match.group("p")
            )
            raw_minute = word_match.group("m")
            minute = (
                30
                if raw_minute == "rưỡi"
                else _parse_number(raw_minute) if raw_minute else 0
            )
            rest = _remove_span(text, word_match.start(), word_match.end())
            if not 0 <= hour <= 23 or not 0 <= minute <= 59:
                raise ReminderParseError("Giờ hoặc phút không hợp lệ.")
            return hour, minute, rest

    if match is None:
        if not required:
            return None
        raise ReminderParseError(
            "Chưa nhận ra giờ. Có thể nhập 18h30, 18:30, 1830, "
            "18 30, 18 giờ 30 phút hoặc mười tám giờ ba mươi."
        )

    hour = _apply_period(int(match.group("h")), match.groupdict().get("p"))
    raw_minute = match.groupdict().get("m")
    minute = (
        30
        if raw_minute == "rưỡi"
        else _parse_number(raw_minute) if raw_minute else 0
    )
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ReminderParseError("Giờ hoặc phút không hợp lệ.")
    rest = _remove_span(text, match.start(), match.end())
    return hour, minute, rest


def _weekday_from_token(token: str) -> int:
    folded = re.sub(r"\s+", "", _fold(token))
    mapping = {
        "t2": 0,
        "thuhai": 0,
        "thu2": 0,
        "t3": 1,
        "thuba": 1,
        "thu3": 1,
        "t4": 2,
        "thutu": 2,
        "thu4": 2,
        "t5": 3,
        "thunam": 3,
        "thu5": 3,
        "t6": 4,
        "thusau": 4,
        "thu6": 4,
        "t7": 5,
        "thubay": 5,
        "thu7": 5,
        "cn": 6,
        "chunhat": 6,
    }
    if folded not in mapping:
        raise ReminderParseError(f"Không hiểu thứ trong tuần {token}.")
    return mapping[folded]


def _extract_recurrence(text: str) -> tuple[Recurrence, str, str | None]:
    """Extract a recurrence rule from anywhere in the request."""
    text = _clean(text)
    folded = _fold(text)

    # Yearly recurrence, for example: 18h30 ngày 20 tháng 10 hàng năm.
    yearly_marker = re.search(r"\b(?:mỗi|hàng|hằng)\s+năm\b", text)
    if yearly_marker:
        date_match = re.search(
            rf"\bngày\s+(?P<d>{SMALL_NUMBER_PATTERN})\s+tháng\s+"
            rf"(?P<m>{SMALL_NUMBER_PATTERN})(?=\s|$)",
            text,
        )
        if not date_match:
            date_match = re.search(
                r"(?<!\d)(?P<d>\d{1,2})[/-](?P<m>\d{1,2})(?![/-]\d)",
                text,
            )
        if not date_match:
            raise ReminderParseError(
                "Nhắc hằng năm cần có ngày và tháng, ví dụ ngày 20 tháng 10."
            )
        day = _parse_number(date_match.group("d"))
        month = _parse_number(date_match.group("m"))
        if not 1 <= day <= 31 or not 1 <= month <= 12:
            raise ReminderParseError("Ngày hoặc tháng lặp hằng năm không hợp lệ.")
        spans = sorted(
            [(yearly_marker.start(), yearly_marker.end()), (date_match.start(), date_match.end())],
            reverse=True,
        )
        rest = text
        for start, end in spans:
            rest = _remove_span(rest, start, end)
        return (
            Recurrence(kind="yearly", day_of_month=day, month=month),
            rest,
            f"hằng năm ngày {day}/{month}",
        )

    # Monthly recurrence, for example: 18h30 ngày 15 hàng tháng.
    monthly_marker = re.search(r"\b(?:mỗi|hàng|hằng)\s+tháng\b", text)
    if monthly_marker:
        day_match = re.search(
            rf"\bngày\s+(?P<d>{SMALL_NUMBER_PATTERN})(?=\s|$)",
            text,
        )
        if not day_match:
            raise ReminderParseError(
                "Nhắc hằng tháng cần có ngày, ví dụ ngày 15 hàng tháng."
            )
        day = _parse_number(day_match.group("d"))
        if not 1 <= day <= 31:
            raise ReminderParseError("Ngày lặp hằng tháng phải từ 1 đến 31.")
        spans = sorted(
            [(monthly_marker.start(), monthly_marker.end()), (day_match.start(), day_match.end())],
            reverse=True,
        )
        rest = text
        for start, end in spans:
            rest = _remove_span(rest, start, end)
        return (
            Recurrence(kind="monthly", day_of_month=day),
            rest,
            f"hằng tháng ngày {day}",
        )

    # Monday-Friday and weekend aliases.
    weekday_group_patterns = (
        r"(?:t\s*2|thứ\s*(?:hai|2))\s*(?:-|đến|tới)\s*(?:t\s*6|thứ\s*(?:sáu|6))",
        r"(?:từ\s+)?thứ\s*(?:hai|2)\s+(?:đến|tới)\s+thứ\s*(?:sáu|6)",
        r"(?:các\s+)?ngày\s+trong\s+tuần",
        r"ngày\s+thường",
    )
    for pattern in weekday_group_patterns:
        match = re.search(pattern, text)
        if match:
            rest = _remove_span(text, match.start(), match.end())
            rest = re.sub(
                r"^\s*(?:(?:mỗi|hàng|hằng)\s+(?:ngày|tuần)\s*)?"
                r"(?:từ|vào)?\s*",
                "",
                rest,
            )
            return Recurrence(kind="weekdays"), _clean(rest), "từ thứ hai đến thứ sáu"

    weekend_patterns = (
        r"cuối\s+tuần",
        r"(?:t\s*7|thứ\s*(?:bảy|7))\s*(?:và|,)\s*(?:cn|chủ\s*nhật)",
    )
    for pattern in weekend_patterns:
        match = re.search(pattern, text)
        if match:
            rest = _remove_span(text, match.start(), match.end())
            rest = re.sub(
                r"^\s*(?:(?:mỗi|hàng|hằng)\s+(?:ngày|tuần)?\s*)?"
                r"(?:vào)?\s*",
                "",
                rest,
            )
            return Recurrence(kind="weekend"), _clean(rest), "cuối tuần"

    # Weekly recurrence supports one or many weekday tokens in any order.
    weekly_marker = re.search(r"\b(?:mỗi|hàng|hằng)\s+tuần\b", text)
    weekday_matches = list(WEEKDAY_TOKEN_RE.finditer(text))
    if weekly_marker and weekday_matches:
        weekdays = sorted({_weekday_from_token(item.group(0)) for item in weekday_matches})
        spans = [(weekly_marker.start(), weekly_marker.end())]
        spans.extend((item.start(), item.end()) for item in weekday_matches)
        rest = text
        for start, end in sorted(spans, reverse=True):
            rest = _remove_span(rest, start, end)
        rest = re.sub(r"\b(?:vào|các|và)\b", " ", rest)
        labels = ", ".join(WEEKDAY_LABELS[item] for item in weekdays)
        return (
            Recurrence(
                kind="weekly",
                weekday=weekdays[0],
                weekdays=weekdays,
            ),
            _clean(rest),
            f"hằng tuần vào {labels}",
        )

    # Legacy/natural form: mỗi thứ ba ...
    weekly_prefix = re.search(
        rf"\b(?:mỗi|hàng|hằng)\s+(?P<w>{WEEKDAY_TOKEN_RE.pattern})",
        text,
    )
    if weekly_prefix:
        weekday = _weekday_from_token(weekly_prefix.group("w"))
        rest = _remove_span(text, weekly_prefix.start(), weekly_prefix.end())
        return (
            Recurrence(kind="weekly", weekday=weekday, weekdays=[weekday]),
            rest,
            f"hằng tuần vào {WEEKDAY_LABELS[weekday]}",
        )

    daily_match = re.search(r"\b(?:mỗi|hàng|hằng)\s+ngày\b", text)
    if daily_match:
        rest = _remove_span(text, daily_match.start(), daily_match.end())
        return Recurrence(kind="daily"), rest, "hằng ngày"

    return Recurrence(), text, None


def _strict_datetime(
    now: datetime,
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
) -> datetime:
    """Create a local datetime and reject impossible explicit dates."""
    if not 1 <= year <= 9999:
        raise ReminderParseError("Năm không hợp lệ.")
    if not 1 <= month <= 12:
        raise ReminderParseError("Tháng phải từ 1 đến 12.")
    max_day = calendar.monthrange(year, month)[1]
    if not 1 <= day <= max_day:
        raise ReminderParseError(
            f"Ngày {day}/{month}/{year} không tồn tại."
        )
    return dt_util.as_local(
        datetime(year, month, day, hour, minute, tzinfo=now.tzinfo)
    )


def _recurring_datetime(
    now: datetime,
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
) -> datetime:
    """Create a recurrence datetime, using month end for day 29-31."""
    if not 1 <= year <= 9999:
        raise ReminderParseError("Năm không hợp lệ.")
    if not 1 <= month <= 12:
        raise ReminderParseError("Tháng phải từ 1 đến 12.")
    day = min(day, calendar.monthrange(year, month)[1])
    return dt_util.as_local(
        datetime(year, month, day, hour, minute, tzinfo=now.tzinfo)
    )


def _next_allowed_weekday(
    now: datetime, weekdays: set[int], hour: int, minute: int
) -> datetime:
    for offset in range(8):
        candidate = (now + timedelta(days=offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if candidate.weekday() in weekdays and candidate > now:
            return candidate
    raise ReminderParseError("Không tính được lần nhắc tiếp theo.")


def _extract_one_time_date(
    text: str, now: datetime
) -> tuple[tuple[int, int, int] | None, int | None, str, bool]:
    """Extract explicit date or one-time weekday.

    Returns (date tuple, weekday, remaining text, year_was_explicit).
    """
    text = _clean(text)

    relative_dates = (
        (r"\bngày\s+kia\b", 2),
        (r"\bngày\s+mai\b", 1),
        (r"\bhôm\s+nay\b", 0),
    )
    for pattern, offset in relative_dates:
        match = re.search(pattern, text)
        if match:
            target = now + timedelta(days=offset)
            return (
                (target.year, target.month, target.day),
                None,
                _remove_span(text, match.start(), match.end()),
                True,
            )

    # Prefer a date containing an explicit year. Keeping this separate from
    # the no-year expression prevents the Vietnamese word ``năm`` (which can
    # mean both the number five and the word year) from being swallowed by the
    # month group.
    word_date = re.search(
        rf"\b(?:ngày\s+)?(?P<d>{SMALL_NUMBER_PATTERN})\s+tháng\s+"
        rf"(?P<m>{SMALL_NUMBER_PATTERN})\s+năm\s+"
        rf"(?P<y>{YEAR_NUMBER_PATTERN})(?=\s|$)",
        text,
    )
    if word_date:
        year = _parse_number(word_date.group("y"))
        if year < 100:
            year += 2000
        return (
            (
                year,
                _parse_number(word_date.group("m")),
                _parse_number(word_date.group("d")),
            ),
            None,
            _remove_span(text, word_date.start(), word_date.end()),
            True,
        )

    word_date = re.search(
        rf"\b(?:ngày\s+)?(?P<d>{SMALL_NUMBER_PATTERN})\s+tháng\s+"
        rf"(?P<m>{SMALL_NUMBER_PATTERN})(?=\s|$)",
        text,
    )
    if word_date:
        return (
            (
                now.year,
                _parse_number(word_date.group("m")),
                _parse_number(word_date.group("d")),
            ),
            None,
            _remove_span(text, word_date.start(), word_date.end()),
            False,
        )

    numeric_date = re.search(
        r"(?<!\d)(?:ngày\s+)?(?P<d>\d{1,2})[/-](?P<m>\d{1,2})"
        r"(?:[/-](?P<y>\d{2,4}))?(?!\d)",
        text,
    )
    if numeric_date:
        raw_year = numeric_date.group("y")
        year = now.year
        if raw_year:
            year = int(raw_year)
            if year < 100:
                year += 2000
        return (
            (year, int(numeric_date.group("m")), int(numeric_date.group("d"))),
            None,
            _remove_span(text, numeric_date.start(), numeric_date.end()),
            raw_year is not None,
        )

    # A weekday without a weekly marker means the nearest one-time occurrence.
    weekday_match = WEEKDAY_TOKEN_RE.search(text)
    if weekday_match:
        weekday = _weekday_from_token(weekday_match.group(0))
        return (
            None,
            weekday,
            _remove_span(text, weekday_match.start(), weekday_match.end()),
            False,
        )

    return None, None, text, False


def _format_time(value: datetime) -> str:
    return value.strftime("%H:%M ngày %d/%m/%Y")


def _parse_duration_expression(text: str) -> timedelta:
    """Parse a Vietnamese duration containing days, hours and minutes."""
    text = _clean(text)
    # Expand compact relative notation such as ``1h30p`` so each component
    # can be parsed independently.
    text = re.sub(r"(?<=\d)([hp])(?=\d)", r"\1 ", text)
    if not text:
        raise ReminderParseError("Thiếu khoảng thời gian.")

    total_minutes = 0
    consumed = [False] * len(text)

    def mark(start: int, end: int) -> None:
        for index in range(start, end):
            consumed[index] = True

    # Natural half-hour forms. Handle these before normal components so the
    # trailing word ``rưỡi`` is not left as unparsed text.
    half_hour_pattern = re.compile(
        rf"(?<!\w)(?P<n>\d+|{YEAR_NUMBER_WORD_PATTERN})\s+"
        rf"(?:giờ|tiếng)\s+rưỡi(?=\s|$)"
    )
    for match in half_hour_pattern.finditer(text):
        amount = _parse_number(match.group("n"))
        if amount <= 0:
            raise ReminderParseError("Khoảng thời gian phải lớn hơn 0.")
        total_minutes += amount * 60 + 30
        mark(match.start(), match.end())

    half_pattern = re.compile(r"(?<!\w)nửa\s+(?:giờ|tiếng)(?=\s|$)")
    for match in half_pattern.finditer(text):
        if any(consumed[match.start() : match.end()]):
            continue
        total_minutes += 30
        mark(match.start(), match.end())

    component_pattern = re.compile(
        rf"(?<!\w)(?P<n>\d+|{YEAR_NUMBER_WORD_PATTERN})\s*"
        rf"(?:(?P<u>ngày|giờ|tiếng|phút)(?=\s|$)"
        rf"|(?P<short_u>h|p)(?=\s|$|\d))"
    )
    for match in component_pattern.finditer(text):
        if any(consumed[match.start() : match.end()]):
            continue
        amount = _parse_number(match.group("n"))
        if amount < 0:
            raise ReminderParseError("Khoảng thời gian không hợp lệ.")
        unit = match.group("u") or match.group("short_u")
        if unit == "ngày":
            total_minutes += amount * 24 * 60
        elif unit in ("giờ", "tiếng", "h"):
            total_minutes += amount * 60
        else:
            total_minutes += amount
        mark(match.start(), match.end())

    leftover = "".join(
        " " if consumed[index] else char for index, char in enumerate(text)
    )
    leftover = re.sub(r"\b(?:và|cộng)\b", " ", leftover)
    leftover = re.sub(r"\s+", " ", leftover).strip()
    if leftover:
        raise ReminderParseError(
            f"Không hiểu khoảng thời gian {text}. "
            "Có thể nói 30 phút nữa hoặc 1 giờ 30 phút nữa."
        )
    if total_minutes <= 0:
        raise ReminderParseError("Khoảng thời gian phải lớn hơn 0.")
    return timedelta(minutes=total_minutes)


def _parse_relative(text: str, now: datetime) -> ParsedReminder | None:
    """Parse requests relative to now, including composite durations."""
    duration_number = rf"(?:\d+|{YEAR_NUMBER_WORD_PATTERN})"
    duration_part = (
        rf"(?:{duration_number}\s+(?:giờ|tiếng)\s+rưỡi"
        rf"|nửa\s+(?:giờ|tiếng)"
        rf"|{duration_number}\s*(?:ngày|giờ|tiếng|phút|h|p))"
    )
    duration_expression = (
        rf"{duration_part}(?:\s*(?:(?:và|cộng)\s+)?{duration_part})*"
    )
    patterns = (
        re.compile(
            rf"^sau\s+(?P<duration>{duration_expression})\s+(?P<msg>.+)$"
        ),
        re.compile(
            rf"^(?P<duration>{duration_expression})\s+nữa\s+(?P<msg>.+)$"
        ),
    )
    match = next(
        (pattern.match(text) for pattern in patterns if pattern.match(text)),
        None,
    )
    if not match:
        return None

    try:
        delta = _parse_duration_expression(match.group("duration"))
    except ReminderParseError:
        # A sentence beginning with ``sau`` or containing ``nữa`` is clearly
        # intended as a relative reminder, so surface the duration error.
        raise

    run = now + delta
    message = _clean(match.group("msg"))
    if not message:
        raise ReminderParseError("Thiếu nội dung nhắc nhở.")
    return ParsedReminder(
        message=message,
        first_run=run,
        recurrence=Recurrence(),
        confirmation=f"Đã tạo nhắc nhở {message} vào {_format_time(run)}.",
    )


def _clean_message(text: str) -> str:
    text = re.sub(r"^(?:vào|lúc|cho|để)\s+", "", _clean(text))
    text = re.sub(r"\b(?:vào|lúc)\s*$", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .:-")
    if not text:
        raise ReminderParseError("Thiếu nội dung nhắc nhở.")
    return text


def parse_reminder_request(
    text: str, now: datetime | None = None
) -> ParsedReminder:
    """Parse a natural Vietnamese reminder request."""
    now = dt_util.as_local(now or dt_util.now())
    text = _strip_command_prefix(_clean(text))
    if not text:
        raise ReminderParseError("Thiếu nội dung nhắc nhở.")

    relative = _parse_relative(text, now)
    if relative is not None:
        return relative

    recurrence, remaining, recurrence_label = _extract_recurrence(text)
    date_tuple: tuple[int, int, int] | None = None
    one_time_weekday: int | None = None
    year_explicit = False
    if recurrence.kind == "none":
        date_tuple, one_time_weekday, remaining, year_explicit = (
            _extract_one_time_date(remaining, now)
        )

    time_result = _extract_time(remaining, required=False)
    time_was_defaulted = time_result is None
    if time_result is None:
        # A date, weekday or recurrence without a clock time naturally uses
        # the current local hour and minute. A request containing neither a
        # date nor a time remains ambiguous and is rejected.
        if (
            recurrence.kind == "none"
            and date_tuple is None
            and one_time_weekday is None
        ):
            raise ReminderParseError(
                "Chưa nhận ra giờ hoặc ngày nhắc. Có thể nói 30 phút nữa, "
                "ngày mai, thứ ba hoặc 18 giờ 30."
            )
        hour, minute = now.hour, now.minute
    else:
        hour, minute, remaining = time_result
    message = _clean_message(remaining)

    if recurrence.kind == "daily":
        run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if run <= now:
            run += timedelta(days=1)
    elif recurrence.kind == "weekdays":
        run = _next_allowed_weekday(now, {0, 1, 2, 3, 4}, hour, minute)
    elif recurrence.kind == "weekend":
        run = _next_allowed_weekday(now, {5, 6}, hour, minute)
    elif recurrence.kind == "weekly":
        weekdays = set(recurrence.weekdays or [])
        if not weekdays and recurrence.weekday is not None:
            weekdays = {recurrence.weekday}
        run = _next_allowed_weekday(now, weekdays, hour, minute)
    elif recurrence.kind == "monthly":
        day = recurrence.day_of_month or now.day
        run = _recurring_datetime(now, now.year, now.month, day, hour, minute)
        if run <= now:
            year = now.year + (1 if now.month == 12 else 0)
            month = 1 if now.month == 12 else now.month + 1
            run = _recurring_datetime(now, year, month, day, hour, minute)
    elif recurrence.kind == "yearly":
        month = recurrence.month or now.month
        day = recurrence.day_of_month or now.day
        run = _recurring_datetime(now, now.year, month, day, hour, minute)
        if run <= now:
            run = _recurring_datetime(
                now, now.year + 1, month, day, hour, minute
            )
    elif one_time_weekday is not None:
        run = _next_allowed_weekday(now, {one_time_weekday}, hour, minute)
    elif date_tuple is not None:
        year, month, day = date_tuple
        run = _strict_datetime(now, year, month, day, hour, minute)
        if (
            time_was_defaulted
            and (year, month, day) == (now.year, now.month, now.day)
            and run <= now
        ):
            # The current minute has usually already started by the time the
            # voice command is processed. Schedule the next full minute rather
            # than moving an implicit date to next year or rejecting it.
            run = (now + timedelta(minutes=1)).replace(
                second=0, microsecond=0
            )
        # A date without a year naturally means the next occurrence.
        elif run <= now and not year_explicit:
            run = _strict_datetime(now, year + 1, month, day, hour, minute)
        elif run <= now:
            raise ReminderParseError("Thời điểm nhắc nhở đã qua.")
    else:
        run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if run <= now:
            run += timedelta(days=1)

    if recurrence.kind == "none":
        confirmation = f"Đã tạo nhắc nhở {message} vào {_format_time(run)}."
    else:
        confirmation = (
            f"Đã tạo nhắc nhở {recurrence_label} lúc "
            f"{hour:02d}:{minute:02d}: {message}."
        )

    return ParsedReminder(
        message=message,
        first_run=run,
        recurrence=recurrence,
        confirmation=confirmation,
    )
