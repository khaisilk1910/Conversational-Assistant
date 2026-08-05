"""Natural-language weather request planning helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
import re
from typing import Any, Iterable

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

_WEEKDAY_PHRASES: tuple[tuple[tuple[str, ...], int], ...] = (
    (("thu hai", "monday"), 0),
    (("thu ba", "tuesday"), 1),
    (("thu tu", "wednesday"), 2),
    (("thu nam", "thursday"), 3),
    (("thu sau", "friday"), 4),
    (("thu bay", "saturday"), 5),
    (("chu nhat", "sunday"), 6),
)

_CONDITION_LABELS_VI = {
    "clear-night": "Trời quang về đêm",
    "cloudy": "Nhiều mây",
    "exceptional": "Thời tiết bất thường",
    "fog": "Sương mù",
    "hail": "Mưa đá",
    "lightning": "Có dông sét",
    "lightning-rainy": "Mưa dông kèm sét",
    "partlycloudy": "Mây thay đổi",
    "pouring": "Mưa rất to",
    "rainy": "Có mưa",
    "snowy": "Có tuyết",
    "snowy-rainy": "Mưa tuyết",
    "sunny": "Trời nắng",
    "windy": "Nhiều gió",
    "windy-variant": "Nhiều gió, có mây",
}
_CONDITION_LABELS_EN = {
    "clear-night": "Clear night",
    "cloudy": "Cloudy",
    "exceptional": "Exceptional weather",
    "fog": "Fog",
    "hail": "Hail",
    "lightning": "Thunderstorms",
    "lightning-rainy": "Thunderstorms with rain",
    "partlycloudy": "Partly cloudy",
    "pouring": "Heavy rain",
    "rainy": "Rain",
    "snowy": "Snow",
    "snowy-rainy": "Snow and rain",
    "sunny": "Sunny",
    "windy": "Windy",
    "windy-variant": "Windy and cloudy",
}
_CONDITION_SEVERITY = {
    "exceptional": 100,
    "lightning-rainy": 95,
    "lightning": 90,
    "hail": 85,
    "pouring": 80,
    "snowy-rainy": 75,
    "snowy": 70,
    "rainy": 65,
    "windy-variant": 55,
    "windy": 50,
    "fog": 45,
    "cloudy": 35,
    "partlycloudy": 25,
    "sunny": 15,
    "clear-night": 10,
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



def _weekday_index(normalized: str) -> int | None:
    """Return the weekday explicitly named in normalized text."""
    for phrases, index in _WEEKDAY_PHRASES:
        if any(re.search(rf"\b{re.escape(phrase)}\b", normalized) for phrase in phrases):
            return index
    return None


def _monday_of_week(value: date) -> date:
    """Return Monday of the week containing value."""
    return value - timedelta(days=value.weekday())


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

    this_week = any(
        phrase in normalized for phrase in ("tuan nay", "this week")
    )
    next_week = any(
        phrase in normalized
        for phrase in ("tuan toi", "tuan sau", "next week")
    )
    weekday_index = _weekday_index(normalized)
    if weekday_index is not None:
        if next_week:
            target = _monday_of_week(today) + timedelta(
                days=7 + weekday_index
            )
        elif this_week:
            target = _monday_of_week(today) + timedelta(days=weekday_index)
        else:
            offset = (weekday_index - today.weekday()) % 7
            target = today + timedelta(days=offset)
        return WeatherQueryPlan(target, 1, explicit_period=True)

    if any(phrase in normalized for phrase in ("cuoi tuan nay", "this weekend")):
        saturday = _monday_of_week(today) + timedelta(days=5)
        start = max(today, saturday)
        return WeatherQueryPlan(
            start,
            max(1, (saturday + timedelta(days=1) - start).days + 1),
            explicit_period=True,
        )
    if any(phrase in normalized for phrase in ("cuoi tuan sau", "next weekend")):
        saturday = _monday_of_week(today) + timedelta(days=12)
        return WeatherQueryPlan(saturday, 2, explicit_period=True)
    if this_week:
        return WeatherQueryPlan(
            today, 7 - today.weekday(), explicit_period=True
        )
    if next_week:
        return WeatherQueryPlan(
            _monday_of_week(today) + timedelta(days=7),
            7,
            explicit_period=True,
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
    if any(
        phrase in normalized
        for phrase in (
            "ngay mai",
            "sang mai",
            "trua mai",
            "chieu mai",
            "toi mai",
            "dem mai",
            "tomorrow",
            "tomorrow morning",
            "tomorrow afternoon",
            "tomorrow evening",
            "tomorrow night",
        )
    ):
        return WeatherQueryPlan(today + timedelta(days=1), 1, explicit_period=True)
    if any(phrase in normalized for phrase in ("hom nay", "today", "toi nay", "tonight")):
        return WeatherQueryPlan(today, 1, explicit_period=True)

    # Complex relative phrases such as "thứ Ba tuần sau" or "cuối tuần này"
    # are delegated to the configured AI parser before the actual search.
    temporal_cues = (
        "dau tuan",
        "giua tuan",
        "early this week",
        "midweek",
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


_CURRENT_CUES = (
    "hien tai",
    "bay gio",
    "luc nay",
    "ngay luc nay",
    "hom nay",
    "today",
    "current weather",
    "right now",
    "now",
)
_HOURLY_CUES = (
    "theo gio",
    "tung gio",
    "moi gio",
    "hourly",
    "sang nay",
    "trua nay",
    "chieu nay",
    "toi nay",
    "dem nay",
    "sang mai",
    "trua mai",
    "chieu mai",
    "toi mai",
    "dem mai",
    "tomorrow morning",
    "tomorrow afternoon",
    "tomorrow evening",
    "tomorrow night",
    "this morning",
    "this afternoon",
    "this evening",
    "tonight",
)
_TWICE_DAILY_CUES = (
    "ban ngay va ban dem",
    "ngay va dem",
    "sang va toi",
    "sang toi",
    "day and night",
    "twice daily",
)


def weather_query_requests_current(
    text: str, plan: WeatherQueryPlan
) -> bool:
    """Return whether current conditions should be included."""
    normalized = normalize_text(text)
    return (not plan.explicit_period) or any(
        cue in normalized for cue in _CURRENT_CUES
    )


def weather_forecast_type_order(
    text: str, plan: WeatherQueryPlan
) -> tuple[str, ...]:
    """Return native forecast action types in request-preferred order."""
    normalized = normalize_text(text)
    if any(cue in normalized for cue in _TWICE_DAILY_CUES):
        return ("twice_daily", "hourly", "daily")
    if (
        any(cue in normalized for cue in _HOURLY_CUES)
        or re.search(r"\b(?:luc|vao|at)\s+\d{1,2}(?:\s*(?:h|gio|:))", normalized)
    ):
        return ("hourly", "twice_daily", "daily")
    if weather_query_requests_current(text, plan):
        return ("hourly", "daily", "twice_daily")
    return ("daily", "twice_daily", "hourly")


def weather_query_location_hint(text: str) -> str | None:
    """Extract a conservative explicit location hint from a weather request.

    The result is intentionally conservative. Returning ``None`` allows the
    selected Home Assistant weather entity to be used. Returning a value tells
    the manager to verify that the request matches the configured entity before
    using local forecast data.
    """
    normalized = normalize_text(text)
    if not normalized:
        return None

    normalized = re.sub(
        r"(?<!\d)\d{1,2}[./-]\d{1,2}(?:[./-]\d{4})?(?!\d)",
        " ",
        normalized,
    )
    normalized = re.sub(r"\b\d{1,2}(?::\d{2})?\s*(?:h|gio)\b", " ", normalized)

    explicit = re.search(
        r"\b(?:o|tai|khu vuc|thanh pho|tinh|in|at)\s+(?P<place>.+)",
        normalized,
    )
    candidate = explicit.group("place") if explicit else normalized

    temporal_patterns = (
        r"\b(?:hom nay|ngay mai|ngay kia|tuan nay|tuan toi|tuan sau|"
        r"cuoi tuan|sang nay|trua nay|chieu nay|toi nay|dem nay|sang mai|"
        r"trua mai|chieu mai|toi mai|dem mai)\b",
        r"\b(?:today|tomorrow|this week|next week|this weekend|next weekend|"
        r"this morning|this afternoon|this evening|tonight|tomorrow morning|"
        r"tomorrow afternoon|tomorrow evening|tomorrow night)\b",
        rf"\b{_NUMBER_PATTERN}\s+(?:ngay|day)s?\b",
        r"\b(?:thu hai|thu ba|thu tu|thu nam|thu sau|thu bay|chu nhat|"
        r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    )
    for pattern in temporal_patterns:
        match = re.search(pattern, candidate)
        if match:
            candidate = candidate[: match.start()]

    remove_phrases = (
        "du bao thoi tiet",
        "weather forecast",
        "ban ngay va ban dem",
        "ngay va dem",
        "sang va toi",
        "nhiet do cao nhat",
        "nhiet do thap nhat",
        "nhiet do cam nhan",
        "co nong khong",
        "co lanh khong",
        "co dep khong",
        "co xau khong",
        "nhu the nao",
        "ra sao",
        "bao nhieu",
        "kha nang mua",
        "xac suat mua",
        "luong mua",
        "toc do gio",
        "huong gio",
        "gio giat",
        "ap suat",
        "tam nhin",
        "do che phu may",
        "theo gio",
        "tung gio",
        "moi gio",
        "du bao",
        "thoi tiet",
        "forecast",
        "weather",
        "co mua khong",
        "nhiet do",
        "do am",
        "chi so uv",
        "uv index",
        "mua",
        "gio",
        "current",
        "hien tai",
        "bay gio",
        "cho toi",
        "xem",
        "kiem tra",
    )
    for phrase in remove_phrases:
        candidate = re.sub(rf"\b{re.escape(phrase)}\b", " ", candidate)

    tokens = [
        token
        for token in candidate.split()
        if token
        not in {
            "o",
            "tai",
            "in",
            "at",
            "luc",
            "vao",
            "sang",
            "trua",
            "chieu",
            "toi",
            "dem",
            "mai",
            "cho",
            "cua",
            "la",
            "co",
            "nhu",
            "the",
            "nao",
            "ra",
            "sao",
            "nong",
            "lanh",
            "mat",
            "dep",
            "xau",
            "cao",
            "thap",
            "nhat",
            "manh",
            "yeu",
            "cam",
            "nhan",
            "theo",
            "dau",
            "khong",
            "bao",
            "nhieu",
            "it",
            "may",
            "nay",
            "toi",
            "tiep",
            "theo",
            "sap",
            "ke",
            "ngay",
            "day",
            "days",
        }
        and not token.isdigit()
    ]
    if not tokens:
        return None
    candidate = " ".join(tokens).strip()
    return candidate[:120] or None


def _forecast_datetime(value: Any, local_tz: tzinfo | None) -> datetime | None:
    """Parse one forecast timestamp and convert it to Home Assistant local time."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_tz or timezone.utc)
    return parsed.astimezone(local_tz or timezone.utc)


def native_forecast_dates(
    forecasts: Iterable[dict[str, Any]], reference_time: datetime
) -> set[date]:
    """Return local calendar dates represented by native forecast entries."""
    result: set[date] = set()
    for item in forecasts:
        parsed = _forecast_datetime(item.get("datetime"), reference_time.tzinfo)
        if parsed is not None:
            result.add(parsed.date())
    return result


def native_forecast_covers_plan(
    forecasts: Iterable[dict[str, Any]],
    plan: WeatherQueryPlan,
    reference_time: datetime,
) -> bool:
    """Return whether native forecast data covers every requested local date."""
    available = native_forecast_dates(forecasts, reference_time)
    requested = {
        plan.start_date + timedelta(days=offset)
        for offset in range(plan.day_count)
    }
    return bool(requested) and requested.issubset(available)


def _safe_float(value: Any) -> float | None:
    """Return one finite float without importing Home Assistant helpers."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _format_number(value: Any, *, language: str, digits: int = 1) -> str | None:
    parsed = _safe_float(value)
    if parsed is None:
        return None
    rounded = round(parsed, digits)
    if abs(rounded - round(rounded)) < 10 ** (-(digits + 1)):
        text = str(int(round(rounded)))
    else:
        text = f"{rounded:.{digits}f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") if language != "en" else text


def _condition_label(value: Any, *, language: str) -> str:
    key = str(value or "").strip().lower()
    labels = _CONDITION_LABELS_EN if language == "en" else _CONDITION_LABELS_VI
    return labels.get(key, key.replace("-", " ").strip().capitalize() or ("Unknown" if language == "en" else "Không rõ"))


def _dominant_condition(entries: list[dict[str, Any]]) -> str | None:
    values = [str(item.get("condition") or "").strip().lower() for item in entries]
    values = [value for value in values if value]
    if not values:
        return None
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return max(
        counts,
        key=lambda item: (
            counts[item],
            _CONDITION_SEVERITY.get(item, 0),
        ),
    )


def _bearing_label(value: Any, *, language: str) -> str | None:
    parsed = _safe_float(value)
    if parsed is None:
        text = str(value or "").strip()
        return text or None
    directions_vi = ("Bắc", "Đông Bắc", "Đông", "Đông Nam", "Nam", "Tây Nam", "Tây", "Tây Bắc")
    directions_en = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    directions = directions_en if language == "en" else directions_vi
    direction = directions[int((parsed + 22.5) // 45) % 8]
    return f"{direction} ({round(parsed)}°)"


def _aggregate_forecast_day(
    entries: list[dict[str, Any]], forecast_type: str
) -> dict[str, Any]:
    """Aggregate daily, twice-daily, or hourly rows into one local day."""
    temperatures = [value for item in entries if (value := _safe_float(item.get("temperature"))) is not None]
    temp_lows = [value for item in entries if (value := _safe_float(item.get("templow"))) is not None]
    apparent = [value for item in entries if (value := _safe_float(item.get("apparent_temperature"))) is not None]
    rain_probs = [value for item in entries if (value := _safe_float(item.get("precipitation_probability"))) is not None]
    precipitation = [value for item in entries if (value := _safe_float(item.get("precipitation"))) is not None]
    humidity = [value for item in entries if (value := _safe_float(item.get("humidity"))) is not None]
    wind = [value for item in entries if (value := _safe_float(item.get("wind_speed"))) is not None]
    gust = [value for item in entries if (value := _safe_float(item.get("wind_gust_speed"))) is not None]
    uv = [value for item in entries if (value := _safe_float(item.get("uv_index"))) is not None]
    cloud = [value for item in entries if (value := _safe_float(item.get("cloud_coverage"))) is not None]
    pressure = [value for item in entries if (value := _safe_float(item.get("pressure"))) is not None]
    visibility = [value for item in entries if (value := _safe_float(item.get("visibility"))) is not None]

    strongest_wind_item = max(
        entries,
        key=lambda item: _safe_float(item.get("wind_speed")) or -1.0,
    )
    periods = []
    if forecast_type == "twice_daily":
        for item in entries:
            periods.append(
                {
                    "is_daytime": item.get("is_daytime"),
                    "condition": item.get("condition"),
                    "temperature": _safe_float(item.get("temperature")),
                    "apparent_temperature": _safe_float(item.get("apparent_temperature")),
                    "precipitation_probability": _safe_float(item.get("precipitation_probability")),
                    "humidity": _safe_float(item.get("humidity")),
                }
            )

    return {
        "condition": _dominant_condition(entries),
        "temperature_low": min(temp_lows or temperatures) if (temp_lows or temperatures) else None,
        "temperature_high": max(temperatures) if temperatures else None,
        "apparent_low": min(apparent) if apparent else None,
        "apparent_high": max(apparent) if apparent else None,
        "precipitation_probability": max(rain_probs) if rain_probs else None,
        "precipitation": (sum(precipitation) if forecast_type in {"hourly", "twice_daily"} else max(precipitation)) if precipitation else None,
        "humidity": _average(humidity),
        "humidity_low": min(humidity) if humidity else None,
        "humidity_high": max(humidity) if humidity else None,
        "wind_speed": max(wind) if wind else None,
        "wind_gust_speed": max(gust) if gust else None,
        "wind_bearing": strongest_wind_item.get("wind_bearing"),
        "uv_index": max(uv) if uv else None,
        "cloud_coverage": _average(cloud),
        "pressure": _average(pressure),
        "visibility": min(visibility) if visibility else None,
        "periods": periods,
    }


def _native_day_summaries(
    forecasts: Iterable[dict[str, Any]],
    forecast_type: str,
    plan: WeatherQueryPlan,
    reference_time: datetime,
) -> list[tuple[date, dict[str, Any]]]:
    groups: dict[date, list[dict[str, Any]]] = {}
    requested = {
        plan.start_date + timedelta(days=offset)
        for offset in range(plan.day_count)
    }
    for item in forecasts:
        parsed = _forecast_datetime(item.get("datetime"), reference_time.tzinfo)
        if parsed is None or parsed.date() not in requested:
            continue
        groups.setdefault(parsed.date(), []).append(dict(item))
    result: list[tuple[date, dict[str, Any]]] = []
    for target in sorted(requested):
        entries = groups.get(target)
        if entries:
            result.append((target, _aggregate_forecast_day(entries, forecast_type)))
    return result


def _temperature_text(
    low: Any,
    high: Any,
    *,
    unit: str,
    language: str,
) -> str | None:
    low_text = _format_number(low, language=language)
    high_text = _format_number(high, language=language)
    suffix = unit or "°C"
    if low_text is not None and high_text is not None:
        if low_text == high_text:
            return f"{high_text}{suffix}"
        return f"{low_text}{suffix} - {high_text}{suffix}"
    value = high_text or low_text
    return f"{value}{suffix}" if value is not None else None


def _period_summary(
    periods: list[dict[str, Any]],
    *,
    temperature_unit: str,
    language: str,
) -> str | None:
    values: list[str] = []
    for period in periods:
        is_daytime = period.get("is_daytime")
        label = (
            "Day" if language == "en" else "Ban ngày"
        ) if is_daytime is True else (
            "Night" if language == "en" else "Ban đêm"
        ) if is_daytime is False else (
            "Period" if language == "en" else "Thời điểm"
        )
        parts = [_condition_label(period.get("condition"), language=language)]
        temperature = _format_number(period.get("temperature"), language=language)
        if temperature is not None:
            parts.append(f"{temperature}{temperature_unit or '°C'}")
        rain = _format_number(period.get("precipitation_probability"), language=language, digits=0)
        if rain is not None:
            parts.append((f"rain {rain}%" if language == "en" else f"mưa {rain}%"))
        values.append(f"{label}: {', '.join(parts)}")
    return "; ".join(values) if values else None


def format_native_weather_response(
    *,
    forecasts: Iterable[dict[str, Any]],
    forecast_type: str,
    plan: WeatherQueryPlan,
    reference_time: datetime,
    current_state: dict[str, Any] | None,
    entity_name: str,
    units: dict[str, str],
    language: str,
    zalo: bool,
    include_current: bool,
) -> str | None:
    """Format a deterministic Home Assistant weather response."""
    days = _native_day_summaries(
        forecasts, forecast_type, plan, reference_time
    )
    current = dict(current_state or {})
    if not days and not (include_current and current):
        return None

    temp_unit = units.get("temperature", "°C") or "°C"
    wind_unit = units.get("wind_speed", "")
    rain_unit = units.get("precipitation", "")
    pressure_unit = units.get("pressure", "")
    visibility_unit = units.get("visibility", "")
    weekdays = _WEEKDAYS_EN if language == "en" else _WEEKDAYS_VI

    if zalo:
        title = "🌦️ **WEATHER FROM HOME ASSISTANT**" if language == "en" else "🌦️ **THỜI TIẾT TỪ HOME ASSISTANT**"
        lines = [title]
        if entity_name:
            source_label = "Source" if language == "en" else "Nguồn"
            lines.append(f"📍 **{source_label}**: {entity_name}")

        if include_current and current:
            lines.extend(["", "⏱️ **Current conditions**" if language == "en" else "⏱️ **Thời tiết hiện tại**"])
            condition = current.get("condition") or current.get("state")
            if condition:
                lines.append(f"🌤️ **{'Condition' if language == 'en' else 'Điều kiện'}**: {_condition_label(condition, language=language)}")
            temperature = _format_number(current.get("temperature"), language=language)
            apparent = _format_number(current.get("apparent_temperature"), language=language)
            if temperature is not None:
                value = f"{temperature}{temp_unit}"
                if apparent is not None:
                    value += f" ({'feels like' if language == 'en' else 'cảm giác'} {apparent}{temp_unit})"
                lines.append(f"🌡️ **{'Temperature' if language == 'en' else 'Nhiệt độ'}**: {value}")
            humidity = _format_number(current.get("humidity"), language=language, digits=0)
            if humidity is not None:
                lines.append(f"💧 **{'Humidity' if language == 'en' else 'Độ ẩm'}**: {humidity}%")
            wind = _format_number(current.get("wind_speed"), language=language)
            if wind is not None:
                value = f"{wind} {wind_unit}".strip()
                bearing = _bearing_label(current.get("wind_bearing"), language=language)
                if bearing:
                    value += f" • {bearing}"
                lines.append(f"💨 **{'Wind' if language == 'en' else 'Sức gió'}**: {value}")

        for target, summary in days:
            lines.extend(["", f"📅 **{weekdays[target.weekday()]}, {target:%d/%m/%Y}**"])
            lines.append(f"🌤️ **{'Condition' if language == 'en' else 'Điều kiện'}**: {_condition_label(summary.get('condition'), language=language)}")
            temperature = _temperature_text(summary.get("temperature_low"), summary.get("temperature_high"), unit=temp_unit, language=language)
            if temperature:
                apparent = _temperature_text(summary.get("apparent_low"), summary.get("apparent_high"), unit=temp_unit, language=language)
                if apparent:
                    temperature += f" • {'Feels like' if language == 'en' else 'Cảm giác'}: {apparent}"
                lines.append(f"🌡️ **{'Temperature' if language == 'en' else 'Nhiệt độ'}**: {temperature}")
            rain = _format_number(summary.get("precipitation_probability"), language=language, digits=0)
            rainfall = _format_number(summary.get("precipitation"), language=language, digits=2)
            if rain is not None or rainfall is not None:
                parts = []
                if rain is not None:
                    parts.append(f"{rain}%")
                if rainfall is not None:
                    parts.append(f"{'Amount' if language == 'en' else 'Lượng mưa'}: {rainfall} {rain_unit}".strip())
                lines.append(f"🌧️ **{'Precipitation' if language == 'en' else 'Khả năng mưa'}**: {' • '.join(parts)}")
            humidity = _format_number(summary.get("humidity"), language=language, digits=0)
            if humidity is not None:
                low_h = _format_number(summary.get("humidity_low"), language=language, digits=0)
                high_h = _format_number(summary.get("humidity_high"), language=language, digits=0)
                humidity_value = f"{humidity}%"
                if low_h is not None and high_h is not None and low_h != high_h:
                    humidity_value += f" ({low_h}% - {high_h}%)"
                lines.append(f"💧 **{'Humidity' if language == 'en' else 'Độ ẩm'}**: {humidity_value}")
            wind = _format_number(summary.get("wind_speed"), language=language)
            gust = _format_number(summary.get("wind_gust_speed"), language=language)
            if wind is not None or gust is not None:
                parts = []
                if wind is not None:
                    parts.append(f"{wind} {wind_unit}".strip())
                if gust is not None:
                    parts.append(f"{'Gust' if language == 'en' else 'Gió giật'}: {gust} {wind_unit}".strip())
                bearing = _bearing_label(summary.get("wind_bearing"), language=language)
                if bearing:
                    parts.append(bearing)
                lines.append(f"💨 **{'Wind' if language == 'en' else 'Sức gió'}**: {' • '.join(parts)}")
            uv = _format_number(summary.get("uv_index"), language=language)
            cloud = _format_number(summary.get("cloud_coverage"), language=language, digits=0)
            pressure = _format_number(summary.get("pressure"), language=language)
            extras = []
            if uv is not None:
                extras.append(f"UV {uv}")
            if cloud is not None:
                extras.append(f"{'Cloud' if language == 'en' else 'Mây'} {cloud}%")
            if pressure is not None:
                extras.append(f"{'Pressure' if language == 'en' else 'Áp suất'} {pressure} {pressure_unit}".strip())
            if extras:
                lines.append(f"☀️ **{'Additional' if language == 'en' else 'Thông tin thêm'}**: {' • '.join(extras)}")
            period_text = _period_summary(summary.get("periods", []), temperature_unit=temp_unit, language=language)
            if period_text:
                lines.append(f"🌓 **{'Day/night' if language == 'en' else 'Ngày/đêm'}**: {period_text}")
        return "\n".join(lines).strip()

    sentences: list[str] = []
    if entity_name:
        sentences.append((f"Weather data from {entity_name} in Home Assistant." if language == "en" else f"Dữ liệu thời tiết từ {entity_name} trong Home Assistant."))
    if include_current and current:
        current_parts = []
        condition = current.get("condition") or current.get("state")
        if condition:
            current_parts.append(_condition_label(condition, language=language))
        temperature = _format_number(current.get("temperature"), language=language)
        if temperature is not None:
            current_parts.append((f"temperature {temperature}{temp_unit}" if language == "en" else f"nhiệt độ {temperature}{temp_unit}"))
        humidity = _format_number(current.get("humidity"), language=language, digits=0)
        if humidity is not None:
            current_parts.append((f"humidity {humidity}%" if language == "en" else f"độ ẩm {humidity}%"))
        if current_parts:
            sentences.append(("Current conditions: " if language == "en" else "Hiện tại: ") + ", ".join(current_parts) + ".")
    for target, summary in days:
        parts = [_condition_label(summary.get("condition"), language=language)]
        temperature = _temperature_text(summary.get("temperature_low"), summary.get("temperature_high"), unit=temp_unit, language=language)
        if temperature:
            parts.append((f"temperature {temperature}" if language == "en" else f"nhiệt độ {temperature}"))
        rain = _format_number(summary.get("precipitation_probability"), language=language, digits=0)
        if rain is not None:
            parts.append((f"rain chance {rain}%" if language == "en" else f"khả năng mưa {rain}%"))
        humidity = _format_number(summary.get("humidity"), language=language, digits=0)
        if humidity is not None:
            parts.append((f"humidity {humidity}%" if language == "en" else f"độ ẩm {humidity}%"))
        wind = _format_number(summary.get("wind_speed"), language=language)
        if wind is not None:
            parts.append((f"wind {wind} {wind_unit}" if language == "en" else f"gió {wind} {wind_unit}").strip())
        date_label = f"{weekdays[target.weekday()]}, {target:%d/%m/%Y}"
        sentences.append(f"{date_label}: {', '.join(parts)}.")
    return " ".join(sentences).strip() or None
