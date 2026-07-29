"""Helpers for selecting notification targets by Vietnamese voice commands."""

from __future__ import annotations

import re
import unicodedata

_INDEX_WORDS = {
    "mot": 1,
    "hai": 2,
    "ba": 3,
    "bon": 4,
    "tu": 4,
    "nam": 5,
    "sau": 6,
    "bay": 7,
    "tam": 8,
    "chin": 9,
    "muoi": 10,
}

_ORDINAL_WORDS = {
    "thu nhat": 1,
    "thu hai": 2,
    "thu ba": 3,
    "thu tu": 4,
    "thu nam": 5,
    "thu sau": 6,
    "thu bay": 7,
    "thu tam": 8,
    "thu chin": 9,
    "thu muoi": 10,
}


def normalize_text(value: str) -> str:
    """Normalize Vietnamese text for forgiving matching."""
    value = unicodedata.normalize("NFD", value.casefold())
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    value = value.replace("đ", "d")
    value = re.sub(r"[^a-z0-9+]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_target_selection(selection: str, target_names: list[str]) -> list[int]:
    """Return selected zero-based target indexes.

    Selection can contain option numbers, Vietnamese number words, target names,
    category phrases such as "tất cả loa", or a general "tất cả" choice.
    Invalid/out-of-range indexes are ignored.
    """
    normalized = normalize_text(selection)
    if not normalized:
        return []

    selected: set[int] = set()
    remaining = normalized

    def add_category(prefixes: tuple[str, ...]) -> None:
        for index, name in enumerate(target_names):
            normalized_name = normalize_text(name)
            if normalized_name.startswith(prefixes):
                selected.add(index)

    category_requested = False
    category_phrases = (
        (("tat ca loa", "toan bo loa", "moi loa"), ("loa ",)),
        (
            ("tat ca dien thoai", "toan bo dien thoai", "moi dien thoai"),
            ("dien thoai ",),
        ),
        (("tat ca zalo", "toan bo zalo", "moi zalo"), ("zalo ",)),
    )
    for phrases, prefixes in category_phrases:
        if any(phrase in normalized for phrase in phrases):
            add_category(prefixes)
            category_requested = True
            for phrase in phrases:
                remaining = remaining.replace(phrase, " ")

    if not category_requested and any(
        phrase in normalized
        for phrase in ("tat ca", "toan bo", "het", "moi noi", "ca hai")
    ):
        return list(range(len(target_names)))

    # Match explicit destination names first. Evaluate aliases globally from
    # longest to shortest so overlapping names such as "Camera 1" and
    # "Camera 10" resolve to the intended destination. Remove matched aliases
    # before parsing digits so numbers inside device names are not interpreted
    # again as global option numbers.
    aliases_by_length: list[tuple[str, int]] = []
    for index, name in enumerate(target_names):
        normalized_name = normalize_text(name)
        aliases = {normalized_name}
        for prefix in (
            "dien thoai ",
            "zalo nhom ",
            "zalo nguoi dung ",
            "loa ",
        ):
            if normalized_name.startswith(prefix):
                aliases.add(normalized_name[len(prefix) :])
        aliases_by_length.extend(
            (alias, index) for alias in aliases if alias
        )

    padded_remaining = f" {remaining} "
    for alias, index in sorted(
        aliases_by_length, key=lambda item: len(item[0]), reverse=True
    ):
        padded_alias = f" {alias} "
        if padded_alias not in padded_remaining:
            continue
        selected.add(index)
        padded_remaining = padded_remaining.replace(padded_alias, " ")
    remaining = padded_remaining.strip()

    remaining = re.sub(r"\s+", " ", remaining).strip()
    for match in re.finditer(r"(?<!\d)\d+(?!\d)", remaining):
        token = match.group()
        value = int(token)
        if 1 <= value <= len(target_names):
            # Prefer an exact option number when it exists. For example, "12"
            # selects option 12 when there are at least 12 destinations.
            selected.add(value - 1)
            continue

        # Be forgiving with a compact answer such as "13" when option 13 does
        # not exist. Treat it as options 1 and 3 only when every digit is a
        # valid single-digit option. This avoids partially accepting "10" or
        # "46" when zero or an out-of-range digit is present.
        if len(token) > 1:
            compact_values = [int(digit) for digit in token]
            if all(
                1 <= compact_value <= min(len(target_names), 9)
                for compact_value in compact_values
            ):
                selected.update(
                    compact_value - 1 for compact_value in compact_values
                )

    padded = f" {remaining} "
    for phrase, value in _ORDINAL_WORDS.items():
        if f" {phrase} " in padded and value <= len(target_names):
            selected.add(value - 1)

    tokens = remaining.split()
    for token in tokens:
        value = _INDEX_WORDS.get(token)
        if value is not None and value <= len(target_names):
            selected.add(value - 1)

    return sorted(selected)
