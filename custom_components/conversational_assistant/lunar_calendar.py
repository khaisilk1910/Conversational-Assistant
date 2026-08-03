"""Natural-language lunar/solar date conversion helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from typing import Any

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


class LunarDateParseError(ValueError):
    """Raised when a conversion request is invalid or incomplete."""


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

    # In "ngày âm tương ứng với ... dương lịch", the requested target is on
    # the left and the source calendar is on the right, so the order is reversed.
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

    # When only one source calendar is stated, common requests such as
    # "lấy ngày âm của 30/11/1984 dương lịch" still have an unambiguous target.
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


def request_from_ai_payload(payload: Any) -> LunarDateConversionRequest | None:
    """Build and validate a request from a strict AI JSON object."""
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


def unwrap_action_response(value: Any) -> dict[str, Any] | None:
    """Find the conversion payload inside common HA service response wrappers."""
    if not isinstance(value, dict):
        return None
    if any(
        key in value
        for key in (
            "error",
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


def _append_detail(lines: list[str], icon: str, label: str, value: Any) -> None:
    text = _clean(value)
    if text:
        lines.append(f"{icon} **{label}:** {text}")


def format_lunar_date_conversion_response(
    payload: dict[str, Any],
    request: LunarDateConversionRequest,
) -> str:
    """Format the complete action response for both Zalo and Voice Assist."""
    error = _clean(payload.get("error"))
    if error:
        return (
            "⚠️ **KHÔNG THỂ CHUYỂN ĐỔI NGÀY**\n\n"
            f"❌ {error}\n\n"
            "💡 Ví dụ hợp lệ: `Đổi ngày 30/11/1984 dương lịch sang âm lịch` "
            "hoặc `Đổi ngày 29/11/1984 âm lịch sang dương lịch`."
        )

    title = (
        "🌙➡️☀️ **KẾT QUẢ ĐỔI ÂM LỊCH SANG DƯƠNG LỊCH**"
        if request.conversion_type == CONVERSION_LUNAR_TO_SOLAR
        else "☀️➡️🌙 **KẾT QUẢ ĐỔI DƯƠNG LỊCH SANG ÂM LỊCH**"
    )
    lines = [title, ""]
    _append_detail(lines, "☀️", "Ngày dương lịch", payload.get("ngay_duong_lich"))
    _append_detail(lines, "🌙", "Ngày âm lịch", payload.get("ngay_am_lich"))
    _append_detail(lines, "🐉", "Năm Can Chi", payload.get("nam_can_chi"))
    converted_parts = [payload.get(key) for key in ("ngay", "thang", "nam")]
    if all(value is not None and _clean(value) for value in converted_parts):
        lines.append(
            "🔢 **Giá trị ngày/tháng/năm trả về:** "
            + "/".join(_clean(value) for value in converted_parts)
        )

    regular_solar = _clean(payload.get("ngay_duong_thang_thuong"))
    leap_solar = _clean(payload.get("ngay_duong_thang_nhuan"))
    if regular_solar or leap_solar:
        lines.extend(["", "🌗 **KẾT QUẢ THÁNG THƯỜNG / THÁNG NHUẬN**"])
        if regular_solar:
            lines.append(f"🌞 **Tháng thường:** {regular_solar}")
        if leap_solar:
            lines.append(f"🌘 **Tháng nhuận:** {leap_solar}")

    details = payload.get("details")
    if isinstance(details, dict):
        lines.extend(["", "📚 **THÔNG TIN CHI TIẾT**"])
        _append_detail(lines, "🔢", "Ngày âm trong tháng", details.get("lunar_day"))
        _append_detail(lines, "🌙", "Tên tháng âm", details.get("month_name"))
        _append_detail(lines, "📆", "Ngày Can Chi", details.get("can_chi_day"))
        _append_detail(lines, "🗓️", "Tháng Can Chi", details.get("can_chi_month"))
        _append_detail(lines, "🐲", "Năm Can Chi", details.get("can_chi_year"))
        _append_detail(lines, "🌿", "Tiết khí", details.get("tiet_khi"))
        _append_detail(lines, "🟢", "Giờ hoàng đạo", details.get("gio_hoang_dao"))
        _append_detail(lines, "⚫", "Giờ hắc đạo", details.get("gio_hac_dao"))

        directions = details.get("huong_xuat_hanh")
        if isinstance(directions, dict) and directions:
            lines.extend(["", "🧭 **HƯỚNG XUẤT HÀNH**"])
            direction_icons = {
                "Hỷ Thần": "🎉",
                "Tài Thần": "💰",
                "Hạc Thần": "🕊️",
            }
            for label, value in directions.items():
                text = _clean(value)
                if text:
                    lines.append(
                        f"{direction_icons.get(str(label), '📍')} **{label}:** {text}"
                    )

        twelve = details.get("thap_nhi_truc")
        if isinstance(twelve, dict):
            name = _clean(twelve.get("name"))
            if name:
                lines.extend(["", f"🏗️ **THẬP NHỊ TRỰC: {name}**"])
            twelve_details = twelve.get("details")
            if isinstance(twelve_details, dict):
                _append_detail(lines, "✅", "Nên làm", twelve_details.get("tot"))
                _append_detail(lines, "⛔", "Kiêng làm", twelve_details.get("xau"))

        stars = details.get("nhi_thap_bat_tu")
        if isinstance(stars, dict):
            name = _clean(stars.get("name"))
            star_details = stars.get("details")
            full_name = ""
            if isinstance(star_details, dict):
                full_name = _clean(star_details.get("tenNgay"))
            heading = " - ".join(item for item in (name, full_name) if item)
            if heading:
                lines.extend(["", f"⭐ **NHỊ THẬP BÁT TÚ: {heading}**"])
            if isinstance(star_details, dict):
                _append_detail(lines, "📊", "Đánh giá", star_details.get("danhGia"))
                _append_detail(lines, "✅", "Nên làm", star_details.get("nenLam"))
                _append_detail(lines, "⛔", "Kiêng cữ", star_details.get("kiengCu"))

        description = _clean(details.get("ngay_mo_ta"))
        day_details = details.get("ngay_chi_tiet")
        if description or isinstance(day_details, list):
            lines.extend(["", "📖 **LUẬN GIẢI NGÀY**"])
            if description:
                lines.append(f"📝 {description}")
            if isinstance(day_details, list):
                for item in day_details:
                    text = _clean(item).lstrip("-• ")
                    if text:
                        lines.append(f"🔎 {text}")

    leap_notice = _clean(payload.get("thong_bao_nhuan"))
    if leap_notice:
        lines.extend(["", f"🌗 **Thông tin tháng nhuận:** {leap_notice}"])

    if len(lines) <= 2:
        return (
            "⚠️ **KẾT QUẢ CHUYỂN ĐỔI KHÔNG HỢP LỆ**\n\n"
            "Action không trả về các trường ngày âm/dương cần thiết. "
            "Hãy kiểm tra nhật ký Home Assistant."
        )
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
