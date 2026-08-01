"""Safe helpers for Zalo-only Home Assistant device control."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from math import isfinite
import re
from typing import Any, Iterable

from .targeting import normalize_text

# Domains with conventional turn_on/turn_off semantics. The manager still
# checks the live service registry before presenting or executing a target.
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

CONTROL_ACTIONS = frozenset(
    {"turn_on", "turn_off", "open_cover", "close_cover"}
)

_ROLLING_DOOR_CUES = (
    "cua cuon",
    "cua gara",
    "cua garage",
    "cua nha xe",
    "garage door",
    "rolling door",
    "roller door",
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


@dataclass(slots=True, frozen=True)
class DevicePowerTarget:
    """One exposed Home Assistant entity supported by Zalo device control."""

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
        return False


@dataclass(slots=True, frozen=True)
class DevicePowerInterpretation:
    """Validated AI interpretation of one device power request."""

    action: str
    targets: tuple[DevicePowerTarget, ...]
    confidence: float


def is_rolling_door_target(target: DevicePowerTarget) -> bool:
    """Return whether a target represents a rolling/garage-style door."""
    device_class = normalize_text(target.device_class)
    if device_class == "garage":
        return True

    searchable = normalize_text(
        " ".join(
            (
                target.display_name,
                target.area_name,
                *target.aliases,
            )
        )
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

    # Accent-preserving checks prevent Vietnamese words such as "bắt",
    # "bất", and "tất" from being mistaken for "bật" or "tắt" after
    # diacritics are removed by normalize_text().
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

    # Text without Vietnamese diacritics is more ambiguous, so reject common
    # non-command prefixes before accepting an ASCII action word.
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
    exact_open = (
        "mo ",
        "open ",
    )
    exact_close = (
        "dong ",
        "close ",
    )
    if normalized.startswith(exact_on):
        return "turn_on"
    if normalized.startswith(exact_off):
        return "turn_off"
    if normalized.startswith(exact_open):
        return "open_cover"
    if normalized.startswith(exact_close):
        return "close_cover"

    if re.match(
        r"^(?:turn|switch|power)\s+.+\s+on(?:\s+please)?$",
        normalized,
    ):
        return "turn_on"
    if re.match(
        r"^(?:turn|switch|power)\s+.+\s+off(?:\s+please)?$",
        normalized,
    ):
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

    # Without Vietnamese diacritics, only accept joined/repeated action words
    # when the remainder begins with a common device cue. This keeps typo
    # recovery useful without routing unrelated words such as "batman".
    on_match = re.match(r"^ba+t+(?P<target>.+)", compact)
    if on_match and on_match.group("target").startswith(_ASCII_JOINED_DEVICE_CUES):
        return "turn_on"
    off_match = re.match(r"^ta+t+(?P<target>.+)", compact)
    if off_match and off_match.group("target").startswith(_ASCII_JOINED_DEVICE_CUES):
        return "turn_off"
    open_match = re.match(r"^mo+(?P<target>.+)", compact)
    if open_match and open_match.group("target").startswith(
        _ASCII_JOINED_DEVICE_CUES
    ):
        return "open_cover"
    close_match = re.match(r"^dong(?P<target>.+)", compact)
    if close_match and close_match.group("target").startswith(
        _ASCII_JOINED_DEVICE_CUES
    ):
        return "close_cover"
    return None


def device_power_request_hint(text: str) -> bool:
    """Return whether text plausibly asks to control a supported device."""
    normalized = normalize_text(text)
    if not normalized or normalized in {
        "bat",
        "tat",
        "mo",
        "dong",
        "turn on",
        "turn off",
        "open",
        "close",
    }:
        return False
    return explicit_power_action(text) is not None


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
        best = max(
            best,
            SequenceMatcher(None, compact, alias_compact).ratio(),
        )

    area_normalized = normalize_text(target.area_name)
    if area_normalized:
        area_compact = area_normalized.replace(" ", "")
        if area_normalized in normalized or area_compact in compact:
            best += 0.8

    domain_cues: dict[str, tuple[str, ...]] = {
        "light": ("den", "light", "lamp"),
        "fan": ("quat", "fan"),
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
        "climate": ("dieu hoa", "may lanh", "climate", "air conditioner"),
        "vacuum": ("robot", "hut bui", "vacuum"),
        "humidifier": ("tao am", "humidifier"),
        "water_heater": ("binh nong lanh", "water heater"),
    }
    if any(cue in normalized for cue in domain_cues.get(target.domain, ())):
        best += 0.35
    return best


def exact_power_targets(
    text: str,
    action: str,
    targets: Iterable[DevicePowerTarget],
) -> list[DevicePowerTarget]:
    """Resolve a unique exact alias match without asking an AI model.

    The longest matching alias wins. If multiple entities share the same best
    alias, return no match so the caller can use Home Assistant's native intent
    resolver or ask the user to be more specific instead of guessing.
    """
    if action not in CONTROL_ACTIONS:
        return []

    normalized = normalize_text(text)
    if re.search(
        r"\b(?:all|every|tat ca|toan bo|cac|nhung)\b",
        normalized,
    ):
        return []
    compact = normalized.replace(" ", "")
    scored: list[tuple[int, DevicePowerTarget]] = []
    for target in targets:
        if not target.supports(action):
            continue
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
            ):
                best_length = max(best_length, len(alias_compact))
        if best_length:
            scored.append((best_length, target))

    if not scored:
        return []
    best_length = max(score for score, _target in scored)
    matches = [target for score, target in scored if score == best_length]
    return matches if len(matches) == 1 else []


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

    # Keep all reasonably matching targets, then fill remaining slots with the
    # highest-ranked entities so a short or badly joined request still has a
    # useful candidate inventory.
    selected = [target for score, target in scored if score >= 0.58][:limit]
    selected_ids = {target.entity_id for target in selected}
    for _score, target in scored:
        if len(selected) >= limit:
            break
        if target.entity_id not in selected_ids:
            selected.append(target)
            selected_ids.add(target.entity_id)
    return selected


def interpretation_from_payload(
    payload: dict[str, Any],
    allowed_targets: Iterable[DevicePowerTarget],
) -> DevicePowerInterpretation | None:
    """Validate a strict AI JSON payload against the live target inventory."""
    action = str(payload.get("action", "") or "").strip().casefold()
    if action not in CONTROL_ACTIONS:
        return None

    raw_entity_ids = payload.get("entity_ids")
    if isinstance(raw_entity_ids, str):
        raw_entity_ids = [raw_entity_ids]
    if not isinstance(raw_entity_ids, list):
        return None

    if not raw_entity_ids or len(raw_entity_ids) > 20:
        return None

    allowed = {target.entity_id: target for target in allowed_targets}
    selected: list[DevicePowerTarget] = []
    seen: set[str] = set()
    for raw_entity_id in raw_entity_ids:
        entity_id = str(raw_entity_id or "").strip()
        target = allowed.get(entity_id)
        if target is None or not target.supports(action):
            # Reject the whole interpretation instead of partially accepting a
            # payload that contains invented or unsupported entity IDs.
            return None
        if entity_id in seen:
            continue
        selected.append(target)
        seen.add(entity_id)
    if not selected:
        return None

    try:
        confidence = float(payload.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if not isfinite(confidence):
        confidence = 0.0
    confidence = max(0.0, min(confidence, 1.0))
    return DevicePowerInterpretation(
        action=action,
        targets=tuple(selected),
        confidence=confidence,
    )
