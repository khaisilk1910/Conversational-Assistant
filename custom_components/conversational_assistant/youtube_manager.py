"""YouTube search and media playback workflow mixin."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
from time import monotonic
from typing import Any
import uuid

from aiohttp import ClientError

from hassil.recognize import RecognizeResult

from homeassistant.components import persistent_notification
from homeassistant.components.media_player.const import MediaPlayerEntityFeature
from homeassistant.const import ATTR_SUPPORTED_FEATURES, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Context
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import (
    CONF_MEDIA_ENTITY_ID,
    CONF_MEDIA_TARGETS,
    CONF_NAMED_TARGET_ENABLED,
    CONF_NAMED_TARGET_ID,
    CONF_NAMED_TARGET_NAME,
    CONF_SPEAKER_ENTITY_ID,
    CONF_SPEAKER_TARGETS,
    CONF_YOUTUBE_API_KEY,
    DISCOVERY_CACHE_SECONDS,
    MEDIA_EXTRACTOR_DOMAIN,
    MEDIA_EXTRACTOR_SERVICE_PLAY_MEDIA,
    MEDIA_PLAYER_DOMAIN,
    MEDIA_PLAYER_SERVICE_PLAY_MEDIA,
    MEDIA_PLAYER_SERVICE_SEARCH_MEDIA,
    MEDIA_PLAYER_SERVICE_TURN_ON,
    PENDING_CONFIRMATION_TIMEOUT_SECONDS,
    PHICOMM_R1_DOMAIN,
    PHICOMM_R1_SERVICE_PLAY_YOUTUBE,
    YOUTUBE_AUDIO_FORMAT_QUERY,
    YOUTUBE_DATA_API_SEARCH_URL,
    YOUTUBE_MEDIA_SERVICE_TIMEOUT_SECONDS,
    YOUTUBE_SEARCH_RESULT_COUNT,
    YOUTUBE_SEARCH_SERVICE_DOMAIN,
    YOUTUBE_SEARCH_SERVICE_NAME,
    YOUTUBE_SEARCH_TIMEOUT_SECONDS,
    YOUTUBE_SELECTION_TIMEOUT_SECONDS,
    YOUTUBE_SHELL_COMMAND_DOMAIN,
    YOUTUBE_SHELL_COMMAND_SERVICE,
    YOUTUBE_SPEAKER_RETRY_DELAY_SECONDS,
    YOUTUBE_SPEAKER_WAIT_SECONDS,
)
from .named_targets import target_aliases
from .targeting import normalize_text, parse_target_selection
from .youtube_flow import (
    YouTubeTarget,
    YouTubeVideo,
    find_target_indexes,
    has_youtube_cue,
    normalize_native_search_response,
    normalize_youtube_api_response,
    parse_youtube_request,
    strip_target_from_query,
    target_kind_from_device_class,
)
from .youtube_proxy import async_register_youtube_audio_proxy

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PendingYouTubeFlow:
    """One isolated multi-turn YouTube request."""

    pending_id: str
    query: str
    targets: list[YouTubeTarget]
    source_keys: set[str]
    created_at: datetime
    expires_at: datetime
    phase: str = "clarify"
    selected_target: YouTubeTarget | None = None
    videos: list[YouTubeVideo] = field(default_factory=list)
    selected_video: YouTubeVideo | None = None
    zalo_context: Any | None = None


@dataclass(slots=True, frozen=True)
class ResolvedYouTubeAudio:
    """One yt-dlp-selected audio-only stream with playback metadata."""

    stream_url: str
    mime_type: str
    headers: dict[str, str] = field(default_factory=dict)
    extension: str = "m4a"
    format_id: str = ""
    container: str = ""
    acodec: str = ""
    vcodec: str = "none"


class YouTubeManagerMixin:
    """State and actions for searching YouTube and playing results."""

    def _initialize_youtube_state(self) -> None:
        self._zalo_pending_youtube: dict[str, PendingYouTubeFlow] = {}
        self._pending_voice_youtube: dict[str, PendingYouTubeFlow] = {}
        self._youtube_auto_tasks: dict[str, asyncio.Task[Any]] = {}
        self._youtube_busy_tasks: dict[str, asyncio.Task[Any]] = {}
        self._youtube_player_locks: dict[str, asyncio.Lock] = {}
        # Serialize busy-state check + playback decision per media player.
        # The lower-level player lock still protects the actual service calls.
        self._youtube_start_locks: dict[str, asyncio.Lock] = {}
        self._youtube_targets_cache: list[YouTubeTarget] | None = None
        self._youtube_targets_cache_until = 0.0

    async def _async_unload_youtube_state(self) -> None:
        tasks = tuple(self._youtube_auto_tasks.values()) + tuple(
            self._youtube_busy_tasks.values()
        )
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._youtube_auto_tasks.clear()
        self._youtube_busy_tasks.clear()
        self._zalo_pending_youtube.clear()
        self._pending_voice_youtube.clear()
        self._youtube_player_locks.clear()
        self._youtube_start_locks.clear()

    @staticmethod
    def _youtube_is_request(text: str) -> bool:
        return has_youtube_cue(text)

    def _youtube_pending_items(self) -> list[PendingYouTubeFlow]:
        return [
            *self._pending_voice_youtube.values(),
            *self._zalo_pending_youtube.values(),
        ]

    def _youtube_zalo_pending(self, owner_key: str) -> PendingYouTubeFlow | None:
        self._purge_expired_youtube_pending()
        return self._zalo_pending_youtube.get(owner_key)

    def _find_pending_voice_youtube(self, user_input: Any) -> PendingYouTubeFlow | None:
        self._purge_expired_youtube_pending()
        source_keys = self._source_keys(user_input)
        matches = [
            item
            for item in self._pending_voice_youtube.values()
            if source_keys & item.source_keys
        ]
        if len(matches) == 1:
            return matches[0]
        if not source_keys and len(self._pending_voice_youtube) == 1:
            return next(iter(self._pending_voice_youtube.values()))
        return None

    def _purge_expired_youtube_pending(self) -> None:
        now = dt_util.now()
        for owner_key, pending in list(self._zalo_pending_youtube.items()):
            if pending.expires_at <= now:
                self._cancel_youtube_task(pending.pending_id)
                self._zalo_pending_youtube.pop(owner_key, None)
        for pending_id, pending in list(self._pending_voice_youtube.items()):
            if pending.expires_at <= now:
                self._cancel_youtube_task(pending.pending_id)
                self._pending_voice_youtube.pop(pending_id, None)

    def _clear_zalo_youtube_pending(self, owner_key: str) -> bool:
        pending = self._zalo_pending_youtube.pop(owner_key, None)
        if pending is None:
            return False
        self._cancel_youtube_task(pending.pending_id)
        return True

    def _clear_voice_youtube_pending_for_source(self, source_keys: set[str]) -> bool:
        removed = False
        for pending_id, pending in list(self._pending_voice_youtube.items()):
            if source_keys & pending.source_keys:
                self._cancel_youtube_task(pending.pending_id)
                self._pending_voice_youtube.pop(pending_id, None)
                removed = True
        return removed

    def _cancel_youtube_task(self, pending_id: str) -> None:
        for store in (self._youtube_auto_tasks, self._youtube_busy_tasks):
            task = store.pop(pending_id, None)
            if task is not None and task is not asyncio.current_task() and not task.done():
                task.cancel()

    def _remove_youtube_pending(self, pending: PendingYouTubeFlow) -> None:
        self._cancel_youtube_task(pending.pending_id)
        if pending.zalo_context is not None:
            owner_key = str(getattr(pending.zalo_context, "owner_key", "") or "")
            if owner_key and self._zalo_pending_youtube.get(owner_key) is pending:
                self._zalo_pending_youtube.pop(owner_key, None)
        self._pending_voice_youtube.pop(pending.pending_id, None)
        self._sync_pending_followup_trigger()

    def _configured_youtube_targets(self) -> list[YouTubeTarget]:
        """Return named media targets plus named speakers, else lazy discovery."""
        now = monotonic()
        if self._youtube_targets_cache is not None and now < self._youtube_targets_cache_until:
            return list(self._youtube_targets_cache)

        records: list[tuple[dict[str, Any], str, str]] = []
        media = self._configured_named_target_records(CONF_MEDIA_TARGETS, CONF_MEDIA_ENTITY_ID)
        speakers = self._configured_named_target_records(CONF_SPEAKER_TARGETS, CONF_SPEAKER_ENTITY_ID)
        if media is not None:
            records.extend((item, CONF_MEDIA_ENTITY_ID, "media") for item in media)
        if speakers is not None:
            records.extend((item, CONF_SPEAKER_ENTITY_ID, "speaker") for item in speakers)

        targets: list[YouTubeTarget] = []
        seen: set[str] = set()
        registry = er.async_get(self.hass)
        for item, entity_key, forced_kind in records:
            if not bool(item.get(CONF_NAMED_TARGET_ENABLED, True)):
                continue
            entity_id = str(item.get(entity_key, "") or "").strip()
            if not entity_id or entity_id in seen:
                continue
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            name = str(item.get(CONF_NAMED_TARGET_NAME, state.name) or state.name).strip()
            device_class = str(state.attributes.get("device_class", "") or "")
            kind = (
                forced_kind
                if forced_kind == "speaker"
                else target_kind_from_device_class(device_class)
            )
            if kind == "media":
                name_tokens = f" {normalize_text(name)} "
                if " loa " in name_tokens or " speaker " in name_tokens:
                    kind = "speaker"
                elif any(
                    token in name_tokens
                    for token in (" tivi ", " tv ", " television ", " may chieu ", " projector ")
                ):
                    kind = "tv"
            entry = registry.async_get(entity_id)
            platform = str(getattr(entry, "platform", "") or "")
            if platform.casefold() == PHICOMM_R1_DOMAIN:
                kind = "speaker"
            prefixes = (
                ("loa", "speaker") if kind == "speaker" else
                (("tivi", "tv", "television", "máy chiếu", "projector") if kind == "tv" else ("media", "thiết bị"))
            )
            targets.append(
                YouTubeTarget(
                    entity_id=entity_id,
                    display_name=name,
                    aliases=target_aliases(name, prefixes=prefixes),
                    kind=kind,
                    available=state.state not in {STATE_UNAVAILABLE, STATE_UNKNOWN},
                    platform=platform,
                )
            )
            seen.add(entity_id)

        # Discover only target categories that have never been explicitly
        # configured. This preserves the user's explicit lists while keeping
        # legacy installs usable without a migration step. Discovery is lazy.
        discover_media = media is None
        discover_speakers = speakers is None
        if discover_media or discover_speakers:
            for state in sorted(
                self.hass.states.async_all(MEDIA_PLAYER_DOMAIN),
                key=lambda item: (item.name.casefold(), item.entity_id),
            ):
                try:
                    features = int(state.attributes.get(ATTR_SUPPORTED_FEATURES, 0) or 0)
                except (TypeError, ValueError):
                    features = 0
                if state.entity_id in seen:
                    continue
                entry = registry.async_get(state.entity_id)
                platform = str(getattr(entry, "platform", "") or "")
                native_youtube = (
                    platform.casefold() == PHICOMM_R1_DOMAIN
                    and self.hass.services.has_service(
                        PHICOMM_R1_DOMAIN, PHICOMM_R1_SERVICE_PLAY_YOUTUBE
                    )
                )
                if (
                    not features & int(MediaPlayerEntityFeature.PLAY_MEDIA)
                    and not native_youtube
                ):
                    continue
                device_class = str(state.attributes.get("device_class", "") or "")
                kind = (
                    "speaker"
                    if platform.casefold() == PHICOMM_R1_DOMAIN
                    else target_kind_from_device_class(device_class)
                )
                name = str(state.name)
                if kind == "media":
                    name_tokens = f" {normalize_text(name)} "
                    if " loa " in name_tokens or " speaker " in name_tokens:
                        kind = "speaker"
                    elif any(
                        token in name_tokens
                        for token in (
                            " tivi ", " tv ", " television ",
                            " may chieu ", " projector ",
                        )
                    ):
                        kind = "tv"
                if kind == "speaker" and not discover_speakers:
                    continue
                if kind != "speaker" and not discover_media:
                    continue
                prefixes = (
                    ("loa", "speaker") if kind == "speaker" else
                    (("tivi", "tv", "television", "máy chiếu", "projector") if kind == "tv" else ("media", "thiết bị"))
                )
                targets.append(
                    YouTubeTarget(
                        entity_id=state.entity_id,
                        display_name=name,
                        aliases=target_aliases(name, prefixes=prefixes),
                        kind=kind,
                        available=state.state not in {STATE_UNAVAILABLE, STATE_UNKNOWN},
                        platform=platform,
                    )
                )

        self._youtube_targets_cache = targets
        self._youtube_targets_cache_until = now + DISCOVERY_CACHE_SECONDS
        return list(targets)

    @staticmethod
    def _youtube_target_prompt(targets: list[YouTubeTarget], query: str) -> str:
        if not targets:
            return (
                "Không tìm thấy media player hỗ trợ phát media. Hãy thêm loa/TV trong "
                "General settings hoặc kiểm tra entity media_player."
            )
        lines = [f"{i}. {target.display_name}" for i, target in enumerate(targets, start=1)]
        return (
            f"Đã hiểu nội dung cần tìm trên YouTube: **{query or 'chưa rõ'}**.\n"
            "Hãy chọn nơi phát:\n"
            + "\n".join(lines)
            + "\nTrả lời số hoặc tên thiết bị. Gửi **Hủy** để dừng."
        )

    @staticmethod
    def _youtube_clarify_prompt(query: str, target: YouTubeTarget | None) -> str:
        missing: list[str] = []
        if not query:
            missing.append("nội dung/bài/video cần tìm")
        if target is None:
            missing.append("loa, TV hoặc thiết bị cần phát")
        detail = " và ".join(missing) or "thông tin cần thiết"
        return (
            f"Tôi nhận ra yêu cầu YouTube nhưng còn thiếu **{detail}**.\n"
            "Ví dụ: `Tìm YouTube nhạc bolero phát loa Phòng Ngủ` hoặc "
            "`Tìm YouTube dạy tiếng Anh phát TV Phòng Ngủ`.\n"
            "Hãy trả lời tự nhiên; tôi sẽ giữ đúng luồng yêu cầu này trong 120 giây."
        )

    @staticmethod
    def _youtube_video_prompt(videos: list[YouTubeVideo], target: YouTubeTarget) -> str:
        lines = []
        for index, video in enumerate(videos, start=1):
            suffix = f" — {video.channel}" if video.channel else ""
            lines.append(f"{index}. {video.title}{suffix}")
        return (
            f"🔎 **{len(videos)} kết quả YouTube** · phát trên **{target.display_name}**\n"
            + "\n".join(lines)
            + f"\n\nChọn 1-{len(videos)} hoặc nói tên video. Nếu không trả lời trong "
            f"{YOUTUBE_SELECTION_TIMEOUT_SECONDS} giây, tôi sẽ tự phát video số 1. "
            "Gửi **Hủy** để dừng."
        )

    async def _async_native_youtube_search(self, query: str, target: YouTubeTarget) -> list[YouTubeVideo]:
        state = self.hass.states.get(target.entity_id)
        if state is None:
            return []
        try:
            features = int(state.attributes.get(ATTR_SUPPORTED_FEATURES, 0) or 0)
        except (TypeError, ValueError):
            features = 0
        search_feature = int(getattr(MediaPlayerEntityFeature, "SEARCH_MEDIA", 0) or 0)
        if not search_feature or not features & search_feature:
            return []
        if not self.hass.services.has_service(MEDIA_PLAYER_DOMAIN, MEDIA_PLAYER_SERVICE_SEARCH_MEDIA):
            return []
        try:
            response = await self._async_call_service(
                MEDIA_PLAYER_DOMAIN,
                MEDIA_PLAYER_SERVICE_SEARCH_MEDIA,
                {"search_query": query, "media_content_type": "video"},
                blocking=True,
                target={"entity_id": target.entity_id},
                return_response=True,
                timeout_seconds=YOUTUBE_SEARCH_TIMEOUT_SECONDS,
            )
        except Exception:  # noqa: BLE001 - fall back to YouTube Data API tool
            _LOGGER.debug("Native media search failed for %s", target.entity_id, exc_info=True)
            return []
        return normalize_native_search_response(response, limit=YOUTUBE_SEARCH_RESULT_COUNT)

    def _youtube_api_key(self) -> str:
        """Return the API key configured in Conversational Assistant options."""
        return str(self._option(CONF_YOUTUBE_API_KEY, "") or "").strip()

    async def _async_youtube_data_api_search(
        self, query: str
    ) -> tuple[list[YouTubeVideo], str]:
        """Search YouTube Data API directly without blocking Home Assistant.

        The key is kept in the config entry options and is never written to logs.
        A compact error code is returned so concurrent flows keep their own state.
        """
        api_key = self._youtube_api_key()
        if not api_key:
            return [], "missing_api_key"

        session = async_get_clientsession(self.hass)
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": str(YOUTUBE_SEARCH_RESULT_COUNT),
            "order": "relevance",
            "key": api_key,
        }
        try:
            async with asyncio.timeout(YOUTUBE_SEARCH_TIMEOUT_SECONDS):
                async with session.get(
                    YOUTUBE_DATA_API_SEARCH_URL, params=params
                ) as response:
                    try:
                        payload = await response.json(content_type=None)
                    except (ValueError, TypeError):
                        payload = {}
                    if response.status >= 400:
                        reason = ""
                        message = ""
                        if isinstance(payload, dict):
                            error = payload.get("error")
                            if isinstance(error, dict):
                                message = str(
                                    error.get("message", "") or ""
                                )
                                error_items = error.get("errors")
                                if (
                                    isinstance(error_items, list)
                                    and error_items
                                    and isinstance(error_items[0], dict)
                                ):
                                    reason = str(
                                        error_items[0].get("reason", "")
                                        or ""
                                    )
                        normalized_reason = reason.casefold()
                        normalized_message = message.casefold()
                        combined = normalized_reason + " " + normalized_message
                        if response.status == 403 and (
                            "quota" in combined
                            or "dailylimit" in combined
                        ):
                            return [], "api_quota"
                        if response.status in {400, 401, 403} and any(
                            marker in combined
                            for marker in (
                                "keyinvalid",
                                "api key",
                                "accessnotconfigured",
                                "iprefererblocked",
                                "forbidden",
                            )
                        ):
                            return [], "api_key_rejected"
                        _LOGGER.warning(
                            "YouTube Data API search failed with HTTP %s",
                            response.status,
                        )
                        return [], f"api_http_{response.status}"
        except TimeoutError:
            _LOGGER.warning("YouTube Data API search timed out")
            return [], "api_timeout"
        except ClientError as err:
            _LOGGER.warning(
                "YouTube Data API network error: %s", type(err).__name__
            )
            return [], "api_network"
        except Exception:  # noqa: BLE001 - preserve legacy fallback
            _LOGGER.exception("Unexpected YouTube Data API search error")
            return [], "api_error"

        videos = normalize_youtube_api_response(
            payload, limit=YOUTUBE_SEARCH_RESULT_COUNT
        )
        return videos, "" if videos else "api_empty"

    async def _async_youtube_search(
        self, query: str, target: YouTubeTarget
    ) -> tuple[list[YouTubeVideo], list[str]]:
        """Search native media, integration API key, then legacy Pyscript."""
        native = await self._async_native_youtube_search(query, target)
        videos = list(native)
        seen = {item.video_id for item in videos}
        errors: list[str] = []
        if len(videos) >= YOUTUBE_SEARCH_RESULT_COUNT:
            return videos[:YOUTUBE_SEARCH_RESULT_COUNT], errors

        api_videos, api_error = await self._async_youtube_data_api_search(query)
        if api_error:
            errors.append(api_error)
        for item in api_videos:
            if item.video_id in seen:
                continue
            videos.append(item)
            seen.add(item.video_id)
            if len(videos) >= YOUTUBE_SEARCH_RESULT_COUNT:
                return videos[:YOUTUBE_SEARCH_RESULT_COUNT], errors

        # Backward compatibility: an existing Pyscript helper may still have
        # its own youtube_api_key in pyscript.config. It is no longer required
        # when the key is configured in Conversational Assistant options.
        if not self.hass.services.has_service(
            YOUTUBE_SEARCH_SERVICE_DOMAIN, YOUTUBE_SEARCH_SERVICE_NAME
        ):
            return videos, errors
        try:
            response = await self._async_call_service(
                YOUTUBE_SEARCH_SERVICE_DOMAIN,
                YOUTUBE_SEARCH_SERVICE_NAME,
                {
                    "query": query,
                    "search_type": ["video"],
                    "results": YOUTUBE_SEARCH_RESULT_COUNT,
                },
                blocking=True,
                return_response=True,
                timeout_seconds=YOUTUBE_SEARCH_TIMEOUT_SECONDS,
            )
        except Exception:
            _LOGGER.exception("Legacy Pyscript YouTube search service failed")
            errors.append("pyscript_error")
            return videos, errors
        if isinstance(response, dict) and response.get("error"):
            errors.append("pyscript_error")
        for item in normalize_youtube_api_response(
            response, limit=YOUTUBE_SEARCH_RESULT_COUNT
        ):
            if item.video_id in seen:
                continue
            videos.append(item)
            seen.add(item.video_id)
            if len(videos) >= YOUTUBE_SEARCH_RESULT_COUNT:
                break
        return videos, errors

    @staticmethod
    def _youtube_search_failure_message(errors: list[str]) -> str:
        """Return an actionable failure without exposing credentials."""
        if "api_quota" in errors:
            return (
                "Không lấy được kết quả YouTube vì quota YouTube Data API đã hết "
                "hoặc đang bị giới hạn. Hãy kiểm tra quota Google Cloud rồi thử lại."
            )
        if "api_key_rejected" in errors:
            return (
                "YouTube Data API đã từ chối API key. Hãy vào **Conversational "
                "Assistant → Configure → YouTube Settings** để kiểm tra "
                "`youtube_api_key`, đồng thời bảo đảm YouTube Data API v3 đã được "
                "bật cho project."
            )
        if "missing_api_key" in errors:
            return (
                "Không có nguồn tìm kiếm YouTube đủ tin cậy. Hãy vào "
                "**Conversational Assistant → Configure → YouTube Settings** và nhập "
                "`youtube_api_key`. Nếu media player tự hỗ trợ tìm YouTube hoặc "
                "Pyscript đã có key riêng thì integration vẫn có thể dùng nguồn đó."
            )
        if "api_timeout" in errors or "api_network" in errors:
            return (
                "Không kết nối được YouTube Data API lúc này. Hãy kiểm tra Internet/DNS "
                "của Home Assistant rồi thử lại."
            )
        return (
            "Không lấy được kết quả YouTube. Hãy kiểm tra **YouTube Settings**, "
            "kết nối Internet và quyền truy cập YouTube Data API v3."
        )

    def _new_youtube_pending(
        self,
        query: str,
        targets: list[YouTubeTarget],
        *,
        source_keys: set[str] | None = None,
        zalo_context: Any | None = None,
    ) -> PendingYouTubeFlow:
        now = dt_util.now()
        return PendingYouTubeFlow(
            pending_id=uuid.uuid4().hex,
            query=query.strip(),
            targets=targets,
            source_keys=source_keys or set(),
            created_at=now,
            expires_at=now + timedelta(seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS),
            zalo_context=zalo_context,
        )

    async def _async_prepare_youtube_results(self, pending: PendingYouTubeFlow) -> str:
        target = pending.selected_target
        if target is None:
            return self._youtube_target_prompt(pending.targets, pending.query)
        if not pending.query:
            pending.phase = "clarify"
            return self._youtube_clarify_prompt(pending.query, target)
        videos, search_errors = await self._async_youtube_search(
            pending.query, target
        )
        if not videos:
            pending.phase = "clarify"
            return self._youtube_search_failure_message(search_errors)
        pending.videos = videos
        pending.phase = "video"
        pending.expires_at = dt_util.now() + timedelta(seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS)
        self._schedule_youtube_auto_first(pending)
        return self._youtube_video_prompt(videos, target)

    def _schedule_youtube_auto_first(self, pending: PendingYouTubeFlow) -> None:
        old = self._youtube_auto_tasks.pop(pending.pending_id, None)
        if old is not None and not old.done():
            old.cancel()
        task = self.hass.async_create_task(self._async_youtube_auto_first(pending))
        self._youtube_auto_tasks[pending.pending_id] = task

        def done(done_task: asyncio.Task[Any]) -> None:
            if self._youtube_auto_tasks.get(pending.pending_id) is done_task:
                self._youtube_auto_tasks.pop(pending.pending_id, None)
            if done_task.cancelled():
                return
            try:
                done_task.result()
            except Exception:
                _LOGGER.exception("Automatic YouTube first-result task failed")

        task.add_done_callback(done)

    async def _async_youtube_auto_first(self, pending: PendingYouTubeFlow) -> None:
        await asyncio.sleep(YOUTUBE_SELECTION_TIMEOUT_SECONDS)
        if pending.phase != "video" or not pending.videos:
            return
        pending.selected_video = pending.videos[0]
        message = await self._async_start_youtube_playback(
            pending, pending.videos[0], automatic=True
        )
        if message:
            await self._async_youtube_background_notice(pending, message)

    @staticmethod
    def _youtube_is_busy(target: YouTubeTarget, state: Any) -> bool:
        if target.kind != "speaker" or state is None:
            return False
        return str(state.state or "").casefold() in {"playing", "buffering"}

    async def _async_start_youtube_playback(
        self,
        pending: PendingYouTubeFlow,
        video: YouTubeVideo,
        *,
        automatic: bool = False,
        force: bool = False,
    ) -> str:
        target = pending.selected_target
        if target is None:
            return "Chưa xác định thiết bị phát YouTube."

        decision_lock = self._youtube_start_locks.setdefault(
            target.entity_id, asyncio.Lock()
        )
        async with decision_lock:
            state = self.hass.states.get(target.entity_id)
            if state is None or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
                self._remove_youtube_pending(pending)
                return f"⚠️ {target.display_name} hiện không khả dụng hoặc mất kết nối."
            if self._youtube_is_busy(target, state) and not force:
                pending.phase = "busy"
                pending.selected_video = video
                pending.expires_at = dt_util.now() + timedelta(
                    seconds=YOUTUBE_SPEAKER_WAIT_SECONDS + 30
                )
                self._schedule_youtube_busy_wait(pending)
                auto = " Video số 1 đã được tự chọn." if automatic else ""
                return (
                    f"🔊 **{target.display_name} đang bận** ({state.state}).{auto}\n"
                    "Bạn có muốn **phát đè** ngay không? Trả lời `Có`/`Phát đè` "
                    "để phát ngay. Nếu trả lời `Không` hoặc không trả lời, tôi sẽ "
                    "chờ loa rảnh tối đa 10 phút rồi tự phát."
                )
            try:
                play_method = await self._async_play_youtube_video(target, video)
                _LOGGER.debug(
                    "YouTube playback confirmed on %s via %s",
                    target.entity_id,
                    play_method,
                )
            except Exception as err:  # noqa: BLE001 - user needs a clear failure
                _LOGGER.exception("Failed playing YouTube on %s", target.entity_id)
                self._remove_youtube_pending(pending)
                return (
                    f"⚠️ Không phát được **{video.title}** trên "
                    f"**{target.display_name}**: {err}"
                )

        self._remove_youtube_pending(pending)
        prefix = "Đã tự chọn video số 1 và " if automatic else "Đã "
        return (
            f"▶️ {prefix}phát **{video.title}** trên **{target.display_name}**."
        )

    def _schedule_youtube_busy_wait(self, pending: PendingYouTubeFlow) -> None:
        old = self._youtube_busy_tasks.pop(pending.pending_id, None)
        if old is not None and not old.done():
            old.cancel()
        task = self.hass.async_create_task(self._async_youtube_wait_for_speaker(pending))
        self._youtube_busy_tasks[pending.pending_id] = task

        def done(done_task: asyncio.Task[Any]) -> None:
            if self._youtube_busy_tasks.get(pending.pending_id) is done_task:
                self._youtube_busy_tasks.pop(pending.pending_id, None)
            if done_task.cancelled():
                return
            try:
                done_task.result()
            except Exception:
                _LOGGER.exception("YouTube speaker wait task failed")

        task.add_done_callback(done)

    async def _async_youtube_wait_for_speaker(
        self, pending: PendingYouTubeFlow
    ) -> None:
        target = pending.selected_target
        video = pending.selected_video
        if target is None or video is None:
            return
        deadline = monotonic() + YOUTUBE_SPEAKER_WAIT_SECONDS
        decision_lock = self._youtube_start_locks.setdefault(
            target.entity_id, asyncio.Lock()
        )
        while monotonic() < deadline:
            async with decision_lock:
                state = self.hass.states.get(target.entity_id)
                if state is None or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
                    message = (
                        f"⚠️ {target.display_name} mất kết nối; đã hủy phát YouTube."
                    )
                    self._remove_youtube_pending(pending)
                    await self._async_youtube_background_notice(pending, message)
                    return
                if not self._youtube_is_busy(target, state):
                    try:
                        play_method = await self._async_play_youtube_video(target, video)
                        _LOGGER.debug(
                            "Waited YouTube playback confirmed on %s via %s",
                            target.entity_id,
                            play_method,
                        )
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.exception(
                            "Failed playing waited YouTube request on %s",
                            target.entity_id,
                        )
                        self._remove_youtube_pending(pending)
                        await self._async_youtube_background_notice(
                            pending,
                            f"⚠️ Không phát được **{video.title}** trên "
                            f"**{target.display_name}**: {err}",
                        )
                        return
                    self._remove_youtube_pending(pending)
                    await self._async_youtube_background_notice(
                        pending,
                        f"▶️ Loa đã rảnh. Đã phát **{video.title}** trên "
                        f"**{target.display_name}**.",
                    )
                    return
            await asyncio.sleep(YOUTUBE_SPEAKER_RETRY_DELAY_SECONDS)

        self._remove_youtube_pending(pending)
        message = (
            f"⌛ {target.display_name} vẫn bận sau 10 phút nên đã hủy phát "
            f"YouTube **{video.title}**."
        )
        await self._async_youtube_background_notice(pending, message)

    async def _async_youtube_background_notice(self, pending: PendingYouTubeFlow, message: str) -> None:
        if pending.zalo_context is not None:
            await self._async_send_zalo_webhook_reply(pending.zalo_context, message)
            return
        delivered = await self._async_send_first_configured_zalo_message(
            "🎬 **YouTube từ Voice Assist**\n\n" + message
        )
        if not delivered:
            persistent_notification.async_create(
                self.hass,
                message,
                title="Conversational Assistant - YouTube",
                notification_id=f"conversational_assistant_youtube_{pending.pending_id}",
            )

    def _youtube_playback_signature(self, entity_id: str) -> tuple[str, str, str, str, str]:
        """Return a compact state signature used to verify real playback."""
        state = self.hass.states.get(entity_id)
        if state is None:
            return ("", "", "", "", "")
        attrs = state.attributes
        return (
            str(state.state or "").casefold(),
            str(attrs.get("media_content_id", "") or ""),
            str(attrs.get("media_title", "") or ""),
            str(attrs.get("app_id", "") or ""),
            str(attrs.get("app_name", "") or ""),
        )

    async def _async_wait_youtube_speaker_started(
        self,
        target: YouTubeTarget,
        before: tuple[str, str, str, str, str],
        *,
        timeout_seconds: float = 10.0,
    ) -> bool:
        """Verify that a speaker actually entered playback after an action.

        Home Assistant service calls can return successfully before a media player
        has accepted the stream.  Media Extractor also schedules the underlying
        media_player.play_media call asynchronously, so a successful service call
        alone is not proof that sound started.
        """
        deadline = monotonic() + max(1.0, timeout_seconds)
        before_was_active = before[0] in {"playing", "buffering"}
        while monotonic() < deadline:
            state = self.hass.states.get(target.entity_id)
            if state is None or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
                return False
            current = self._youtube_playback_signature(target.entity_id)
            if current[0] in {"playing", "buffering"}:
                if not before_was_active:
                    return True
                if current[1:] != before[1:]:
                    return True
                # A force/overwrite request can remain in PLAYING throughout and
                # some integrations do not expose media title/content id.  If the
                # player is still active after a short settling period, accept it.
                if monotonic() + 7.0 >= deadline:
                    return True
            await asyncio.sleep(0.5)
        return False

    @staticmethod
    def _youtube_audio_mime(info: dict[str, Any]) -> str:
        """Choose a concrete MIME type for a yt-dlp audio-only stream."""
        mime = str(info.get("mime_type", "") or "").strip().casefold()
        if mime.startswith("audio/"):
            return mime
        ext = str(info.get("ext", "") or "").strip().casefold()
        acodec = str(info.get("acodec", "") or "").strip().casefold()
        if ext in {"m4a", "mp4"} or acodec.startswith("mp4a"):
            return "audio/mp4"
        if ext == "webm" or "opus" in acodec:
            return "audio/webm"
        if ext == "mp3" or "mp3" in acodec:
            return "audio/mpeg"
        if ext in {"ogg", "oga", "opus"}:
            return "audio/ogg"
        if ext == "aac" or "aac" in acodec:
            return "audio/aac"
        return "audio/mp4"

    async def _async_extract_youtube_audio_stream(
        self, video_url: str
    ) -> ResolvedYouTubeAudio | None:
        """Resolve and validate a real audio-only YouTube stream with yt-dlp.

        yt-dlp copies the selected format back into the final info dictionary,
        including ``url``, codecs, container and calculated HTTP headers.  Keep
        all of that information instead of throwing everything away except the
        URL; several legacy speakers need the headers or a conventional media
        suffix to accept Googlevideo audio streams.
        """
        config_dir = self.hass.config.config_dir

        def extract() -> ResolvedYouTubeAudio | None:
            try:
                from yt_dlp import YoutubeDL
            except ImportError:
                return None

            options: dict[str, Any] = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "format": YOUTUBE_AUDIO_FORMAT_QUERY,
                "socket_timeout": 20,
                "retries": 2,
                "fragment_retries": 1,
            }
            cookies_file = Path(config_dir, "media_extractor", "cookies.txt")
            if cookies_file.exists():
                options["cookiefile"] = str(cookies_file)
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(video_url, download=False)
            if not isinstance(info, dict):
                return None
            entries = info.get("entries")
            if isinstance(entries, list) and entries:
                first = entries[0]
                if isinstance(first, dict):
                    info = first

            stream_url = str(info.get("url", "") or "").strip()
            if not stream_url.startswith(("http://", "https://")):
                return None

            # Do not trust the format expression alone.  Explicitly reject a
            # muxed/video format before ever handing it to an audio-only target.
            acodec = str(info.get("acodec", "") or "").strip().casefold()
            vcodec = str(info.get("vcodec", "") or "").strip().casefold()
            if not acodec or acodec == "none":
                return None
            if vcodec and vcodec != "none":
                _LOGGER.debug(
                    "Rejected non-audio-only yt-dlp format %s (vcodec=%s)",
                    info.get("format_id"),
                    vcodec,
                )
                return None

            raw_headers = info.get("http_headers")
            headers = (
                {str(key): str(value) for key, value in raw_headers.items() if value}
                if isinstance(raw_headers, Mapping)
                else {}
            )
            extension = str(info.get("ext", "") or "m4a").strip().casefold()
            return ResolvedYouTubeAudio(
                stream_url=stream_url,
                mime_type=self._youtube_audio_mime(info),
                headers=headers,
                extension=extension,
                format_id=str(info.get("format_id", "") or ""),
                container=str(info.get("container", "") or ""),
                acodec=acodec,
                vcodec=vcodec or "none",
            )

        try:
            async with asyncio.timeout(YOUTUBE_MEDIA_SERVICE_TIMEOUT_SECONDS):
                return await self.hass.async_add_executor_job(extract)
        except TimeoutError:
            _LOGGER.warning("Timed out resolving a YouTube audio-only stream")
        except Exception:  # noqa: BLE001 - continue to compatibility fallbacks
            _LOGGER.debug("Direct yt-dlp YouTube audio extraction failed", exc_info=True)
        return None

    async def _async_extract_youtube_audio_stream_shell(
        self, video_id: str
    ) -> ResolvedYouTubeAudio | None:
        """Use an optional user-defined shell_command.youtube_stream fallback.

        This directly supports the user's proven YAML pattern:
        ``yt-dlp -f 140 -g https://www.youtube.com/watch?v={{ video_id }}``.
        The command is optional; the integration does not require configuration
        YAML when the bundled Python yt-dlp path works.
        """
        if not self.hass.services.has_service(
            YOUTUBE_SHELL_COMMAND_DOMAIN, YOUTUBE_SHELL_COMMAND_SERVICE
        ):
            return None
        try:
            response = await self._async_call_service(
                YOUTUBE_SHELL_COMMAND_DOMAIN,
                YOUTUBE_SHELL_COMMAND_SERVICE,
                {"video_id": video_id},
                blocking=True,
                return_response=True,
                timeout_seconds=min(55, YOUTUBE_MEDIA_SERVICE_TIMEOUT_SECONDS),
            )
        except Exception:  # noqa: BLE001
            _LOGGER.debug("shell_command.youtube_stream failed", exc_info=True)
            return None
        if not isinstance(response, dict):
            return None
        try:
            returncode = int(response.get("returncode", 1))
        except (TypeError, ValueError):
            returncode = 1
        if returncode != 0:
            _LOGGER.debug(
                "shell_command.youtube_stream returned code %s", returncode
            )
            return None
        stdout = str(response.get("stdout", "") or "")
        for line in stdout.splitlines():
            candidate = line.strip()
            if candidate.startswith(("http://", "https://")):
                # The documented/example command forces YouTube itag 140, which
                # is M4A/AAC.  Keep the semantic media type as ``music`` when
                # sending it to the player; the MIME is only a fallback.
                return ResolvedYouTubeAudio(
                    stream_url=candidate,
                    mime_type="audio/mp4",
                    extension="m4a",
                    format_id="140",
                    container="m4a_dash",
                    acodec="mp4a",
                    vcodec="none",
                )
        return None

    @staticmethod
    def _youtube_state_mapping_video_id(value: Any) -> str:
        """Return a YouTube id from a media-player state mapping when present."""
        if not isinstance(value, dict):
            return ""
        for key in ("video_id", "id", "media_id"):
            candidate = str(value.get(key, "") or "").strip()
            if candidate:
                return candidate
        return ""

    def _youtube_phicomm_reports_video(
        self, entity_id: str, video_id: str
    ) -> bool:
        """Confirm Phicomm R1 accepted the selected YouTube video."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
            return False
        attrs = state.attributes
        last_play = attrs.get("last_music_play")
        if isinstance(last_play, dict):
            source = str(last_play.get("source", "") or "").casefold()
            if (
                self._youtube_state_mapping_video_id(last_play) == video_id
                and (not source or "youtube" in source)
            ):
                return True
        playback = attrs.get("aibox_playback")
        if isinstance(playback, dict):
            source = str(playback.get("source", "") or "").casefold()
            playback_state = str(
                playback.get("state", playback.get("play_state", "")) or ""
            ).casefold()
            is_playing = bool(playback.get("is_playing")) or playback_state in {
                "1",
                "play",
                "playing",
            }
            if (
                self._youtube_state_mapping_video_id(playback) == video_id
                and "youtube" in source
                and is_playing
            ):
                return True
        return False

    async def _async_play_youtube_platform_native(
        self,
        target: YouTubeTarget,
        video: YouTubeVideo,
        attempts: list[str],
    ) -> str | None:
        """Prefer a platform's native YouTube action when it exposes one.

        Phicomm R1 is the important case: its current custom integration exposes
        ``phicomm_r1.play_youtube(video_id=...)`` and routes the video id through
        the speaker's AiboxPlus WebSocket API.  That is fundamentally more
        compatible than handing an expiring Googlevideo URL to a legacy player.
        """
        platform = str(target.platform or "").strip().casefold()
        if platform != PHICOMM_R1_DOMAIN:
            return None
        if not self.hass.services.has_service(
            PHICOMM_R1_DOMAIN, PHICOMM_R1_SERVICE_PLAY_YOUTUBE
        ):
            attempts.append("phicomm_r1.play_youtube:unavailable")
            return None

        try:
            await self._async_call_service(
                PHICOMM_R1_DOMAIN,
                PHICOMM_R1_SERVICE_PLAY_YOUTUBE,
                {"video_id": video.video_id},
                blocking=True,
                target={"entity_id": target.entity_id},
                timeout_seconds=YOUTUBE_MEDIA_SERVICE_TIMEOUT_SECONDS,
            )
        except Exception as err:  # noqa: BLE001
            attempts.append(
                f"phicomm_r1.play_youtube:{type(err).__name__}"
            )
            _LOGGER.debug(
                "Native Phicomm R1 YouTube playback failed for %s",
                target.entity_id,
                exc_info=True,
            )
            return None

        deadline = monotonic() + 12.0
        while monotonic() < deadline:
            if self._youtube_phicomm_reports_video(
                target.entity_id, video.video_id
            ):
                return "phicomm_r1.play_youtube"
            await asyncio.sleep(0.5)
        attempts.append("phicomm_r1.play_youtube:no_confirmation")
        return None

    async def _async_play_youtube_audio_url(
        self,
        target: YouTubeTarget,
        stream_url: str,
        mime_type: str,
        *,
        label: str,
        attempts: list[str],
    ) -> str | None:
        """Send a direct audio URL to a speaker using compatible content types.

        Many legacy/custom media_player integrations branch on the semantic
        Home Assistant type ``music`` and do not accept ``audio/mp4`` even when
        the URL itself is an M4A stream.  Therefore ``music`` is deliberately
        tried first, matching the working Home Assistant YAML supplied by the
        user, and the concrete MIME type is used only as a second attempt.
        """
        if not self.hass.services.has_service(
            MEDIA_PLAYER_DOMAIN, MEDIA_PLAYER_SERVICE_PLAY_MEDIA
        ):
            attempts.append(f"{label}:play_media_unavailable")
            return None

        content_types = ["music"]
        normalized_mime = str(mime_type or "").strip().casefold()
        if normalized_mime and normalized_mime != "music":
            content_types.append(normalized_mime)

        for content_type in content_types:
            before = self._youtube_playback_signature(target.entity_id)
            try:
                await self._async_call_service(
                    MEDIA_PLAYER_DOMAIN,
                    MEDIA_PLAYER_SERVICE_PLAY_MEDIA,
                    {
                        "media_content_id": stream_url,
                        "media_content_type": content_type,
                    },
                    blocking=True,
                    target={"entity_id": target.entity_id},
                    timeout_seconds=YOUTUBE_MEDIA_SERVICE_TIMEOUT_SECONDS,
                )
                if await self._async_wait_youtube_speaker_started(
                    target, before, timeout_seconds=12.0
                ):
                    return f"{label}:{content_type}"
                attempts.append(f"{label}:{content_type}:no_state_change")
            except Exception as err:  # noqa: BLE001
                attempts.append(f"{label}:{content_type}:{type(err).__name__}")
                _LOGGER.debug(
                    "Direct YouTube audio playback failed for %s via %s/%s",
                    target.entity_id,
                    label,
                    content_type,
                    exc_info=True,
                )
        return None

    async def _async_play_youtube_speaker(
        self, target: YouTubeTarget, video: YouTubeVideo
    ) -> str:
        """Play YouTube on an audio target using the most compatible path.

        Native speaker integrations win when they expose their own YouTube
        action.  Generic speakers then receive a signed Home Assistant proxy URL
        for a yt-dlp-validated audio-only stream.  The proxy preserves yt-dlp's
        calculated request headers and Range semantics and gives older players a
        conventional .m4a/.webm suffix.
        """
        attempts: list[str] = []

        # 0) Platform-native playback. Phicomm R1 has a dedicated entity service
        # that sends the YouTube video id to AiboxPlus; do not force this device
        # through media_player.play_media when its own API is available.
        native_method = await self._async_play_youtube_platform_native(
            target, video, attempts
        )
        if native_method:
            return native_method

        state = self.hass.states.get(target.entity_id)
        if (
            state is not None
            and str(state.state or "").casefold() == "off"
            and self.hass.services.has_service(
                MEDIA_PLAYER_DOMAIN, MEDIA_PLAYER_SERVICE_TURN_ON
            )
        ):
            try:
                await self._async_call_service(
                    MEDIA_PLAYER_DOMAIN,
                    MEDIA_PLAYER_SERVICE_TURN_ON,
                    {},
                    blocking=True,
                    target={"entity_id": target.entity_id},
                    timeout_seconds=min(15, YOUTUBE_MEDIA_SERVICE_TIMEOUT_SECONDS),
                )
                await asyncio.sleep(0.5)
            except Exception:
                _LOGGER.debug(
                    "Could not explicitly turn on YouTube speaker %s",
                    target.entity_id,
                    exc_info=True,
                )

        # 1) Resolve a real audio-only stream with yt-dlp.  The attached yt-dlp
        # source shows that selected format headers/container/codecs are copied
        # into the final info dict; retain and use those values.
        audio_stream = await self._async_extract_youtube_audio_stream(video.url)
        if audio_stream:
            attempts.append(
                "yt_dlp:"
                f"{audio_stream.format_id or '?'}:"
                f"{audio_stream.container or audio_stream.extension}:"
                f"{audio_stream.acodec}"
            )
            # Prefer a signed HA URL over exposing Googlevideo directly. This is
            # especially useful for old speakers that probe a suffix or issue
            # byte-range requests and cannot reproduce yt-dlp's HTTP headers.
            try:
                proxy_url = async_register_youtube_audio_proxy(
                    self.hass,
                    stream_url=audio_stream.stream_url,
                    mime_type=audio_stream.mime_type,
                    headers=audio_stream.headers,
                    extension=audio_stream.extension,
                )
            except Exception as err:  # noqa: BLE001
                attempts.append(f"ha_audio_proxy:create:{type(err).__name__}")
                _LOGGER.debug(
                    "Could not create Home Assistant YouTube audio proxy",
                    exc_info=True,
                )
            else:
                method = await self._async_play_youtube_audio_url(
                    target,
                    proxy_url,
                    audio_stream.mime_type,
                    label="ha_audio_proxy",
                    attempts=attempts,
                )
                if method:
                    return method

            # Keep direct Googlevideo as a compatibility fallback for speakers
            # that already understand the upstream URL.
            method = await self._async_play_youtube_audio_url(
                target,
                audio_stream.stream_url,
                audio_stream.mime_type,
                label="yt_dlp_audio_direct",
                attempts=attempts,
            )
            if method:
                return method
        else:
            attempts.append("yt_dlp_audio:no_url")

        # 2) Exact compatibility fallback for an existing
        # shell_command.youtube_stream using ``yt-dlp -f 140 -g``.
        shell_stream = await self._async_extract_youtube_audio_stream_shell(
            video.video_id
        )
        if shell_stream:
            try:
                proxy_url = async_register_youtube_audio_proxy(
                    self.hass,
                    stream_url=shell_stream.stream_url,
                    mime_type=shell_stream.mime_type,
                    headers=shell_stream.headers,
                    extension=shell_stream.extension,
                )
            except Exception as err:  # noqa: BLE001
                attempts.append(f"shell_audio_proxy:create:{type(err).__name__}")
            else:
                method = await self._async_play_youtube_audio_url(
                    target,
                    proxy_url,
                    shell_stream.mime_type,
                    label="shell_audio_proxy",
                    attempts=attempts,
                )
                if method:
                    return method
            method = await self._async_play_youtube_audio_url(
                target,
                shell_stream.stream_url,
                shell_stream.mime_type,
                label="shell_yt_dlp_audio_direct",
                attempts=attempts,
            )
            if method:
                return method
        elif self.hass.services.has_service(
            YOUTUBE_SHELL_COMMAND_DOMAIN, YOUTUBE_SHELL_COMMAND_SERVICE
        ):
            attempts.append("shell_yt_dlp_audio:no_url")

        # 3) Late Home Assistant fallback. Media Extractor can choose a muxed
        # YouTube format, so it is deliberately behind the audio-only paths.
        if self.hass.services.has_service(
            MEDIA_EXTRACTOR_DOMAIN, MEDIA_EXTRACTOR_SERVICE_PLAY_MEDIA
        ):
            before = self._youtube_playback_signature(target.entity_id)
            try:
                await self._async_call_service(
                    MEDIA_EXTRACTOR_DOMAIN,
                    MEDIA_EXTRACTOR_SERVICE_PLAY_MEDIA,
                    {
                        "media_content_id": video.url,
                        "media_content_type": "music",
                    },
                    blocking=True,
                    target={"entity_id": target.entity_id},
                    timeout_seconds=YOUTUBE_MEDIA_SERVICE_TIMEOUT_SECONDS,
                )
                if await self._async_wait_youtube_speaker_started(
                    target, before, timeout_seconds=10.0
                ):
                    return "media_extractor.play_media"
                attempts.append("media_extractor.play_media:no_state_change")
            except Exception as err:  # noqa: BLE001
                attempts.append(f"media_extractor.play_media:{type(err).__name__}")

        # 4) A few integrations accept a YouTube page URL directly.
        if self.hass.services.has_service(
            MEDIA_PLAYER_DOMAIN, MEDIA_PLAYER_SERVICE_PLAY_MEDIA
        ):
            before = self._youtube_playback_signature(target.entity_id)
            try:
                await self._async_call_service(
                    MEDIA_PLAYER_DOMAIN,
                    MEDIA_PLAYER_SERVICE_PLAY_MEDIA,
                    {
                        "media_content_id": video.url,
                        "media_content_type": "music",
                    },
                    blocking=True,
                    target={"entity_id": target.entity_id},
                    timeout_seconds=YOUTUBE_MEDIA_SERVICE_TIMEOUT_SECONDS,
                )
                if await self._async_wait_youtube_speaker_started(
                    target, before, timeout_seconds=8.0
                ):
                    return "media_player.youtube_url"
                attempts.append("media_player.youtube_url:no_state_change")
            except Exception as err:  # noqa: BLE001
                attempts.append(f"media_player.youtube_url:{type(err).__name__}")

        detail = ", ".join(attempts[-10:]) or "no supported playback action"
        raise RuntimeError(
            "không xác nhận được loa đã bắt đầu phát; đã thử native YouTube, "
            "audio-only qua Home Assistant proxy và các fallback "
            f"({detail})"
        )

    async def _async_play_youtube_video(self, target: YouTubeTarget, video: YouTubeVideo) -> str:
        """Play using native TV methods; speakers use verified audio playback."""
        lock = self._youtube_player_locks.setdefault(target.entity_id, asyncio.Lock())
        async with lock:
            platform = normalize_text(target.platform)
            if (
                target.kind == "tv"
                and self.hass.services.has_service(
                    MEDIA_PLAYER_DOMAIN, MEDIA_PLAYER_SERVICE_TURN_ON
                )
            ):
                try:
                    await self._async_call_service(
                        MEDIA_PLAYER_DOMAIN,
                        MEDIA_PLAYER_SERVICE_TURN_ON,
                        {},
                        blocking=True,
                        target={"entity_id": target.entity_id},
                        timeout_seconds=YOUTUBE_MEDIA_SERVICE_TIMEOUT_SECONDS,
                    )
                except Exception:
                    # Some platforms report a turn-on action but reject it;
                    # play_media may still wake/start the app, so continue.
                    _LOGGER.debug(
                        "Could not turn on YouTube TV target %s",
                        target.entity_id,
                        exc_info=True,
                    )
            # Native methods mirror the supplied Voice Assist blueprint for
            # Cast, Android TV/Google TV and Apple TV.
            if target.kind == "tv" and self.hass.services.has_service(MEDIA_PLAYER_DOMAIN, MEDIA_PLAYER_SERVICE_PLAY_MEDIA):
                try:
                    if platform == "cast":
                        await self._async_call_service(
                            MEDIA_PLAYER_DOMAIN,
                            MEDIA_PLAYER_SERVICE_PLAY_MEDIA,
                            {
                                "media_content_type": "cast",
                                "media_content_id": json.dumps({"app_name": "youtube", "media_id": video.video_id}),
                            },
                            blocking=True,
                            target={"entity_id": target.entity_id},
                            timeout_seconds=YOUTUBE_MEDIA_SERVICE_TIMEOUT_SECONDS,
                        )
                        return "tv_cast_youtube"
                    if platform == "androidtv remote" or platform == "androidtv_remote":
                        await self._async_call_service(
                            MEDIA_PLAYER_DOMAIN,
                            MEDIA_PLAYER_SERVICE_PLAY_MEDIA,
                            {"media_content_type": "url", "media_content_id": video.url},
                            blocking=True,
                            target={"entity_id": target.entity_id},
                            timeout_seconds=YOUTUBE_MEDIA_SERVICE_TIMEOUT_SECONDS,
                        )
                        return "tv_android_youtube"
                    if platform == "apple tv" or platform == "apple_tv":
                        await self._async_call_service(
                            MEDIA_PLAYER_DOMAIN,
                            MEDIA_PLAYER_SERVICE_PLAY_MEDIA,
                            {
                                "media_content_type": "url",
                                "media_content_id": f"youtube://www.youtube.com/watch?v={video.video_id}",
                            },
                            blocking=True,
                            target={"entity_id": target.entity_id},
                            timeout_seconds=YOUTUBE_MEDIA_SERVICE_TIMEOUT_SECONDS,
                        )
                        return "tv_apple_youtube"
                except Exception:
                    _LOGGER.debug("Native YouTube app playback failed; falling back", exc_info=True)

            if target.kind == "speaker":
                return await self._async_play_youtube_speaker(target, video)

            if self.hass.services.has_service(MEDIA_EXTRACTOR_DOMAIN, MEDIA_EXTRACTOR_SERVICE_PLAY_MEDIA):
                await self._async_call_service(
                    MEDIA_EXTRACTOR_DOMAIN,
                    MEDIA_EXTRACTOR_SERVICE_PLAY_MEDIA,
                    {
                        "media_content_id": video.url,
                        "media_content_type": "music" if target.kind == "speaker" else "video",
                    },
                    blocking=True,
                    target={"entity_id": target.entity_id},
                    timeout_seconds=YOUTUBE_MEDIA_SERVICE_TIMEOUT_SECONDS,
                )
                return "media_extractor.play_media"

            await self._async_call_service(
                MEDIA_PLAYER_DOMAIN,
                MEDIA_PLAYER_SERVICE_PLAY_MEDIA,
                {
                    "media_content_id": video.url,
                    "media_content_type": "music" if target.kind == "speaker" else "video",
                },
                blocking=True,
                target={"entity_id": target.entity_id},
                timeout_seconds=YOUTUBE_MEDIA_SERVICE_TIMEOUT_SECONDS,
            )
            return "media_player.play_media"

    async def _async_begin_youtube(self, text: str, *, source_keys: set[str] | None = None, zalo_context: Any | None = None) -> tuple[PendingYouTubeFlow, str]:
        parsed = parse_youtube_request(text)
        targets = self._configured_youtube_targets()
        pending = self._new_youtube_pending("", targets, source_keys=source_keys, zalo_context=zalo_context)
        if parsed is None:
            return pending, self._youtube_clarify_prompt("", None)

        pending.query = parsed.query.strip()
        target_indexes = find_target_indexes(parsed.target_text or parsed.query, targets)
        if target_indexes:
            pending.selected_target = targets[target_indexes[0]]
            if not parsed.target_text:
                pending.query = strip_target_from_query(pending.query, pending.selected_target)
        elif parsed.target_text:
            # The user clearly named a destination, but it does not match a
            # configured/discovered media player: keep query and ask for target.
            pending.query = parsed.query.strip()

        if not pending.query and pending.selected_target is None:
            pending.phase = "clarify"
            return pending, self._youtube_clarify_prompt("", None)
        if not pending.query:
            pending.phase = "clarify"
            return pending, self._youtube_clarify_prompt("", pending.selected_target)
        if pending.selected_target is None:
            pending.phase = "target"
            return pending, self._youtube_target_prompt(targets, pending.query)
        return pending, await self._async_prepare_youtube_results(pending)

    async def _async_youtube_from_zalo(self, context: Any, service_context: Context | None = None) -> str:
        self._clear_zalo_youtube_pending(context.owner_key)
        pending, message = await self._async_begin_youtube(context.text, zalo_context=context)
        self._zalo_pending_youtube[context.owner_key] = pending
        self._schedule_pending_expiry()
        return message

    async def _async_youtube_pending_reply_from_zalo(self, context: Any, pending: PendingYouTubeFlow) -> str:
        normalized = normalize_text(context.text)
        if self._is_cancel_pending_text(context.text) or normalized in {"huy youtube", "dung youtube", "khong phat nua"}:
            self._remove_youtube_pending(pending)
            return "Đã hủy yêu cầu YouTube."
        pending.expires_at = dt_util.now() + timedelta(seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS)

        if pending.phase == "clarify":
            # A natural reply may contain only the missing query or only a target.
            indexes = find_target_indexes(context.text, pending.targets)
            if indexes:
                pending.selected_target = pending.targets[indexes[0]]
                remainder = strip_target_from_query(context.text, pending.selected_target)
                if remainder and not pending.query:
                    pending.query = remainder
            elif not pending.query:
                pending.query = context.text.strip()
            if pending.query and pending.selected_target is None:
                pending.phase = "target"
                return self._youtube_target_prompt(pending.targets, pending.query)
            if not pending.query:
                return self._youtube_clarify_prompt("", pending.selected_target)
            return await self._async_prepare_youtube_results(pending)

        if pending.phase == "target":
            indexes = parse_target_selection(context.text, [item.display_name for item in pending.targets])
            if not indexes:
                indexes = find_target_indexes(context.text, pending.targets)
            if not indexes:
                return self._youtube_target_prompt(pending.targets, pending.query)
            pending.selected_target = pending.targets[indexes[0]]
            return await self._async_prepare_youtube_results(pending)

        if pending.phase == "video":
            indexes = parse_target_selection(context.text, [item.title for item in pending.videos])
            if not indexes:
                return self._youtube_video_prompt(pending.videos, pending.selected_target)
            video = pending.videos[indexes[0]]
            pending.selected_video = video
            task = self._youtube_auto_tasks.pop(pending.pending_id, None)
            if task is not None and task is not asyncio.current_task() and not task.done():
                task.cancel()
            return await self._async_start_youtube_playback(pending, video)

        if pending.phase == "busy":
            if normalized in {"co", "dong y", "phat de", "phat de ngay", "phat ngay", "yes", "override"}:
                task = self._youtube_busy_tasks.pop(pending.pending_id, None)
                if task is not None and task is not asyncio.current_task() and not task.done():
                    task.cancel()
                assert pending.selected_video is not None
                return await self._async_start_youtube_playback(pending, pending.selected_video, force=True)
            if normalized in {"khong", "khong phat de", "cho loa ranh", "doi loa ranh", "no"}:
                return "Được. Tôi tiếp tục chờ loa rảnh, tối đa 10 phút; bạn vẫn có thể gửi **Hủy**."
            return "Loa đang bận. Trả lời **Phát đè** để phát ngay, **Không** để tiếp tục chờ, hoặc **Hủy**."
        return self._youtube_clarify_prompt(pending.query, pending.selected_target)

    async def _async_youtube_from_voice(self, user_input: Any, _result: RecognizeResult) -> str:
        source_keys = self._source_keys(user_input)
        self._clear_voice_youtube_pending_for_source(source_keys)
        pending, message = await self._async_begin_youtube(user_input.text, source_keys=source_keys)
        self._pending_voice_youtube[pending.pending_id] = pending
        self._sync_pending_followup_trigger()
        return await self._async_voice_response(user_input, message)

    async def _async_youtube_pending_reply_from_voice(self, user_input: Any, pending: PendingYouTubeFlow) -> str:
        # Reuse the Zalo state machine with a tiny context proxy only for text.
        class _Reply:
            text = user_input.text
            owner_key = ""

        # Keep the flow in the voice store and prevent Zalo-store mutations.
        original_context = pending.zalo_context
        pending.zalo_context = None
        try:
            message = await self._async_youtube_pending_reply_from_zalo(_Reply(), pending)
        finally:
            pending.zalo_context = original_context
        return await self._async_voice_response(user_input, message)
