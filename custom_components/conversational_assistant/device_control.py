"""Safe helpers for fast Home Assistant device power control."""

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
)


@dataclass(slots=True, frozen=True)
class DevicePowerTarget:
    """One exposed Home Assistant entity that can be powered on or off."""

    entity_id: str
    display_name: str
    domain: str
    aliases: tuple[str, ...]
    supports_turn_on: bool
    supports_turn_off: bool
    area_name: str = ""

    def supports(self, action: str) -> bool:
        """Return whether this entity supports the requested action."""
        if action == "turn_on":
            return self.supports_turn_on
        if action == "turn_off":
            return self.supports_turn_off
        return False


@dataclass(slots=True, frozen=True)
class DevicePowerInterpretation:
    """Validated AI interpretation of one device power request."""

    action: str
    targets: tuple[DevicePowerTarget, ...]
    confidence: float
    needs_confirmation: bool


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
        "dung bat",
        "dung tat",
        "do not turn on",
        "do not turn off",
        "dont turn on",
        "dont turn off",
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
    if normalized.startswith(exact_on):
        return "turn_on"
    if normalized.startswith(exact_off):
        return "turn_off"

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

    compact = normalized.replace(" ", "")
    if re.match(r"^(?:kichhoat)(?=.+)", compact):
        return "turn_on"
    if re.match(r"^(?:vohieuhoa)(?=.+)", compact):
        return "turn_off"
    if re.match(r"^(?:turnon|switchon|poweron|activate)(?=.+)", compact):
        return "turn_on"
    if re.match(r"^(?:turnoff|switchoff|poweroff|deactivate)(?=.+)", compact):
        return "turn_off"

    # Without Vietnamese diacritics, only accept joined/repeated action words
    # when the remainder begins with a common device cue. This keeps typo
    # recovery useful without routing unrelated words such as "batman".
    on_match = re.match(r"^ba+t+(?P<target>.+)", compact)
    if on_match and on_match.group("target").startswith(_ASCII_JOINED_DEVICE_CUES):
        return "turn_on"
    off_match = re.match(r"^ta+t+(?P<target>.+)", compact)
    if off_match and off_match.group("target").startswith(_ASCII_JOINED_DEVICE_CUES):
        return "turn_off"
    return None


def device_power_request_hint(text: str) -> bool:
    """Return whether text plausibly asks to turn a device on or off."""
    normalized = normalize_text(text)
    if not normalized or normalized in {"bat", "tat", "turn on", "turn off"}:
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
        "media_player": ("loa", "tv", "tivi", "nhac", "speaker"),
        "climate": ("dieu hoa", "may lanh", "climate", "air conditioner"),
        "vacuum": ("robot", "hut bui", "vacuum"),
        "humidifier": ("tao am", "humidifier"),
        "water_heater": ("binh nong lanh", "water heater"),
    }
    if any(cue in normalized for cue in domain_cues.get(target.domain, ())):
        best += 0.35
    return best


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
    if action not in {"turn_on", "turn_off"}:
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
    raw_confirmation = payload.get("needs_confirmation", True)
    needs_confirmation = (
        raw_confirmation if isinstance(raw_confirmation, bool) else True
    )
    return DevicePowerInterpretation(
        action=action,
        targets=tuple(selected),
        confidence=confidence,
        needs_confirmation=needs_confirmation,
    )
