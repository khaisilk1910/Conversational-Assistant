"""Natural-language lunar/solar date conversion and lookup helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
from typing import Any
import unicodedata

from .targeting import normalize_text

CONVERSION_LUNAR_TO_SOLAR = "lunar_to_solar"
CONVERSION_SOLAR_TO_LUNAR = "solar_to_lunar"
SUPPORTED_CONVERSION_TYPES = {
    CONVERSION_LUNAR_TO_SOLAR,
    CONVERSION_SOLAR_TO_LUNAR,
}

_DATE_NUMERIC_RE = re.compile(
    r"(?<!\d)(?P<day>\d{1,2})\s*[/.-]\s*(?P<month>\d{1,2})"
    r"\s*[/.-]\s*(?P<year>\d{4})(?!\d)"
)
_DATE_NUMERIC_NO_YEAR_RE = re.compile(
    r"(?<!\d)(?P<day>\d{1,2})\s*[/.-]\s*(?P<month>\d{1,2})(?!\s*[/.-]\s*\d)"
)
_DATE_WORD_RE = re.compile(
    r"\b(?:ngay\s+)?(?P<day>\d{1,2})\s+thang\s+(?P<month>\d{1,2})"
    r"\s+nam\s+(?P<year>\d{4})\b"
)
_DATE_ENGLISH_RE = re.compile(
    r"\b(?P<day>\d{1,2})\s+(?:of\s+)?(?P<month>\d{1,2})"
    r"\s+(?P<year>\d{4})\b"
)

_LUNAR_MARKERS = (
    "am lich",
    "lich am",
    "ngay am",
    "lunar",
)
_SOLAR_MARKERS = (
    "duong lich",
    "lich duong",
    "ngay duong",
    "solar",
    "gregorian",
)
_CONVERSION_MARKERS = (
    "doi",
    "chuyen",
    "quy doi",
    "chuyen doi",
    "tra",
    "tra cuu",
    "xem",
    "lay",
    "tim",
    "tinh",
    "tuong ung",
    "sang",
    "qua",
    "thanh",
    "ra",
    "convert",
    "conversion",
    "change",
    "what date",
    "which date",
    "equivalent",
)
_LOOKUP_RELATIVE_MARKERS = (
    "hom nay",
    "ngay mai",
    "ngay kia",
    "ngay kia",
    "hom qua",
    "hom kia",
    "tuan nay",
    "tuan sau",
    "tuan toi",
    "today",
    "tomorrow",
    "day after tomorrow",
    "yesterday",
    "next week",
    "this week",
)
_LOOKUP_DETAIL_MARKERS = (
    "chi tiet",
    "day du",
    "gio hoang dao",
    "gio hac dao",
    "tiet khi",
    "huong xuat hanh",
    "thap nhi truc",
    "nhi thap bat tu",
    "luan giai",
    "tot xau",
    "detail",
    "full information",
)
_WEEKDAY_NAMES = (
    "thu hai",
    "thu ba",
    "thu tu",
    "thu nam",
    "thu sau",
    "thu bay",
    "chu nhat",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
_VI_WEEKDAYS = (
    "Thứ Hai",
    "Thứ Ba",
    "Thứ Tư",
    "Thứ Năm",
    "Thứ Sáu",
    "Thứ Bảy",
    "Chủ Nhật",
)


@dataclass(slots=True, frozen=True)
class LunarDateConversionRequest:
    """A validated conversion request for am_lich_viet_nam.convert_date."""

    conversion_type: str
    day: int
    month: int
    year: int

    def service_data(self) -> dict[str, Any]:
        """Return Home Assistant action data."""
        return {
            "conversion_type": self.conversion_type,
            "day": self.day,
            "month": self.month,
            "year": self.year,
        }


@dataclass(slots=True, frozen=True)
class LunarDateLookupRequest:
    """One natural-language date lookup resolved to a Gregorian date."""

    target_date: date
    reference_label: str
    include_weekday: bool = True
    include_lunar: bool = False
    include_solar: bool = False
    include_details: bool = False

    def service_data(self) -> dict[str, Any]:
        """Return action data; lookups always start from a Gregorian date."""
        return {
            "conversion_type": CONVERSION_SOLAR_TO_LUNAR,
            "day": self.target_date.day,
            "month": self.target_date.month,
            "year": self.target_date.year,
        }


class LunarDateParseError(ValueError):
    """Raised when a conversion or lookup request is invalid or incomplete."""


def _contains_any(text: str, values: tuple[str, ...]) -> bool:
    return any(value in text for value in values)


def _calendar_mentions(text: str) -> tuple[bool, bool]:
    """Return (mentions_lunar, mentions_solar), including bare am/duong tokens."""
    tokens = set(text.split())
    has_lunar = _contains_any(text, _LUNAR_MARKERS) or "am" in tokens
    has_solar = _contains_any(text, _SOLAR_MARKERS) or "duong" in tokens
    return has_lunar, has_solar


def extract_date_parts(text: str) -> tuple[int, int, int] | None:
    """Extract day, month, year from common Vietnamese date expressions."""
    raw = str(text or "")
    match = _DATE_NUMERIC_RE.search(raw)
    if match is None:
        normalized = normalize_text(raw)
        match = _DATE_WORD_RE.search(normalized)
        if match is None:
            match = _DATE_ENGLISH_RE.search(normalized)
    if match is None:
        return None
    return tuple(int(match.group(name)) for name in ("day", "month", "year"))


def is_lunar_date_conversion_request(text: str) -> bool:
    """Return whether text appears to request lunar/solar date conversion."""
    if extract_date_parts(text) is None:
        return False
    normalized = normalize_text(text)
    has_lunar, has_solar = _calendar_mentions(normalized)
    has_conversion = _contains_any(normalized, _CONVERSION_MARKERS)
    if has_lunar and has_solar:
        return True
    return has_conversion and (has_lunar or has_solar) and any(
        word in normalized
        for word in ("ngay", "date", "lich", "calendar")
    )


def _has_lookup_time_reference(text: str) -> bool:
    normalized = normalize_text(text)
    if extract_date_parts(text) is not None:
        return True
    if _DATE_NUMERIC_NO_YEAR_RE.search(str(text or "")):
        return True
    if _contains_any(normalized, _LOOKUP_RELATIVE_MARKERS):
        return True
    if _contains_any(normalized, _WEEKDAY_NAMES):
        return True
    if re.search(r"\bthu\s*[2-7]\b", normalized):
        return True
    if re.search(
        r"\b(?:sau\s+)?\d{1,4}\s*(?:ngay|hom|tuan|thang|nam)\s*"
        r"(?:nua|sau|toi|ke tu hom nay|tinh tu hom nay)?\b",
        normalized,
    ):
        return True
    return False


def is_lunar_date_lookup_request(text: str) -> bool:
    """Return whether text asks for weekday, lunar, or solar date information."""
    normalized = normalize_text(text)
    if not normalized:
        return False
    has_lunar, has_solar = _calendar_mentions(normalized)
    asks_weekday = any(
        phrase in normalized
        for phrase in (
            "thu may",
            "la thu gi",
            "vao thu may",
            "what day of the week",
            "which weekday",
        )
    )
    asks_date = any(
        phrase in normalized
        for phrase in (
            "ngay bao nhieu",
            "la ngay nao",
            "ngay gi",
            "what date",
            "which date",
        )
    )
    asks_calendar = has_lunar or has_solar
    asks_information = asks_weekday or asks_date or asks_calendar
    if not asks_information:
        return False
    if _has_lookup_time_reference(text):
        return True
    return any(
        phrase in normalized
        for phrase in (
            "thu may",
            "am lich bao nhieu",
            "lich am bao nhieu",
            "duong lich bao nhieu",
            "lich duong bao nhieu",
            "ngay am bao nhieu",
            "ngay duong bao nhieu",
        )
    )


def _direction_from_order(normalized: str) -> str | None:
    """Infer direction from the order around connectors such as 'sang'."""
    connectors = (
        " sang ",
        " qua ",
        " thanh ",
        " ra ",
        " la bao nhieu ",
        " to ",
        " into ",
    )
    padded = f" {normalized} "
    for connector in connectors:
        if connector not in padded:
            continue
        left, right = padded.split(connector, 1)
        left_lunar, left_solar = _calendar_mentions(left)
        right_lunar, right_solar = _calendar_mentions(right)
        if left_lunar and right_solar:
            return CONVERSION_LUNAR_TO_SOLAR
        if left_solar and right_lunar:
            return CONVERSION_SOLAR_TO_LUNAR

    reverse_connector = " tuong ung voi "
    if reverse_connector in padded:
        left, right = padded.split(reverse_connector, 1)
        left_lunar, left_solar = _calendar_mentions(left)
        right_lunar, right_solar = _calendar_mentions(right)
        if left_lunar and right_solar:
            return CONVERSION_SOLAR_TO_LUNAR
        if left_solar and right_lunar:
            return CONVERSION_LUNAR_TO_SOLAR
    return None


def infer_conversion_type(text: str) -> str | None:
    """Infer conversion direction from natural Vietnamese or English text."""
    normalized = normalize_text(text)
    ordered = _direction_from_order(normalized)
    if ordered is not None:
        return ordered
    if any(phrase in normalized for phrase in ("am duong", "duong am")):
        return None

    lunar_to_solar_patterns = (
        "am sang duong",
        "am lich sang duong lich",
        "lich am sang lich duong",
        "lunar to solar",
        "lunar to gregorian",
        "ngay duong cua",
        "duong lich cua ngay am",
        "ngay am tuong ung ngay duong nao",
        "ngay am la ngay duong nao",
        "am lich la ngay duong nao",
        "doi ngay am",
        "chuyen ngay am",
        "quy doi ngay am",
    )
    solar_to_lunar_patterns = (
        "duong sang am",
        "duong lich sang am lich",
        "lich duong sang lich am",
        "solar to lunar",
        "gregorian to lunar",
        "ngay am cua",
        "am lich cua ngay duong",
        "ngay duong tuong ung ngay am nao",
        "ngay duong la ngay am nao",
        "duong lich la ngay am nao",
        "doi ngay duong",
        "chuyen ngay duong",
        "quy doi ngay duong",
    )
    if _contains_any(normalized, lunar_to_solar_patterns):
        return CONVERSION_LUNAR_TO_SOLAR
    if _contains_any(normalized, solar_to_lunar_patterns):
        return CONVERSION_SOLAR_TO_LUNAR

    has_lunar, has_solar = _calendar_mentions(normalized)
    asks_lunar_result = any(
        phrase in normalized
        for phrase in (
            "lay ngay am",
            "xem ngay am",
            "tra ngay am",
            "tim ngay am",
            "ngay am cua",
            "am lich cua",
        )
    )
    asks_solar_result = any(
        phrase in normalized
        for phrase in (
            "lay ngay duong",
            "xem ngay duong",
            "tra ngay duong",
            "tim ngay duong",
            "ngay duong cua",
            "duong lich cua",
        )
    )
    if asks_lunar_result and has_solar:
        return CONVERSION_SOLAR_TO_LUNAR
    if asks_solar_result and has_lunar:
        return CONVERSION_LUNAR_TO_SOLAR
    return None


def validate_request(request: LunarDateConversionRequest) -> None:
    """Validate basic date bounds before calling the integration action."""
    if request.conversion_type not in SUPPORTED_CONVERSION_TYPES:
        raise LunarDateParseError("Loại chuyển đổi ngày không hợp lệ.")
    if not 1 <= request.year <= 9999:
        raise LunarDateParseError("Năm phải nằm trong khoảng 1 đến 9999.")
    if request.conversion_type == CONVERSION_SOLAR_TO_LUNAR:
        try:
            date(request.year, request.month, request.day)
        except ValueError as err:
            raise LunarDateParseError(
                f"Ngày dương lịch {request.day}/{request.month}/{request.year} không tồn tại."
            ) from err
        return
    if not 1 <= request.month <= 12 or not 1 <= request.day <= 30:
        raise LunarDateParseError(
            "Ngày âm lịch phải có tháng từ 1 đến 12 và ngày từ 1 đến 30."
        )


def parse_lunar_date_conversion_request(
    text: str,
) -> LunarDateConversionRequest | None:
    """Parse a deterministic conversion request; return None if ambiguous."""
    parts = extract_date_parts(text)
    if parts is None:
        return None
    conversion_type = infer_conversion_type(text)
    if conversion_type is None:
        return None
    request = LunarDateConversionRequest(conversion_type, *parts)
    validate_request(request)
    return request


def _lookup_preferences(text: str) -> tuple[bool, bool, bool, bool]:
    normalized = normalize_text(text)
    has_lunar, has_solar = _calendar_mentions(normalized)
    include_weekday = True
    include_lunar = has_lunar
    include_solar = has_solar
    asks_weekday = any(
        phrase in normalized
        for phrase in ("thu may", "la thu gi", "vao thu may", "weekday")
    )
    if any(
        phrase in normalized
        for phrase in ("ngay bao nhieu", "la ngay nao", "what date", "which date")
    ):
        include_solar = True
    conversion_type = infer_conversion_type(text)
    if conversion_type == CONVERSION_SOLAR_TO_LUNAR:
        include_lunar = True
        include_solar = True
    elif conversion_type == CONVERSION_LUNAR_TO_SOLAR:
        include_solar = True
    if not include_lunar and not include_solar and not asks_weekday:
        include_solar = True
    include_details = _contains_any(normalized, _LOOKUP_DETAIL_MARKERS)
    return include_weekday, include_lunar, include_solar, include_details


def build_lunar_date_lookup_request(
    text: str,
    target_date: date,
    reference_label: str | None = None,
) -> LunarDateLookupRequest:
    """Build a lookup request after a deterministic time resolver found a date."""
    include_weekday, include_lunar, include_solar, include_details = (
        _lookup_preferences(text)
    )
    return LunarDateLookupRequest(
        target_date=target_date,
        reference_label=(reference_label or f"Ngày {target_date.strftime('%d/%m/%Y')}").strip(),
        include_weekday=include_weekday,
        include_lunar=include_lunar,
        include_solar=include_solar,
        include_details=include_details,
    )


def _weekday_from_lookup_text(normalized: str) -> int | None:
    numeric = re.search(r"\bthu\s*(?P<weekday>[2-7])\b", normalized)
    if numeric:
        return int(numeric.group("weekday")) - 2
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


def parse_basic_lunar_date_lookup_request(
    text: str,
    now: datetime,
) -> LunarDateLookupRequest | None:
    """Resolve common relative and explicit time expressions without AI."""
    raw = unicodedata.normalize("NFC", str(text or "").casefold())
    normalized = normalize_text(text)
    today = now.date()

    parts = extract_date_parts(text)
    if parts is not None:
        try:
            target = date(parts[2], parts[1], parts[0])
        except ValueError as err:
            raise LunarDateParseError(
                f"Ngày dương lịch {parts[0]}/{parts[1]}/{parts[2]} không tồn tại."
            ) from err
        return build_lunar_date_lookup_request(text, target)

    no_year = _DATE_NUMERIC_NO_YEAR_RE.search(str(text or ""))
    if no_year:
        day = int(no_year.group("day"))
        month = int(no_year.group("month"))
        try:
            target = date(today.year, month, day)
        except ValueError as err:
            raise LunarDateParseError(
                f"Ngày dương lịch {day}/{month}/{today.year} không tồn tại."
            ) from err
        return build_lunar_date_lookup_request(text, target)

    relative: tuple[int, str] | None = None
    if "hôm nay" in raw or "hom nay" in normalized or "today" in normalized:
        relative = (0, "Hôm nay")
    elif "ngày mai" in raw or "ngay mai" in normalized or "tomorrow" in normalized:
        relative = (1, "Ngày mai")
    elif "ngày kìa" in raw:
        relative = (3, "Ngày kìa")
    elif "day after tomorrow" in normalized or "ngay kia" in normalized:
        relative = (2, "Ngày kia")
    elif "hôm qua" in raw or "hom qua" in normalized or "yesterday" in normalized:
        relative = (-1, "Hôm qua")
    elif "hôm kia" in raw or "hom kia" in normalized:
        relative = (-2, "Hôm kia")
    if relative is not None:
        target = today + timedelta(days=relative[0])
        return build_lunar_date_lookup_request(text, target, relative[1])

    duration = re.search(
        r"\b(?:sau\s+)?(?P<days>\d{1,4})\s*(?:ngay|hom)\s*"
        r"(?:nua|sau|toi|ke tu hom nay|tinh tu hom nay)\b",
        normalized,
    )
    if duration:
        days = int(duration.group("days"))
        if 0 <= days <= 3650:
            target = today + timedelta(days=days)
            return build_lunar_date_lookup_request(
                text, target, f"Sau {days} ngày"
            )

    weekday = _weekday_from_lookup_text(normalized)
    if weekday is not None:
        if any(phrase in normalized for phrase in ("tuan sau", "tuan toi", "next week")):
            next_monday = today + timedelta(days=7 - today.weekday())
            target = next_monday + timedelta(days=weekday)
            label = f"{_VI_WEEKDAYS[weekday]} tuần sau"
        elif any(phrase in normalized for phrase in ("tuan nay", "this week")):
            this_monday = today - timedelta(days=today.weekday())
            target = this_monday + timedelta(days=weekday)
            label = f"{_VI_WEEKDAYS[weekday]} tuần này"
        else:
            target = today + timedelta(days=(weekday - today.weekday()) % 7)
            label = _VI_WEEKDAYS[weekday]
        return build_lunar_date_lookup_request(text, target, label)
    return None


def request_from_ai_payload(payload: Any) -> LunarDateConversionRequest | None:
    """Build and validate a conversion request from a strict AI JSON object."""
    if not isinstance(payload, dict) or payload.get("error"):
        return None
    try:
        request = LunarDateConversionRequest(
            conversion_type=str(payload.get("conversion_type", "")).strip(),
            day=int(payload.get("day")),
            month=int(payload.get("month")),
            year=int(payload.get("year")),
        )
        validate_request(request)
    except (LunarDateParseError, TypeError, ValueError):
        return None
    return request


def lookup_request_from_ai_payload(
    payload: Any,
    original_text: str,
) -> LunarDateLookupRequest | None:
    """Build and validate a date lookup request from strict AI JSON."""
    if not isinstance(payload, dict) or payload.get("error"):
        return None
    try:
        target = date(
            int(payload.get("year")),
            int(payload.get("month")),
            int(payload.get("day")),
        )
    except (TypeError, ValueError):
        return None
    label = str(payload.get("reference_label", "") or "").strip()
    request = build_lunar_date_lookup_request(original_text, target, label or None)
    fields = payload.get("fields")
    if not isinstance(fields, list):
        return request
    normalized_fields = {normalize_text(str(field)) for field in fields}
    return LunarDateLookupRequest(
        target_date=request.target_date,
        reference_label=request.reference_label,
        include_weekday=True,
        include_lunar=(
            request.include_lunar
            or bool(normalized_fields & {"lunar", "am lich", "ngay am"})
        ),
        include_solar=(
            request.include_solar
            or bool(normalized_fields & {"solar", "duong lich", "ngay duong"})
        ),
        include_details=(
            request.include_details
            or bool(normalized_fields & {"details", "detail", "chi tiet", "day du"})
        ),
    )


def unwrap_action_response(value: Any) -> dict[str, Any] | None:
    """Find the conversion payload inside common HA service response wrappers."""
    if not isinstance(value, dict):
        return None
    if any(
        key in value
        for key in (
            "error",
            "thu",
            "ngay_am_lich",
            "ngay_duong_lich",
            "ngay_duong_thang_thuong",
            "ngay_duong_thang_nhuan",
        )
    ):
        return value
    for key in ("response", "result", "data", "service_response"):
        nested = unwrap_action_response(value.get(key))
        if nested is not None:
            return nested
    for nested_value in value.values():
        nested = unwrap_action_response(nested_value)
        if nested is not None:
            return nested
    return None


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _append_detail(
    lines: list[str],
    icon: str,
    label: str,
    value: Any,
    *,
    zalo: bool,
) -> None:
    text = _clean(value)
    if not text:
        return
    if zalo:
        lines.append(f"• {icon} **{label}:** {text}")
    elif label == "Thứ":
        lines.append(f"Ngày tra cứu là {text}")
    else:
        lines.append(f"{label}: {text}")


def _heading(text: str, icon: str, *, zalo: bool) -> str:
    return f"{icon} **{text}**" if zalo else text


def _weekday_value(payload: dict[str, Any], target_date: date | None = None) -> str:
    weekday = _clean(payload.get("thu"))
    if weekday:
        return weekday
    if target_date is not None:
        return _VI_WEEKDAYS[target_date.weekday()]
    return ""


def format_lunar_date_conversion_response(
    payload: dict[str, Any],
    request: LunarDateConversionRequest,
    *,
    zalo: bool = True,
) -> str:
    """Format the complete action response with rich Zalo presentation."""
    error = _clean(payload.get("error"))
    if error:
        if zalo:
            return (
                "⚠️ **KHÔNG THỂ CHUYỂN ĐỔI NGÀY**\n\n"
                f"• ❌ {error}\n"
                "• 💡 Ví dụ: `Đổi ngày 30/11/1984 dương lịch sang âm lịch` "
                "hoặc `Đổi ngày 29/11/1984 âm lịch sang dương lịch`."
            )
        return f"Không thể chuyển đổi ngày. {error}"

    if request.conversion_type == CONVERSION_LUNAR_TO_SOLAR:
        title = _heading(
            "KẾT QUẢ ĐỔI ÂM LỊCH SANG DƯƠNG LỊCH", "🌙➡️☀️", zalo=zalo
        )
    else:
        title = _heading(
            "KẾT QUẢ ĐỔI DƯƠNG LỊCH SANG ÂM LỊCH", "☀️➡️🌙", zalo=zalo
        )
    lines = [title, ""]
    _append_detail(lines, "📅", "Thứ", payload.get("thu"), zalo=zalo)
    _append_detail(lines, "☀️", "Ngày dương lịch", payload.get("ngay_duong_lich"), zalo=zalo)
    _append_detail(lines, "🌙", "Ngày âm lịch", payload.get("ngay_am_lich"), zalo=zalo)
    _append_detail(lines, "🐉", "Năm Can Chi", payload.get("nam_can_chi"), zalo=zalo)
    converted_parts = [payload.get(key) for key in ("ngay", "thang", "nam")]
    if all(value is not None and _clean(value) for value in converted_parts):
        _append_detail(
            lines,
            "🔢",
            "Giá trị ngày/tháng/năm trả về",
            "/".join(_clean(value) for value in converted_parts),
            zalo=zalo,
        )

    regular_solar = _clean(payload.get("ngay_duong_thang_thuong"))
    leap_solar = _clean(payload.get("ngay_duong_thang_nhuan"))
    if regular_solar or leap_solar:
        lines.extend(["", _heading("KẾT QUẢ THÁNG THƯỜNG / THÁNG NHUẬN", "🌗", zalo=zalo)])
        _append_detail(lines, "🌞", "Tháng thường", regular_solar, zalo=zalo)
        _append_detail(lines, "🌘", "Tháng nhuận", leap_solar, zalo=zalo)

    details = payload.get("details")
    if isinstance(details, dict):
        lines.extend(["", _heading("THÔNG TIN CHI TIẾT", "📚", zalo=zalo)])
        _append_detail(lines, "🔢", "Ngày âm trong tháng", details.get("lunar_day"), zalo=zalo)
        _append_detail(lines, "🌙", "Tên tháng âm", details.get("month_name"), zalo=zalo)
        _append_detail(lines, "📆", "Ngày Can Chi", details.get("can_chi_day"), zalo=zalo)
        _append_detail(lines, "🗓️", "Tháng Can Chi", details.get("can_chi_month"), zalo=zalo)
        _append_detail(lines, "🐲", "Năm Can Chi", details.get("can_chi_year"), zalo=zalo)
        _append_detail(lines, "🌿", "Tiết khí", details.get("tiet_khi"), zalo=zalo)
        _append_detail(lines, "🟢", "Giờ hoàng đạo", details.get("gio_hoang_dao"), zalo=zalo)
        _append_detail(lines, "⚫", "Giờ hắc đạo", details.get("gio_hac_dao"), zalo=zalo)

        directions = details.get("huong_xuat_hanh")
        if isinstance(directions, dict) and directions:
            lines.extend(["", _heading("HƯỚNG XUẤT HÀNH", "🧭", zalo=zalo)])
            direction_icons = {
                "Hỷ Thần": "🎉",
                "Tài Thần": "💰",
                "Hạc Thần": "🕊️",
            }
            for label, value in directions.items():
                _append_detail(
                    lines,
                    direction_icons.get(str(label), "📍"),
                    str(label),
                    value,
                    zalo=zalo,
                )

        twelve = details.get("thap_nhi_truc")
        if isinstance(twelve, dict):
            name = _clean(twelve.get("name"))
            if name:
                lines.extend(["", _heading(f"THẬP NHỊ TRỰC: {name}", "🏗️", zalo=zalo)])
            twelve_details = twelve.get("details")
            if isinstance(twelve_details, dict):
                _append_detail(lines, "✅", "Nên làm", twelve_details.get("tot"), zalo=zalo)
                _append_detail(lines, "⛔", "Kiêng làm", twelve_details.get("xau"), zalo=zalo)

        stars = details.get("nhi_thap_bat_tu")
        if isinstance(stars, dict):
            name = _clean(stars.get("name"))
            star_details = stars.get("details")
            full_name = _clean(star_details.get("tenNgay")) if isinstance(star_details, dict) else ""
            heading = " - ".join(item for item in (name, full_name) if item)
            if heading:
                lines.extend(["", _heading(f"NHỊ THẬP BÁT TÚ: {heading}", "⭐", zalo=zalo)])
            if isinstance(star_details, dict):
                _append_detail(lines, "📊", "Đánh giá", star_details.get("danhGia"), zalo=zalo)
                _append_detail(lines, "✅", "Nên làm", star_details.get("nenLam"), zalo=zalo)
                _append_detail(lines, "⛔", "Kiêng cữ", star_details.get("kiengCu"), zalo=zalo)

        description = _clean(details.get("ngay_mo_ta"))
        day_details = details.get("ngay_chi_tiet")
        if description or isinstance(day_details, list):
            lines.extend(["", _heading("LUẬN GIẢI NGÀY", "📖", zalo=zalo)])
            _append_detail(lines, "📝", "Mô tả", description, zalo=zalo)
            if isinstance(day_details, list):
                for item in day_details:
                    text = _clean(item).lstrip("-• ")
                    if text:
                        lines.append(f"• 🔎 {text}" if zalo else text)

    leap_notice = _clean(payload.get("thong_bao_nhuan"))
    if leap_notice:
        lines.extend(["", _heading("THÔNG TIN THÁNG NHUẬN", "🌗", zalo=zalo)])
        _append_detail(lines, "ℹ️", "Thông báo", leap_notice, zalo=zalo)

    meaningful = [line for line in lines[1:] if line.strip()]
    if not meaningful:
        return (
            "⚠️ **KẾT QUẢ CHUYỂN ĐỔI KHÔNG HỢP LỆ**\n\n"
            "• Action không trả về các trường ngày âm/dương cần thiết."
            if zalo
            else "Kết quả chuyển đổi không hợp lệ. Action không trả về dữ liệu ngày âm dương cần thiết."
        )
    return "\n".join(lines).strip()


def format_lunar_date_lookup_response(
    payload: dict[str, Any],
    request: LunarDateLookupRequest,
    *,
    zalo: bool = True,
) -> str:
    """Format a natural-language day lookup, returning only useful fields."""
    error = _clean(payload.get("error"))
    if error:
        if zalo:
            return (
                "⚠️ **KHÔNG THỂ TRA CỨU NGÀY**\n\n"
                f"• ❌ {error}\n"
                "• 💡 Hãy nói rõ mốc thời gian, ví dụ: `ngày mai âm lịch bao nhiêu`."
            )
        return f"Không thể tra cứu ngày. {error}"

    if not zalo and not request.include_details:
        weekday = _weekday_value(payload, request.target_date)
        parts = [f"{request.reference_label} là {weekday}"]
        if request.include_solar:
            solar = (
                _clean(payload.get("ngay_duong_lich"))
                or f"{request.target_date.day}/{request.target_date.month}/{request.target_date.year}"
            )
            parts.append(f"ngày dương lịch {solar}")
        if request.include_lunar:
            lunar = _clean(payload.get("ngay_am_lich"))
            if lunar:
                parts.append(f"ngày âm lịch {lunar}")
        return ". ".join(part for part in parts if part).strip()

    if request.include_details:
        conversion = LunarDateConversionRequest(
            CONVERSION_SOLAR_TO_LUNAR,
            request.target_date.day,
            request.target_date.month,
            request.target_date.year,
        )
        detailed = format_lunar_date_conversion_response(
            payload, conversion, zalo=zalo
        )
        if zalo:
            first_break = detailed.find("\n")
            body = detailed[first_break + 1 :].lstrip() if first_break >= 0 else detailed
            return (
                "📅 **KẾT QUẢ TRA CỨU NGÀY**\n\n"
                f"• ⏳ **Mốc yêu cầu:** {request.reference_label}\n"
                f"{body}"
            ).strip()
        return f"Mốc yêu cầu {request.reference_label}. {detailed}"

    lines = [_heading("KẾT QUẢ TRA CỨU NGÀY", "📅", zalo=zalo), ""]
    _append_detail(lines, "⏳", "Mốc yêu cầu", request.reference_label, zalo=zalo)
    weekday = _weekday_value(payload, request.target_date)
    if request.include_weekday:
        _append_detail(lines, "📌", "Thứ", weekday, zalo=zalo)
    if request.include_solar:
        solar = _clean(payload.get("ngay_duong_lich")) or f"{request.target_date.day}/{request.target_date.month}/{request.target_date.year}"
        _append_detail(lines, "☀️", "Ngày dương lịch", solar, zalo=zalo)
    if request.include_lunar:
        _append_detail(lines, "🌙", "Ngày âm lịch", payload.get("ngay_am_lich"), zalo=zalo)
    return "\n".join(lines).strip()


def conversion_usage_error() -> str:
    """Return a friendly retry prompt for incomplete conversion requests."""
    return (
        "🤔 **Tôi chưa xác định được chiều chuyển đổi ngày.**\n\n"
        "Hãy nêu đủ **ngày**, **loại lịch nguồn** và **loại lịch đích**.\n"
        "• `Đổi ngày 30/11/1984 dương lịch sang âm lịch`\n"
        "• `Đổi ngày 29/11/1984 âm lịch sang dương lịch`\n"
        "• `Lấy ngày âm của 30-11-1984 dương lịch`"
    )


def lookup_usage_error() -> str:
    """Return a friendly retry prompt when no requested time can be resolved."""
    return (
        "🤔 **Tôi chưa xác định được mốc thời gian cần tra cứu.**\n\n"
        "• Hãy nói rõ mốc như `hôm nay`, `ngày mai`, `ngày kia`, "
        "`thứ 3 tuần sau` hoặc `10 ngày nữa`.\n"
        "• Ví dụ: `Ngày mai âm lịch bao nhiêu` hoặc `Thứ 3 tuần sau là thứ mấy`."
    )
