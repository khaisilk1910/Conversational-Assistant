"""Natural YouTube search/play helpers for Conversational Assistant."""

from __future__ import annotations

from dataclasses import dataclass
import html
import re
from typing import Any, Iterable

from .targeting import normalize_text


@dataclass(slots=True, frozen=True)
class YouTubeVideo:
    """One normalized YouTube search result."""

    title: str
    video_id: str
    url: str
    channel: str = ""
    thumbnail_url: str = ""


@dataclass(slots=True, frozen=True)
class YouTubeTarget:
    """One media player usable for YouTube playback."""

    entity_id: str
    display_name: str
    aliases: tuple[str, ...]
    kind: str  # speaker | tv | media
    available: bool = True
    platform: str = ""


@dataclass(slots=True, frozen=True)
class ParsedYouTubeRequest:
    """Parsed natural YouTube request before target resolution."""

    query: str
    target_text: str
    has_youtube_cue: bool


_YOUTUBE_TERMS = (
    "youtube",
    "you tube",
    "youtu be",
    "youtube com",
)

_DESTINATION_MARKERS = (
    "phat ra",
    "phat tren",
    "phat o",
    "phat vao",
    "phat",
    "mo tren",
    "mo o",
    "mo ra",
    "mo",
    "chieu tren",
    "chieu o",
    "chieu ra",
    "chieu",
    "xem tren",
    "xem o",
    "tren",
    "ra",
    "o",
    "toi",
    "bang",
    "play on",
    "play to",
    "play through",
    "play",
    "open on",
    "open",
    "watch on",
    "on",
)

_QUERY_PREFIXES = (
    "tim kiem tren youtube",
    "tim tren youtube",
    "tim youtube",
    "tim kiem youtube",
    "search youtube for",
    "search youtube",
    "youtube search",
    "mo youtube",
    "bat youtube",
    "phat youtube",
    "xem youtube",
    "youtube",
)

_GENERIC_MEDIA_WORDS = {
    "loa",
    "speaker",
    "tivi",
    "tv",
    "television",
    "may chieu",
    "projector",
    "media player",
    "thiet bi",
}


def has_youtube_cue(text: str) -> bool:
    """Return True when the request explicitly references YouTube."""
    normalized = normalize_text(text)
    return any(term in normalized for term in _YOUTUBE_TERMS)


def _strip_youtube_prefix(raw: str) -> str:
    normalized = normalize_text(raw)
    for prefix in _QUERY_PREFIXES:
        if normalized == prefix:
            return ""
        if normalized.startswith(prefix + " "):
            # Re-find the prefix using normalized words so accents/case in the
            # original request do not matter.
            raw_words = raw.split()
            norm_words = [normalize_text(word) for word in raw_words]
            prefix_words = prefix.split()
            if norm_words[: len(prefix_words)] == prefix_words:
                return " ".join(raw_words[len(prefix_words) :]).strip()
    # YouTube may appear later: "phát nhạc bolero youtube ...".
    cleaned = re.sub(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)\S*", " ", raw, flags=re.I)
    cleaned = re.sub(
        r"(?i)\b(?:trên|tren|từ|tu|from|on)\s+(?:youtube|you\s*tube)\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"(?i)\b(?:youtube|you\s*tube)\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:-")
    cleaned = re.sub(
        r"(?i)^(?:hãy\s+|please\s+)?(?:tìm(?:\s+kiếm)?|search|mở|bật|phát|xem|play|open|watch)\s+",
        "",
        cleaned,
    ).strip(" ,;:-")
    return cleaned


def parse_youtube_request(text: str) -> ParsedYouTubeRequest | None:
    """Parse a natural YouTube request into query and unresolved target text.

    Target resolution is intentionally handled by the manager because it owns
    configured aliases and live Home Assistant entities.
    """
    raw = str(text or "").strip()
    if not raw or not has_youtube_cue(raw):
        return None

    tail = _strip_youtube_prefix(raw)
    if not tail:
        return ParsedYouTubeRequest(query="", target_text="", has_youtube_cue=True)

    normalized = normalize_text(tail)
    # Split on the last destination marker. This keeps phrases such as
    # "nhạc để học tiếng Anh" intact while handling "... phát loa phòng ngủ".
    best: tuple[int, int] | None = None
    for marker in _DESTINATION_MARKERS:
        pattern = rf"(?:^|\s){re.escape(marker)}(?:\s|$)"
        for match in re.finditer(pattern, normalized):
            start = match.start()
            end = match.end()
            if best is None or start > best[0]:
                best = (start, end)
    if best is None:
        return ParsedYouTubeRequest(query=tail.strip(), target_text="", has_youtube_cue=True)

    # Map normalized split position back by word count; normalize_text preserves
    # word boundaries for the Vietnamese/English commands used here.
    norm_left = normalized[: best[0]].strip()
    left_count = len(norm_left.split())
    raw_words = tail.split()
    query = " ".join(raw_words[:left_count]).strip(" ,;:-")
    target = " ".join(raw_words[left_count:]).strip(" ,;:-")

    # Remove the marker from the target side.
    target_norm_words = normalize_text(target).split()
    for marker in sorted(_DESTINATION_MARKERS, key=lambda item: len(item.split()), reverse=True):
        marker_words = marker.split()
        if target_norm_words[: len(marker_words)] == marker_words:
            target = " ".join(target.split()[len(marker_words) :]).strip(" ,;:-")
            break
    return ParsedYouTubeRequest(query=query, target_text=target, has_youtube_cue=True)


def find_target_indexes(text: str, targets: Iterable[YouTubeTarget]) -> list[int]:
    """Return target indexes whose aliases are present in natural text."""
    normalized = f" {normalize_text(text)} "
    matches: list[tuple[int, int]] = []
    for index, target in enumerate(targets):
        best_len = 0
        for alias in target.aliases or (target.display_name,):
            alias_norm = normalize_text(alias)
            if not alias_norm:
                continue
            if f" {alias_norm} " in normalized or normalized.strip() == alias_norm:
                best_len = max(best_len, len(alias_norm.split()))
        if best_len:
            matches.append((best_len, index))
    matches.sort(reverse=True)
    if not matches:
        return []
    longest = matches[0][0]
    return [index for length, index in matches if length == longest]


def strip_target_from_query(query: str, target: YouTubeTarget) -> str:
    """Remove a resolved target alias from the end of a query."""
    raw = str(query or "").strip()
    normalized = normalize_text(raw)
    aliases = sorted(
        (alias for alias in target.aliases if alias),
        key=lambda item: len(normalize_text(item).split()),
        reverse=True,
    )
    for alias in aliases:
        alias_norm = normalize_text(alias)
        if normalized == alias_norm:
            return ""
        if normalized.endswith(" " + alias_norm):
            word_count = len(alias_norm.split())
            return " ".join(raw.split()[:-word_count]).strip(" ,;:-")
    return raw


def normalize_youtube_api_response(response: Any, *, limit: int = 10) -> list[YouTubeVideo]:
    """Normalize pyscript YouTube Data API response into video rows."""
    if not isinstance(response, dict):
        return []
    nested = response.get("response")
    if isinstance(nested, dict) and not response.get("items"):
        response = nested
    items = response.get("items")
    if not isinstance(items, list):
        return []

    videos: list[YouTubeVideo] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        video_id = ""
        if isinstance(item_id, dict):
            video_id = str(item_id.get("videoId", "") or "").strip()
        elif isinstance(item_id, str):
            video_id = item_id.strip()
        if not video_id or video_id in seen:
            continue
        snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
        title = html.unescape(str(snippet.get("title", "") or "").strip())
        channel = html.unescape(str(snippet.get("channelTitle", "") or "").strip())
        thumbnails = snippet.get("thumbnails") if isinstance(snippet.get("thumbnails"), dict) else {}
        thumbnail_url = ""
        for key in ("maxres", "standard", "high", "medium", "default"):
            value = thumbnails.get(key)
            if isinstance(value, dict) and value.get("url"):
                thumbnail_url = str(value["url"])
                break
        if not title:
            title = video_id
        videos.append(
            YouTubeVideo(
                title=title,
                video_id=video_id,
                url=f"https://www.youtube.com/watch?v={video_id}",
                channel=channel,
                thumbnail_url=thumbnail_url,
            )
        )
        seen.add(video_id)
        if len(videos) >= limit:
            break
    return videos


def normalize_native_search_response(response: Any, *, limit: int = 10) -> list[YouTubeVideo]:
    """Normalize media_player.search_media response when it contains YouTube IDs."""
    if not isinstance(response, dict):
        return []
    roots: list[dict[str, Any]] = []
    for value in response.values():
        if isinstance(value, dict):
            roots.append(value)
    if not roots:
        roots = [response]

    videos: list[YouTubeVideo] = []
    seen: set[str] = set()

    def walk(node: Any) -> None:
        if len(videos) >= limit or not isinstance(node, dict):
            return
        media_id = str(node.get("media_content_id", "") or "").strip()
        media_type = str(node.get("media_content_type", "") or "").strip()
        thumbnail = str(
            node.get("thumbnail") or node.get("thumbnail_url") or ""
        ).strip()
        title = html.unescape(str(node.get("title", "") or "").strip())
        video_id = ""
        match = re.search(
            r"(?:[?&]v=|youtu\.be/|youtube\.com/(?:shorts|embed)/)"
            r"([A-Za-z0-9_-]{11})",
            media_id,
            flags=re.I,
        )
        if match:
            video_id = match.group(1)
        else:
            # A bare 11-character ID is ambiguous: many local/media-server
            # integrations use similar IDs. Accept it only when the search
            # result itself contains a clear YouTube hint.
            youtube_hint = any(
                hint in (media_id + " " + media_type + " " + thumbnail).casefold()
                for hint in ("youtube", "youtu.be", "ytimg.com")
            )
            if youtube_hint and re.fullmatch(r"[A-Za-z0-9_-]{11}", media_id):
                video_id = media_id
        if video_id and video_id not in seen:
            videos.append(
                YouTubeVideo(
                    title=title or video_id,
                    video_id=video_id,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                )
            )
            seen.add(video_id)
        children = node.get("children")
        if isinstance(children, list):
            for child in children:
                walk(child)
                if len(videos) >= limit:
                    break

    for root in roots:
        walk(root)
        if len(videos) >= limit:
            break
    return videos


def target_kind_from_device_class(device_class: str) -> str:
    """Classify a media player as speaker, TV, or generic media."""
    value = normalize_text(device_class)
    if value in {"tv", "television", "projector"}:
        return "tv"
    if value in {"speaker", "receiver", "soundbar"}:
        return "speaker"
    return "media"
