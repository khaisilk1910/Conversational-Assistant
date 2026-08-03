"""Natural-language weather request planning helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
from typing import Any

from .targeting import normalize_text

MAX_WEATHER_FORECAST_DAYS = 7

_WEEKDAYS_VI = (
    "Thứ Hai",
    "Thứ Ba",
    "Thứ Tư",
    "Thứ Năm",
    "Thứ Sáu",
    "Thứ Bảy",
    "Chủ Nhật",
)
_WEEKDAYS_EN = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

_VI_DIGITS = {
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
_EN_NUMBERS = {
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
}
_NUMBER_PATTERN = (
    r"(?:\d{1,3}|(?:khong|mot|hai|ba|bon|tu|nam|lam|sau|bay|tam|chin|muoi)"
    r"(?:\s+(?:khong|mot|hai|ba|bon|tu|nam|lam|sau|bay|tam|chin|muoi))?"
    r"|(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
    r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty|thirty)(?:\s+(?:one|two|three|four|five|six|seven|eight|nine))?)"
)


@dataclass(slots=True, frozen=True)
class WeatherQueryPlan:
    """Resolved day window for one forecast request."""

    start_date: date
    day_count: int
    needs_ai: bool = False
    explicit_period: bool = False

    @property
    def exceeds_limit(self) -> bool:
        """Return whether the requested consecutive forecast is unsupported."""
        return self.day_count > MAX_WEATHER_FORECAST_DAYS


def _small_number(value: str) -> int | None:
    """Parse common Vietnamese or English natural numbers."""
    normalized = normalize_text(value)
    if not normalized:
        return None
    if normalized.isdigit():
        return int(normalized)
    tokens = normalized.split()
    if all(token in _EN_NUMBERS for token in tokens):
        if len(tokens) == 1:
            return _EN_NUMBERS[tokens[0]]
        if tokens[0] in {"twenty", "thirty"}:
            return _EN_NUMBERS[tokens[0]] + _EN_NUMBERS.get(tokens[-1], 0)
        return sum(_EN_NUMBERS[token] for token in tokens)
    allowed = set(_VI_DIGITS) | {"muoi"}
    if any(token not in allowed for token in tokens):
        return None
    if len(tokens) == 1:
        return 10 if tokens[0] == "muoi" else _VI_DIGITS.get(tokens[0])
    if tokens[0] == "muoi":
        return 10 + _VI_DIGITS.get(tokens[-1], 0)
    if len(tokens) >= 2 and tokens[1] == "muoi":
        return _VI_DIGITS.get(tokens[0], 0) * 10 + _VI_DIGITS.get(
            tokens[-1], 0
        )
    return None


def is_storm_check_request(text: str) -> bool:
    """Return whether text explicitly asks about a tropical storm threat."""
    value = normalize_text(text)
    if not value:
        return False
    phrases = (
        "kiem tra bao",
        "kiem tra tin bao",
        "tin bao moi nhat",
        "thong tin bao",
        "tinh hinh bao",
        "co bao khong",
        "co con bao nao",
        "bao anh huong viet nam",
        "bao vao viet nam",
        "bao sap vao",
        "canh bao bao",
        "ap thap nhiet doi",
        "xoay thuan nhiet doi",
        "tropical storm",
        "tropical depression",
        "tropical cyclone",
        "storm affecting vietnam",
        "storm threat to vietnam",
        "check storm",
        "check typhoon",
        "typhoon affecting vietnam",
    )
    return any(
        value == phrase
        or value.startswith(f"{phrase} ")
        or f" {phrase} " in f" {value} "
        for phrase in phrases
    )


def _valid_date(year: int, month: int, day: int) -> date | None:
    """Return one valid calendar date or None."""
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _explicit_weather_date(
    text: str,
    normalized: str,
    reference_time: datetime,
) -> date | None:
    """Resolve common explicit Vietnamese/English calendar date formats."""
    numeric_match = re.search(
        r"(?<!\d)(?P<day>\d{1,2})[./-](?P<month>\d{1,2})"
        r"(?:[./-](?P<year>\d{4}))?(?!\d)",
        str(text or ""),
    )
    if numeric_match:
        year = int(numeric_match.group("year") or reference_time.year)
        return _valid_date(
            year,
            int(numeric_match.group("month")),
            int(numeric_match.group("day")),
        )

    word_match = re.search(
        r"(?:ngay\s+)?(?P<day>\d{1,2})\s+thang\s+"
        r"(?P<month>\d{1,2})(?:\s+(?:nam\s+)?(?P<year>\d{4}))?",
        normalized,
    )
    if word_match:
        year = int(word_match.group("year") or reference_time.year)
        return _valid_date(
            year,
            int(word_match.group("month")),
            int(word_match.group("day")),
        )
    return None


def parse_weather_query_plan(
    text: str,
    reference_time: datetime,
) -> WeatherQueryPlan:
    """Resolve common one-day and consecutive-day weather expressions locally."""
    normalized = normalize_text(text)
    today = reference_time.date()

    explicit_date = _explicit_weather_date(text, normalized, reference_time)

    # Consecutive ranges: "3 ngày tiếp theo", "5 days forecast", etc.
    range_patterns: tuple[tuple[str, bool], ...] = (
        # "N ngày tiếp theo/tới" always begins after the current date.
        # Thus one next day means tomorrow, and two next days means tomorrow
        # plus the day after tomorrow.
        (
            rf"(?P<n>{_NUMBER_PATTERN})\s+ngay\s+"
            rf"(?:tiep(?:\s+theo)?|toi|sap toi|ke tiep)",
            True,
        ),
        (rf"next\s+(?P<n>{_NUMBER_PATTERN})\s+day(?:s)?", True),
        (
            rf"(?P<n>{_NUMBER_PATTERN})\s+day(?:s)?\s+"
            rf"(?:ahead|next)",
            True,
        ),
        # A plain "weather N days" request keeps the historical behaviour of
        # including today unless the wording explicitly says next/tomorrow.
        (
            rf"(?:du bao|thoi tiet)\s+(?P<n>{_NUMBER_PATTERN})\s+"
            rf"ngay(?!\s+nua)(?:\s|$)",
            False,
        ),
        (
            rf"(?:weather|forecast)\s+(?:for\s+)?"
            rf"(?P<n>{_NUMBER_PATTERN})\s+day(?:s)?"
            rf"(?!\s+from\s+now)(?:\s|$)",
            False,
        ),
        (rf"(?P<n>{_NUMBER_PATTERN})[- ]day\s+forecast", False),
    )
    for pattern, starts_after_today in range_patterns:
        match = re.search(pattern, normalized)
        if match:
            parsed = _small_number(match.group("n"))
            if parsed is not None and parsed > 0:
                explicit_tomorrow = any(
                    phrase in normalized
                    for phrase in (
                        "tu ngay mai",
                        "bat dau ngay mai",
                        "starting tomorrow",
                    )
                )
                start = explicit_date or (
                    today
                    + timedelta(
                        days=1
                        if starts_after_today or explicit_tomorrow
                        else 0
                    )
                )
                return WeatherQueryPlan(
                    start_date=start,
                    day_count=parsed,
                    explicit_period=True,
                )

    if explicit_date is not None:
        return WeatherQueryPlan(
            start_date=explicit_date,
            day_count=1,
            explicit_period=True,
        )

    if "7 ngay toi" in normalized:
        return WeatherQueryPlan(
            today + timedelta(days=1), 7, explicit_period=True
        )
    if any(phrase in normalized for phrase in ("tuan toi", "next week")):
        return WeatherQueryPlan(
            today, 7, needs_ai=True, explicit_period=True
        )

    if any(
        phrase in normalized
        for phrase in (
            "hom nay va ngay mai",
            "hom nay lan ngay mai",
            "hom nay ngay mai",
            "today and tomorrow",
        )
    ):
        return WeatherQueryPlan(today, 2, explicit_period=True)

    if any(
        phrase in normalized
        for phrase in (
            "ngay mai va ngay kia",
            "ngay mai ngay kia",
            "tomorrow and the day after tomorrow",
        )
    ):
        return WeatherQueryPlan(
            today + timedelta(days=1),
            2,
            explicit_period=True,
        )

    # A number followed by "ngày nữa" means one target date N days from now,
    # not an N-day range.
    offset_match = re.search(
        rf"(?P<n>{_NUMBER_PATTERN})\s+ngay\s+nua", normalized
    ) or re.search(rf"in\s+(?P<n>{_NUMBER_PATTERN})\s+day(?:s)?", normalized)
    if offset_match:
        parsed = _small_number(offset_match.group("n"))
        if parsed is not None and parsed >= 0:
            return WeatherQueryPlan(
                start_date=today + timedelta(days=parsed),
                day_count=1,
                explicit_period=True,
            )

    if any(phrase in normalized for phrase in ("ngay kia", "day after tomorrow")):
        return WeatherQueryPlan(today + timedelta(days=2), 1, explicit_period=True)
    if any(phrase in normalized for phrase in ("ngay mai", "tomorrow")):
        return WeatherQueryPlan(today + timedelta(days=1), 1, explicit_period=True)
    if any(phrase in normalized for phrase in ("hom nay", "today", "toi nay", "tonight")):
        return WeatherQueryPlan(today, 1, explicit_period=True)

    # Complex relative phrases such as "thứ Ba tuần sau" or "cuối tuần này"
    # are delegated to the configured AI parser before the actual search.
    temporal_cues = (
        "thu ",
        "tuan nay",
        "tuan sau",
        "cuoi tuan",
        "dau tuan",
        "giua tuan",
        "next monday",
        "next tuesday",
        "next wednesday",
        "next thursday",
        "next friday",
        "next saturday",
        "next sunday",
        "this weekend",
        "next weekend",
    )
    needs_ai = any(cue in normalized for cue in temporal_cues)
    return WeatherQueryPlan(
        start_date=today,
        day_count=1,
        needs_ai=needs_ai,
        explicit_period=False,
    )


def weather_plan_from_ai_payload(
    payload: dict[str, Any], reference_time: datetime
) -> WeatherQueryPlan | None:
    """Convert a strict AI parser payload into a safe weather plan."""
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < 0.65:
        return None
    raw_start = str(payload.get("start_date") or "").strip()
    try:
        start = date.fromisoformat(raw_start)
    except ValueError:
        start = reference_time.date()
    try:
        day_count = int(float(payload.get("day_count", 1)))
    except (TypeError, ValueError):
        return None
    if day_count < 1 or day_count > 366:
        return None
    return WeatherQueryPlan(
        start_date=start,
        day_count=day_count,
        needs_ai=False,
        explicit_period=True,
    )


def weather_date_labels(plan: WeatherQueryPlan, *, language: str) -> list[str]:
    """Return exact localized labels for every requested forecast date."""
    weekdays = _WEEKDAYS_EN if language == "en" else _WEEKDAYS_VI
    labels: list[str] = []
    for offset in range(plan.day_count):
        target = plan.start_date + timedelta(days=offset)
        if language == "en":
            labels.append(f"{weekdays[target.weekday()]}, {target:%d/%m/%Y}")
        else:
            labels.append(f"{weekdays[target.weekday()]}, ngày {target:%d/%m/%Y}")
    return labels


def resolved_weather_query(
    original_text: str,
    plan: WeatherQueryPlan,
    *,
    language: str,
) -> str:
    """Append an exact, non-ambiguous forecast window to the user's wording."""
    labels = weather_date_labels(plan, language=language)
    if language == "en":
        constraint = (
            f"Resolved forecast window: exactly {plan.day_count} day(s): "
            + "; ".join(labels)
            + ". List every requested date separately and do not add dates outside this window."
        )
    else:
        constraint = (
            f"Mốc dự báo đã chuẩn hóa: đúng {plan.day_count} ngày: "
            + "; ".join(labels)
            + ". Phải liệt kê riêng từng ngày và không thêm ngày ngoài khoảng này."
        )
    return f"{original_text.strip()}\n\n{constraint}"


def weather_limit_message(*, zalo: bool, language: str) -> str:
    """Return the shared seven-day limit response."""
    if language == "en":
        body = "I can list at most 7 consecutive forecast days. Please request 1 to 7 days."
        return f"⚠️ **Forecast limit: 7 days**\n\n{body}" if zalo else body
    body = (
        "Tích hợp chỉ hỗ trợ liệt kê nhiều nhất 7 ngày dự báo liên tiếp. "
        "Hãy yêu cầu từ 1 đến 7 ngày."
    )
    return f"⚠️ **CHỈ HỖ TRỢ TỐI ĐA 7 NGÀY**\n\n{body}" if zalo else body
