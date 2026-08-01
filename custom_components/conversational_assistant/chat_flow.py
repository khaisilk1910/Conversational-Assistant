"""Pure helpers for the Zalo AI chat flow."""

from __future__ import annotations

import re
import unicodedata

from .targeting import normalize_text

# The phrases are intentionally narrow so ordinary words such as "tám" or
# "buôn" inside another sentence do not unexpectedly capture the Zalo router.
_CHAT_START_PHRASES: tuple[tuple[str, ...], ...] = (
    ("tro", "chuyen", "di"),
    ("tam", "di"),
    ("buon", "di"),
)

# Keep this list conservative to avoid flagging normal Vietnamese words after
# accent folding. These are strong, unambiguous forms only.
_INAPPROPRIATE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?<!\w)địt(?!\w)",
        r"(?<!\w)đụ(?!\w)",
        r"(?<!\w)đéo(?!\w)",
        r"(?<!\w)đm+(?!\w)",
        r"(?<!\w)dm{2,}(?!\w)",
        r"(?<!\w)vcl(?!\w)",
        r"(?<!\w)clm(?!\w)",
        r"(?<!\w)cmm(?!\w)",
        r"(?<!\w)fuck(?:ing)?(?!\w)",
        r"(?<!\w)shit(?:ty)?(?!\w)",
        r"(?<!\w)bitch(?:es)?(?!\w)",
        r"(?<!\w)asshole(?:s)?(?!\w)",
    )
)


def chat_start_request(text: str) -> str | None:
    """Return optional first-turn text when a dedicated chat trigger matches.

    ``None`` means the message is not a chat trigger. An empty string means the
    user only opened the chat. Any words following the trigger are preserved as
    the first AI turn, including Vietnamese accents and original capitalization.
    """
    raw_tokens = re.findall(r"\S+", str(text or "").strip())
    if not raw_tokens:
        return None

    normalized_tokens = [normalize_text(token) for token in raw_tokens]
    start = 0
    if normalized_tokens[0] in {"hay", "please"}:
        start = 1

    for phrase in _CHAT_START_PHRASES:
        end = start + len(phrase)
        if tuple(normalized_tokens[start:end]) != phrase:
            continue
        suffix = " ".join(raw_tokens[end:]).lstrip(" ,:;.!?-–—\t\n")
        return suffix.strip()
    return None


def contains_inappropriate_language(text: str) -> bool:
    """Return whether text contains a strong, unambiguous vulgar expression."""
    value = unicodedata.normalize("NFC", str(text or ""))
    return any(
        pattern.search(value) is not None
        for pattern in _INAPPROPRIATE_PATTERNS
    )


def sanitize_chat_reply(text: str) -> str:
    """Remove strong vulgar expressions from an AI reply as a final safeguard."""
    cleaned = unicodedata.normalize("NFC", str(text or ""))
    for pattern in _INAPPROPRIATE_PATTERNS:
        cleaned = pattern.sub("…", cleaned)
    return cleaned.strip()
