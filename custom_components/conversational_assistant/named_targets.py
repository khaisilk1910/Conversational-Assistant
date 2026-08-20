"""Helpers for configured devices with user-defined spoken names."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable
import uuid

from .targeting import normalize_text


@dataclass(slots=True, frozen=True)
class DirectTargetMatch:
    """Configured target indexes consumed from the start of a request."""

    indexes: tuple[int, ...]
    remainder: str


def normalize_named_target_list(
    value: Any,
    *,
    reference_key: str,
) -> list[dict[str, Any]]:
    """Return a stable, validated list of named target dictionaries."""
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_refs: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        reference = str(item.get(reference_key, "") or "").strip()
        name = " ".join(str(item.get("name", "") or "").split())[:80]
        if not reference or not name or reference in seen_refs:
            continue
        target_id = str(item.get("target_id", "") or "").strip()
        if not target_id or target_id in seen_ids:
            target_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"conversational-assistant:named-target:{reference_key}:{reference}",
            ).hex
        seen_ids.add(target_id)
        seen_refs.add(reference)
        normalized.append(
            {
                "target_id": target_id,
                "name": name,
                "enabled": bool(item.get("enabled", True)),
                reference_key: reference,
            }
        )
    return normalized


def make_named_target(
    user_input: dict[str, Any],
    *,
    reference_key: str,
    target_id: str | None = None,
) -> dict[str, Any]:
    """Normalize one named target submitted by a config flow."""
    reference = str(user_input.get(reference_key, "") or "").strip()
    name = " ".join(str(user_input.get("name", "") or "").split())[:80]
    return {
        "target_id": target_id or uuid.uuid4().hex,
        "name": name,
        "enabled": bool(user_input.get("enabled", True)),
        reference_key: reference,
    }


def spoken_name_key(name: str) -> str:
    """Return a category-neutral key for duplicate spoken-name checks."""
    normalized = normalize_text(" ".join(str(name or "").split()))
    generic_prefixes = (
        "zalo nguoi dung",
        "zalo nhom",
        "may quay",
        "dien thoai",
        "camera",
        "speaker",
        "tivi",
        "tv",
        "television",
        "may chieu",
        "projector",
        "media player",
        "media",
        "thiet bi",
        "mobile",
        "phone",
        "zalo",
        "cam",
        "loa",
    )
    for prefix in generic_prefixes:
        if normalized.startswith(prefix + " "):
            return normalized[len(prefix) + 1 :].strip()
    return normalized


def named_target_errors(
    user_input: dict[str, Any],
    *,
    reference_key: str,
    existing: Iterable[dict[str, Any]] = (),
    editing_target_id: str | None = None,
) -> dict[str, str]:
    """Validate required fields and duplicate aliases/references."""
    errors: dict[str, str] = {}
    name = " ".join(str(user_input.get("name", "") or "").split())
    reference = str(user_input.get(reference_key, "") or "").strip()
    if not name:
        errors["name"] = "required"
    if not reference:
        errors[reference_key] = "required"
    normalized_name = spoken_name_key(name)
    for item in existing:
        if str(item.get("target_id", "")) == str(editing_target_id or ""):
            continue
        if reference and str(item.get(reference_key, "") or "").strip() == reference:
            errors[reference_key] = "duplicate_target"
        if normalized_name and spoken_name_key(
            str(item.get("name", "") or "")
        ) == normalized_name:
            errors["name"] = "duplicate_name"
    return errors


def target_aliases(name: str, *, prefixes: Iterable[str] = ()) -> tuple[str, ...]:
    """Build matching aliases from one user-defined spoken name."""
    clean = " ".join(str(name or "").split())
    aliases = [clean]
    clean_normalized = normalize_text(clean)
    for prefix in prefixes:
        prefix = " ".join(str(prefix or "").split())
        if not prefix:
            continue
        aliases.append(f"{prefix} {clean}")
        normalized_prefix = normalize_text(prefix)
        if clean_normalized.startswith(normalized_prefix + " "):
            stripped = clean.split(maxsplit=len(prefix.split()))[-1].strip()
            if stripped:
                aliases.append(stripped)
    unique: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        normalized = normalize_text(alias)
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(alias)
    return tuple(unique)


def extract_leading_named_targets(
    text: str,
    aliases_by_index: list[tuple[str, ...]],
) -> DirectTargetMatch:
    """Consume one or more configured aliases from the beginning of text.

    Examples include ``phòng ngủ xuống ăn cơm`` and
    ``phòng ngủ và phòng khách xuống ăn cơm``. Longest aliases win, so
    overlapping names such as ``Cam Cổng`` and ``Cam Cổng Phụ`` remain safe.
    """
    raw = str(text or "").strip()
    if not raw:
        return DirectTargetMatch((), "")

    word_matches = list(re.finditer(r"[^\W_]+|\d+", raw, re.UNICODE))
    normalized_words = [normalize_text(match.group(0)) for match in word_matches]
    candidates: list[tuple[tuple[str, ...], int]] = []
    for index, aliases in enumerate(aliases_by_index):
        for alias in aliases:
            tokens = tuple(normalize_text(alias).split())
            if tokens:
                candidates.append((tokens, index))
    candidates.sort(key=lambda item: len(item[0]), reverse=True)

    selected: list[int] = []
    position = 0
    last_end = 0
    connectors = {"va", "and", "voi", "cung", "them"}
    while position < len(normalized_words):
        matched: tuple[tuple[str, ...], int] | None = None
        for tokens, index in candidates:
            end = position + len(tokens)
            if tuple(normalized_words[position:end]) == tokens:
                matched = (tokens, index)
                break
        if matched is None:
            break
        tokens, index = matched
        if index not in selected:
            selected.append(index)
        position += len(tokens)
        last_end = word_matches[position - 1].end()
        if position < len(normalized_words) and normalized_words[position] in connectors:
            position += 1
            last_end = word_matches[position - 1].end()
            continue
        break

    if not selected:
        return DirectTargetMatch((), raw)
    remainder = raw[last_end:].lstrip(" \t\r\n,;:-–—")
    return DirectTargetMatch(tuple(selected), remainder)
