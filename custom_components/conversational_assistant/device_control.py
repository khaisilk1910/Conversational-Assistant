"""Safe, capability-aware Home Assistant device control for Zalo and Voice Assist."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from math import isfinite
import re
from typing import Any, Iterable, Mapping

from .targeting import normalize_text, parse_target_selection

# Domains with conventional turn_on/turn_off semantics. The manager still
# checks the live service registry and Assist exposure before presenting or
# executing a target.
POWER_CONTROL_DOMAINS = frozenset(
    {
        "automation",
        "climate",
        "cover",
        "fan",
        "humidifier",
        "input_boolean",
        "light",
        "media_player",
        "remote",
        "script",
        "siren",
        "switch",
        "vacuum",
        "water_heater",
    }
)

POWER_CONTROL_ACTIONS = frozenset(
    {"turn_on", "turn_off", "open_cover", "close_cover"}
)
CLIMATE_CONTROL_ACTIONS = frozenset(
    {
        "climate_set_temperature",
        "climate_set_temperature_range",
        "climate_increase_temperature",
        "climate_decrease_temperature",
        "climate_set_hvac_mode",
        "climate_set_fan_mode",
        "climate_increase_fan_mode",
        "climate_decrease_fan_mode",
        "climate_set_swing_mode",
        "climate_set_swing_horizontal_mode",
        "climate_set_preset_mode",
        "climate_set_humidity",
    }
)
FAN_CONTROL_ACTIONS = frozenset(
    {
        "fan_set_percentage",
        "fan_increase_speed",
        "fan_decrease_speed",
        "fan_oscillate",
        "fan_set_direction",
        "fan_set_preset_mode",
    }
)
CONTROL_ACTIONS = POWER_CONTROL_ACTIONS | CLIMATE_CONTROL_ACTIONS | FAN_CONTROL_ACTIONS

_ROLLING_DOOR_CUES = (
    "cua cuon",
    "cua gara",
    "cua garage",
    "cua nha xe",
    "garage door",
    "rolling door",
    "roller door",
)

_CLIMATE_CUES = (
    "dieu hoa",
    "may lanh",
    "may dieu hoa",
    "climate",
    "air conditioner",
    "air conditioning",
    "thermostat",
)
_FAN_CUES = ("quat", "fan")
_DEVICE_CUES = (
    *_CLIMATE_CUES,
    *_FAN_CUES,
    "den",
    "light",
    "lamp",
    "cong tac",
    "switch",
    "o cam",
    "plug",
    "rem",
    "curtain",
    "cover",
    "cua cuon",
    "cua gara",
    "garage door",
    "loa",
    "speaker",
    "tivi",
    "tv",
    "robot",
    "hut bui",
    "vacuum",
    "tao am",
    "humidifier",
    "binh nong lanh",
    "water heater",
    "thiet bi",
    "device",
)

_POLITE_PREFIXES = (
    "hãy ",
    "hay ",
    "bạn hãy ",
    "ban hay ",
    "vui lòng ",
    "vui long ",
    "làm ơn ",
    "lam on ",
    "giúp tôi ",
    "giup toi ",
    "cho tôi ",
    "cho toi ",
    "tôi muốn ",
    "toi muon ",
    "please ",
    "can you ",
    "could you ",
    "i want to ",
)

_NON_ACTION_PREFIXES = (
    "bat dau",
    "bat mi",
    "bat ngo",
    "bat ky",
    "bat cu",
    "bat chap",
    "bat buoc",
    "bat dong san",
    "bat an",
    "bat loi",
    "bat luc",
    "bat tien",
    "bat thuong",
    "bat hop",
    "batman",
    "batch",
    "battery",
    "battle",
    "mo khoa",
    "mo nhac",
    "mo video",
    "mo ung dung",
    "dong ung dung",
    "tat ca",
    "tat nhien",
    "tat yeu",
)

_RAW_NON_POWER_PREFIXES = (
    "bật mí",
    "bật nhạc",
    "tắt nhạc",
    "bật tiếng",
    "tắt tiếng",
    "bật âm thanh",
    "tắt âm thanh",
    "bật video",
    "tắt video",
    "mở khóa",
    "mở khoá",
    "mở nhạc",
    "mở video",
    "mở ứng dụng",
    "đóng ứng dụng",
)

_ASCII_JOINED_DEVICE_CUES = (
    "den",
    "quat",
    "may",
    "loa",
    "tivi",
    "tv",
    "dieuhoa",
    "maylanh",
    "robot",
    "rem",
    "congtac",
    "ocam",
    "camera",
    "cam",
    "binhnonglanh",
    "taoam",
    "hutbui",
    "cuacuon",
    "cuagara",
    "garagedoor",
    "rollingdoor",
    "cong",
)

_NUMBER_WORDS: dict[str, float] = {
    "mot": 1,
    "một": 1,
    "hai": 2,
    "ba": 3,
    "bon": 4,
    "bốn": 4,
    "tu": 4,
    "tư": 4,
    "nam": 5,
    "năm": 5,
    "sau": 6,
    "sáu": 6,
    "bay": 7,
    "bảy": 7,
    "tam": 8,
    "tám": 8,
    "chin": 9,
    "chín": 9,
    "muoi": 10,
    "mười": 10,
    "nua": 0.5,
    "nửa": 0.5,
}

_HVAC_ALIASES: dict[str, tuple[str, ...]] = {
    "off": ("off", "tat", "dung"),
    "heat": ("heat", "suoi", "suoi am", "lam am"),
    "cool": ("cool", "lam lanh", "lam mat", "mat", "lanh"),
    "heat_cool": ("heat cool", "nong lanh", "suoi va lam lanh"),
    "auto": ("auto", "tu dong", "automatic"),
    "dry": ("dry", "hut am", "lam kho", "khu am"),
    "fan_only": ("fan only", "chi quat", "quat gio", "thong gio"),
}
_MODE_ALIASES: dict[str, tuple[str, ...]] = {
    "off": ("off", "tat", "dung"),
    "on": ("on", "bat"),
    "auto": ("auto", "tu dong", "automatic"),
    "low": ("low", "thap", "nhe", "cham"),
    "medium": ("medium", "mid", "trung binh", "vua"),
    "high": ("high", "cao", "manh", "nhanh"),
    "top": ("top", "toi da", "max", "maximum"),
    "turbo": ("turbo", "tang cuong", "cuc manh"),
    "quiet": ("quiet", "silent", "yen tinh", "im lang"),
    "sleep": ("sleep", "ngu", "ban dem"),
    "eco": ("eco", "tiet kiem", "tiet kiem dien"),
    "boost": ("boost", "tang cuong"),
    "comfort": ("comfort", "de chiu"),
    "away": ("away", "vang nha"),
    "home": ("home", "o nha"),
    "both": ("both", "ca hai", "ngang va doc"),
    "vertical": ("vertical", "doc", "len xuong"),
    "horizontal": ("horizontal", "ngang", "trai phai"),
    "forward": ("forward", "xuoi", "thuan", "cung chieu"),
    "reverse": ("reverse", "nguoc", "dao chieu", "nguoc chieu"),
}


@dataclass(slots=True, frozen=True)
class DevicePowerTarget:
    """One exposed Home Assistant entity supported by integration device control."""

    entity_id: str
    display_name: str
    domain: str
    aliases: tuple[str, ...]
    supports_turn_on: bool
    supports_turn_off: bool
    supports_open_cover: bool = False
    supports_close_cover: bool = False
    area_name: str = ""
    device_class: str = ""
    supported_actions: tuple[str, ...] = ()
    hvac_modes: tuple[str, ...] = ()
    fan_modes: tuple[str, ...] = ()
    swing_modes: tuple[str, ...] = ()
    swing_horizontal_modes: tuple[str, ...] = ()
    preset_modes: tuple[str, ...] = ()
    min_temp: float | None = None
    max_temp: float | None = None
    target_temp_step: float | None = None
    target_temperature: float | None = None
    temperature_unit: str = "°C"
    target_temp_low: float | None = None
    target_temp_high: float | None = None
    current_temperature: float | None = None
    min_humidity: float | None = None
    max_humidity: float | None = None
    target_humidity_step: float | None = None
    target_humidity: float | None = None
    percentage: int | None = None
    percentage_step: float | None = None
    current_hvac_mode: str = ""
    current_fan_mode: str = ""
    current_swing_mode: str = ""
    current_swing_horizontal_mode: str = ""
    current_preset_mode: str = ""
    current_direction: str = ""
    current_oscillating: bool | None = None

    def supports(self, action: str) -> bool:
        """Return whether this entity supports the requested action."""
        if action == "turn_on":
            return self.supports_turn_on or (
                is_rolling_door_target(self) and self.supports_open_cover
            )
        if action == "turn_off":
            return self.supports_turn_off or (
                is_rolling_door_target(self) and self.supports_close_cover
            )
        if action == "open_cover":
            return self.supports_open_cover or (
                is_rolling_door_target(self) and self.supports_turn_on
            )
        if action == "close_cover":
            return self.supports_close_cover or (
                is_rolling_door_target(self) and self.supports_turn_off
            )
        return action in self.supported_actions


@dataclass(slots=True)
class DeviceControlInterpretation:
    """Validated interpretation of one integration device-control request."""

    action: str
    targets: tuple[DevicePowerTarget, ...]
    parameters: dict[str, Any] = field(default_factory=dict)
    scheduled_for: datetime | None = None
    confidence: float = 1.0
    target_domain: str = ""


# Compatibility alias retained for older manager code and external imports.
DevicePowerInterpretation = DeviceControlInterpretation


def _float_or_none(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(
        text
        for item in value
        if (text := str(item or "").strip())
    )


def is_rolling_door_target(target: DevicePowerTarget) -> bool:
    """Return whether a target represents a rolling/garage-style door."""
    device_class = normalize_text(target.device_class)
    if device_class == "garage":
        return True

    searchable = normalize_text(
        " ".join((target.display_name, target.area_name, *target.aliases))
    )
    return any(cue in searchable for cue in _ROLLING_DOOR_CUES)


def rolling_door_open_request_hint(text: str) -> bool:
    """Return whether text explicitly asks to open a rolling-style door."""
    action = explicit_power_action(text)
    if action not in {"open_cover", "turn_on"}:
        return False
    normalized = normalize_text(text)
    return any(cue in normalized for cue in _ROLLING_DOOR_CUES) or bool(
        re.search(r"\b(?:gara|garage)\b", normalized)
    )


def explicit_power_action(text: str) -> str | None:
    """Extract a clear leading power action, including joined-word input."""
    raw = str(text or "").strip().casefold()
    while raw:
        for prefix in _POLITE_PREFIXES:
            if raw.startswith(prefix):
                raw = raw[len(prefix) :].lstrip()
                break
        else:
            break
    normalized = normalize_text(raw)
    if not normalized:
        return None

    negative_prefixes = (
        "khong bat",
        "khong tat",
        "khong mo",
        "khong dong",
        "dung bat",
        "dung tat",
        "dung mo",
        "dung dong",
        "do not turn on",
        "do not turn off",
        "do not open",
        "do not close",
        "dont turn on",
        "dont turn off",
        "dont open",
        "dont close",
    )
    if normalized.startswith(negative_prefixes):
        return None

    if raw.startswith(("bắt", "bất")) or raw.startswith("tất"):
        return None
    if raw.startswith(_RAW_NON_POWER_PREFIXES):
        return None
    if raw.startswith("bật") and len(raw) > len("bật"):
        return "turn_on"
    if raw.startswith("tắt") and len(raw) > len("tắt"):
        return "turn_off"
    if raw.startswith("mở") and len(raw) > len("mở"):
        return "open_cover"
    if raw.startswith("đóng") and len(raw) > len("đóng"):
        return "close_cover"

    if normalized.startswith(_NON_ACTION_PREFIXES):
        return None

    exact_on = (
        "bat ",
        "bat len ",
        "kich hoat ",
        "turn on ",
        "switch on ",
        "power on ",
        "activate ",
    )
    exact_off = (
        "tat ",
        "tat di ",
        "vo hieu hoa ",
        "turn off ",
        "switch off ",
        "power off ",
        "deactivate ",
    )
    exact_open = ("mo ", "open ")
    exact_close = ("dong ", "close ")
    if normalized.startswith(exact_on):
        return "turn_on"
    if normalized.startswith(exact_off):
        return "turn_off"
    if normalized.startswith(exact_open):
        return "open_cover"
    if normalized.startswith(exact_close):
        return "close_cover"

    if re.match(r"^(?:turn|switch|power)\s+.+\s+on(?:\s+please)?$", normalized):
        return "turn_on"
    if re.match(r"^(?:turn|switch|power)\s+.+\s+off(?:\s+please)?$", normalized):
        return "turn_off"
    if re.match(r"^open\s+.+(?:\s+please)?$", normalized):
        return "open_cover"
    if re.match(r"^close\s+.+(?:\s+please)?$", normalized):
        return "close_cover"

    compact = normalized.replace(" ", "")
    if re.match(r"^(?:kichhoat)(?=.+)", compact):
        return "turn_on"
    if re.match(r"^(?:vohieuhoa)(?=.+)", compact):
        return "turn_off"
    if re.match(r"^(?:turnon|switchon|poweron|activate)(?=.+)", compact):
        return "turn_on"
    if re.match(r"^(?:turnoff|switchoff|poweroff|deactivate)(?=.+)", compact):
        return "turn_off"
    if re.match(r"^(?:open)(?=.+)", compact):
        return "open_cover"
    if re.match(r"^(?:close)(?=.+)", compact):
        return "close_cover"

    on_match = re.match(r"^ba+t+(?P<target>.+)", compact)
    if on_match and on_match.group("target").startswith(_ASCII_JOINED_DEVICE_CUES):
        return "turn_on"
    off_match = re.match(r"^ta+t+(?P<target>.+)", compact)
    if off_match and off_match.group("target").startswith(_ASCII_JOINED_DEVICE_CUES):
        return "turn_off"
    open_match = re.match(r"^mo+(?P<target>.+)", compact)
    if open_match and open_match.group("target").startswith(_ASCII_JOINED_DEVICE_CUES):
        return "open_cover"
    close_match = re.match(r"^dong(?P<target>.+)", compact)
    if close_match and close_match.group("target").startswith(_ASCII_JOINED_DEVICE_CUES):
        return "close_cover"
    return None


def requested_device_domains(text: str) -> set[str]:
    """Return explicit or action-implied climate/fan category hints."""
    normalized = normalize_text(text)
    domains: set[str] = set()
    if any(cue in normalized for cue in _CLIMATE_CUES):
        domains.add("climate")
    if any(cue in normalized for cue in _FAN_CUES):
        domains.add("fan")
    if any(
        cue in normalized
        for cue in (
            "nhiet do",
            "temperature",
            "dao gio",
            "swing",
            "hvac",
            "do am muc tieu",
            "target humidity",
        )
    ) or re.search(r"\d+(?:[.,]\d+)?\s*(?:do|°c)\b", normalized):
        domains.add("climate")
    return domains


def _contains_schedule_hint(normalized: str) -> bool:
    return bool(
        re.search(
            r"\b(?:hen\s*(?:gio|giơ)|dat lich|schedule|timer|sau|trong|"
            r"luc|vao|ngay mai|hom nay|nua)\b",
            normalized,
        )
    )


def device_control_request_hint(text: str) -> bool:
    """Return whether text plausibly asks to control or schedule a device."""
    normalized = normalize_text(text)
    if not normalized:
        return False
    if explicit_power_action(text) is not None:
        return True

    action_cues = (
        "nhiet do",
        "temperature",
        "do c",
        "toc do",
        "speed",
        "che do",
        "mode",
        "dao gio",
        "swing",
        "quay",
        "oscillat",
        "huong quay",
        "direction",
        "do am",
        "humidity",
        "tang gio",
        "giam gio",
    )
    numeric_temperature = bool(
        re.search(r"\b\d+(?:[.,]\d+)?\s*(?:do|c)\b", normalized)
    ) or bool(re.search(r"\d+(?:[.,]\d+)?\s*°\s*c?", str(text).casefold()))
    numeric_percentage = bool(
        re.search(r"\d+(?:[.,]\d+)?\s*%", str(text).casefold())
    )
    has_action = (
        any(cue in normalized for cue in action_cues)
        or numeric_temperature
        or numeric_percentage
    )
    has_device = any(cue in normalized for cue in _DEVICE_CUES)
    control_verb = bool(
        re.search(
            r"\b(?:dat|chinh|dieu khien|doi|tang|giam|chuyen|bat|tat|mo|dong|"
            r"set|adjust|control|increase|decrease|raise|lower|change|turn)\b",
            normalized,
        )
    )
    implied_climate = bool(requested_device_domains(text) & {"climate"})
    if has_action and (has_device or (control_verb and implied_climate)):
        return True
    if control_verb and has_device:
        return True
    if _contains_schedule_hint(normalized) and (has_device or implied_climate):
        return True
    return False


# Compatibility name used by the manager and previous releases.
def device_power_request_hint(text: str) -> bool:
    return device_control_request_hint(text)


def _target_score(text: str, target: DevicePowerTarget) -> float:
    """Score how likely one target is mentioned in possibly malformed text."""
    normalized = normalize_text(text)
    compact = normalized.replace(" ", "")
    query_tokens = set(normalized.split())
    best = 0.0

    for alias in target.aliases:
        alias_normalized = normalize_text(alias)
        if not alias_normalized:
            continue
        alias_compact = alias_normalized.replace(" ", "")
        if alias_normalized in normalized or alias_compact in compact:
            best = max(best, 3.0 + min(len(alias_compact), 40) / 100)
        alias_tokens = set(alias_normalized.split())
        if alias_tokens:
            overlap = len(query_tokens & alias_tokens) / len(alias_tokens)
            best = max(best, overlap * 2.0)
        best = max(best, SequenceMatcher(None, compact, alias_compact).ratio())

    area_normalized = normalize_text(target.area_name)
    if area_normalized:
        area_compact = area_normalized.replace(" ", "")
        if area_normalized in normalized or area_compact in compact:
            best += 0.8

    domain_cues: dict[str, tuple[str, ...]] = {
        "light": ("den", "light", "lamp"),
        "fan": _FAN_CUES,
        "switch": ("cong tac", "switch", "o cam", "plug"),
        "cover": (
            "cua cuon",
            "cua gara",
            "garage door",
            "rolling door",
            "rem",
            "curtain",
            "cover",
        ),
        "media_player": ("loa", "tv", "tivi", "nhac", "speaker"),
        "climate": _CLIMATE_CUES,
        "vacuum": ("robot", "hut bui", "vacuum"),
        "humidifier": ("tao am", "humidifier"),
        "water_heater": ("binh nong lanh", "water heater"),
    }
    if any(cue in normalized for cue in domain_cues.get(target.domain, ())):
        best += 0.35
    return best


def _all_request(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:all|every|tat ca|toan bo|cac|nhung|mọi|moi)\b",
            normalize_text(text),
        )
    )


def _all_request_domains(text: str, targets: Iterable[DevicePowerTarget]) -> set[str]:
    """Infer domains for an explicit all/plural request."""
    normalized = normalize_text(text)
    domains = set(requested_device_domains(text))
    cues: dict[str, tuple[str, ...]] = {
        "light": ("den", "light", "lamp"),
        "switch": ("cong tac", "switch", "o cam", "plug"),
        "cover": ("rem", "curtain", "cover", "cua", "door"),
        "media_player": ("loa", "speaker", "tivi", "tv"),
        "vacuum": ("robot", "hut bui", "vacuum"),
        "humidifier": ("tao am", "humidifier"),
        "water_heater": ("binh nong lanh", "water heater"),
        "automation": ("automation", "tu dong hoa"),
        "script": ("script", "kich ban"),
        "siren": ("coi", "siren"),
        "remote": ("remote", "dieu khien tu xa"),
        "input_boolean": ("input boolean",),
    }
    for domain, domain_cues in cues.items():
        if any(cue in normalized for cue in domain_cues):
            domains.add(domain)
    if any(cue in normalized for cue in ("tat ca thiet bi", "toan bo thiet bi", "all devices", "every device")):
        domains.update(target.domain for target in targets)
    return domains


def exact_named_targets(
    text: str,
    targets: Iterable[DevicePowerTarget],
) -> list[DevicePowerTarget]:
    """Resolve explicit entity names, or an explicit all-of-category request."""
    target_list = list(targets)
    normalized = normalize_text(text)
    compact = normalized.replace(" ", "")
    domain_hints = requested_device_domains(text)

    if _all_request(text):
        all_domains = _all_request_domains(text, target_list)
        if not all_domains:
            return []
        candidates = [target for target in target_list if target.domain in all_domains]
        area_matches = [
            target
            for target in candidates
            if target.area_name and normalize_text(target.area_name) in normalized
        ]
        return area_matches or candidates

    scored: list[tuple[int, DevicePowerTarget]] = []
    for target in target_list:
        best_length = 0
        for alias in target.aliases:
            alias_normalized = normalize_text(alias)
            if not alias_normalized:
                continue
            alias_compact = alias_normalized.replace(" ", "")
            if (
                re.search(
                    rf"(?<!\w){re.escape(alias_normalized)}(?!\w)",
                    normalized,
                )
                or (
                    " " in alias_normalized
                    and len(alias_compact) >= 4
                    and alias_compact in compact
                )
                or alias_normalized == target.entity_id
            ):
                best_length = max(best_length, len(alias_compact))
        if best_length:
            scored.append((best_length, target))

    if not scored:
        return []
    best_length = max(score for score, _target in scored)
    matches = [target for score, target in scored if score == best_length]
    return matches if len(matches) == 1 else []


def parse_device_target_selection(
    text: str,
    targets: Iterable[DevicePowerTarget],
) -> list[int]:
    """Parse a pending device choice without mistaking values for indexes.

    The shared selection parser intentionally accepts every valid number. In a
    device follow-up, however, numbers may be temperatures, percentages,
    durations, clock times, or dates. Remove those value-shaped fragments
    before resolving option numbers and exact entity names.
    """
    target_list = list(targets)
    if not target_list:
        return []

    sanitized = str(text or "")
    value_patterns = (
        # Dates and clock times.
        r"(?<!\d)\d{1,2}\s*[/-]\s*\d{1,2}(?:\s*[/-]\s*\d{2,4})?(?!\d)",
        r"(?<!\d)(?:[01]?\d|2[0-3])\s*:\s*[0-5]\d(?!\d)",
        r"(?<!\d)(?:[01]?\d|2[0-3])\s*(?:h|giờ|gio|hour)\s*(?:[0-5]?\d)?",
        # Temperature, percentage, and relative-duration values.
        r"(?<!\d)[+-]?\d+(?:[.,]\d+)?\s*(?:°\s*[cf]?|độ\s*[cf]?|do\s*[cf]?)(?!\w)",
        r"(?<!\d)\d+(?:[.,]\d+)?\s*%(?!\w)",
        r"(?<!\d)\d+(?:[.,]\d+)?\s*(?:giây|giay|phút|phut|giờ|gio|ngày|ngay|seconds?|minutes?|hours?|days?)\b",
    )
    for pattern in value_patterns:
        sanitized = re.sub(pattern, " ", sanitized, flags=re.IGNORECASE)

    return parse_target_selection(
        sanitized,
        [target.display_name for target in target_list],
    )


def exact_power_targets(
    text: str,
    action: str,
    targets: Iterable[DevicePowerTarget],
) -> list[DevicePowerTarget]:
    """Resolve exact targets that support a requested power action."""
    if action not in POWER_CONTROL_ACTIONS:
        return []
    return [target for target in exact_named_targets(text, targets) if target.supports(action)]


def rank_power_targets(
    text: str,
    targets: Iterable[DevicePowerTarget],
    *,
    limit: int = 80,
) -> list[DevicePowerTarget]:
    """Return the most relevant exposed targets for an AI parser prompt."""
    scored = [(_target_score(text, target), target) for target in targets]
    scored.sort(
        key=lambda item: (
            -item[0],
            item[1].display_name.casefold(),
            item[1].entity_id,
        )
    )
    if len(scored) <= limit:
        return [target for _score, target in scored]

    selected = [target for score, target in scored if score >= 0.58][:limit]
    selected_ids = {target.entity_id for target in selected}
    for _score, target in scored:
        if len(selected) >= limit:
            break
        if target.entity_id not in selected_ids:
            selected.append(target)
            selected_ids.add(target.entity_id)
    return selected


def _extract_number(text: str, patterns: tuple[str, ...]) -> float | None:
    normalized = normalize_text(text)
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        raw = match.group("value").replace(",", ".")
        if raw in _NUMBER_WORDS:
            return _NUMBER_WORDS[raw]
        value = _float_or_none(raw)
        if value is not None:
            return value
    return None


def _extract_temperature(text: str) -> float | None:
    return _extract_number(
        text,
        (
            r"(?P<value>-?\d+(?:[.,]\d+)?)\s*(?:do\s*[cf]|°\s*[cf]|do|[cf])(?!\w)",
            r"(?:nhiet do|temperature)\s*(?:la|len|xuong|ve|at|to)?\s*"
            r"(?P<value>-?\d+(?:[.,]\d+)?)",
        ),
    )


def _extract_temperature_range(text: str) -> tuple[float, float] | None:
    """Extract an explicit lower/upper climate target range."""
    normalized = normalize_text(text)
    patterns = (
        r"(?:tu|from)\s*(?P<low>-?\d+(?:[.,]\d+)?)\s*(?:do\s*[cf]|do|[cf])?\s*"
        r"(?:den|toi|to|through|-)\s*(?P<high>-?\d+(?:[.,]\d+)?)\s*(?:do\s*[cf]|do|[cf])?\b",
        r"(?:khoang nhiet do|temperature range|range)"
        r"(?:\s+[a-z0-9]+){0,10}?\s+"
        r"(?P<low>-?\d+(?:[.,]\d+)?)\s*(?:den|toi|to|through|\s+)\s*"
        r"(?P<high>-?\d+(?:[.,]\d+)?)\s*(?:do\s*[cf]|do|[cf])?\b",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        low = _float_or_none(match.group("low").replace(",", "."))
        high = _float_or_none(match.group("high").replace(",", "."))
        if low is not None and high is not None and low < high:
            return low, high
    return None


def _extract_percentage(text: str) -> float | None:
    raw = str(text or "").casefold().replace(",", ".")
    match = re.search(r"(?P<value>\d+(?:\.\d+)?)\s*%", raw)
    if match:
        return _float_or_none(match.group("value"))
    return _extract_number(
        text,
        (
            r"(?P<value>\d+(?:[.,]\d+)?)\s*phan tram",
            r"(?:toc do|speed|percentage)\s*(?:la|len|xuong|ve|at|to)?\s*"
            r"(?P<value>\d+(?:[.,]\d+)?)",
        ),
    )


def _extract_humidity(text: str) -> float | None:
    normalized = normalize_text(text)
    if not any(cue in normalized for cue in ("do am", "humidity")):
        return None
    return _extract_percentage(text)


def _extract_adjustment_amount(text: str, *, percentage: bool = False) -> float | None:
    raw = str(text or "").casefold().replace(",", ".")
    if percentage:
        match = re.search(
            r"(?:tăng|giảm|increase|decrease|raise|lower).*?"
            r"(?P<value>\d+(?:\.\d+)?)\s*%",
            raw,
        )
        if match:
            return _float_or_none(match.group("value"))

    normalized = normalize_text(text)
    unit = r"(?:phan tram)" if percentage else r"(?:do\s*[cf]|do|[cf])"
    match = re.search(
        rf"(?:tang|giam|increase|decrease|raise|lower).*?"
        rf"(?P<value>\d+(?:[.,]\d+)?)\s*{unit}",
        normalized,
    )
    if not match:
        return None
    return _float_or_none(match.group("value").replace(",", "."))


def _option_aliases(option: str) -> tuple[str, ...]:
    normalized = normalize_text(option)
    aliases = {normalized}
    aliases.update(_MODE_ALIASES.get(normalized, ()))
    aliases.update(_HVAC_ALIASES.get(normalized, ()))
    return tuple(sorted(aliases, key=len, reverse=True))


def match_supported_option(text: str, options: Iterable[str]) -> str | None:
    """Match a user phrase to one exact option exposed by the entity."""
    normalized = normalize_text(text)
    compact = normalized.replace(" ", "")
    matches: list[tuple[int, str]] = []
    for option in options:
        option_text = str(option or "").strip()
        if not option_text:
            continue
        for alias in _option_aliases(option_text):
            if not alias:
                continue
            if (
                re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized)
                or (len(alias) >= 4 and alias.replace(" ", "") in compact)
            ):
                matches.append((len(alias), option_text))
                break
    if not matches:
        return None
    best_length = max(length for length, _option in matches)
    best = {option for length, option in matches if length == best_length}
    return next(iter(best)) if len(best) == 1 else None


def _target_domains(targets: Iterable[DevicePowerTarget]) -> set[str]:
    return {target.domain for target in targets}


def _has_any(normalized: str, cues: Iterable[str]) -> bool:
    return any(cue in normalized for cue in cues)


def _embedded_power_action(text: str) -> str | None:
    """Extract a power verb that follows timer wording or other prefixes."""
    explicit = explicit_power_action(text)
    if explicit is not None:
        return explicit
    normalized = normalize_text(text)
    negative = (
        "khong bat",
        "khong tat",
        "khong mo",
        "khong dong",
        "do not turn on",
        "do not turn off",
        "do not open",
        "do not close",
    )
    if any(cue in normalized for cue in negative):
        return None
    patterns = (
        (r"\b(?:bat|turn on|switch on|power on|activate)\b", "turn_on"),
        (r"\b(?:tat|turn off|switch off|power off|deactivate)\b", "turn_off"),
        (r"\b(?:mo|open)\b", "open_cover"),
        (r"\b(?:dong|close)\b", "close_cover"),
    )
    for pattern, action in patterns:
        if re.search(pattern, normalized):
            return action
    return None


def deterministic_action_and_parameters(
    text: str,
    targets: Iterable[DevicePowerTarget] = (),
) -> tuple[str, dict[str, Any]]:
    """Parse common Vietnamese/English climate and fan commands locally."""
    target_list = list(targets)
    domains = _target_domains(target_list) or requested_device_domains(text)
    normalized = normalize_text(text)
    parameters: dict[str, Any] = {}

    temperature_range = _extract_temperature_range(text)
    temperature = _extract_temperature(text)
    temperature_context = _has_any(
        normalized, ("nhiet do", "temperature", "do c")
    ) or temperature is not None or temperature_range is not None

    # Advanced climate/fan operations take precedence over a leading "bật/tắt"
    # because phrases such as "bật đảo gió" and "bật quay quạt" are not power
    # commands for the whole entity.
    if "climate" in domains or _has_any(normalized, _CLIMATE_CUES):
        if temperature_context:
            if temperature_range is not None:
                parameters["target_temp_low"] = temperature_range[0]
                parameters["target_temp_high"] = temperature_range[1]
                return "climate_set_temperature_range", parameters
            if _has_any(normalized, ("tang", "increase", "raise", "cao hon")):
                amount = _extract_adjustment_amount(text)
                if amount is not None:
                    parameters["amount"] = amount
                return "climate_increase_temperature", parameters
            if _has_any(normalized, ("giam", "decrease", "lower", "ha", "thap hon")):
                amount = _extract_adjustment_amount(text)
                if amount is not None:
                    parameters["amount"] = amount
                return "climate_decrease_temperature", parameters
            if temperature is not None:
                parameters["temperature"] = temperature
            return "climate_set_temperature", parameters

        if _has_any(normalized, ("do am", "humidity")):
            humidity = _extract_humidity(text)
            if humidity is not None:
                parameters["humidity"] = humidity
            return "climate_set_humidity", parameters

        swing_context = _has_any(
            normalized,
            ("dao gio", "dao canh", "swing", "canh gio", "huong gio"),
        )
        if swing_context:
            horizontal = _has_any(
                normalized,
                ("ngang", "trai phai", "horizontal", "left right"),
            )
            action = (
                "climate_set_swing_horizontal_mode"
                if horizontal
                else "climate_set_swing_mode"
            )
            key = "swing_horizontal_mode" if horizontal else "swing_mode"
            matched_swing_modes = {
                option
                for target in target_list
                if target.domain == "climate"
                and (
                    option := match_supported_option(
                        text,
                        target.swing_horizontal_modes
                        if horizontal
                        else target.swing_modes,
                    )
                )
                is not None
            }
            if len(matched_swing_modes) == 1:
                parameters[key] = next(iter(matched_swing_modes))
            elif _has_any(normalized, ("tat", "off", "dung", "stop")):
                parameters[key] = "off"
            elif _has_any(normalized, ("bat", "on", "dao", "swing")):
                parameters[key] = "on"
            return action, parameters

        fan_mode_context = _has_any(
            normalized,
            (
                "toc do gio",
                "toc do quat dieu hoa",
                "toc do quat may lanh",
                "fan mode",
                "muc gio",
            ),
        )
        if fan_mode_context:
            if _has_any(normalized, ("tang", "increase", "nhanh hon", "manh hon")):
                return "climate_increase_fan_mode", parameters
            if _has_any(normalized, ("giam", "decrease", "cham hon", "nhe hon")):
                return "climate_decrease_fan_mode", parameters
            matched_fan_modes = {
                option
                for target in target_list
                if target.domain == "climate"
                and (option := match_supported_option(text, target.fan_modes))
                is not None
            }
            if len(matched_fan_modes) == 1:
                parameters["fan_mode"] = next(iter(matched_fan_modes))
            return "climate_set_fan_mode", parameters

        hvac_mode_context = _has_any(
            normalized,
            ("che do dieu hoa", "che do may lanh", "hvac mode", "climate mode"),
        )
        matched_hvac_options = {
            option
            for target in target_list
            if target.domain == "climate"
            and (option := match_supported_option(text, target.hvac_modes))
            is not None
        }
        matched_hvac_option = bool(matched_hvac_options)
        mode_change_verb = _has_any(
            normalized, ("chuyen", "dat", "set", "change", "sang", "ve")
        )
        if (matched_hvac_option and mode_change_verb) or hvac_mode_context or (
            "che do" in normalized
            and _has_any(
                normalized,
                (
                    "lam lanh",
                    "lam mat",
                    "suoi",
                    "hut am",
                    "fan only",
                    "chi quat",
                    "tu dong",
                    "cool",
                    "heat",
                    "dry",
                ),
            )
        ):
            if len(matched_hvac_options) == 1:
                parameters["hvac_mode"] = next(iter(matched_hvac_options))
            return "climate_set_hvac_mode", parameters

        matched_climate_presets = {
            option
            for target in target_list
            if target.domain == "climate"
            and (option := match_supported_option(text, target.preset_modes))
            is not None
        }
        if matched_climate_presets or _has_any(
            normalized, ("preset", "che do dat truoc", "che do ngu", "eco")
        ):
            if len(matched_climate_presets) == 1:
                parameters["preset_mode"] = next(iter(matched_climate_presets))
            return "climate_set_preset_mode", parameters

    if "fan" in domains or (_has_any(normalized, _FAN_CUES) and "climate" not in domains):
        if _has_any(
            normalized,
            ("huong quay", "direction", "quay nguoc", "quay xuoi", "dao chieu"),
        ):
            if _has_any(normalized, ("nguoc", "reverse", "dao chieu")):
                parameters["direction"] = "reverse"
            elif _has_any(normalized, ("xuoi", "thuan", "forward", "cung chieu")):
                parameters["direction"] = "forward"
            return "fan_set_direction", parameters

        if _has_any(normalized, ("quay", "oscillat", "dao qua lai", "lac")):
            parameters["oscillating"] = not _has_any(
                normalized,
                ("tat", "dung", "khong quay", "off", "stop"),
            )
            return "fan_oscillate", parameters

        percentage = _extract_percentage(text)
        speed_context = _has_any(
            normalized,
            ("toc do", "speed", "phan tram", "muc gio", "muc quat"),
        ) or percentage is not None
        if speed_context:
            if _has_any(normalized, ("tang", "increase", "nhanh hon", "manh hon")):
                amount = _extract_adjustment_amount(text, percentage=True)
                if amount is not None:
                    parameters["percentage_step"] = amount
                return "fan_increase_speed", parameters
            if _has_any(normalized, ("giam", "decrease", "cham hon", "nhe hon")):
                amount = _extract_adjustment_amount(text, percentage=True)
                if amount is not None:
                    parameters["percentage_step"] = amount
                return "fan_decrease_speed", parameters
            if percentage is not None:
                parameters["percentage"] = percentage
            return "fan_set_percentage", parameters

        matched_fan_presets = {
            option
            for target in target_list
            if target.domain == "fan"
            and (option := match_supported_option(text, target.preset_modes))
            is not None
        }
        if matched_fan_presets or _has_any(
            normalized,
            ("preset", "che do quat", "che do gio", "che do ngu", "eco"),
        ):
            if len(matched_fan_presets) == 1:
                parameters["preset_mode"] = next(iter(matched_fan_presets))
            return "fan_set_preset_mode", parameters

    power_action = _embedded_power_action(text)
    if power_action is not None:
        if domains and domains <= {"climate", "fan"}:
            if power_action == "open_cover":
                power_action = "turn_on"
            elif power_action == "close_cover":
                power_action = "turn_off"
        return power_action, parameters

    return "", parameters


def _parse_duration_value(raw: str) -> float | None:
    normalized = normalize_text(raw).strip()
    if normalized in _NUMBER_WORDS:
        return _NUMBER_WORDS[normalized]
    return _float_or_none(normalized.replace(",", "."))


def parse_scheduled_for(text: str, now: datetime) -> datetime | None:
    """Parse common relative, clock, and calendar timer wording safely."""
    normalized = normalize_text(text)
    raw = str(text or "").casefold()

    # Relative wording must be explicit. Avoid treating "hẹn giờ ... 19 giờ"
    # as a 19-hour duration; that phrase normally denotes a clock time.
    relative_patterns = (
        r"(?:sau|trong|in)\s+"
        r"(?P<value>\d+(?:[.,]\d+)?|mot|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi|nua)\s*"
        r"(?P<unit>giay|phut|gio|ngay|second|seconds|minute|minutes|hour|hours|day|days)",
        r"(?P<value>\d+(?:[.,]\d+)?|mot|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi|nua)\s*"
        r"(?P<unit>giay|phut|gio|ngay|second|seconds|minute|minutes|hour|hours|day|days)\s*"
        r"(?:nua|from now)",
    )
    for pattern in relative_patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        value = _parse_duration_value(match.group("value"))
        if value is None or value <= 0:
            continue
        unit = match.group("unit")
        if unit in {"giay", "second", "seconds"}:
            delta = timedelta(seconds=value)
        elif unit in {"phut", "minute", "minutes"}:
            delta = timedelta(minutes=value)
        elif unit in {"gio", "hour", "hours"}:
            delta = timedelta(hours=value)
        else:
            delta = timedelta(days=value)
        return now + delta

    if not _contains_schedule_hint(normalized):
        return None

    hour: int | None = None
    minute = 0
    daypart = ""

    # A colon is unambiguous.
    colon_matches = list(
        re.finditer(
            r"(?<!\d)(?P<hour>[01]?\d|2[0-3])\s*:\s*"
            r"(?P<minute>[0-5]\d)(?!\d)",
            raw,
        )
    )
    if colon_matches:
        match = colon_matches[-1]
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
        daypart = normalize_text(raw[match.end() : match.end() + 16])
    else:
        # Vietnamese 19h30 / 19 giờ 30 and equivalent English hour notation.
        h_matches = list(
            re.finditer(
                r"(?<!\d)(?P<hour>[01]?\d|2[0-3])\s*"
                r"(?:h|giờ|gio|hour)\s*(?P<minute>[0-5]?\d)?\s*"
                r"(?P<daypart>sáng|sang|trưa|trua|chiều|chieu|tối|toi|đêm|dem|am|pm)?\b",
                raw,
            )
        )
        if h_matches:
            match = h_matches[-1]
            hour = int(match.group("hour"))
            minute = int(match.group("minute") or 0)
            daypart = normalize_text(str(match.group("daypart") or ""))
        else:
            # Explicit clock introducers. normalize_text turns punctuation into
            # spaces, so a separated minute is accepted only after lúc/vào/at.
            clock_matches = list(
                re.finditer(
                    r"\b(?:luc|vao|at)\s+"
                    r"(?P<hour>[01]?\d|2[0-3])"
                    r"(?:\s+(?P<minute>[0-5]?\d))?\s*"
                    r"(?P<daypart>sang|trua|chieu|toi|dem|am|pm)?\b",
                    normalized,
                )
            )
            if clock_matches:
                match = clock_matches[-1]
                hour = int(match.group("hour"))
                minute = int(match.group("minute") or 0)
                daypart = str(match.group("daypart") or "")

    if hour is None:
        return None
    if daypart.startswith(("chieu", "toi", "dem", "pm")) and hour < 12:
        hour += 12
    elif daypart.startswith(("sang", "am")) and hour == 12:
        hour = 0

    explicit_year: int | None = None
    explicit_month: int | None = None
    explicit_day: int | None = None
    date_match = re.search(
        r"(?:ngày|ngay|on)?\s*(?P<day>\d{1,2})\s*[/-]\s*"
        r"(?P<month>\d{1,2})(?:\s*[/-]\s*(?P<year>\d{2,4}))?",
        raw,
    )
    if date_match:
        explicit_day = int(date_match.group("day"))
        explicit_month = int(date_match.group("month"))
        if date_match.group("year"):
            explicit_year = int(date_match.group("year"))
            if explicit_year < 100:
                explicit_year += 2000
    else:
        word_date = re.search(
            r"\bngay\s+(?P<day>\d{1,2})\s+thang\s+"
            r"(?P<month>\d{1,2})(?:\s+nam\s+(?P<year>\d{4}))?\b",
            normalized,
        )
        if word_date:
            explicit_day = int(word_date.group("day"))
            explicit_month = int(word_date.group("month"))
            if word_date.group("year"):
                explicit_year = int(word_date.group("year"))

    if explicit_day is not None and explicit_month is not None:
        year = explicit_year or now.year
        try:
            candidate = now.replace(
                year=year,
                month=explicit_month,
                day=explicit_day,
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )
        except ValueError:
            return None
        if candidate <= now and explicit_year is None:
            try:
                candidate = candidate.replace(year=year + 1)
            except ValueError:
                return None
        return candidate if candidate > now else None

    day_offset = 1 if "ngay mai" in normalized or "tomorrow" in normalized else 0
    candidate = now.replace(
        hour=hour, minute=minute, second=0, microsecond=0
    ) + timedelta(days=day_offset)
    explicit_today = "hom nay" in normalized or "today" in normalized
    if candidate <= now and not explicit_today and day_offset == 0:
        candidate += timedelta(days=1)
    if candidate <= now:
        return None
    return candidate


def deterministic_interpretation(
    text: str,
    targets: Iterable[DevicePowerTarget],
    now: datetime,
) -> DeviceControlInterpretation:
    """Build a best-effort local interpretation without invoking AI."""
    target_list = exact_named_targets(text, targets)
    action, parameters = deterministic_action_and_parameters(text, target_list)
    target_domain = ""
    domain_hints = requested_device_domains(text)
    if len(domain_hints) == 1:
        target_domain = next(iter(domain_hints))
    return DeviceControlInterpretation(
        action=action,
        targets=tuple(target_list),
        parameters=parameters,
        scheduled_for=parse_scheduled_for(text, now),
        confidence=1.0 if action and target_list else 0.0,
        target_domain=target_domain,
    )


def _parse_ai_schedule(value: Any, now: datetime | None) -> datetime | None:
    text = str(value or "").strip()
    if not text or now is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None and now.tzinfo is not None:
        parsed = parsed.replace(tzinfo=now.tzinfo)
    try:
        if parsed <= now or parsed > now + timedelta(days=366):
            return None
    except TypeError:
        return None
    return parsed


def interpretation_from_payload(
    payload: Mapping[str, Any],
    allowed_targets: Iterable[DevicePowerTarget],
    *,
    now: datetime | None = None,
) -> DeviceControlInterpretation | None:
    """Validate a strict AI JSON payload against the live target inventory."""
    action = str(payload.get("action", "") or "").strip().casefold()
    if action and action not in CONTROL_ACTIONS:
        return None

    raw_entity_ids = payload.get("entity_ids")
    if isinstance(raw_entity_ids, str):
        raw_entity_ids = [raw_entity_ids]
    if raw_entity_ids is None:
        raw_entity_ids = []
    if not isinstance(raw_entity_ids, list) or len(raw_entity_ids) > 20:
        return None

    allowed = {target.entity_id: target for target in allowed_targets}
    selected: list[DevicePowerTarget] = []
    seen: set[str] = set()
    for raw_entity_id in raw_entity_ids:
        entity_id = str(raw_entity_id or "").strip()
        target = allowed.get(entity_id)
        if target is None:
            return None
        if entity_id in seen:
            continue
        selected.append(target)
        seen.add(entity_id)

    target_domain = str(payload.get("target_domain", "") or "").strip().casefold()
    if target_domain not in {"", "climate", "fan"}:
        return None
    if selected and target_domain and any(
        target.domain != target_domain for target in selected
    ):
        return None

    raw_parameters = payload.get("parameters")
    if raw_parameters is None:
        raw_parameters = {}
    if not isinstance(raw_parameters, Mapping):
        return None
    parameters: dict[str, Any] = {}
    allowed_parameter_keys = {
        "temperature",
        "target_temp_low",
        "target_temp_high",
        "amount",
        "hvac_mode",
        "fan_mode",
        "swing_mode",
        "swing_horizontal_mode",
        "preset_mode",
        "humidity",
        "percentage",
        "percentage_step",
        "oscillating",
        "direction",
    }
    for key, value in raw_parameters.items():
        normalized_key = str(key or "").strip()
        if normalized_key not in allowed_parameter_keys:
            return None
        if isinstance(value, (str, int, float, bool)) or value is None:
            parameters[normalized_key] = value
        else:
            return None

    try:
        confidence = float(payload.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if not isfinite(confidence):
        confidence = 0.0
    confidence = max(0.0, min(confidence, 1.0))

    scheduled_for = _parse_ai_schedule(payload.get("schedule_at"), now)
    return DeviceControlInterpretation(
        action=action,
        targets=tuple(selected),
        parameters=parameters,
        scheduled_for=scheduled_for,
        confidence=confidence,
        target_domain=target_domain,
    )
