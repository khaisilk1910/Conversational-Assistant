"""Reminder manager for Conversational Assistant."""

from __future__ import annotations

import asyncio
import calendar
import json
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
from functools import partial
import logging
import os
import re
from time import monotonic
from typing import Any
import unicodedata
import uuid

from hassil.recognize import RecognizeResult

from homeassistant.components import media_source, persistent_notification
from homeassistant.components.calendar.const import CalendarEntityFeature
from homeassistant.components.mobile_app.const import ATTR_WEBHOOK_ID
from homeassistant.components.mobile_app.util import get_notify_service
from homeassistant.components.media_player.const import MediaPlayerEntityFeature
from homeassistant.components.conversation.agent_manager import (
    async_converse,
    get_agent_manager,
)
from homeassistant.components.conversation.const import HOME_ASSISTANT_AGENT
from homeassistant.components.conversation.models import ConversationInput
from homeassistant.components.homeassistant.exposed_entities import (
    async_should_expose,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_SUPPORTED_FEATURES,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Context, CoreState, Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ACTION_DISMISS,
    ACTION_SNOOZE,
    AI_TASK_DOMAIN,
    AI_TASK_SERVICE_GENERATE_IMAGE,
    ASSIST_SATELLITE_DOMAIN,
    ASSIST_SATELLITE_SERVICE_ANNOUNCE,
    CAMERA_SENTENCES,
    CONF_AI_AGENT_FAILOVER_ENABLED,
    CONF_AI_IMAGE_TASK_ENTITY_ID,
    CONF_AI_SEARCH_AGENT_ID,
    CANCEL_SENTENCES,
    COMMAND_DELETE_SENTENCES,
    COMMAND_LEARN_SENTENCES,
    COMMAND_LIST_SENTENCES,
    CONF_CONFIRM_TARGETS,
    CONF_DISMISS_ON_CLEAR,
    CONF_SPEAKER_ENABLED,
    CONF_TTS_ENTITY_ID,
    CONF_ZALO_ACCOUNT_SELECTION,
    CONF_ZALO_CONVERSATION_AGENT_ID,
    CONF_ZALO_ENABLED,
    CONF_ZALO_HOME_ASSISTANT_ENABLED,
    CONF_ZALO_TARGET_ENABLED,
    CONF_ZALO_TARGET_ID,
    CONF_ZALO_TARGET_NAME,
    CONF_ZALO_TARGETS,
    CONF_ZALO_THREAD_ID,
    CONF_ZALO_TYPE,
    CONF_ZALO_WEBHOOK_ACCOUNT_SELECTION,
    CONF_ZALO_WEBHOOK_BOT_ACCOUNT_ID,
    CONF_ZALO_WEBHOOK_ENABLED,
    CREATE_SENTENCES,
    DEFAULT_AI_AGENT_FAILOVER_ENABLED,
    DEFAULT_AI_IMAGE_TASK_ENTITY_ID,
    DEFAULT_AI_SEARCH_AGENT_ID,
    DEFAULT_CONFIRM_TARGETS,
    DEFAULT_DISMISS_ON_CLEAR,
    DEFAULT_SPEAKER_ENABLED,
    DEFAULT_SNOOZE_MINUTES,
    DEFAULT_ZALO_ENABLED,
    DEFAULT_ZALO_CONVERSATION_AGENT_ID,
    DEFAULT_ZALO_HOME_ASSISTANT_ENABLED,
    DEFAULT_ZALO_TYPE,
    DEFAULT_ZALO_WEBHOOK_BOT_ACCOUNT_ID,
    DEFAULT_ZALO_WEBHOOK_ENABLED,
    DISCOVERY_CACHE_SECONDS,
    DOMAIN,
    EVENT_NOTIFICATION_ACTION,
    EVENT_NOTIFICATION_CLEARED,
    HELP_SENTENCES,
    IMAGE_GENERATION_PREFIXES,
    LIST_SENTENCES,
    MEDIA_PLAYER_DOMAIN,
    PENDING_FOLLOWUP_SENTENCES,
    PENDING_SELECTION_TIMEOUT_MINUTES,
    SEARCH_SENTENCES,
    SIGNAL_UPDATE,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
    TTS_DOMAIN,
    TTS_SERVICE_SPEAK,
    ZALO_DOMAIN,
    ZALO_SERVICE_SEND_IMAGE,
    ZALO_SERVICE_SEND_IMAGES_TO_GROUP,
    ZALO_SERVICE_SEND_MESSAGE,
    ZALO_SERVICE_SEND_TYPING_EVENT,
    ZALO_IMAGE_TIMEOUT_SECONDS,
    ZALO_SEARCH_TIMEOUT_SECONDS,
    ZALO_TYPING_REFRESH_SECONDS,
    ZALO_TYPE_GROUP,
    ZALO_TYPE_USER,
    ZALO_WEBHOOK_SEEN_MESSAGE_LIMIT,
)
from .command_memory import (
    ACTION_CAMERA,
    ACTION_CALENDAR,
    ACTION_HELP,
    ACTION_HOME_ASSISTANT,
    ACTION_IMAGE_GENERATION,
    ACTION_LABELS,
    ACTION_NOTE_CREATE,
    ACTION_NOTE_DELETE,
    ACTION_NOTE_EDIT,
    ACTION_NOTE_LIST,
    ACTION_NOTE_VIEW,
    ACTION_REMINDER_CREATE,
    ACTION_REMINDER_DELETE,
    ACTION_REMINDER_LIST,
    ACTION_SEARCH,
    CommandMemoryError,
    LearnedCommand,
    MAX_LEARNED_COMMANDS,
    REQUEST_ACTIONS,
    canonical_text,
    explicit_target_action,
    hassil_sentences,
    management_command_kind,
    match_learned_command,
    parse_delete_request,
    parse_learn_request,
)
from .models import Reminder
from .note_flow import (
    NoteManagerMixin,
    is_primary_note_voice_command,
    note_zalo_command_kind,
)
from .parser import (
    ParsedReminder,
    ReminderParseError,
    parse_reminder_request,
)
from .targeting import normalize_text, parse_target_selection
from .zalo_home_assistant import (
    CalendarCreateRequest,
    CalendarWindow,
    calendar_create_request_from_ai_payload,
    calendar_has_time_reference,
    calendar_matches_query,
    calendar_request_action,
    calendar_window_from_text,
    event_from_calendar_state,
    explicit_home_assistant_request_kind,
    extract_calendar_events,
    format_calendar_create_request,
    format_calendar_events,
)

_LOGGER = logging.getLogger(__name__)


_HELP_EXACT_PHRASES = frozenset(
    {
        "help",
        "show help",
        "usage guide",
        "user guide",
        "instructions",
        "commands",
        "features",
        "how to use the integration",
        "how do i use the integration",
        "how can i use the integration",
        "how to use conversational assistant",
        "how do i use conversational assistant",
        "how can i use conversational assistant",
        "how does the integration work",
        "how does conversational assistant work",
        "what can the integration do",
        "what can conversational assistant do",
        "what features are supported",
        "tro giup",
        "huong dan",
        "huong dan su dung",
        "huong dan su dung tich hop",
        "su dung tich hop",
        "dung tich hop",
        "cach su dung tich hop",
        "huong dan tich hop",
        "gioi thieu tich hop",
        "hoc cach su dung tich hop",
        "hoc su dung tich hop",
        "huong dan conversational assistant",
        "huong dan su dung conversational assistant",
        "cach su dung conversational assistant",
        "hoc cach su dung conversational assistant",
        "lenh",
        "cac lenh",
        "cac tinh nang",
        "cac lenh ho tro",
        "huong dan cac tinh nang",
        "huong dan tinh nang",
        "gioi thieu cac tinh nang",
        "cach su dung cac tinh nang",
        "tich hop co tinh nang gi",
        "tich hop ho tro tinh nang gi",
        "conversational assistant co tinh nang gi",
        "conversational assistant ho tro tinh nang gi",
        "toi co the dung tich hop nhu the nao",
        "toi co the su dung tich hop nhu the nao",
    }
)


def _is_integration_help_request(text: str) -> bool:
    """Return whether text asks how to use this integration."""
    normalized = normalize_text(text)
    if normalized.startswith("hay "):
        normalized = normalized[4:].strip()
    elif normalized.startswith("please "):
        normalized = normalized[7:].strip()
    if not normalized:
        return False
    if normalized in _HELP_EXACT_PHRASES:
        return True

    mentions_subject = any(
        term in normalized
        for term in (
            "tich hop",
            "integration",
            "assistant",
            "conversational assistant",
            "cac tinh nang",
            "tinh nang cua",
            "cac lenh ho tro",
        )
    )
    asks_for_guidance = any(
        term in normalized
        for term in (
            "help",
            "guide",
            "instructions",
            "how to use",
            "how do i use",
            "how can i use",
            "how does",
            "what can",
            "what features",
            "show commands",
            "show features",
            "huong dan",
            "cach su dung",
            "cach dung",
            "hoc cach",
            "gioi thieu",
            "lam duoc gi",
            "tinh nang gi",
            "su dung nhu the nao",
            "dung nhu the nao",
        )
    )
    return mentions_subject and asks_for_guidance


def _request_language(text: str) -> str:
    """Infer whether an inbound command should use English or Vietnamese."""
    normalized = normalize_text(text)
    tokens = set(normalized.split())
    english_markers = {
        "the", "a", "an", "my", "me", "please", "turn", "switch", "set",
        "open", "close", "lock", "unlock", "check", "status", "weather",
        "temperature", "calendar", "event", "today", "tomorrow", "remind",
        "reminder", "note", "camera", "take", "photo", "picture", "show",
        "list", "delete", "cancel", "help", "what", "which", "where",
        "is", "are", "any", "light", "lights", "fan", "fans", "device",
        "devices", "room", "floor", "upstairs", "downstairs", "living",
        "kitchen", "bedroom", "brightness", "volume", "thermostat", "door",
        "search", "internet", "web", "find", "look", "latest", "news",
        "price", "information", "generate", "create", "make", "draw",
        "image", "schedule", "book", "meeting", "appointment", "week",
        "month", "year", "days", "weeks", "months", "years", "morning",
        "afternoon", "evening", "night", "noon",
    }
    vietnamese_markers = {
        "toi", "hay", "bat", "tat", "mo", "dong", "kiem", "tra",
        "trang", "thai", "thoi", "tiet", "nhac", "ghi", "chu", "chup",
        "anh", "hom", "nay", "ngay", "mai", "xoa", "huy", "danh", "sach",
        "tim", "kiem", "mang", "tra", "cuu", "thong", "tin", "tao",
        "buc", "ve",
    }
    english_score = len(tokens & english_markers)
    vietnamese_score = len(tokens & vietnamese_markers)
    return "en" if english_score > vietnamese_score else "vi"


def _search_request(text: str) -> str | None:
    """Return a natural-language Internet query, or None when not a search."""
    words = str(text or "").strip().split()
    normalized_words = [normalize_text(word) for word in words]
    if normalized_words and normalized_words[0] in {"hay", "please"}:
        words = words[1:]
        normalized_words = normalized_words[1:]

    prefixes = (
        ("tim", "kiem", "tren", "mang"),
        ("tim", "kiem", "thong", "tin"),
        ("tim", "thong", "tin"),
        ("tim", "tren", "mang"),
        ("tra", "cuu", "thong", "tin"),
        ("tra", "thong", "tin"),
        ("tim", "kiem"),
        ("tra", "cuu"),
        ("search", "the", "internet", "for"),
        ("search", "the", "web", "for"),
        ("find", "information", "about"),
        ("search", "for"),
        ("look", "up"),
        ("web", "search"),
    )
    for prefix in prefixes:
        if tuple(normalized_words[: len(prefix)]) == prefix:
            return " ".join(words[len(prefix) :]).strip()
    return None


def _image_generation_request(text: str) -> str | None:
    """Return image instructions, or None when text is not an image request."""
    words = str(text or "").strip().split()
    if not words:
        return None
    if normalize_text(words[0]) in {"hay", "please"}:
        words = words[1:]
    normalized_words = [normalize_text(word) for word in words]
    for raw_prefix in IMAGE_GENERATION_PREFIXES:
        prefix = tuple(normalize_text(raw_prefix).split())
        if tuple(normalized_words[: len(prefix)]) == prefix:
            return " ".join(words[len(prefix) :]).strip()
    return None


@dataclass(slots=True)
class NotificationTarget:
    """A selectable notification destination."""

    target_id: str
    kind: str
    display_name: str
    mobile_device_id: str | None = None
    zalo: dict[str, Any] | None = None
    speaker_entity_id: str | None = None


@dataclass(slots=True)
class PendingReminder:
    """Parsed reminder waiting for target selection."""

    pending_id: str
    parsed: ParsedReminder
    targets: list[NotificationTarget]
    source_keys: set[str]
    created_at: datetime
    expires_at: datetime


@dataclass(slots=True)
class PendingDeletion:
    """Numbered reminder list waiting for deletion selection."""

    pending_id: str
    reminders: list[tuple[datetime, Reminder]]
    source_keys: set[str]
    created_at: datetime
    expires_at: datetime


@dataclass(slots=True)
class PendingZaloDeletion:
    """Numbered deletion list waiting for a reply in one Zalo chat."""

    reminders: list[tuple[datetime, Reminder]]
    expires_at: datetime


@dataclass(slots=True)
class PendingZaloReminder:
    """Parsed reminder waiting for target selection in one Zalo chat."""

    parsed: ParsedReminder
    targets: list[NotificationTarget]
    expires_at: datetime


@dataclass(slots=True, frozen=True)
class CameraTarget:
    """One camera entity selectable from a Zalo conversation."""

    entity_id: str
    display_name: str
    available: bool


@dataclass(slots=True)
class PendingZaloCamera:
    """Camera list waiting for a selection in one Zalo chat."""

    cameras: list[CameraTarget]
    expires_at: datetime


@dataclass(slots=True, frozen=True)
class CalendarTarget:
    """One writable calendar selectable from a Zalo conversation."""

    entity_id: str
    display_name: str


@dataclass(slots=True)
class PendingZaloCalendarEvent:
    """Parsed calendar event waiting for a calendar selection."""

    request: CalendarCreateRequest
    calendars: list[CalendarTarget]
    expires_at: datetime
    ai_attempted_agents: list[str]


@dataclass(slots=True)
class PendingVoiceCamera:
    """Voice camera request waiting for selection or final confirmation."""

    pending_id: str
    cameras: list[CameraTarget]
    zalo_targets: list[dict[str, Any]]
    source_keys: set[str]
    selected_cameras: list[CameraTarget]
    phase: str
    created_at: datetime
    expires_at: datetime


@dataclass(slots=True, frozen=True)
class ZaloDirectResponse:
    """A response already delivered directly without a text reply."""

    sent: bool
    response_type: str


@dataclass(slots=True)
class ZaloWebhookContext:
    """Normalized data needed to process one incoming Zalo message."""

    account_id: str
    sender_id: str
    thread_id: str
    thread_type: str
    display_name: str
    owner_key: str
    message_id: str
    text: str


def _add_month(value: datetime, target_day: int) -> datetime:
    """Add one month while preserving the requested day when possible."""
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    day = min(target_day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _add_year(value: datetime, month: int, target_day: int) -> datetime:
    """Add one year while preserving month/day when possible."""
    year = value.year + 1
    day = min(target_day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _next_allowed_weekday(
    previous: datetime, allowed_weekdays: set[int]
) -> datetime:
    """Return the next occurrence on one of the allowed weekdays."""
    for offset in range(1, 8):
        candidate = previous + timedelta(days=offset)
        if candidate.weekday() in allowed_weekdays:
            return candidate
    return previous + timedelta(days=7)


def _next_recurrence(reminder: Reminder, previous: datetime) -> datetime | None:
    """Calculate the next recurrence after previous."""
    recurrence = reminder.recurrence
    if recurrence.kind == "daily":
        return previous + timedelta(days=1)
    if recurrence.kind == "weekly":
        weekdays = set(recurrence.weekdays or [])
        if not weekdays and recurrence.weekday is not None:
            weekdays = {recurrence.weekday}
        if weekdays:
            return _next_allowed_weekday(previous, weekdays)
        return previous + timedelta(days=7)
    if recurrence.kind == "weekdays":
        return _next_allowed_weekday(previous, {0, 1, 2, 3, 4})
    if recurrence.kind == "weekend":
        return _next_allowed_weekday(previous, {5, 6})
    if recurrence.kind == "monthly":
        return _add_month(previous, recurrence.day_of_month or previous.day)
    if recurrence.kind == "yearly":
        return _add_year(
            previous,
            recurrence.month or previous.month,
            recurrence.day_of_month or previous.day,
        )
    return None


def _prepare_camera_snapshot_path(filename: str) -> None:
    """Create the snapshot directory and remove any previous image."""
    os.makedirs(os.path.dirname(filename), mode=0o755, exist_ok=True)
    try:
        os.remove(filename)
    except FileNotFoundError:
        pass


def _sanitize_spoken_text(value: str) -> str:
    """Return TTS-friendly text without markup, emoji, or punctuation."""
    normalized = unicodedata.normalize("NFC", value.strip())
    characters: list[str] = []
    for character in normalized:
        category = unicodedata.category(character)
        if character.isspace():
            characters.append(" ")
        elif category.startswith(("L", "N")):
            characters.append(character)
        else:
            characters.append(" ")
    return " ".join("".join(characters).split())


class _ConversationInputTextProxy:
    """Expose one ConversationInput with replacement text.

    Home Assistant's ConversationInput implementation can change between
    releases. Delegating every other attribute avoids depending on its
    constructor while letting existing handlers parse a canonical command.
    """

    def __init__(self, original: ConversationInput, text: str) -> None:
        self._original = original
        self.text = text

    def __getattr__(self, name: str) -> Any:
        return getattr(self._original, name)


class ConversationalAssistantManager(NoteManagerMixin):
    """Store, schedule, send, and manage reminders."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize manager."""
        self.hass = hass
        self.entry = entry
        self.reminders: dict[str, Reminder] = {}
        self.learned_commands: dict[str, LearnedCommand] = {}
        self._initialize_note_state()
        self._pending: dict[str, PendingReminder] = {}
        self._pending_deletions: dict[str, PendingDeletion] = {}
        self._pending_voice_cameras: dict[str, PendingVoiceCamera] = {}
        self._zalo_pending_creations: dict[str, PendingZaloReminder] = {}
        self._zalo_pending_deletions: dict[str, PendingZaloDeletion] = {}
        self._zalo_pending_cameras: dict[str, PendingZaloCamera] = {}
        self._zalo_pending_calendar_events: dict[
            str, PendingZaloCalendarEvent
        ] = {}
        self._zalo_seen_message_ids: deque[str] = deque()
        self._zalo_seen_message_id_set: set[str] = set()
        self._zalo_ha_conversation_ids: dict[str, str] = {}
        self._zalo_search_conversation_ids: dict[str, str] = {}
        self._zalo_background_tasks: set[asyncio.Task[Any]] = set()
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}.{entry.entry_id}",
        )
        self._unsub_timer: Callable[[], None] | None = None
        self._unsub_pending_trigger: Callable[[], None] | None = None
        self._unsub_pending_expiry_timer: Callable[[], None] | None = None
        self._unsubs: list[Callable[[], None]] = []
        self._learned_trigger_unsubs: list[Callable[[], None]] = []
        # Optional targets are discovered only when a command actually needs
        # them.  Never populate these caches from async_setup(), otherwise a
        # large device/entity registry can delay Home Assistant startup.
        self._mobile_targets_cache: list[NotificationTarget] | None = None
        self._mobile_targets_cache_until = 0.0
        self._speaker_targets_cache: list[NotificationTarget] | None = None
        self._speaker_targets_cache_until = 0.0
        self._camera_targets_cache: list[CameraTarget] | None = None
        self._camera_targets_cache_until = 0.0
        self._tts_entity_id_cache: str | None = None
        self._tts_entity_id_cache_set = False
        self._tts_entity_id_cache_until = 0.0

    @property
    def update_signal(self) -> str:
        """Return dispatcher signal for this entry."""
        return f"{SIGNAL_UPDATE}_{self.entry.entry_id}"

    @property
    def zalo_webhook_action(self) -> str:
        """Return the action that accepts payloads from an existing webhook."""
        return f"{DOMAIN}.process_zalo_webhook"

    @property
    def zalo_webhook_enabled(self) -> bool:
        """Return whether incoming Zalo message handling is enabled."""
        return bool(
            self._option(
                CONF_ZALO_WEBHOOK_ENABLED, DEFAULT_ZALO_WEBHOOK_ENABLED
            )
        )

    @property
    def zalo_webhook_bot_account_id(self) -> str:
        """Return the Zalo account ID used to reject self-originated events."""
        return str(
            self._option(
                CONF_ZALO_WEBHOOK_BOT_ACCOUNT_ID,
                DEFAULT_ZALO_WEBHOOK_BOT_ACCOUNT_ID,
            )
            or ""
        ).strip()

    @property
    def zalo_home_assistant_enabled(self) -> bool:
        """Return whether Zalo can query and control Home Assistant."""
        return bool(
            self._option(
                CONF_ZALO_HOME_ASSISTANT_ENABLED,
                DEFAULT_ZALO_HOME_ASSISTANT_ENABLED,
            )
        )

    @property
    def zalo_conversation_agent_id(self) -> str:
        """Return the Conversation agent used for Zalo commands."""
        return str(
            self._option(
                CONF_ZALO_CONVERSATION_AGENT_ID,
                DEFAULT_ZALO_CONVERSATION_AGENT_ID,
            )
            or HOME_ASSISTANT_AGENT
        ).strip()

    @property
    def ai_search_agent_id(self) -> str:
        """Return the optional Conversation agent used for Internet search."""
        return str(
            self._option(CONF_AI_SEARCH_AGENT_ID, DEFAULT_AI_SEARCH_AGENT_ID)
            or ""
        ).strip()

    @property
    def ai_image_task_entity_id(self) -> str:
        """Return the optional AI Task entity used for image generation."""
        return str(
            self._option(
                CONF_AI_IMAGE_TASK_ENTITY_ID,
                DEFAULT_AI_IMAGE_TASK_ENTITY_ID,
            )
            or ""
        ).strip()

    @property
    def ai_agent_failover_enabled(self) -> bool:
        """Return whether failed AI requests rotate through available agents."""
        return bool(
            self._option(
                CONF_AI_AGENT_FAILOVER_ENABLED,
                DEFAULT_AI_AGENT_FAILOVER_ENABLED,
            )
        )

    def _conversation_agent_display_name(self, agent_id: str) -> str:
        """Return a stable, user-facing name for a Conversation agent."""
        state = self.hass.states.get(agent_id)
        if state is not None:
            friendly_name = str(
                state.attributes.get("friendly_name", "") or ""
            ).strip()
            if friendly_name:
                return friendly_name

        entry = self.hass.config_entries.async_get_entry(agent_id)
        if entry is not None:
            return str(entry.title or entry.domain or agent_id)

        if agent_id == HOME_ASSISTANT_AGENT:
            return "Home Assistant"
        return agent_id

    def _conversation_agent_candidates(
        self, primary_agent_id: str
    ) -> list[tuple[str, str]]:
        """Return the configured agent first, then every available HA agent."""
        agent_ids: list[str] = []

        def add(agent_id: str | None) -> None:
            normalized = str(agent_id or "").strip()
            if normalized and normalized not in agent_ids:
                agent_ids.append(normalized)

        add(primary_agent_id)
        if self.ai_agent_failover_enabled:
            try:
                agent_manager = get_agent_manager(self.hass)
                infos = sorted(
                    agent_manager.async_get_agent_info(),
                    key=lambda item: (str(item.name).casefold(), str(item.id)),
                )
            except Exception:  # noqa: BLE001 - discovery must not break requests
                _LOGGER.exception(
                    "Failed listing Conversation agents for AI failover"
                )
                infos = []
            for info in infos:
                if str(info.id) != HOME_ASSISTANT_AGENT:
                    add(str(info.id))

            try:
                states = sorted(
                    self.hass.states.async_all("conversation"),
                    key=lambda item: (
                        str(
                            item.attributes.get("friendly_name", "")
                        ).casefold(),
                        item.entity_id,
                    ),
                )
            except Exception:  # noqa: BLE001 - keep the selected agent usable
                _LOGGER.exception(
                    "Failed listing Conversation entities for AI failover"
                )
                states = []
            for state in states:
                if (
                    state.entity_id != HOME_ASSISTANT_AGENT
                    and state.state != STATE_UNAVAILABLE
                ):
                    add(state.entity_id)
            add(HOME_ASSISTANT_AGENT)

        return [
            (agent_id, self._conversation_agent_display_name(agent_id))
            for agent_id in agent_ids
        ]

    def _ai_task_agent_display_name(self, entity_id: str) -> str:
        """Return a stable, user-facing name for an AI Task entity."""
        state = self.hass.states.get(entity_id)
        if state is not None:
            friendly_name = str(
                state.attributes.get("friendly_name", "") or ""
            ).strip()
            if friendly_name:
                return friendly_name
        return entity_id

    def _ai_image_agent_candidates(
        self, primary_entity_id: str
    ) -> list[tuple[str, str]]:
        """Return the configured image agent first, then compatible AI Tasks."""
        entity_ids: list[str] = []

        def add(entity_id: str | None) -> None:
            normalized = str(entity_id or "").strip()
            if normalized and normalized not in entity_ids:
                entity_ids.append(normalized)

        add(primary_entity_id)
        if self.ai_agent_failover_enabled:
            states = sorted(
                self.hass.states.async_all(AI_TASK_DOMAIN),
                key=lambda item: (
                    str(item.attributes.get("friendly_name", "")).casefold(),
                    item.entity_id,
                ),
            )
            for state in states:
                if state.state == STATE_UNAVAILABLE:
                    continue
                raw_features = state.attributes.get(ATTR_SUPPORTED_FEATURES)
                if raw_features is not None:
                    try:
                        if not (int(raw_features) & 4):
                            continue
                    except (TypeError, ValueError):
                        _LOGGER.debug(
                            "AI Task entity %s has invalid supported_features %r",
                            state.entity_id,
                            raw_features,
                        )
                add(state.entity_id)

        return [
            (entity_id, self._ai_task_agent_display_name(entity_id))
            for entity_id in entity_ids
        ]

    @staticmethod
    def _conversation_result_error_code(result: Any) -> str:
        """Return a normalized error code from a Conversation result."""
        response = getattr(result, "response", None)
        raw_error_code = getattr(response, "error_code", "") or ""
        return str(getattr(raw_error_code, "value", raw_error_code) or "").strip()

    @staticmethod
    def _ai_attempt_summary(
        attempted_agents: list[str], *, language: str, zalo: bool
    ) -> str:
        """Describe a failover sequence without exposing provider errors."""
        if len(attempted_agents) <= 1:
            return ""
        names = " → ".join(attempted_agents)
        if language == "en":
            summary = f"Tried {len(attempted_agents)} AI agents: {names}."
            return f"🔄 **AI failover:** {summary}" if zalo else summary
        summary = f"Đã thử {len(attempted_agents)} AI agent: {names}."
        return f"🔄 **AI dự phòng:** {summary}" if zalo else summary

    @classmethod
    def _append_ai_attempt_summary(
        cls,
        text: str,
        attempted_agents: list[str],
        *,
        language: str,
        zalo: bool,
    ) -> str:
        """Append the failover summary only when more than one agent ran."""
        summary = cls._ai_attempt_summary(
            attempted_agents, language=language, zalo=zalo
        )
        if not summary:
            return text
        separator = "\n\n" if zalo else " "
        return f"{text.rstrip()}{separator}{summary}"

    async def _async_send_ai_failover_notice(
        self,
        context: ZaloWebhookContext | None,
        _service_context: Context | None,
        *,
        feature: str,
        failed_agent: str,
        next_agent: str,
        next_attempt: int,
        total_attempts: int,
        language: str,
    ) -> None:
        """Tell Zalo that the next agent receives a fresh timeout window."""
        if context is None:
            return
        if language == "en":
            feature_name = {
                "image": "image generation",
                "conversation": "conversation",
                "calendar": "calendar analysis",
            }.get(feature, "search")
            message = (
                f"🔄 **Switching AI for {feature_name}**\n\n"
                f"Agent **{failed_agent}** did not complete the request. "
                f"Trying agent **{next_attempt}/{total_attempts}: {next_agent}**. "
                "**The waiting timer has restarted for this agent.**"
            )
        else:
            feature_name = {
                "image": "tạo ảnh",
                "conversation": "hội thoại",
                "calendar": "phân tích lịch",
            }.get(feature, "tìm kiếm")
            message = (
                f"🔄 **Đang chuyển AI dự phòng cho {feature_name}**\n\n"
                f"Agent **{failed_agent}** chưa hoàn thành yêu cầu. "
                f"Đang thử agent **{next_attempt}/{total_attempts}: {next_agent}**. "
                "**Thời gian chờ đã được tính lại từ đầu cho agent này.**"
            )
        await self._async_send_zalo_webhook_reply(context, message)

    def _ai_long_running_candidate_count(self, action: str) -> int:
        """Return the current number of candidates for the safety timeout."""
        if action == ACTION_IMAGE_GENERATION:
            candidates = self._ai_image_agent_candidates(
                self.ai_image_task_entity_id
            )
        elif action == ACTION_CALENDAR:
            candidates = self._conversation_agent_candidates(
                self.zalo_conversation_agent_id
            )
        else:
            candidates = self._conversation_agent_candidates(
                self.ai_search_agent_id
            )
        return max(1, len(candidates))

    def _raw_next_due(self) -> datetime | None:
        """Return the earliest stored due time, including overdue items."""
        due_values: list[datetime] = []
        for reminder in self.reminders.values():
            if reminder.next_run is not None:
                due_values.append(reminder.next_run)
            if reminder.snooze_until is not None:
                due_values.append(reminder.snooze_until)
        return min(due_values) if due_values else None

    @staticmethod
    def _upcoming_due_for(
        reminder: Reminder, now: datetime
    ) -> datetime | None:
        """Return the next future occurrence for one reminder."""
        due_values: list[datetime] = []

        if reminder.snooze_until is not None and reminder.snooze_until > now:
            due_values.append(reminder.snooze_until)

        next_run = reminder.next_run
        if next_run is not None:
            if reminder.is_recurring:
                while next_run <= now:
                    following = _next_recurrence(reminder, next_run)
                    if following is None or following <= next_run:
                        next_run = None
                        break
                    next_run = following
            elif next_run <= now:
                next_run = None

            if next_run is not None:
                due_values.append(next_run)

        return min(due_values) if due_values else None

    @property
    def upcoming_reminders(self) -> list[tuple[datetime, Reminder]]:
        """Return active reminders ordered from nearest to farthest."""
        now = dt_util.now()
        upcoming: list[tuple[datetime, Reminder]] = []
        for reminder in self.reminders.values():
            due = self._upcoming_due_for(reminder, now)
            if due is not None:
                upcoming.append((due, reminder))
        upcoming.sort(key=lambda item: (item[0], item[1].created_at))
        return upcoming

    @property
    def deletable_reminders(self) -> list[tuple[datetime, Reminder]]:
        """Return every stored reminder in a stable management order.

        Future occurrences are listed first. Delivered one-time reminders are
        retained for notification actions and are listed afterwards, newest
        first, so the user can explicitly remove them as well.
        """
        now = dt_util.now()
        upcoming: list[tuple[datetime, Reminder]] = []
        historical: list[tuple[datetime, Reminder]] = []
        for reminder in self.reminders.values():
            due = self._upcoming_due_for(reminder, now)
            if due is not None:
                upcoming.append((due, reminder))
                continue
            fallback = (
                reminder.last_notified
                or reminder.next_run
                or reminder.snooze_until
                or reminder.created_at
            )
            historical.append((fallback, reminder))

        upcoming.sort(key=lambda item: (item[0], item[1].created_at))
        historical.sort(key=lambda item: item[0], reverse=True)
        return upcoming + historical

    @property
    def active_count(self) -> int:
        """Return reminders with a future one-time or recurring occurrence."""
        return len(self.upcoming_reminders)

    @property
    def next_due(self) -> datetime | None:
        """Return the earliest future reminder occurrence."""
        upcoming = self.upcoming_reminders
        return upcoming[0][0] if upcoming else None

    @property
    def next_reminder(self) -> Reminder | None:
        """Return the reminder associated with the earliest future time."""
        upcoming = self.upcoming_reminders
        return upcoming[0][1] if upcoming else None

    async def async_setup(self) -> None:
        """Load data and register listeners."""
        stored = await self._store.async_load() or {}
        for item in stored.get("reminders", []):
            try:
                reminder = Reminder.from_dict(item)
            except (KeyError, TypeError, ValueError):
                _LOGGER.warning("Skipping invalid stored reminder: %s", item)
                continue
            self.reminders[reminder.reminder_id] = reminder
        self._load_notes(stored)
        for item in stored.get("learned_commands", []):
            try:
                command = LearnedCommand.from_dict(item)
            except (CommandMemoryError, KeyError, TypeError, ValueError):
                _LOGGER.warning("Skipping invalid learned command: %s", item)
                continue
            self.learned_commands[command.command_id] = command

        agent_manager = get_agent_manager(self.hass)
        self._unsubs.extend(
            [
                agent_manager.register_trigger(
                    COMMAND_LEARN_SENTENCES,
                    self._async_learn_command_from_voice,
                ),
                agent_manager.register_trigger(
                    COMMAND_LIST_SENTENCES,
                    self._async_list_learned_commands_from_voice,
                ),
                agent_manager.register_trigger(
                    COMMAND_DELETE_SENTENCES,
                    self._async_delete_learned_command_from_voice,
                ),
                agent_manager.register_trigger(
                    CREATE_SENTENCES, self._async_create_from_voice
                ),
                agent_manager.register_trigger(
                    LIST_SENTENCES, self._async_list_from_voice
                ),
                agent_manager.register_trigger(
                    CANCEL_SENTENCES, self._async_cancel_from_voice
                ),
                agent_manager.register_trigger(
                    CAMERA_SENTENCES, self._async_camera_from_voice
                ),
                agent_manager.register_trigger(
                    SEARCH_SENTENCES, self._async_search_from_voice
                ),
                agent_manager.register_trigger(
                    HELP_SENTENCES, self._async_help_from_voice
                ),
                *self._register_note_triggers(agent_manager),
                self.hass.bus.async_listen(
                    EVENT_NOTIFICATION_ACTION, self._async_notification_action
                ),
                self.hass.bus.async_listen(
                    EVENT_NOTIFICATION_CLEARED, self._async_notification_cleared
                ),
            ]
        )
        self._sync_learned_command_triggers(agent_manager)
        self._unsubs.append(
            async_at_started(self.hass, self._async_home_assistant_started)
        )
        self._notify_update()

        # Do not scan Mobile App devices, speakers, TTS entities, or cameras
        # here.  Those optional resources are resolved lazily on first use.

    @callback
    def _async_home_assistant_started(self, _hass: HomeAssistant) -> None:
        """Start reminder scheduling only after Home Assistant is ready."""
        self._schedule_next()

    async def async_unload(self) -> None:
        """Unload listeners and timer."""
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None
        if self._unsub_pending_expiry_timer is not None:
            self._unsub_pending_expiry_timer()
            self._unsub_pending_expiry_timer = None
        if self._unsub_pending_trigger is not None:
            self._unsub_pending_trigger()
            self._unsub_pending_trigger = None
        self._clear_learned_command_triggers()
        for unsub in self._unsubs:
            unsub()
        self._zalo_ha_conversation_ids.clear()
        self._unsubs.clear()
        self._pending.clear()
        self._pending_deletions.clear()
        self._pending_voice_cameras.clear()
        self._zalo_pending_creations.clear()
        self._zalo_pending_deletions.clear()
        self._zalo_pending_cameras.clear()
        self._zalo_pending_calendar_events.clear()
        self._clear_discovery_caches()
        self._clear_all_note_pending()
        background_tasks = tuple(self._zalo_background_tasks)
        for task in background_tasks:
            task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
        self._zalo_background_tasks.clear()
        await self._store.async_save(self._serialize())

    @callback
    def _clear_discovery_caches(self) -> None:
        """Drop lazily populated optional-device caches."""
        self._mobile_targets_cache = None
        self._mobile_targets_cache_until = 0.0
        self._speaker_targets_cache = None
        self._speaker_targets_cache_until = 0.0
        self._camera_targets_cache = None
        self._camera_targets_cache_until = 0.0
        self._tts_entity_id_cache = None
        self._tts_entity_id_cache_set = False
        self._tts_entity_id_cache_until = 0.0

    def _serialize(self) -> dict[str, Any]:
        """Serialize all reminders."""
        return {
            "reminders": [
                reminder.as_dict() for reminder in self.reminders.values()
            ],
            "notes": self._serialize_notes(),
            "learned_commands": [
                command.as_dict()
                for command in sorted(
                    self.learned_commands.values(),
                    key=lambda item: item.created_at,
                )
            ],
        }

    @callback
    def _save_later(self) -> None:
        """Schedule a storage write."""
        self._store.async_delay_save(self._serialize, 1)

    @property
    def learned_command_count(self) -> int:
        """Return the number of persistent custom command phrases."""
        return len(self.learned_commands)

    @property
    def learned_command_sensor_rows(self) -> list[dict[str, Any]]:
        """Return learned command metadata safe for sensor attributes."""
        commands = sorted(
            self.learned_commands.values(),
            key=lambda item: (item.phrase, item.command_id),
        )
        return [
            {
                "stt": index,
                "command_id": command.command_id,
                "cau_lenh": command.phrase,
                "chuc_nang": command.action_label,
                "lenh_dich": command.target_label,
                "nhan_noi_dung_theo": command.accepts_request,
                "cap_nhat_luc": command.updated_at.isoformat(),
            }
            for index, command in enumerate(commands, start=1)
        ]

    @callback
    def _clear_learned_command_triggers(self) -> None:
        """Unregister every dynamically learned Assist trigger."""
        for unsub in self._learned_trigger_unsubs:
            try:
                unsub()
            except Exception:  # noqa: BLE001 - best effort during reload
                _LOGGER.debug(
                    "Failed to unregister one learned command trigger",
                    exc_info=True,
                )
        self._learned_trigger_unsubs.clear()

    @callback
    def _sync_learned_command_triggers(self, agent_manager: Any | None = None) -> None:
        """Re-register all learned aliases so changes apply immediately."""
        self._clear_learned_command_triggers()
        agent_manager = agent_manager or get_agent_manager(self.hass)
        for command in sorted(
            self.learned_commands.values(),
            key=lambda item: (item.phrase, item.command_id),
        ):
            try:
                unsub = agent_manager.register_trigger(
                    hassil_sentences(command),
                    partial(
                        self._async_execute_learned_command_from_voice,
                        command_id=command.command_id,
                    ),
                )
            except Exception:  # noqa: BLE001 - keep other aliases active
                _LOGGER.exception(
                    "Failed to register learned command phrase %s",
                    command.phrase,
                )
                continue
            self._learned_trigger_unsubs.append(unsub)

    def _supported_action_for_text(self, text: str) -> str | None:
        """Resolve one existing command phrase to a learnable action."""
        explicit = explicit_target_action(text)
        if explicit is not None:
            return explicit

        note_kind = note_zalo_command_kind(text)
        if note_kind is not None:
            return note_kind

        builtin = self._builtin_zalo_command_kind(text)
        if builtin in {
            ACTION_REMINDER_CREATE,
            ACTION_REMINDER_LIST,
            ACTION_REMINDER_DELETE,
            ACTION_HELP,
            ACTION_SEARCH,
            ACTION_IMAGE_GENERATION,
        }:
            return builtin

        ha_kind = explicit_home_assistant_request_kind(text)
        if ha_kind == "camera":
            return ACTION_CAMERA
        if ha_kind == "calendar":
            return ACTION_CALENDAR
        if ha_kind == "conversation":
            return ACTION_HOME_ASSISTANT
        return None

    def _learned_commands_text(self) -> str:
        """Build a compact numbered list for Voice Assist or Zalo."""
        commands = sorted(
            self.learned_commands.values(),
            key=lambda item: (item.phrase, item.command_id),
        )
        if not commands:
            return (
                "Bộ nhớ câu lệnh chưa có câu nào. Ví dụ, hãy nói: "
                "học câu lệnh xem cổng để chụp ảnh camera."
            )
        lines = ["Các câu lệnh đã học là:"]
        for index, command in enumerate(commands, start=1):
            suffix = " và nội dung phía sau" if command.accepts_request else ""
            lines.append(
                f"{index} - {command.phrase}: {command.target_label}{suffix}."
            )
        lines.append(
            "Có thể nói xóa câu lệnh rồi đọc đúng câu cần quên."
        )
        return "\n".join(lines)

    def _upsert_learned_command(
        self, phrase: str, action: str, target_text: str | None = None
    ) -> tuple[LearnedCommand | None, str]:
        """Create or update one alias and return a user-facing result."""
        builtin_action = self._supported_action_for_text(phrase)
        if builtin_action is not None:
            if builtin_action == action:
                return None, (
                    f"Câu {phrase} đã là câu lệnh có sẵn cho chức năng "
                    f"{ACTION_LABELS[action]}, nên không cần lưu thêm."
                )
            return None, (
                f"Câu {phrase} đang là câu lệnh có sẵn cho chức năng "
                f"{ACTION_LABELS.get(builtin_action, builtin_action)}. "
                "Hãy chọn cách nói khác để tránh nhầm lẫn."
            )

        normalized = normalize_text(phrase)
        existing = next(
            (
                command
                for command in self.learned_commands.values()
                if command.normalized_phrase == normalized
            ),
            None,
        )
        for other in self.learned_commands.values():
            if existing is not None and other.command_id == existing.command_id:
                continue
            other_phrase = other.normalized_phrase
            new_accepts_request = action in REQUEST_ACTIONS
            overlaps = (
                other.accepts_request
                and normalized.startswith(f"{other_phrase} ")
            ) or (
                new_accepts_request
                and other_phrase.startswith(f"{normalized} ")
            )
            if overlaps:
                return None, (
                    f"Câu {phrase} dễ nhầm với câu đã học {other.phrase}. "
                    "Hãy dùng cách nói khác rõ hơn."
                )
        now = dt_util.now()
        if existing is not None:
            old_action = existing.action
            old_target_label = existing.target_label
            existing.phrase = phrase
            existing.normalized_phrase = normalized
            existing.action = action
            existing.target_text = target_text
            existing.updated_at = now
            self._sync_learned_command_triggers()
            self._save_later()
            self._notify_update()
            if old_action == action and old_target_label == existing.target_label:
                return existing, (
                    f"Câu {phrase} đã được ghi nhớ cho chức năng "
                    f"{existing.target_label}."
                )
            return existing, (
                f"Đã đổi câu {phrase} từ {old_target_label} "
                f"sang {existing.target_label}."
            )

        if len(self.learned_commands) >= MAX_LEARNED_COMMANDS:
            return None, (
                f"Bộ nhớ đã đạt giới hạn {MAX_LEARNED_COMMANDS} câu lệnh. "
                "Hãy xóa câu không còn dùng trước khi dạy câu mới."
            )

        command = LearnedCommand(
            command_id=uuid.uuid4().hex,
            phrase=phrase,
            normalized_phrase=normalized,
            action=action,
            created_at=now,
            updated_at=now,
            target_text=target_text,
        )
        self.learned_commands[command.command_id] = command
        self._sync_learned_command_triggers()
        self._save_later()
        self._notify_update()
        suffix = (
            " Nội dung nói phía sau câu này cũng sẽ được chuyển tiếp."
            if command.accepts_request
            else ""
        )
        return command, (
            f"Đã học câu lệnh {command.phrase} cho chức năng "
            f"{command.target_label}.{suffix}"
        )

    def _delete_learned_command_text(self, text: str) -> str:
        """Delete one or all aliases from a natural management request."""
        try:
            clear_all, phrase = parse_delete_request(text)
        except CommandMemoryError as err:
            return str(err)

        if clear_all:
            count = len(self.learned_commands)
            if not count:
                return "Bộ nhớ câu lệnh đang trống."
            self.learned_commands.clear()
            self._sync_learned_command_triggers()
            self._save_later()
            self._notify_update()
            return f"Đã xóa toàn bộ {count} câu lệnh đã học."

        normalized = normalize_text(phrase)
        matches = [
            command
            for command in self.learned_commands.values()
            if command.normalized_phrase == normalized
        ]
        if not matches:
            return (
                f"Không tìm thấy câu lệnh {phrase} trong bộ nhớ. "
                "Hãy nói danh sách câu lệnh đã học để kiểm tra."
            )
        for command in matches:
            self.learned_commands.pop(command.command_id, None)
        self._sync_learned_command_triggers()
        self._save_later()
        self._notify_update()
        return f"Đã quên câu lệnh {phrase}."

    def _learn_command_text(self, text: str) -> str:
        """Parse and persist one natural teach request."""
        try:
            phrase, target = parse_learn_request(text)
        except CommandMemoryError as err:
            return str(err)
        action = self._supported_action_for_text(target)
        if action is None:
            supported = ", ".join(ACTION_LABELS.values())
            return (
                f"Chưa nhận ra chức năng {target}. Các chức năng có thể học gồm: "
                f"{supported}."
            )
        target_text = (
            target
            if action in {ACTION_HOME_ASSISTANT, ACTION_CALENDAR}
            else None
        )
        _command, response = self._upsert_learned_command(
            phrase, action, target_text
        )
        return response

    @callback
    def _notify_update(self) -> None:
        """Notify entities that reminder data changed."""
        async_dispatcher_send(self.hass, self.update_signal)

    @callback
    def _schedule_next(self) -> None:
        """Schedule the next reminder callback."""
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None

        # Avoid firing overdue reminders and scanning notification targets
        # while other integrations are still starting.
        if self.hass.state is not CoreState.running:
            return

        due = self._raw_next_due()
        if due is None:
            return
        now = dt_util.now()
        if due <= now:
            due = now + timedelta(seconds=1)
        self._unsub_timer = async_track_point_in_time(
            self.hass, self._async_timer_fired, due
        )

    async def _async_timer_fired(self, _now: datetime) -> None:
        """Process reminders that are due."""
        self._unsub_timer = None
        now = dt_util.now()
        changed = False

        for reminder in list(self.reminders.values()):
            should_notify = False

            if reminder.snooze_until is not None and reminder.snooze_until <= now:
                reminder.snooze_until = None
                should_notify = True
                changed = True

            if reminder.next_run is not None and reminder.next_run <= now:
                should_notify = True
                changed = True
                if reminder.is_recurring:
                    next_run = reminder.next_run
                    while next_run is not None and next_run <= now:
                        next_run = _next_recurrence(reminder, next_run)
                    reminder.next_run = next_run
                else:
                    reminder.next_run = None
                    reminder.delivered = True

            if should_notify:
                reminder.last_notified = now
                await self._async_send_notification(reminder)

        if changed:
            self._save_later()
            self._notify_update()
        self._schedule_next()

    async def async_add_reminder(self, reminder: Reminder) -> None:
        """Add and schedule a reminder."""
        self.reminders[reminder.reminder_id] = reminder
        self._save_later()
        self._schedule_next()
        self._notify_update()

    async def async_snooze(self, reminder_id: str, minutes: int) -> bool:
        """Snooze a reminder."""
        reminder = self.reminders.get(reminder_id)
        if reminder is None:
            return False
        reminder.snooze_until = dt_util.now() + timedelta(minutes=minutes)
        self._save_later()
        self._schedule_next()
        self._notify_update()
        return True

    async def async_dismiss(self, reminder_id: str) -> bool:
        """Dismiss current occurrence; delete one-time reminder."""
        reminder = self.reminders.get(reminder_id)
        if reminder is None:
            return False
        if reminder.is_recurring:
            reminder.snooze_until = None
        else:
            del self.reminders[reminder_id]
        self._save_later()
        self._schedule_next()
        self._notify_update()
        return True

    async def async_delete(self, reminder_id: str) -> bool:
        """Delete a reminder entirely."""
        reminder = self.reminders.pop(reminder_id, None)
        if reminder is None:
            return False
        await self._async_clear_notification(reminder)
        self._save_later()
        self._schedule_next()
        self._notify_update()
        return True

    def _option(self, key: str, default: Any = None) -> Any:
        """Return an option value with config data fallback."""
        return self.entry.options.get(
            key,
            self.entry.data.get(key, default),
        )

    def _discovered_mobile_device_ids(self) -> list[str]:
        """Return every Mobile App device with an available notify service."""
        return [
            target.mobile_device_id
            for target in self._discovered_mobile_targets()
            if target.mobile_device_id
        ]

    def _legacy_zalo_target(self) -> dict[str, Any] | None:
        """Convert version 0.1 single-Zalo options to one target."""
        if not bool(self._option(CONF_ZALO_ENABLED, DEFAULT_ZALO_ENABLED)):
            return None
        thread_id = str(self._option(CONF_ZALO_THREAD_ID, "")).strip()
        account_selection = str(
            self._option(CONF_ZALO_ACCOUNT_SELECTION, "")
        ).strip()
        zalo_type = str(self._option(CONF_ZALO_TYPE, DEFAULT_ZALO_TYPE)).strip()
        if not thread_id or not account_selection:
            return None
        stable_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"conversational-assistant:{zalo_type}:{thread_id}:{account_selection}",
        ).hex
        return {
            CONF_ZALO_TARGET_ID: stable_id,
            CONF_ZALO_TARGET_NAME: thread_id,
            CONF_ZALO_TARGET_ENABLED: True,
            CONF_ZALO_TYPE: zalo_type,
            CONF_ZALO_THREAD_ID: thread_id,
            CONF_ZALO_ACCOUNT_SELECTION: account_selection,
        }

    def _configured_zalo_targets(self) -> list[dict[str, Any]]:
        """Return normalized enabled Zalo destinations."""
        if CONF_ZALO_TARGETS in self.entry.options:
            raw_targets = self.entry.options.get(CONF_ZALO_TARGETS, [])
        elif CONF_ZALO_TARGETS in self.entry.data:
            raw_targets = self.entry.data.get(CONF_ZALO_TARGETS, [])
        else:
            legacy = self._legacy_zalo_target()
            raw_targets = [legacy] if legacy else []

        if not isinstance(raw_targets, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in raw_targets:
            if not isinstance(item, dict):
                continue
            thread_id = str(item.get(CONF_ZALO_THREAD_ID, "")).strip()
            account_selection = str(
                item.get(CONF_ZALO_ACCOUNT_SELECTION, "")
            ).strip()
            if not thread_id or not account_selection:
                continue
            target_id = str(item.get(CONF_ZALO_TARGET_ID, "")).strip()
            if not target_id:
                target_id = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    (
                        "conversational-assistant:"
                        f"{item.get(CONF_ZALO_TYPE, DEFAULT_ZALO_TYPE)}:"
                        f"{thread_id}:{account_selection}"
                    ),
                ).hex
            normalized.append(
                {
                    CONF_ZALO_TARGET_ID: target_id,
                    CONF_ZALO_TARGET_NAME: str(
                        item.get(CONF_ZALO_TARGET_NAME, thread_id)
                    ).strip()
                    or thread_id,
                    CONF_ZALO_TARGET_ENABLED: bool(
                        item.get(CONF_ZALO_TARGET_ENABLED, True)
                    ),
                    CONF_ZALO_TYPE: str(
                        item.get(CONF_ZALO_TYPE, DEFAULT_ZALO_TYPE)
                    ).strip(),
                    CONF_ZALO_THREAD_ID: thread_id,
                    CONF_ZALO_ACCOUNT_SELECTION: account_selection,
                }
            )
        return [
            target
            for target in normalized
            if target.get(CONF_ZALO_TARGET_ENABLED, True)
        ]

    def _zalo_webhook_account_selection(self) -> str:
        """Return the zalo_bot account selector used for webhook replies."""
        configured = str(
            self._option(CONF_ZALO_WEBHOOK_ACCOUNT_SELECTION, "") or ""
        ).strip()
        if configured:
            return configured

        accounts: list[str] = []
        for target in self._configured_zalo_targets():
            account = str(
                target.get(CONF_ZALO_ACCOUNT_SELECTION, "") or ""
            ).strip()
            if account and account not in accounts:
                accounts.append(account)
        if accounts:
            if len(accounts) > 1:
                _LOGGER.warning(
                    "Several Zalo sending accounts are configured; using %s "
                    "for webhook replies. Set %s to select one explicitly",
                    accounts[0],
                    CONF_ZALO_WEBHOOK_ACCOUNT_SELECTION,
                )
            return accounts[0]
        return ""

    @staticmethod
    def _truthy(value: Any) -> bool:
        """Return a tolerant boolean for webhook JSON values."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        return str(value or "").strip().casefold() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _strip_zalo_bot_mention(
        self, text: str, data: dict[str, Any], account_ids: set[str]
    ) -> str:
        """Remove a leading zca-js mention of the bot account, when present."""
        mentions = data.get("mentions")
        if not isinstance(mentions, list):
            return text.strip()

        for mention in mentions:
            if not isinstance(mention, dict):
                continue
            uid = str(mention.get("uid", "")).strip()
            if not uid or uid not in account_ids:
                continue
            try:
                position = int(mention.get("pos", -1))
                length = int(mention.get("len", 0))
            except (TypeError, ValueError):
                continue
            if position != 0 or length <= 0:
                continue
            return text[length:].lstrip(" ,:;-\t\n")
        return text.strip()

    def _normalize_zalo_webhook_context(
        self, payload: Any
    ) -> tuple[ZaloWebhookContext | None, str]:
        """Validate and normalize one zca-js compatible message event."""
        if not isinstance(payload, dict):
            return None, "invalid_payload"
        data = payload.get("data")
        if not isinstance(data, dict):
            return None, "missing_data"

        configured_account_id = self.zalo_webhook_bot_account_id
        event_account_id = str(payload.get("_accountId", "") or "").strip()
        if (
            configured_account_id
            and event_account_id
            and event_account_id != configured_account_id
        ):
            return None, "other_account"

        sender_id = str(data.get("uidFrom", "") or "").strip()
        account_ids = {
            value
            for value in (configured_account_id, event_account_id)
            if value
        }
        if self._truthy(payload.get("isSelf")):
            return None, "self_message"
        if sender_id and sender_id in account_ids:
            return None, "self_message"

        content = data.get("content")
        if not isinstance(content, str) or not content.strip():
            return None, "unsupported_content"

        raw_thread_type = str(
            payload.get("type", ZALO_TYPE_USER)
        ).strip().casefold()
        thread_type = (
            ZALO_TYPE_GROUP
            if raw_thread_type in {ZALO_TYPE_GROUP, "group"}
            else ZALO_TYPE_USER
        )
        thread_id = str(payload.get("threadId", "") or "").strip()
        if not thread_id and thread_type == ZALO_TYPE_USER:
            thread_id = sender_id
        if not sender_id or not thread_id:
            return None, "missing_sender_or_thread"

        content = self._strip_zalo_bot_mention(content, data, account_ids)
        if not content:
            return None, "empty_message"

        message_id = str(
            data.get("msgId")
            or data.get("cliMsgId")
            or data.get("actionId")
            or ""
        ).strip()
        display_name = str(data.get("dName", "") or "").strip()
        if not display_name:
            display_name = sender_id
        owner_key = f"zalo:{thread_type}:{thread_id}"
        return (
            ZaloWebhookContext(
                account_id=event_account_id or configured_account_id,
                sender_id=sender_id,
                thread_id=thread_id,
                thread_type=thread_type,
                display_name=display_name,
                owner_key=owner_key,
                message_id=message_id,
                text=content[:4000],
            ),
            "ok",
        )

    def _is_duplicate_zalo_message(self, message_id: str) -> bool:
        """Remember recent message IDs so webhook retries are idempotent."""
        if not message_id:
            return False
        if message_id in self._zalo_seen_message_id_set:
            return True

        self._zalo_seen_message_ids.append(message_id)
        self._zalo_seen_message_id_set.add(message_id)
        while (
            len(self._zalo_seen_message_ids)
            > ZALO_WEBHOOK_SEEN_MESSAGE_LIMIT
        ):
            expired = self._zalo_seen_message_ids.popleft()
            self._zalo_seen_message_id_set.discard(expired)
        return False

    @staticmethod
    def _builtin_zalo_command_kind(text: str) -> str | None:
        """Classify built-in reminder, note, and help commands from Zalo."""
        note_kind = note_zalo_command_kind(text)
        if note_kind is not None:
            return note_kind
        normalized = normalize_text(text)
        if not normalized:
            return None

        if _is_integration_help_request(text):
            return "help"
        if _image_generation_request(text) is not None:
            return ACTION_IMAGE_GENERATION
        if _search_request(text) is not None:
            return ACTION_SEARCH

        list_phrases = {
            "list reminders",
            "list my reminders",
            "show reminders",
            "show my reminders",
            "show reminder list",
            "show my reminder list",
            "read reminders",
            "what reminders do i have",
            "what is my next reminder",
            "whats my next reminder",
            "next reminder",
            "liet ke nhac nho",
            "liet ke nhac hen",
            "liet ke lich nhac",
            "liet ke hen gio",
            "doc danh sach nhac nho",
            "doc danh sach nhac hen",
            "doc danh sach lich nhac",
            "doc danh sach hen gio",
            "xem danh sach nhac nho",
            "xem danh sach nhac hen",
            "xem danh sach lich nhac",
            "xem danh sach hen gio",
            "danh sach nhac nho",
            "danh sach nhac hen",
            "danh sach lich nhac",
            "danh sach hen gio",
            "cho toi danh sach nhac nho",
            "cho toi danh sach nhac hen",
            "cho toi danh sach lich nhac",
            "cho toi danh sach hen gio",
            "toi co nhung nhac nho nao",
            "toi co nhung nhac hen nao",
            "toi co nhung lich nhac nao",
            "toi co nhung hen gio nao",
            "nhac nho tiep theo la gi",
            "nhac hen tiep theo la gi",
            "lich nhac tiep theo la gi",
            "hen gio tiep theo la gi",
        }
        if normalized in list_phrases:
            return "list"

        delete_prefixes = (
            "delete reminder",
            "delete a reminder",
            "delete my reminder",
            "remove reminder",
            "remove a reminder",
            "cancel reminder",
            "cancel a reminder",
            "delete all reminders",
            "remove all reminders",
            "cancel all reminders",
            "clear all reminders",
            "huy nhac hen",
            "xoa nhac hen",
            "huy nhac nho",
            "xoa nhac nho",
            "huy lich nhac",
            "xoa lich nhac",
            "huy hen gio",
            "xoa hen gio",
        )
        if normalized.startswith(delete_prefixes):
            return "delete"

        create_prefixes = (
            "remind me ",
            "please remind me ",
            "set reminder ",
            "set a reminder ",
            "please set reminder ",
            "please set a reminder ",
            "create reminder ",
            "create a reminder ",
            "add reminder ",
            "add a reminder ",
            "schedule reminder ",
            "schedule a reminder ",
            "nhac ",
            "hay nhac ",
            "hen ",
            "hay hen ",
            "them nhac ",
            "them nhac nho ",
            "them nhac hen ",
            "them lich nhac ",
            "them hen gio ",
            "hay them nhac ",
            "tao nhac ",
            "tao nhac nho ",
            "tao nhac hen ",
            "tao lich nhac ",
            "tao hen gio ",
            "hay tao nhac ",
            "dat nhac ",
            "dat nhac nho ",
            "dat nhac hen ",
            "dat lich nhac ",
            "dat hen gio ",
            "hay dat nhac ",
        )
        if normalized.startswith(create_prefixes):
            return "create"
        return None

    def _zalo_command_kind(self, text: str) -> str | None:
        """Classify management commands before the normal built-in router."""
        memory_kind = management_command_kind(text)
        if memory_kind is not None:
            return memory_kind
        return self._builtin_zalo_command_kind(text)

    @staticmethod
    def _zalo_delete_request(text: str) -> str:
        """Return normalized text following a delete command prefix."""
        normalized = normalize_text(text)
        if normalized in {
            "delete all reminders",
            "remove all reminders",
            "cancel all reminders",
            "clear all reminders",
        }:
            return "all"
        prefixes = (
            "delete reminder",
            "delete a reminder",
            "delete my reminder",
            "remove reminder",
            "remove a reminder",
            "cancel reminder",
            "cancel a reminder",
            "delete all reminders",
            "remove all reminders",
            "cancel all reminders",
            "clear all reminders",
            "huy nhac hen",
            "xoa nhac hen",
            "huy nhac nho",
            "xoa nhac nho",
            "huy lich nhac",
            "xoa lich nhac",
            "huy hen gio",
            "xoa hen gio",
        )
        for prefix in prefixes:
            if normalized == prefix:
                return ""
            if normalized.startswith(f"{prefix} "):
                return normalized[len(prefix) :].strip()
        return normalized

    @staticmethod
    def _integration_help_text() -> str:
        """Return a compact bilingual guide for Voice Assist and Zalo."""
        return (
            "HƯỚNG DẪN / CONVERSATIONAL ASSISTANT GUIDE\n"
            "Có thể dùng tiếng Việt hoặc English trên Voice Assistant và Zalo.\n\n"
            "1. NHÀ THÔNG MINH / SMART HOME\n"
            "• Bật đèn phòng khách. / Turn on the living room light.\n"
            "• Kiểm tra tầng 2. / Check which devices are on upstairs.\n\n"
            "2. THỜI TIẾT VÀ LỊCH / WEATHER & CALENDAR\n"
            "• Thời tiết hôm nay thế nào? / What's the weather today?\n"
            "• Sự kiện trong 15 ngày nữa. / Events in the next 15 days.\n"
            "• Tạo sự kiện họp nhóm lúc 18h30 ngày mai; sau đó chọn lịch.\n\n"
            "3. TÌM KIẾM INTERNET / INTERNET SEARCH\n"
            "• Tìm thông tin giá vàng hôm nay. / Search for today's gold price.\n"
            "• Tra cứu tin mới về Home Assistant. / Look up the latest Home Assistant news.\n\n"
            "4. TẠO ẢNH AI TRÊN ZALO / AI IMAGE ON ZALO\n"
            "• Tạo ảnh một chú mèo phi hành gia.\n"
            "• Generate an image of a cozy smart home at night.\n\n"
            "5. CAMERA\n"
            "• Chụp camera. / Take a camera photo.\n"
            "• Lấy ảnh camera sân trước. / Capture the front yard camera.\n\n"
            "6. NHẮC HẸN / REMINDERS\n"
            "• Nhắc tôi 30 phút nữa uống thuốc.\n"
            "• Remind me to take medicine in 30 minutes.\n"
            "• Danh sách nhắc hẹn. / Show my reminders.\n\n"
            "7. GHI CHÚ / NOTES\n"
            "• Ghi nhớ mã tủ đồ là 2468. / Remember that the locker code is 2468.\n"
            "• Danh sách ghi chú. / Show my notes.\n\n"
            "8. BỘ NHỚ CÂU LỆNH / COMMAND MEMORY\n"
            "• Học câu lệnh xem cổng để chụp ảnh camera.\n"
            "• Học câu lệnh vẽ giúp tôi để tạo ảnh.\n"
            "• Learn command check the gate to take a camera photo.\n"
            "• Xóa câu lệnh xem cổng. / Delete command check the gate.\n\n"
            "Nói 'hướng dẫn sử dụng tích hợp' hoặc 'how to use the integration' để xem lại."
        )

    def _zalo_upcoming_reminders(
        self, owner_key: str
    ) -> list[tuple[datetime, Reminder]]:
        """Return upcoming reminders created from one Zalo chat."""
        return [
            item
            for item in self.upcoming_reminders
            if item[1].owner_key == owner_key
        ]

    def _zalo_deletable_reminders(
        self, owner_key: str
    ) -> list[tuple[datetime, Reminder]]:
        """Return reminders manageable from one Zalo chat."""
        return [
            item
            for item in self.deletable_reminders
            if item[1].owner_key == owner_key
        ]

    @staticmethod
    def _zalo_deletion_prompt(
        reminders: list[tuple[datetime, Reminder]], invalid: bool = False
    ) -> str:
        """Build a numbered deletion prompt for a Zalo chat."""
        lines: list[str] = []
        for index, (due, reminder) in enumerate(reminders, start=1):
            recurrence = " - lặp lại" if reminder.is_recurring else ""
            lines.append(
                f"{index} - {due.strftime('%H:%M ngày %d/%m/%Y')} - "
                f"{reminder.message}{recurrence}"
            )
        prefix = (
            "Lựa chọn chưa hợp lệ. Hãy trả lời đúng số trong "
            "danh sách.\n"
            if invalid
            else "Các nhắc hẹn có thể xóa là:\n"
        )
        return (
            f"{prefix}{chr(10).join(lines)}\n"
            "Trả lời số cần xóa, ví dụ 1, 1 và 3, hoặc tất cả. "
            "Gửi 'không xóa' để hủy."
        )

    def _zalo_pending_creation(
        self, owner_key: str
    ) -> PendingZaloReminder | None:
        """Return a non-expired target selection for a Zalo chat."""
        pending = self._zalo_pending_creations.get(owner_key)
        if pending is None:
            return None
        if pending.expires_at <= dt_util.now():
            self._zalo_pending_creations.pop(owner_key, None)
            return None
        return pending

    def _zalo_pending_deletion(
        self, owner_key: str
    ) -> PendingZaloDeletion | None:
        """Return a non-expired pending deletion for a Zalo chat."""
        pending = self._zalo_pending_deletions.get(owner_key)
        if pending is None:
            return None
        if pending.expires_at <= dt_util.now():
            self._zalo_pending_deletions.pop(owner_key, None)
            return None
        return pending

    def _zalo_pending_camera(
        self, owner_key: str
    ) -> PendingZaloCamera | None:
        """Return a non-expired camera selection for a Zalo chat."""
        pending = self._zalo_pending_cameras.get(owner_key)
        if pending is None:
            return None
        if pending.expires_at <= dt_util.now():
            self._zalo_pending_cameras.pop(owner_key, None)
            return None
        return pending

    def _zalo_pending_calendar_event(
        self, owner_key: str
    ) -> PendingZaloCalendarEvent | None:
        """Return a non-expired calendar creation selection."""
        pending = self._zalo_pending_calendar_events.get(owner_key)
        if pending is None:
            return None
        if pending.expires_at <= dt_util.now():
            self._zalo_pending_calendar_events.pop(owner_key, None)
            return None
        return pending

    def _zalo_target_for_context(
        self, context: ZaloWebhookContext, account_selection: str
    ) -> dict[str, Any]:
        """Create a stable notification destination for an inbound chat."""
        target_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            (
                "conversational-assistant:zalo-webhook:"
                f"{context.thread_type}:{context.thread_id}:"
                f"{account_selection}"
            ),
        ).hex
        name = (
            f"Nhóm {context.thread_id}"
            if context.thread_type == ZALO_TYPE_GROUP
            else context.display_name
        )
        return {
            CONF_ZALO_TARGET_ID: target_id,
            CONF_ZALO_TARGET_NAME: name,
            CONF_ZALO_TARGET_ENABLED: True,
            CONF_ZALO_TYPE: context.thread_type,
            CONF_ZALO_THREAD_ID: context.thread_id,
            CONF_ZALO_ACCOUNT_SELECTION: account_selection,
        }

    def _zalo_notification_target_for_context(
        self, context: ZaloWebhookContext, account_selection: str
    ) -> NotificationTarget:
        """Return the originating Zalo conversation as a selectable target."""
        zalo = self._zalo_target_for_context(context, account_selection)
        if context.thread_type == ZALO_TYPE_GROUP:
            display_name = "Zalo nhóm hiện tại"
        else:
            display_name = (
                f"Zalo người dùng {context.display_name} "
                "(cuộc trò chuyện này)"
            )
        return NotificationTarget(
            target_id=f"zalo:{zalo[CONF_ZALO_TARGET_ID]}",
            kind="zalo",
            display_name=display_name,
            zalo=zalo,
        )

    @staticmethod
    def _same_zalo_destination(
        first: NotificationTarget, second: NotificationTarget
    ) -> bool:
        """Return whether two selectable targets point to the same Zalo chat."""
        if first.zalo is None or second.zalo is None:
            return False
        keys = (
            CONF_ZALO_TYPE,
            CONF_ZALO_THREAD_ID,
            CONF_ZALO_ACCOUNT_SELECTION,
        )
        return all(
            str(first.zalo.get(key, "")).strip()
            == str(second.zalo.get(key, "")).strip()
            for key in keys
        )

    def _available_targets_for_zalo(
        self, context: ZaloWebhookContext, account_selection: str
    ) -> list[NotificationTarget]:
        """Return voice-like choices plus the originating Zalo conversation."""
        current = self._zalo_notification_target_for_context(
            context, account_selection
        )
        configured_zalo = [
            target
            for target in self._configured_zalo_selection_targets()
            if not self._same_zalo_destination(target, current)
        ]
        return [
            *self._discovered_mobile_targets(),
            current,
            *configured_zalo,
            *self._configured_speaker_targets(),
        ]

    async def _async_send_zalo_webhook_reply(
        self, context: ZaloWebhookContext, message: str
    ) -> bool:
        """Reply to the exact user/group that sent a webhook command."""
        if not self.hass.services.has_service(
            ZALO_DOMAIN, ZALO_SERVICE_SEND_MESSAGE
        ):
            _LOGGER.error(
                "Cannot reply to Zalo webhook because %s.%s is unavailable",
                ZALO_DOMAIN,
                ZALO_SERVICE_SEND_MESSAGE,
            )
            return False

        account_selection = self._zalo_webhook_account_selection()
        if not account_selection:
            _LOGGER.error(
                "Cannot reply to Zalo webhook: configure %s or at least one "
                "Zalo destination with an account selection",
                CONF_ZALO_WEBHOOK_ACCOUNT_SELECTION,
            )
            return False

        try:
            await self.hass.services.async_call(
                ZALO_DOMAIN,
                ZALO_SERVICE_SEND_MESSAGE,
                {
                    "type": context.thread_type,
                    "ttl": 0,
                    "message": message,
                    "thread_id": context.thread_id,
                    "account_selection": account_selection,
                },
                blocking=True,
            )
        except Exception:  # noqa: BLE001 - webhook must still return HTTP 200
            _LOGGER.exception(
                "Failed to reply to Zalo webhook thread %s",
                context.thread_id,
            )
            return False
        return True

    async def _async_create_from_zalo(
        self, context: ZaloWebhookContext
    ) -> str:
        """Parse a Zalo reminder and optionally ask for destinations."""
        try:
            parsed = parse_reminder_request(context.text)
        except ReminderParseError as err:
            return (
                f"Tôi chưa tạo được nhắc nhở. {err} "
                "Ví dụ: nhắc tôi 30 phút nữa uống thuốc; hoặc "
                "tạo nhắc hẹn 18h30 ngày mai đi tập thể dục."
            )

        account_selection = self._zalo_webhook_account_selection()
        if not account_selection:
            return (
                "Chưa cấu hình tài khoản gửi Zalo. Hãy đặt mục "
                "'Tài khoản Zalo trả lời webhook' trong tùy chọn "
                "Conversational Assistant."
            )

        targets = self._available_targets_for_zalo(
            context, account_selection
        )
        if not targets:
            return (
                "Chưa có Mobile App, Zalo hoặc loa có thể nhận nhắc hẹn. "
                "Hãy kiểm tra cấu hình Conversational Assistant."
            )

        confirm_targets = bool(
            self._option(CONF_CONFIRM_TARGETS, DEFAULT_CONFIRM_TARGETS)
        )
        if confirm_targets:
            self._zalo_pending_creations[context.owner_key] = (
                PendingZaloReminder(
                    parsed=parsed,
                    targets=targets,
                    expires_at=dt_util.now()
                    + timedelta(minutes=PENDING_SELECTION_TIMEOUT_MINUTES),
                )
            )
            return self._target_prompt_text(parsed, targets)

        current_target = self._zalo_notification_target_for_context(
            context, account_selection
        )
        reminder = self._reminder_from_targets(
            parsed, [current_target], owner_key=context.owner_key
        )
        await self.async_add_reminder(reminder)
        return (
            f"{parsed.confirmation} "
            "Tôi sẽ gửi lại vào cuộc trò chuyện này."
        )

    async def _async_zalo_pending_creation_reply(
        self,
        context: ZaloWebhookContext,
        pending: PendingZaloReminder,
    ) -> str:
        """Complete a pending Zalo reminder after target selection."""
        if self._is_cancel_pending_text(context.text):
            self._zalo_pending_creations.pop(context.owner_key, None)
            return "Đã hủy nhắc hẹn đang tạo."

        indexes = parse_target_selection(
            context.text,
            [target.display_name for target in pending.targets],
        )
        if not indexes:
            pending.expires_at = dt_util.now() + timedelta(
                minutes=PENDING_SELECTION_TIMEOUT_MINUTES
            )
            return self._target_prompt_text(
                pending.parsed, pending.targets, invalid=True
            )

        selected = [pending.targets[index] for index in indexes]
        reminder = self._reminder_from_targets(
            pending.parsed, selected, owner_key=context.owner_key
        )
        await self.async_add_reminder(reminder)
        self._zalo_pending_creations.pop(context.owner_key, None)

        target_names = ", ".join(
            target.display_name for target in selected
        )
        return (
            f"{pending.parsed.confirmation} "
            f"Sẽ thông báo đến {target_names}."
        )

    async def _async_list_from_zalo(
        self, context: ZaloWebhookContext
    ) -> str:
        """List upcoming reminders belonging to the current Zalo chat."""
        upcoming = self._zalo_upcoming_reminders(context.owner_key)
        if not upcoming:
            return "Cuộc trò chuyện này chưa có nhắc hẹn nào đang chờ."

        lines = ["Các nhắc hẹn sắp tới là:"]
        for index, (due, reminder) in enumerate(upcoming[:10], start=1):
            recurrence = " - lặp lại" if reminder.is_recurring else ""
            lines.append(
                f"{index} - {due.strftime('%H:%M ngày %d/%m/%Y')} - "
                f"{reminder.message}{recurrence}"
            )
        if len(upcoming) > 10:
            lines.append(f"Còn {len(upcoming) - 10} nhắc hẹn khác.")
        return "\n".join(lines)

    async def _async_delete_from_zalo(
        self, context: ZaloWebhookContext
    ) -> str:
        """Delete named/all reminders or start numbered selection in Zalo."""
        request = self._zalo_delete_request(context.text)
        reminders = self._zalo_deletable_reminders(context.owner_key)
        if not reminders:
            return "Cuộc trò chuyện này không có nhắc hẹn nào để xóa."

        if not request:
            self._zalo_pending_deletions[context.owner_key] = (
                PendingZaloDeletion(
                    reminders=reminders,
                    expires_at=dt_util.now()
                    + timedelta(minutes=PENDING_SELECTION_TIMEOUT_MINUTES),
                )
            )
            return self._zalo_deletion_prompt(reminders)

        if request in {"all", "everything", "tat ca", "toan bo", "het"}:
            deleted = 0
            for _due, reminder in reminders:
                if await self.async_delete(reminder.reminder_id):
                    deleted += 1
            self._zalo_pending_deletions.pop(context.owner_key, None)
            return f"Đã xóa {deleted} nhắc hẹn của cuộc trò chuyện này."

        candidates = [
            reminder
            for _due, reminder in reminders
            if request in normalize_text(reminder.message)
            or normalize_text(reminder.message) in request
        ]
        if not candidates:
            return f"Tôi không tìm thấy nhắc hẹn có nội dung {request}."

        reminder = candidates[0]
        await self.async_delete(reminder.reminder_id)
        self._zalo_pending_deletions.pop(context.owner_key, None)
        return f"Đã xóa nhắc hẹn {reminder.message}."

    async def _async_zalo_pending_deletion_reply(
        self,
        context: ZaloWebhookContext,
        pending: PendingZaloDeletion,
    ) -> str:
        """Process a numbered follow-up reply for Zalo deletion."""
        if self._is_cancel_pending_text(context.text):
            self._zalo_pending_deletions.pop(context.owner_key, None)
            return "Đã hủy yêu cầu xóa nhắc hẹn."

        labels = [
            f"{due.strftime('%H:%M ngày %d/%m/%Y')} {reminder.message}"
            for due, reminder in pending.reminders
        ]
        indexes = parse_target_selection(context.text, labels)
        if not indexes:
            pending.expires_at = dt_util.now() + timedelta(
                minutes=PENDING_SELECTION_TIMEOUT_MINUTES
            )
            return self._zalo_deletion_prompt(
                pending.reminders, invalid=True
            )

        selected = [pending.reminders[index][1] for index in indexes]
        self._zalo_pending_deletions.pop(context.owner_key, None)
        deleted_names: list[str] = []
        for reminder in selected:
            if (
                reminder.owner_key == context.owner_key
                and await self.async_delete(reminder.reminder_id)
            ):
                deleted_names.append(reminder.message)

        if not deleted_names:
            return "Danh sách đã thay đổi nên không còn mục nào để xóa."
        if len(deleted_names) == 1:
            return f"Đã xóa nhắc hẹn {deleted_names[0]}."
        return (
            f"Đã xóa {len(deleted_names)} nhắc hẹn: "
            + "; ".join(deleted_names)
            + "."
        )

    def _discovered_camera_targets(self) -> list[CameraTarget]:
        """Return cameras, scanning lazily and caching their identities."""
        now = monotonic()
        cached = self._camera_targets_cache
        if cached is None or now >= self._camera_targets_cache_until:
            states = sorted(
                self.hass.states.async_all("camera"),
                key=lambda state: (
                    str(state.name or state.entity_id).casefold(),
                    state.entity_id,
                ),
            )
            name_counts: dict[str, int] = {}
            for state in states:
                name = str(state.name or state.entity_id).strip()
                key = normalize_text(name)
                name_counts[key] = name_counts.get(key, 0) + 1

            cached = []
            for state in states:
                name = str(state.name or state.entity_id).strip()
                if name_counts.get(normalize_text(name), 0) > 1:
                    name = f"{name} ({state.entity_id})"
                cached.append(
                    CameraTarget(
                        entity_id=state.entity_id,
                        display_name=name,
                        available=state.state
                        not in {STATE_UNAVAILABLE, STATE_UNKNOWN},
                    )
                )
            self._camera_targets_cache = cached
            self._camera_targets_cache_until = (
                now + DISCOVERY_CACHE_SECONDS
            )

        # Camera availability can change quickly, so refresh only the cheap
        # state lookup while reusing the cached entity list and display names.
        cameras: list[CameraTarget] = []
        for camera in cached:
            state = self.hass.states.get(camera.entity_id)
            if state is None:
                continue
            cameras.append(
                CameraTarget(
                    entity_id=camera.entity_id,
                    display_name=camera.display_name,
                    available=state.state
                    not in {STATE_UNAVAILABLE, STATE_UNKNOWN},
                )
            )
        return cameras

    @staticmethod
    def _camera_selection_prompt(
        cameras: list[CameraTarget], invalid: bool = False
    ) -> str:
        """Build a numbered multi-camera confirmation prompt for Zalo."""
        lines = []
        for index, camera in enumerate(cameras, start=1):
            status = " — không khả dụng" if not camera.available else ""
            lines.append(f"{index} - {camera.display_name}{status}")
        prefix = (
            "Lựa chọn chưa hợp lệ. Hãy chọn ít nhất một camera.\n"
            if invalid
            else "Các camera đang có trên Home Assistant:\n"
        )
        return (
            f"{prefix}{chr(10).join(lines)}\n"
            "Trả lời một hoặc nhiều số/tên camera để xác nhận, ví dụ: "
            "1 3 10. Có thể gửi 'tất cả' để chụp mọi camera khả dụng. "
            "Gửi 'không chụp' để hủy."
        )

    @staticmethod
    def _voice_camera_selection_prompt(
        cameras: list[CameraTarget], invalid: bool = False
    ) -> str:
        """Build a numbered camera selection prompt for Assist."""
        lines = []
        for index, camera in enumerate(cameras, start=1):
            status = " - không khả dụng" if not camera.available else ""
            lines.append(f"{index} - {camera.display_name}{status}")
        prefix = (
            "Lựa chọn chưa hợp lệ. Hãy chọn ít nhất một camera khả dụng.\n"
            if invalid
            else "Các camera đang có trên Home Assistant:\n"
        )
        return (
            f"{prefix}{chr(10).join(lines)}\n"
            "Hãy nói một hoặc nhiều số hoặc tên camera, ví dụ 1 và 3. "
            "Bạn cũng có thể nói tất cả, hoặc nói không chụp để hủy."
        )

    @staticmethod
    def _voice_camera_confirmation_prompt(
        cameras: list[CameraTarget],
        zalo_targets: list[dict[str, Any]],
        invalid: bool = False,
    ) -> str:
        """Ask for final consent before capturing and sending images."""
        camera_names = ", ".join(camera.display_name for camera in cameras)
        destination_names = ", ".join(
            str(target.get(CONF_ZALO_TARGET_NAME, "")).strip()
            or str(target.get(CONF_ZALO_THREAD_ID, "")).strip()
            for target in zalo_targets
        )
        prefix = (
            "Tôi chưa nhận được xác nhận rõ ràng. "
            if invalid
            else ""
        )
        return (
            f"{prefix}Bạn đã chọn {camera_names}. "
            f"Ảnh sẽ được gửi lên Zalo đến {destination_names}. "
            "Hãy nói đồng ý để chụp và gửi, hoặc nói không chụp để hủy."
        )

    async def _async_camera_from_zalo(
        self, context: ZaloWebhookContext
    ) -> str:
        """Start camera selection for an image request from Zalo."""
        self._clear_zalo_pending_for_owner(context.owner_key)
        cameras = self._discovered_camera_targets()
        if not cameras:
            return (
                "Chưa tìm thấy entity camera nào trên Home Assistant. "
                "Hãy kiểm tra tích hợp camera đã được tải và entity camera "
                "đang tồn tại."
            )

        self._zalo_pending_cameras[context.owner_key] = PendingZaloCamera(
            cameras=cameras,
            expires_at=dt_util.now()
            + timedelta(minutes=PENDING_SELECTION_TIMEOUT_MINUTES),
        )
        return self._camera_selection_prompt(cameras)

    async def _async_camera_from_voice(
        self, user_input: ConversationInput, _result: RecognizeResult
    ) -> str:
        """Start camera selection from an Assist voice command."""
        zalo_targets = self._configured_zalo_targets()
        if not zalo_targets:
            return await self._async_voice_response(
                user_input,
                "Chưa có Zalo destination nào được cấu hình. Hãy mở cấu hình "
                "Conversational Assistant, thêm ít nhất một Zalo destination, "
                "sau đó quay lại yêu cầu chụp ảnh camera.",
            )

        cameras = self._discovered_camera_targets()
        if not cameras:
            return await self._async_voice_response(
                user_input,
                "Chưa tìm thấy camera nào trên Home Assistant. Hãy kiểm tra "
                "tích hợp camera và trạng thái các entity camera.",
            )

        self._set_pending_voice_camera(user_input, cameras, zalo_targets)
        return await self._async_voice_response(
            user_input, self._voice_camera_selection_prompt(cameras)
        )

    @staticmethod
    def _camera_snapshot_paths(
        media_root: str, owner_key: str, entity_id: str
    ) -> tuple[str, str]:
        """Return filesystem and /media paths for a stable camera snapshot."""
        snapshot_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"conversational-assistant-camera:{owner_key}:{entity_id}",
        ).hex
        relative_path = os.path.join(
            "conversational_assistant", f"camera_{snapshot_id}.jpg"
        )
        return (
            os.path.join(media_root, relative_path),
            "/media/" + relative_path.replace(os.sep, "/"),
        )

    async def _async_send_zalo_typing_to_target(
        self,
        thread_id: str,
        account_selection: str,
        service_context: Context | None = None,
    ) -> bool:
        """Show Zalo typing status without delaying or failing a feature."""
        if not thread_id or not account_selection:
            return False
        if not self.hass.services.has_service(
            ZALO_DOMAIN, ZALO_SERVICE_SEND_TYPING_EVENT
        ):
            return False

        try:
            await self.hass.services.async_call(
                ZALO_DOMAIN,
                ZALO_SERVICE_SEND_TYPING_EVENT,
                {
                    "thread_id": thread_id,
                    "account_selection": account_selection,
                },
                blocking=False,
                context=service_context,
            )
        except Exception:  # noqa: BLE001 - typing is best effort only
            _LOGGER.debug(
                "Failed sending Zalo typing event to thread %s",
                thread_id,
                exc_info=True,
            )
            return False
        return True

    async def _async_send_zalo_typing_event(
        self,
        context: ZaloWebhookContext,
        service_context: Context | None = None,
    ) -> bool:
        """Show typing in the Zalo conversation that sent the request."""
        return await self._async_send_zalo_typing_to_target(
            context.thread_id,
            self._zalo_webhook_account_selection(),
            service_context,
        )

    async def _async_keep_zalo_typing_active(
        self,
        context: ZaloWebhookContext,
        service_context: Context | None,
        stop_event: asyncio.Event,
    ) -> None:
        """Refresh typing until every part of a Zalo request is complete."""
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=ZALO_TYPING_REFRESH_SECONDS
                )
            except TimeoutError:
                await self._async_send_zalo_typing_event(
                    context, service_context
                )

    async def _async_capture_camera_snapshot(
        self,
        owner_key: str,
        camera: CameraTarget,
        service_context: Context | None,
    ) -> tuple[str | None, str | None]:
        """Capture one camera and return its /media path or an error message."""
        camera_state = self.hass.states.get(camera.entity_id)
        if (
            camera_state is None
            or camera_state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}
        ):
            return None, f"{camera.display_name}: camera không khả dụng"

        media_root = self.hass.config.media_dirs.get("local", "/media")
        filename, image_path = self._camera_snapshot_paths(
            media_root, owner_key, camera.entity_id
        )
        await self.hass.async_add_executor_job(
            _prepare_camera_snapshot_path, filename
        )

        try:
            await self.hass.services.async_call(
                "camera",
                "snapshot",
                {
                    "entity_id": camera.entity_id,
                    "filename": filename,
                },
                blocking=True,
                context=service_context,
            )
        except Exception:  # noqa: BLE001 - continue with other cameras
            _LOGGER.exception(
                "Failed to capture snapshot from %s", camera.entity_id
            )
            return None, f"{camera.display_name}: không chụp được ảnh"

        snapshot_exists = await self.hass.async_add_executor_job(
            os.path.isfile, filename
        )
        if not snapshot_exists:
            return None, f"{camera.display_name}: không tạo được file ảnh"
        return image_path, None

    async def _async_send_camera_images_to_zalo(
        self,
        context: ZaloWebhookContext,
        image_paths: list[str],
        camera_names: list[str],
        service_context: Context | None,
    ) -> tuple[bool, str | None]:
        """Send captured camera images to the originating Zalo conversation."""
        account_selection = self._zalo_webhook_account_selection()
        if not account_selection:
            return False, (
                "Chưa có tài khoản Zalo gửi ảnh. Hãy cấu hình tài khoản "
                "phản hồi webhook trong Conversational Assistant."
            )

        # Zalo Bot exposes a native bulk action for groups. Prefer it whenever
        # two or more images were selected, then fall back to send_image if the
        # installed Zalo Bot version does not provide that action.
        if (
            context.thread_type == ZALO_TYPE_GROUP
            and len(image_paths) > 1
            and self.hass.services.has_service(
                ZALO_DOMAIN, ZALO_SERVICE_SEND_IMAGES_TO_GROUP
            )
        ):
            try:
                await self.hass.services.async_call(
                    ZALO_DOMAIN,
                    ZALO_SERVICE_SEND_IMAGES_TO_GROUP,
                    {
                        "thread_id": context.thread_id,
                        "account_selection": account_selection,
                        "image_paths": ",".join(image_paths),
                    },
                    blocking=True,
                    context=service_context,
                )
            except Exception:  # noqa: BLE001 - return a useful Zalo error
                _LOGGER.exception(
                    "Failed sending grouped camera snapshots to Zalo thread %s",
                    context.thread_id,
                )
                return False, (
                    "Đã chụp ảnh nhưng không gửi được nhóm ảnh lên Zalo. "
                    "Hãy kiểm tra action zalo_bot.send_images_to_group."
                )
            return True, None

        if not self.hass.services.has_service(
            ZALO_DOMAIN, ZALO_SERVICE_SEND_IMAGE
        ):
            return False, (
                f"Action {ZALO_DOMAIN}.{ZALO_SERVICE_SEND_IMAGE} chưa sẵn sàng. "
                "Hãy kiểm tra tích hợp zalo_bot."
            )

        for image_path, camera_name in zip(
            image_paths, camera_names, strict=True
        ):
            try:
                await self.hass.services.async_call(
                    ZALO_DOMAIN,
                    ZALO_SERVICE_SEND_IMAGE,
                    {
                        "type": context.thread_type,
                        "ttl": 0,
                        "image_path": image_path,
                        "message": f"Đã chụp ảnh {camera_name}",
                        "thread_id": context.thread_id,
                        "account_selection": account_selection,
                    },
                    blocking=True,
                    context=service_context,
                )
            except Exception:  # noqa: BLE001 - stop on delivery failure
                _LOGGER.exception(
                    "Failed sending camera snapshot to Zalo thread %s",
                    context.thread_id,
                )
                return False, (
                    f"Đã chụp ảnh {camera_name} nhưng không gửi được lên Zalo. "
                    "Hãy kiểm tra action zalo_bot.send_image."
                )
        return True, None

    async def _async_send_camera_images_to_configured_zalo(
        self,
        image_paths: list[str],
        camera_names: list[str],
        zalo_targets: list[dict[str, Any]],
        service_context: Context | None,
    ) -> tuple[list[str], list[str]]:
        """Send camera images to every configured Zalo destination."""
        sent_targets: list[str] = []
        failures: list[str] = []

        for target in zalo_targets:
            target_name = (
                str(target.get(CONF_ZALO_TARGET_NAME, "")).strip()
                or str(target.get(CONF_ZALO_THREAD_ID, "")).strip()
                or "Zalo"
            )
            thread_id = str(target.get(CONF_ZALO_THREAD_ID, "")).strip()
            account_selection = str(
                target.get(CONF_ZALO_ACCOUNT_SELECTION, "")
            ).strip()
            thread_type = str(
                target.get(CONF_ZALO_TYPE, DEFAULT_ZALO_TYPE)
            ).strip()
            if not thread_id or not account_selection:
                failures.append(f"{target_name}: thiếu cấu hình")
                continue

            await self._async_send_zalo_typing_to_target(
                thread_id, account_selection, service_context
            )

            if (
                thread_type == ZALO_TYPE_GROUP
                and len(image_paths) > 1
                and self.hass.services.has_service(
                    ZALO_DOMAIN, ZALO_SERVICE_SEND_IMAGES_TO_GROUP
                )
            ):
                try:
                    await self.hass.services.async_call(
                        ZALO_DOMAIN,
                        ZALO_SERVICE_SEND_IMAGES_TO_GROUP,
                        {
                            "thread_id": thread_id,
                            "account_selection": account_selection,
                            "image_paths": ",".join(image_paths),
                        },
                        blocking=True,
                        context=service_context,
                    )
                except Exception:  # noqa: BLE001 - continue other targets
                    _LOGGER.exception(
                        "Failed sending grouped voice camera snapshots to %s",
                        thread_id,
                    )
                    failures.append(f"{target_name}: gửi nhóm ảnh thất bại")
                    continue
                sent_targets.append(target_name)
                continue

            if not self.hass.services.has_service(
                ZALO_DOMAIN, ZALO_SERVICE_SEND_IMAGE
            ):
                failures.append(
                    f"{target_name}: action {ZALO_DOMAIN}."
                    f"{ZALO_SERVICE_SEND_IMAGE} chưa sẵn sàng"
                )
                continue

            target_failed = False
            for image_path, camera_name in zip(
                image_paths, camera_names, strict=True
            ):
                try:
                    await self.hass.services.async_call(
                        ZALO_DOMAIN,
                        ZALO_SERVICE_SEND_IMAGE,
                        {
                            "type": thread_type,
                            "ttl": 0,
                            "image_path": image_path,
                            "message": f"Đã chụp ảnh {camera_name}",
                            "thread_id": thread_id,
                            "account_selection": account_selection,
                        },
                        blocking=True,
                        context=service_context,
                    )
                except Exception:  # noqa: BLE001 - continue other targets
                    _LOGGER.exception(
                        "Failed sending voice camera snapshot to %s",
                        thread_id,
                    )
                    failures.append(f"{target_name}: gửi ảnh thất bại")
                    target_failed = True
                    break
            if not target_failed:
                sent_targets.append(target_name)

        return sent_targets, failures

    @staticmethod
    def _is_voice_camera_confirmation(text: str) -> bool:
        """Return True when a follow-up clearly approves capture and send."""
        normalized = normalize_text(text)
        return normalized in {
            "yes",
            "yes take it",
            "yes capture",
            "confirm",
            "confirmed",
            "go ahead",
            "proceed",
            "take it",
            "take the photo",
            "capture it",
            "capture and send",
            "send it",
            "dong y",
            "dong y chup",
            "dong y chup va gui",
            "toi dong y",
            "xac nhan",
            "xac nhan chup",
            "toi xac nhan",
            "co",
            "duoc",
            "duoc roi",
            "vang",
            "vang dong y",
            "ok",
            "oke",
            "chup di",
            "chup anh di",
            "hay chup",
            "chup va gui",
            "gui di",
            "tien hanh",
        }

    @staticmethod
    def _is_voice_camera_cancellation(text: str) -> bool:
        """Return True for a clear camera cancellation response."""
        normalized = normalize_text(text)
        return normalized in {
            "no",
            "cancel",
            "stop",
            "do not capture",
            "dont capture",
            "don t capture",
            "do not take the photo",
            "dont take the photo",
            "don t take the photo",
            "never mind",
            "khong",
            "khong dong y",
            "khong chup",
            "khong chup anh",
            "huy",
            "huy chup",
            "thoi",
            "thoi khong chup",
        }

    def _current_voice_camera_zalo_targets(
        self, pending: PendingVoiceCamera
    ) -> list[dict[str, Any]]:
        """Return still-configured destinations from the original confirmation."""
        current_targets = self._configured_zalo_targets()
        current_by_id = {
            str(target.get(CONF_ZALO_TARGET_ID, "")): target
            for target in current_targets
        }
        selected: list[dict[str, Any]] = []
        for original in pending.zalo_targets:
            target_id = str(original.get(CONF_ZALO_TARGET_ID, ""))
            current = current_by_id.get(target_id)
            if current is not None:
                selected.append(current)
        return selected

    async def _async_capture_voice_cameras(
        self,
        user_input: ConversationInput,
        pending: PendingVoiceCamera,
        zalo_targets: list[dict[str, Any]],
    ) -> str:
        """Capture selected cameras and send them to configured Zalo targets."""
        if not self.hass.services.has_service("camera", "snapshot"):
            return "Action camera.snapshot chưa sẵn sàng trên Home Assistant."

        for target in zalo_targets:
            await self._async_send_zalo_typing_to_target(
                str(target.get(CONF_ZALO_THREAD_ID, "")).strip(),
                str(target.get(CONF_ZALO_ACCOUNT_SELECTION, "")).strip(),
                user_input.context,
            )

        owner_key = "voice:" + uuid.uuid5(
            uuid.NAMESPACE_URL,
            "|".join(sorted(pending.source_keys)),
        ).hex
        image_paths: list[str] = []
        camera_names: list[str] = []
        capture_failures: list[str] = []
        for camera in pending.selected_cameras:
            image_path, error = await self._async_capture_camera_snapshot(
                owner_key, camera, user_input.context
            )
            if image_path is not None:
                image_paths.append(image_path)
                camera_names.append(camera.display_name)
            elif error:
                capture_failures.append(error)

        if not image_paths:
            details = "; ".join(capture_failures)
            return (
                "Không chụp được ảnh từ các camera đã chọn. "
                + (details or "Hãy kiểm tra camera và thư mục media.")
            )

        sent_targets, send_failures = (
            await self._async_send_camera_images_to_configured_zalo(
                image_paths,
                camera_names,
                zalo_targets,
                user_input.context,
            )
        )
        if not sent_targets:
            details = "; ".join(send_failures)
            return (
                f"Đã chụp {len(image_paths)} ảnh nhưng chưa gửi được lên Zalo. "
                + (details or "Hãy kiểm tra tích hợp zalo_bot.")
            )

        response = (
            f"Đã chụp {len(image_paths)} ảnh và gửi lên Zalo đến "
            + ", ".join(sent_targets)
            + "."
        )
        problems = [*capture_failures, *send_failures]
        if problems:
            response += " Một số mục không hoàn tất: " + "; ".join(problems) + "."
        return response

    async def _async_capture_cameras_to_zalo(
        self,
        context: ZaloWebhookContext,
        cameras: list[CameraTarget],
        service_context: Context | None,
    ) -> ZaloDirectResponse | str:
        """Capture selected cameras, then send all successful images to Zalo."""
        if not self.hass.services.has_service("camera", "snapshot"):
            return "Action camera.snapshot chưa sẵn sàng trên Home Assistant."

        image_paths: list[str] = []
        camera_names: list[str] = []
        failures: list[str] = []
        for camera in cameras:
            image_path, error = await self._async_capture_camera_snapshot(
                context.owner_key, camera, service_context
            )
            if image_path is not None:
                image_paths.append(image_path)
                camera_names.append(camera.display_name)
            elif error:
                failures.append(error)

        if not image_paths:
            details = "; ".join(failures)
            return (
                "Không chụp được ảnh từ các camera đã chọn. "
                + (details or "Hãy kiểm tra camera và thư mục /media.")
            )

        sent, send_error = await self._async_send_camera_images_to_zalo(
            context,
            image_paths,
            camera_names,
            service_context,
        )
        if not sent:
            return send_error or "Không gửi được ảnh camera lên Zalo."

        if failures:
            await self._async_send_zalo_webhook_reply(
                context,
                f"Đã gửi {len(image_paths)} ảnh. Không chụp được: "
                + "; ".join(failures)
                + ".",
            )
        return ZaloDirectResponse(
            sent=True,
            response_type="images" if len(image_paths) > 1 else "image",
        )

    async def _async_zalo_pending_camera_reply(
        self,
        context: ZaloWebhookContext,
        pending: PendingZaloCamera,
        service_context: Context | None,
    ) -> ZaloDirectResponse | str:
        """Handle one or more camera selections from Zalo."""
        normalized = normalize_text(context.text)
        cancel_phrases = {
            "no",
            "cancel",
            "stop",
            "skip",
            "do not capture",
            "dont capture",
            "don t capture",
            "do not take a photo",
            "dont take a photo",
            "don t take a photo",
            "never mind",
            "khong",
            "huy",
            "bo qua",
            "khong chup",
            "khong chup anh",
            "khong lay anh",
        }
        if normalized in cancel_phrases:
            self._zalo_pending_cameras.pop(context.owner_key, None)
            self._zalo_pending_calendar_events.pop(context.owner_key, None)
            return "Đã hủy yêu cầu chụp ảnh camera."

        selected = parse_target_selection(
            context.text, [camera.display_name for camera in pending.cameras]
        )
        if not selected:
            pending.expires_at = dt_util.now() + timedelta(
                minutes=PENDING_SELECTION_TIMEOUT_MINUTES
            )
            return self._camera_selection_prompt(
                pending.cameras, invalid=True
            )

        cameras = [pending.cameras[index] for index in selected]
        unavailable = [
            camera.display_name for camera in cameras if not camera.available
        ]
        available = [camera for camera in cameras if camera.available]
        if not available:
            pending.expires_at = dt_util.now() + timedelta(
                minutes=PENDING_SELECTION_TIMEOUT_MINUTES
            )
            return (
                "Các camera đã chọn hiện không khả dụng: "
                + ", ".join(unavailable)
                + ". Hãy chọn camera khác.\n"
                + self._camera_selection_prompt(pending.cameras)
            )

        self._zalo_pending_cameras.pop(context.owner_key, None)
        self._zalo_pending_calendar_events.pop(context.owner_key, None)
        result = await self._async_capture_cameras_to_zalo(
            context, available, service_context
        )
        if unavailable and isinstance(result, ZaloDirectResponse):
            await self._async_send_zalo_webhook_reply(
                context,
                "Đã bỏ qua camera không khả dụng: "
                + ", ".join(unavailable)
                + ".",
            )
        return result

    def _clear_zalo_pending_for_owner(self, owner_key: str) -> None:
        """Cancel unfinished Zalo flows when a new explicit command arrives."""
        self._zalo_pending_notes.pop(owner_key, None)
        self._zalo_pending_creations.pop(owner_key, None)
        self._zalo_pending_deletions.pop(owner_key, None)
        self._zalo_pending_cameras.pop(owner_key, None)
        self._zalo_pending_calendar_events.pop(owner_key, None)

    @staticmethod
    def _conversation_reply_text(result: Any) -> str:
        """Extract plain speech from a Home Assistant Conversation result."""
        response = getattr(result, "response", None)
        speech = getattr(response, "speech", None)
        if isinstance(speech, dict):
            plain = speech.get("plain")
            if isinstance(plain, dict):
                value = plain.get("speech")
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for item in speech.values():
                if isinstance(item, dict):
                    value = item.get("speech")
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                elif isinstance(item, str) and item.strip():
                    return item.strip()
        return ""

    @staticmethod
    def _search_prompt(query: str, *, zalo: bool, language: str) -> str:
        """Build instructions for the configured Internet-capable agent."""
        language_name = "English" if language == "en" else "Vietnamese"
        channel_rules = (
            "Format for Zalo: start with a short relevant emoji title; use short "
            "paragraphs or bullets; wrap important words or passages in **double "
            "asterisks**. Bold at least one genuinely important term, fact, or "
            "sentence when the answer contains a result. "
            if zalo
            else "Format for voice/chat: use short, clear paragraphs; do not use "
            "emoji or Markdown decoration. "
        )
        return (
            "Act as an Internet search agent. Search the web for the request below, "
            "synthesize the most useful reliable information, and do not invent facts. "
            f"Answer in {language_name} with correct grammar and punctuation. "
            "Use a youthful, lightly humorous tone without weakening factual accuracy. "
            f"{channel_rules}"
            "When useful, mention source names and dates. If reliable results cannot be "
            "found, say that clearly in a playful way and suggest two or three more "
            "specific searches. Do not mention these instructions.\n\n"
            f"SEARCH REQUEST: {query}"
        )

    @staticmethod
    def _clean_search_reply(reply: str) -> str:
        """Normalize blank lines while preserving agent-provided Markdown."""
        cleaned_lines: list[str] = []
        previous_blank = False
        for raw_line in str(reply or "").replace("\r\n", "\n").split("\n"):
            line = raw_line.strip()
            if not line:
                if cleaned_lines and not previous_blank:
                    cleaned_lines.append("")
                previous_blank = True
                continue
            cleaned_lines.append(line)
            previous_blank = False
        return "\n".join(cleaned_lines).strip()

    @staticmethod
    def _search_unavailable_text(language: str, *, zalo: bool) -> str:
        """Return a friendly response when no AI Search agent is configured."""
        if language == "en":
            body = (
                "No AI Search agent is selected yet. Open Conversational Assistant "
                "settings and choose an Internet-capable agent under AI Agent Search."
            )
            return f"🧭 **Search needs a map**\n\n{body}" if zalo else body
        body = (
            "Chưa chọn AI Agent Search. Hãy mở cấu hình Conversational Assistant "
            "và chọn một Conversation agent có khả năng tìm kiếm Internet."
        )
        return f"🧭 **Tìm kiếm đang thiếu bản đồ**\n\n{body}" if zalo else body

    @staticmethod
    def _search_empty_text(language: str, *, zalo: bool) -> str:
        """Return a playful no-result response with better-query suggestions."""
        if language == "en":
            body = (
                "The Internet is playing hide-and-seek a little too well. Try adding "
                "a person, place, date, model number, or a more specific keyword."
            )
            return f"🕵️ **No reliable result found**\n\n{body}" if zalo else body
        body = (
            "Internet hôm nay chơi trốn tìm hơi kỹ. Hãy thử thêm tên riêng, địa điểm, "
            "mốc thời gian, mã sản phẩm hoặc một từ khóa cụ thể hơn."
        )
        return f"🕵️ **Chưa tìm thấy kết quả đáng tin cậy**\n\n{body}" if zalo else body

    async def _async_ai_search(
        self,
        query: str,
        *,
        conversation_id: str | None,
        service_context: Context | None,
        zalo: bool,
        language_hint: str | None = None,
        zalo_context: ZaloWebhookContext | None = None,
    ) -> tuple[str, str | None]:
        """Run one Internet query with per-agent timeout and automatic failover."""
        language = language_hint or _request_language(query)
        if not query.strip():
            prompt = (
                "Please tell me what you want to search for."
                if language == "en"
                else "Bạn muốn tôi tìm thông tin gì trên Internet?"
            )
            if zalo:
                prompt = (
                    "🔎 **Bạn muốn tìm gì?**\n\n"
                    "Hãy nhập nội dung sau lệnh **Tìm thông tin**."
                    if language != "en"
                    else "🔎 **What should I search for?**\n\n"
                    "Add your topic after **Search for**."
                )
            return prompt, None

        candidates = self._conversation_agent_candidates(self.ai_search_agent_id)
        if not candidates:
            return self._search_unavailable_text(language, zalo=zalo), None

        attempted_agents: list[str] = []
        had_empty_response = False
        primary_agent_id = self.ai_search_agent_id
        total_attempts = len(candidates)
        prompt_text = self._search_prompt(
            query, zalo=zalo, language=language
        )

        for index, (agent_id, agent_name) in enumerate(candidates):
            attempted_agents.append(agent_name)
            try:
                async with asyncio.timeout(ZALO_SEARCH_TIMEOUT_SECONDS):
                    result = await async_converse(
                        hass=self.hass,
                        text=prompt_text,
                        conversation_id=(
                            conversation_id if index == 0 else None
                        ),
                        context=service_context or Context(),
                        language=language,
                        agent_id=agent_id,
                    )
            except TimeoutError:
                _LOGGER.warning(
                    "AI Search agent %s timed out after %s seconds for query %s",
                    agent_id,
                    ZALO_SEARCH_TIMEOUT_SECONDS,
                    query,
                )
            except Exception:  # noqa: BLE001 - rotate instead of failing silently
                _LOGGER.exception(
                    "AI Search agent %s failed for query %s", agent_id, query
                )
            else:
                error_code = self._conversation_result_error_code(result)
                reply = self._clean_search_reply(
                    self._conversation_reply_text(result)
                )
                if not error_code and reply:
                    next_conversation_id = str(
                        getattr(result, "conversation_id", "") or ""
                    ).strip() or None
                    if zalo:
                        heading = (
                            "🔎 **Search results**"
                            if language == "en"
                            else "🔎 **Kết quả tìm kiếm**"
                        )
                        if (
                            "**" not in reply
                            or not reply.startswith(
                                ("🔎", "🌐", "📰", "📌", "💡", "🧭")
                            )
                        ):
                            reply = f"{heading}\n\n{reply}"
                    reply = self._append_ai_attempt_summary(
                        reply,
                        attempted_agents,
                        language=language,
                        zalo=zalo,
                    )
                    # Conversation IDs are provider-specific. Do not replace the
                    # primary agent's stored ID with one produced by a fallback.
                    if primary_agent_id and agent_id != primary_agent_id:
                        next_conversation_id = None
                    return reply, next_conversation_id

                had_empty_response = had_empty_response or not error_code
                _LOGGER.warning(
                    "AI Search agent %s returned no usable answer (error=%s)",
                    agent_id,
                    error_code or "empty_reply",
                )

            if index + 1 < total_attempts:
                await self._async_send_ai_failover_notice(
                    zalo_context,
                    service_context,
                    feature="search",
                    failed_agent=agent_name,
                    next_agent=candidates[index + 1][1],
                    next_attempt=index + 2,
                    total_attempts=total_attempts,
                    language=language,
                )

        if had_empty_response:
            message = self._search_empty_text(language, zalo=zalo)
        else:
            message = (
                "All available search agents failed or timed out. Check the AI "
                "agents configured in Home Assistant and try again."
                if language == "en"
                else "Tất cả AI agent tìm kiếm khả dụng đều lỗi hoặc hết thời gian "
                "chờ. Hãy kiểm tra các AI agent trong Home Assistant rồi thử lại."
            )
            if zalo:
                message = (
                    f"⚠️ **Search agents unavailable**\n\n{message}"
                    if language == "en"
                    else f"⚠️ **Các AI tìm kiếm đều chưa phản hồi**\n\n{message}"
                )
        return (
            self._append_ai_attempt_summary(
                message,
                attempted_agents,
                language=language,
                zalo=zalo,
            ),
            None,
        )

    async def _async_search_from_zalo(
        self,
        context: ZaloWebhookContext,
        service_context: Context | None,
    ) -> str:
        """Search the Internet for a natural-language Zalo request."""
        query = _search_request(context.text)
        reply, conversation_id = await self._async_ai_search(
            query or "",
            conversation_id=self._zalo_search_conversation_ids.get(
                context.owner_key
            ),
            service_context=service_context,
            zalo=True,
            language_hint=_request_language(context.text),
            zalo_context=context,
        )
        if conversation_id:
            self._zalo_search_conversation_ids[context.owner_key] = conversation_id
        return reply

    @staticmethod
    def _image_generation_unavailable_text(language: str) -> str:
        """Return a friendly reply when no image-capable AI Task is selected."""
        if language == "en":
            return (
                "🎨 **The AI artist has no paintbrush yet**\n\n"
                "Open **Conversational Assistant → AI settings** and select an "
                "**AI Task agent for image generation**."
            )
        return (
            "🎨 **Họa sĩ AI đang thiếu cọ vẽ**\n\n"
            "Hãy mở **Conversational Assistant → Cài đặt AI** và chọn "
            "**AI Task Agent tạo ảnh**."
        )

    async def _async_ai_image_delivery_path(
        self, media_source_id: str
    ) -> str | None:
        """Return the best path accepted by zalo_bot.send_image.

        New Home Assistant releases expose a real local Path on PlayMedia.
        Older releases and some custom media-source implementations may only
        provide the media-source URI. The /media fallback matches the working
        Zalo automation format and avoids rejecting a successfully generated
        image only because no filesystem Path was exposed.
        """
        if not media_source_id.startswith("media-source://"):
            return None

        fallback_path = media_source_id.replace(
            "media-source://", "/media/", 1
        )
        try:
            resolved = await media_source.async_resolve_media(
                self.hass, media_source_id, None
            )
        except Exception:  # noqa: BLE001 - keep the proven /media fallback
            _LOGGER.warning(
                "Could not resolve AI generated media source %s; using %s",
                media_source_id,
                fallback_path,
                exc_info=True,
            )
            return fallback_path

        local_path = str(getattr(resolved, "path", "") or "").strip()
        if local_path and await self.hass.async_add_executor_job(
            os.path.isfile, local_path
        ):
            return local_path

        _LOGGER.warning(
            "AI media source %s did not expose an existing local path; using %s",
            media_source_id,
            fallback_path,
        )
        return fallback_path

    async def _async_generate_image_from_zalo(
        self,
        context: ZaloWebhookContext,
        service_context: Context | None,
    ) -> str | ZaloDirectResponse:
        """Generate an image with per-agent timeout and automatic failover."""
        language = _request_language(context.text)
        instructions = _image_generation_request(context.text)
        if instructions is None or not instructions.strip():
            if language == "en":
                return (
                    "🖌️ **What should I draw?**\n\n"
                    "Add a description after **Generate an image**, for example: "
                    "**Generate an image of an astronaut cat**."
                )
            return (
                "🖌️ **Bạn muốn vẽ gì?**\n\n"
                "Hãy thêm mô tả sau lệnh **Tạo ảnh**, ví dụ: "
                "**Tạo ảnh một chú mèo phi hành gia**."
            )

        candidates = self._ai_image_agent_candidates(
            self.ai_image_task_entity_id
        )
        if not candidates:
            return self._image_generation_unavailable_text(language)
        if not self.hass.services.has_service(
            AI_TASK_DOMAIN, AI_TASK_SERVICE_GENERATE_IMAGE
        ):
            if language == "en":
                return (
                    "🤖💥 **AI Task is not ready**\n\n"
                    "Check that Home Assistant provides the action "
                    "**ai_task.generate_image**, then try again."
                )
            return (
                "🤖💥 **AI Task chưa sẵn sàng**\n\n"
                "Hãy kiểm tra Home Assistant đã có action "
                "**ai_task.generate_image** và thử lại nhé."
            )

        account_selection = self._zalo_webhook_account_selection()
        if not account_selection:
            if language == "en":
                return (
                    "📮 **No Zalo sending account is configured**\n\n"
                    "Set **Zalo account for webhook replies** in "
                    "**Zalo settings**."
                )
            return (
                "📮 **Chưa có tài khoản gửi Zalo**\n\n"
                "Hãy cấu hình **Tài khoản Zalo trả lời webhook** trong "
                "**Cài đặt Zalo**."
            )
        if not self.hass.services.has_service(
            ZALO_DOMAIN, ZALO_SERVICE_SEND_IMAGE
        ):
            if language == "en":
                return (
                    "📷 **Zalo cannot receive the image yet**\n\n"
                    f"The action **{ZALO_DOMAIN}.{ZALO_SERVICE_SEND_IMAGE}** "
                    "is not available."
                )
            return (
                "📷 **Zalo chưa nhận ảnh được**\n\n"
                f"Action **{ZALO_DOMAIN}.{ZALO_SERVICE_SEND_IMAGE}** chưa sẵn sàng."
            )

        attempted_agents: list[str] = []
        image_path: str | None = None
        total_attempts = len(candidates)
        for index, (entity_id, agent_name) in enumerate(candidates):
            attempted_agents.append(agent_name)
            try:
                async with asyncio.timeout(ZALO_IMAGE_TIMEOUT_SECONDS):
                    response = await self.hass.services.async_call(
                        AI_TASK_DOMAIN,
                        AI_TASK_SERVICE_GENERATE_IMAGE,
                        {
                            "task_name": "Conversational Assistant Zalo Image",
                            "entity_id": entity_id,
                            "instructions": instructions,
                        },
                        blocking=True,
                        context=service_context,
                        return_response=True,
                    )

                    result = response if isinstance(response, dict) else {}
                    nested_result = result.get("response")
                    if (
                        not result.get("media_source_id")
                        and isinstance(nested_result, dict)
                    ):
                        result = nested_result
                    media_source_id = str(
                        result.get("media_source_id", "") or ""
                    ).strip()
                    image_path = await self._async_ai_image_delivery_path(
                        media_source_id
                    )
                    if image_path is None:
                        raise RuntimeError(
                            "AI Task returned no usable media_source_id"
                        )
            except TimeoutError:
                image_path = None
                _LOGGER.warning(
                    "AI Task entity %s timed out after %s seconds for Zalo thread %s",
                    entity_id,
                    ZALO_IMAGE_TIMEOUT_SECONDS,
                    context.thread_id,
                )
            except Exception:  # noqa: BLE001 - rotate instead of failing silently
                image_path = None
                _LOGGER.exception(
                    "AI Task entity %s failed to generate an image for Zalo thread %s",
                    entity_id,
                    context.thread_id,
                )

            if image_path is not None:
                break

            if index + 1 < total_attempts:
                await self._async_send_ai_failover_notice(
                    context,
                    service_context,
                    feature="image",
                    failed_agent=agent_name,
                    next_agent=candidates[index + 1][1],
                    next_attempt=index + 2,
                    total_attempts=total_attempts,
                    language=language,
                )

        if image_path is None:
            if language == "en":
                message = (
                    "🤖💥 **All AI artists failed or timed out**\n\n"
                    "Check the image-capable AI Task agents in Home Assistant "
                    "and try again."
                )
            else:
                message = (
                    "🤖💥 **Tất cả họa sĩ AI đều lỗi hoặc hết thời gian chờ**\n\n"
                    "Hãy kiểm tra các AI Task Agent có hỗ trợ tạo ảnh trong "
                    "Home Assistant rồi thử lại."
                )
            return self._append_ai_attempt_summary(
                message,
                attempted_agents,
                language=language,
                zalo=True,
            )

        summary = " ".join(instructions.split())
        if len(summary) > 240:
            summary = f"{summary[:237].rstrip()}..."
        message = (
            f"🎨 Generated image: **{summary}**"
            if language == "en"
            else f"🎨 Đã tạo ảnh: **{summary}**"
        )
        message = self._append_ai_attempt_summary(
            message,
            attempted_agents,
            language=language,
            zalo=True,
        )
        try:
            await self.hass.services.async_call(
                ZALO_DOMAIN,
                ZALO_SERVICE_SEND_IMAGE,
                {
                    "type": context.thread_type,
                    "ttl": 0,
                    "image_path": image_path,
                    "message": message,
                    "thread_id": context.thread_id,
                    "account_selection": account_selection,
                },
                blocking=True,
                context=service_context,
            )
        except Exception:  # noqa: BLE001 - return a useful delivery error
            _LOGGER.exception(
                "Failed sending AI generated image to Zalo thread %s",
                context.thread_id,
            )
            if language == "en":
                delivery_error = (
                    "📦 **The image is ready, but Zalo did not receive it**\n\n"
                    "Check **zalo_bot.send_image** and the sending account."
                )
            else:
                delivery_error = (
                    "📦 **Ảnh đã tạo xong nhưng Zalo chưa nhận được**\n\n"
                    "Hãy kiểm tra action **zalo_bot.send_image** và tài khoản gửi."
                )
            return self._append_ai_attempt_summary(
                delivery_error,
                attempted_agents,
                language=language,
                zalo=True,
            )
        return ZaloDirectResponse(sent=True, response_type="generated_image")

    async def _async_home_assistant_conversation_from_zalo(
        self,
        context: ZaloWebhookContext,
        service_context: Context | None,
    ) -> str:
        """Send a Zalo command through HA Conversation with AI failover."""
        language = _request_language(context.text)
        primary_agent_id = self.zalo_conversation_agent_id
        candidates = self._conversation_agent_candidates(primary_agent_id)
        attempted_agents: list[str] = []
        total_attempts = len(candidates)

        for index, (agent_id, agent_name) in enumerate(candidates):
            attempted_agents.append(agent_name)
            try:
                async with asyncio.timeout(ZALO_SEARCH_TIMEOUT_SECONDS):
                    result = await async_converse(
                        hass=self.hass,
                        text=context.text,
                        conversation_id=(
                            self._zalo_ha_conversation_ids.get(context.owner_key)
                            if index == 0
                            else None
                        ),
                        context=service_context or Context(),
                        language=language,
                        agent_id=agent_id,
                    )
            except TimeoutError:
                _LOGGER.warning(
                    "Conversation agent %s timed out after %s seconds for Zalo "
                    "thread %s",
                    agent_id,
                    ZALO_SEARCH_TIMEOUT_SECONDS,
                    context.thread_id,
                )
            except Exception:  # noqa: BLE001 - rotate instead of failing silently
                _LOGGER.exception(
                    "Conversation agent %s failed for Zalo thread %s",
                    agent_id,
                    context.thread_id,
                )
            else:
                error_code = self._conversation_result_error_code(result)
                reply = self._conversation_reply_text(result)

                if error_code == "no_valid_targets":
                    message = (
                        "No matching device was found. Check the device, room, "
                        "area, or floor name and enable its Assist exposure."
                        if language == "en"
                        else "Không tìm thấy thiết bị phù hợp. Hãy kiểm tra tên "
                        "thiết bị, phòng/khu vực/sàn và bật expose cho Assist."
                    )
                    return self._append_ai_attempt_summary(
                        message,
                        attempted_agents,
                        language=language,
                        zalo=True,
                    )

                if not error_code and reply:
                    conversation_id = str(
                        getattr(result, "conversation_id", "") or ""
                    ).strip()
                    if agent_id == primary_agent_id and conversation_id:
                        self._zalo_ha_conversation_ids[
                            context.owner_key
                        ] = conversation_id
                    return self._append_ai_attempt_summary(
                        reply,
                        attempted_agents,
                        language=language,
                        zalo=True,
                    )

                _LOGGER.warning(
                    "Conversation agent %s returned no usable answer (error=%s)",
                    agent_id,
                    error_code or "empty_reply",
                )

            if index + 1 < total_attempts:
                await self._async_send_ai_failover_notice(
                    context,
                    service_context,
                    feature="conversation",
                    failed_agent=agent_name,
                    next_agent=candidates[index + 1][1],
                    next_attempt=index + 2,
                    total_attempts=total_attempts,
                    language=language,
                )

        message = (
            "All available Conversation agents failed or timed out. Check the "
            "configured agents and device exposure for Assist."
            if language == "en"
            else "Tất cả Conversation agent khả dụng đều lỗi hoặc hết thời gian "
            "chờ. Hãy kiểm tra agent đã cấu hình và quyền expose thiết bị cho "
            "Assist."
        )
        return self._append_ai_attempt_summary(
            message,
            attempted_agents,
            language=language,
            zalo=True,
        )

    async def _async_home_assistant_conversation_from_voice(
        self,
        user_input: ConversationInput,
        text: str,
    ) -> str:
        """Run a learned HA macro with per-agent timeout and AI failover."""
        conversation_language = str(
            getattr(user_input, "language", "vi") or "vi"
        )
        language = (
            "en"
            if conversation_language.casefold().startswith("en")
            else _request_language(text)
        )
        primary_agent_id = self.zalo_conversation_agent_id
        candidates = self._conversation_agent_candidates(primary_agent_id)
        attempted_agents: list[str] = []

        for index, (agent_id, agent_name) in enumerate(candidates):
            attempted_agents.append(agent_name)
            try:
                async with asyncio.timeout(ZALO_SEARCH_TIMEOUT_SECONDS):
                    result = await async_converse(
                        hass=self.hass,
                        text=text,
                        conversation_id=(
                            user_input.conversation_id if index == 0 else None
                        ),
                        context=user_input.context,
                        language=conversation_language,
                        agent_id=agent_id,
                    )
            except TimeoutError:
                _LOGGER.warning(
                    "Conversation agent %s timed out after %s seconds for learned "
                    "command %s",
                    agent_id,
                    ZALO_SEARCH_TIMEOUT_SECONDS,
                    text,
                )
            except Exception:  # noqa: BLE001 - rotate instead of failing silently
                _LOGGER.exception(
                    "Conversation agent %s failed for learned command %s",
                    agent_id,
                    text,
                )
            else:
                error_code = self._conversation_result_error_code(result)
                reply = self._conversation_reply_text(result)
                if error_code == "no_valid_targets":
                    reply = (
                        "No matching device was found. Check the device name and "
                        "its Assist exposure."
                        if language == "en"
                        else "Không tìm thấy thiết bị phù hợp. Hãy kiểm tra tên "
                        "thiết bị và quyền expose cho Assist."
                    )
                    reply = self._append_ai_attempt_summary(
                        reply,
                        attempted_agents,
                        language=language,
                        zalo=False,
                    )
                    return await self._async_voice_response(user_input, reply)

                if not error_code and reply:
                    reply = self._append_ai_attempt_summary(
                        reply,
                        attempted_agents,
                        language=language,
                        zalo=False,
                    )
                    return await self._async_voice_response(user_input, reply)

                _LOGGER.warning(
                    "Conversation agent %s returned no usable answer for learned "
                    "command (error=%s)",
                    agent_id,
                    error_code or "empty_reply",
                )

        reply = (
            "All available Conversation agents failed or timed out. Check the "
            "configured agents and Assist device exposure."
            if language == "en"
            else "Tất cả Conversation agent khả dụng đều lỗi hoặc hết thời gian "
            "chờ. Hãy kiểm tra agent đã cấu hình và quyền expose thiết bị cho "
            "Assist."
        )
        reply = self._append_ai_attempt_summary(
            reply,
            attempted_agents,
            language=language,
            zalo=False,
        )
        return await self._async_voice_response(user_input, reply)

    def _zalo_exposed_calendar_states(self, text: str) -> list[Any]:
        """Return calendar entities exposed to Home Assistant Assist."""
        states = []
        for state in self.hass.states.async_all("calendar"):
            try:
                exposed = async_should_expose(
                    self.hass,
                    "conversation",
                    state.entity_id,
                )
            except Exception:  # noqa: BLE001 - exposure data may be unavailable
                _LOGGER.exception(
                    "Failed checking Assist exposure for %s", state.entity_id
                )
                exposed = False
            if exposed and state.state != STATE_UNAVAILABLE:
                states.append(state)

        matched = [
            state
            for state in states
            if calendar_matches_query(
                text,
                state.entity_id,
                str(state.name or state.entity_id),
            )
        ]
        return matched or states

    def _zalo_writable_calendar_targets(self) -> list[CalendarTarget]:
        """Return exposed calendars that advertise event creation support."""
        if not self.hass.services.has_service("calendar", "create_event"):
            return []
        targets: list[CalendarTarget] = []
        for state in self._zalo_exposed_calendar_states(""):
            raw_features = state.attributes.get(ATTR_SUPPORTED_FEATURES, 0)
            try:
                supported = int(raw_features)
            except (TypeError, ValueError):
                supported = 0
            if not supported & int(CalendarEntityFeature.CREATE_EVENT):
                continue
            targets.append(
                CalendarTarget(
                    entity_id=state.entity_id,
                    display_name=str(state.name or state.entity_id),
                )
            )
        return sorted(
            targets,
            key=lambda target: (target.display_name.casefold(), target.entity_id),
        )

    @staticmethod
    def _calendar_json_object(reply: str) -> dict[str, Any] | None:
        """Extract one JSON object from an AI parser response."""
        text = str(reply or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        first = text.find("{")
        last = text.rfind("}")
        if first < 0 or last <= first:
            return None
        try:
            payload = json.loads(text[first : last + 1])
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    async def _async_ai_calendar_create_request(
        self,
        text: str,
        now: datetime,
        context: ZaloWebhookContext,
        service_context: Context | None,
    ) -> tuple[CalendarCreateRequest | None, list[str]]:
        """Ask configured Conversation agents to parse one event request."""
        language = _request_language(text)
        candidates = self._conversation_agent_candidates(
            self.zalo_conversation_agent_id
        )
        attempted_agents: list[str] = []
        total_attempts = len(candidates)
        prompt = (
            "You are a strict calendar request parser. Do not execute actions. "
            "Return exactly one JSON object and no explanation. Current local "
            f"datetime is {dt_util.as_local(now).isoformat()}. Parse this user "
            f"request: {text!r}. JSON fields: summary (required string), "
            "all_day (boolean), start_date and end_date for all-day events, or "
            "start_date_time and end_date_time as ISO 8601 with timezone for "
            "timed events; optional description and location. End is exclusive. "
            "Resolve natural Vietnamese or English dates and number words. "
            "Never invent the event content. If the date/time or content is "
            "missing, return {\"error\":\"missing_information\"}."
        )
        for index, (agent_id, agent_name) in enumerate(candidates):
            attempted_agents.append(agent_name)
            try:
                async with asyncio.timeout(min(30, ZALO_SEARCH_TIMEOUT_SECONDS)):
                    result = await async_converse(
                        hass=self.hass,
                        text=prompt,
                        conversation_id=None,
                        context=service_context or Context(),
                        language=language,
                        agent_id=agent_id,
                    )
            except TimeoutError:
                _LOGGER.warning(
                    "Calendar parser agent %s timed out for Zalo thread %s",
                    agent_id,
                    context.thread_id,
                )
            except Exception:  # noqa: BLE001 - rotate to another parser agent
                _LOGGER.exception(
                    "Calendar parser agent %s failed for Zalo thread %s",
                    agent_id,
                    context.thread_id,
                )
            else:
                if not self._conversation_result_error_code(result):
                    payload = self._calendar_json_object(
                        self._conversation_reply_text(result)
                    )
                    if payload and not payload.get("error"):
                        parsed = calendar_create_request_from_ai_payload(
                            payload, now
                        )
                        if parsed is not None:
                            return parsed, attempted_agents

            if index + 1 < total_attempts:
                await self._async_send_ai_failover_notice(
                    context,
                    service_context,
                    feature="calendar",
                    failed_agent=agent_name,
                    next_agent=candidates[index + 1][1],
                    next_attempt=index + 2,
                    total_attempts=total_attempts,
                    language=language,
                )
        return None, attempted_agents

    async def _async_ai_calendar_window(
        self,
        text: str,
        now: datetime,
        context: ZaloWebhookContext,
        service_context: Context | None,
    ) -> tuple[CalendarWindow | None, list[str]]:
        """Use AI only as a fallback for an uncommon explicit time horizon."""
        language = _request_language(text)
        candidates = self._conversation_agent_candidates(
            self.zalo_conversation_agent_id
        )
        attempted_agents: list[str] = []
        total_attempts = len(candidates)
        local_now = dt_util.as_local(now)
        prompt = (
            "You are a strict calendar time-range parser. Do not execute actions. "
            "Return exactly JSON with end_date_time (ISO 8601 with timezone) and "
            "label. The range always starts now. Do not choose a default date. "
            f"Current local datetime: {local_now.isoformat()}. User request: "
            f"{text!r}. If no explicit time horizon exists, return "
            "{\"error\":\"missing_time_horizon\"}."
        )
        for index, (agent_id, agent_name) in enumerate(candidates):
            attempted_agents.append(agent_name)
            try:
                async with asyncio.timeout(min(30, ZALO_SEARCH_TIMEOUT_SECONDS)):
                    result = await async_converse(
                        hass=self.hass,
                        text=prompt,
                        conversation_id=None,
                        context=service_context or Context(),
                        language=language,
                        agent_id=agent_id,
                    )
            except TimeoutError:
                _LOGGER.warning(
                    "Calendar window parser agent %s timed out", agent_id
                )
            except Exception:  # noqa: BLE001 - rotate to another parser agent
                _LOGGER.exception(
                    "Calendar window parser agent %s failed", agent_id
                )
            else:
                if not self._conversation_result_error_code(result):
                    payload = self._calendar_json_object(
                        self._conversation_reply_text(result)
                    )
                    if payload and not payload.get("error"):
                        end = dt_util.parse_datetime(
                            str(payload.get("end_date_time") or "")
                        )
                        if end is not None:
                            if end.tzinfo is None:
                                end = end.replace(tzinfo=local_now.tzinfo)
                            end = dt_util.as_local(end)
                            if local_now < end <= local_now + timedelta(days=3650):
                                label = str(payload.get("label") or "đến mốc đã yêu cầu").strip()
                                return CalendarWindow(local_now, end, label), attempted_agents

            if index + 1 < total_attempts:
                await self._async_send_ai_failover_notice(
                    context,
                    service_context,
                    feature="calendar",
                    failed_agent=agent_name,
                    next_agent=candidates[index + 1][1],
                    next_attempt=index + 2,
                    total_attempts=total_attempts,
                    language=language,
                )
        return None, attempted_agents

    @staticmethod
    def _deterministic_calendar_create_request(
        text: str, now: datetime
    ) -> CalendarCreateRequest:
        """Parse common event creation language without requiring cloud AI."""
        body = str(text or "").strip()
        prefix_patterns = (
            r"^(?:hãy\s+|please\s+)?(?:tạo|thêm|đặt|lên)\s+"
            r"(?:một\s+)?(?:sự\s+kiện|event|lịch)\s*",
            r"^(?:hãy\s+)?(?:tạo|thêm|đặt|lên)\s+"
            r"(?=(?:một\s+)?(?:cuộc\s+họp|cuộc\s+hẹn))",
            r"^(?:please\s+)?(?:create|add|schedule|book)\s+"
            r"(?:an?\s+)?(?:calendar\s+)?event\s*",
            r"^(?:please\s+)?(?:create|add|schedule|book)\s+"
            r"(?=(?:an?\s+)?(?:meeting|appointment))",
        )
        for pattern in prefix_patterns:
            stripped = re.sub(pattern, "", body, count=1, flags=re.IGNORECASE)
            if stripped != body:
                body = stripped.strip(" :-,.")
                break
        if not body:
            raise ReminderParseError("Thiếu nội dung và thời gian sự kiện.")

        # Keep event titles clean when the user explicitly says "all day".
        explicit_all_day = bool(
            re.search(r"\b(?:cả\s+ngày|ca\s+ngay|all\s+day)\b", body, re.IGNORECASE)
        )
        body = re.sub(
            r"\b(?:cả\s+ngày|ca\s+ngay|all\s+day)\b",
            " ",
            body,
            flags=re.IGNORECASE,
        )

        # Standalone day-parts are valid natural clock expressions. Convert
        # them to stable defaults before handing the rest to the reminder
        # parser: morning 08:00, noon 12:00, afternoon 15:00, evening 19:00,
        # night 22:00.
        period_hour: int | None = None
        preserved_meal_period: str | None = None
        period_labels = {
            "sáng": 8,
            "sang": 8,
            "morning": 8,
            "trưa": 12,
            "trua": 12,
            "noon": 12,
            "chiều": 15,
            "chieu": 15,
            "afternoon": 15,
            "tối": 19,
            "toi": 19,
            "evening": 19,
            "đêm": 22,
            "dem": 22,
            "night": 22,
        }
        numeric_clock = bool(
            re.search(
                r"(?:\b(?:[01]?\d|2[0-3])\s*(?:h|giờ|gio|:)"
                r"(?:\s*[0-5]?\d)?\b|"
                r"\b(?:at\s+)?(?:1[0-2]|0?[1-9])(?:[:.]?[0-5]\d)?\s*(?:am|pm)\b)",
                body,
                re.IGNORECASE,
            )
        )
        if not numeric_clock:
            # "tối nay", "sáng mai", "chiều mốt" need both a date and a
            # clock. Replace the complete phrase so bare "mai" is not left
            # behind after removing the day-part.
            compact_period = re.search(
                r"\b(?P<p>sáng|sang|trưa|trua|chiều|chieu|tối|toi|đêm|dem)"
                r"\s+(?P<d>nay|mai|kia|mốt|mot)\b",
                body,
                re.IGNORECASE,
            )
            if compact_period:
                period_word = compact_period.group("p")
                period_hour = period_labels[period_word.casefold()]
                # In phrases such as "ăn tối mai", the day-part is also an
                # essential part of the event title. Remember it while still
                # using it as the natural clock expression.
                if re.search(
                    r"\b(?:ăn|an|dùng\s+bữa|dung\s+bua)\s*$",
                    body[: compact_period.start()],
                    re.IGNORECASE,
                ):
                    preserved_meal_period = period_word
                date_word = compact_period.group("d").casefold()
                replacement = "hôm nay" if date_word == "nay" else (
                    "ngày mai" if date_word == "mai" else "ngày kia"
                )
                body = (
                    body[: compact_period.start()]
                    + replacement
                    + body[compact_period.end() :]
                )
            else:
                period_match = re.search(
                    r"\b(?:vào|vao|lúc|luc)?\s*(?:buổi|buoi)?\s*"
                    r"(?P<p>sáng|sang|trưa|trua|chiều|chieu|tối|toi|đêm|dem|"
                    r"morning|noon|afternoon|evening|night)\b",
                    body,
                    re.IGNORECASE,
                )
                if period_match:
                    period_hour = period_labels[period_match.group("p").casefold()]
                    body = (
                        body[: period_match.start()]
                        + " "
                        + body[period_match.end() :]
                    )

        # The reminder parser already understands concrete dates. For relative
        # durations placed anywhere in the sentence ("họp 2 hôm nữa", "sau
        # hai tuần họp"), resolve the target date first, remove only the time
        # phrase, and feed an explicit date back into that parser.
        number_token = (
            r"(?:\d+|không|khong|một|mot|mốt|hai|ba|bốn|bon|tư|tu|năm|nam|"
            r"lăm|lam|sáu|sau|bảy|bay|tám|tam|chín|chin|mười|muoi|mươi|"
            r"trăm|tram|linh|lẻ|le|one|two|three|four|five|six|seven|eight|"
            r"nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
            r"seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|"
            r"seventy|eighty|ninety|hundred)"
        )
        number_expression = rf"{number_token}(?:\s+{number_token}){{0,5}}"
        unit = r"(?:hôm|hom|ngày|ngay|tuần|tuan|tháng|thang|năm|nam|days?|weeks?|months?|years?)"
        relative_component = rf"(?:{number_expression})\s+{unit}"
        relative_sequence = (
            rf"{relative_component}(?:\s*(?:,|và|va|and)?\s*"
            rf"{relative_component})*"
        )
        relative_tail = (
            r"(?:nữa|nua|sau|tới|toi|kể\s+từ\s+hôm\s+nay|"
            r"ke\s+tu\s+hom\s+nay|tính\s+từ\s+hôm\s+nay|"
            r"tinh\s+tu\s+hom\s+nay|from\s+now|from\s+today|ahead)"
        )
        relative_pattern = re.compile(
            rf"\b(?:"
            rf"(?:sau|trong|after|in)\s+{relative_sequence}"
            rf"(?:\s+{relative_tail})?"
            rf"|{relative_sequence}\s+{relative_tail}"
            rf")\b",
            re.IGNORECASE,
        )
        parser_body = body
        named_horizon_pattern = re.compile(
            r"\b(?:"
            r"(?:thứ|thu)\s+(?:hai|ba|tư|tu|năm|nam|sáu|sau|bảy|bay)"
            r"\s+(?:tuần|tuan)\s+(?:này|nay|sau|tới|toi)"
            r"|(?:chủ\s+nhật|chu\s+nhat)\s+(?:tuần|tuan)"
            r"\s+(?:này|nay|sau|tới|toi)"
            r"|(?:(?:this|next)\s+)?(?:monday|tuesday|wednesday|"
            r"thursday|friday|saturday|sunday)\s+(?:this|next)\s+week"
            r"|(?:ngày|ngay)\s+(?:\d{1,2}|không|khong|một|mot|hai|ba|"
            r"bốn|bon|tư|tu|năm|nam|lăm|lam|sáu|sau|bảy|bay|tám|tam|"
            r"chín|chin|mười|muoi)(?:\s+(?:một|mot|hai|ba|bốn|bon|tư|"
            r"tu|năm|nam|lăm|lam|sáu|sau|bảy|bay|tám|tam|chín|chin))*"
            r"\s+(?:tháng|thang)\s+(?:này|nay|sau|tới|toi)"
            r"|(?:cuối|cuoi)\s+(?:tuần|tuan)\s+(?:sau|tới|toi)"
            r"|(?:cuối|cuoi)\s+(?:tháng|thang)(?:\s+(?:sau|tới|toi))?"
            r"|(?:đầu|dau)\s+(?:tháng|thang)\s+(?:sau|tới|toi)"
            r"|(?:cuối|cuoi)\s+năm"
            r"|next\s+weekend|end\s+of\s+(?:this|next)\s+month|"
            r"end\s+of\s+this\s+year"
            r")\b",
            re.IGNORECASE,
        )
        named_horizon = named_horizon_pattern.search(body)
        if named_horizon:
            target_window = calendar_window_from_text(
                named_horizon.group(0), now
            )
            if target_window is None:
                raise ReminderParseError(
                    "Mốc ngày được yêu cầu đã qua hoặc không hợp lệ."
                )
            target_date = (
                dt_util.as_local(target_window.end)
                - timedelta(microseconds=1)
            ).date()
            parser_body = (
                body[: named_horizon.start()]
                + " "
                + body[named_horizon.end() :]
            ).strip()
            parser_body = f"{parser_body} {target_date.strftime('%d/%m/%Y')}"
        else:
            relative_match = relative_pattern.search(body)
            if relative_match:
                relative_text = relative_match.group(0)
                # The calendar range parser treats "hôm" and "ngày" equally
                # and supports words, digits, weeks, months, and years.
                target_window = calendar_window_from_text(relative_text, now)
                if target_window is not None:
                    # Calendar windows use an exclusive end at midnight so the
                    # entire requested target day is included. Subtract one
                    # tiny unit to recover that inclusive target date.
                    target_date = (
                        dt_util.as_local(target_window.end)
                        - timedelta(microseconds=1)
                    ).date()
                    parser_body = (
                        body[: relative_match.start()]
                        + " "
                        + body[relative_match.end() :]
                    ).strip()
                    parser_body = (
                        f"{parser_body} {target_date.strftime('%d/%m/%Y')}"
                    )

        parser_body = re.sub(r"\s+", " ", parser_body).strip(" :-,.")
        if not parser_body:
            raise ReminderParseError("Thiếu nội dung sự kiện.")

        parser_prefix = (
            "remind me to "
            if _request_language(text).startswith("en")
            else "nhắc tôi "
        )
        parsed = parse_reminder_request(f"{parser_prefix}{parser_body}", now=now)
        summary = parsed.message.strip()
        if preserved_meal_period and not re.search(
            rf"\b{re.escape(preserved_meal_period)}\b",
            summary,
            re.IGNORECASE,
        ):
            summary = f"{summary} {preserved_meal_period}".strip()
        if not summary:
            raise ReminderParseError("Thiếu nội dung sự kiện.")
        local_start = dt_util.as_local(parsed.first_run)

        if period_hour is not None:
            local_start = local_start.replace(
                hour=period_hour, minute=0, second=0, microsecond=0
            )
            if local_start <= dt_util.as_local(now):
                raise ReminderParseError("Thời điểm sự kiện đã qua.")

        all_day = explicit_all_day or (not numeric_clock and period_hour is None)
        if all_day:
            start = datetime.combine(
                local_start.date(), time.min, tzinfo=local_start.tzinfo
            )
            end = start + timedelta(days=1)
        else:
            start = local_start
            end = start + timedelta(hours=1)
        return CalendarCreateRequest(
            summary=summary,
            start=start,
            end=end,
            all_day=all_day,
        )

    @staticmethod
    def _calendar_selection_prompt(
        request: CalendarCreateRequest,
        calendars: list[CalendarTarget],
        *,
        invalid: bool = False,
    ) -> str:
        """Build a numbered writable-calendar selection prompt."""
        lines = [
            (
                "⚠️ Lựa chọn chưa hợp lệ. Hãy trả lời đúng số lịch."
                if invalid
                else "📝 **Đã phân tích yêu cầu tạo sự kiện**"
            ),
            f"\n{format_calendar_create_request(request)}",
            "\n🗓️ **Chọn lịch sẽ thêm sự kiện:**",
        ]
        for index, target in enumerate(calendars, start=1):
            lines.append(f"{index}. {target.display_name}")
        lines.append(
            "\nTrả lời số lịch, ví dụ **1**. Có thể chọn nhiều lịch như "
            "**1 và 3**. Gửi **hủy** để dừng."
        )
        return "\n".join(lines)

    @staticmethod
    def _calendar_create_service_data(
        request: CalendarCreateRequest, entity_id: str
    ) -> dict[str, Any]:
        """Build calendar.create_event data using exclusive end semantics."""
        data: dict[str, Any] = {
            "entity_id": entity_id,
            "summary": request.summary,
        }
        if request.description:
            data["description"] = request.description
        if request.location:
            data["location"] = request.location
        if request.all_day:
            data["start_date"] = request.start.date().isoformat()
            data["end_date"] = request.end.date().isoformat()
        else:
            data["start_date_time"] = request.start.isoformat()
            data["end_date_time"] = request.end.isoformat()
        return data

    async def _async_create_calendar_event_from_zalo(
        self,
        context: ZaloWebhookContext,
        service_context: Context | None,
    ) -> str:
        """Parse an event, list writable calendars, and wait for selection."""
        calendars = self._zalo_writable_calendar_targets()
        if not calendars:
            return (
                "Chưa có lịch nào vừa được expose cho Assist vừa hỗ trợ tạo "
                "sự kiện. Hãy dùng Local Calendar, Google Calendar hoặc lịch "
                "khác có quyền ghi, rồi bật expose cho entity đó."
            )

        now = dt_util.now()
        parsed: CalendarCreateRequest | None = None
        attempted_agents: list[str] = []

        # Prefer the configured AI for nuanced language, but keep a complete
        # deterministic fallback so calendar creation still works offline.
        if self.zalo_conversation_agent_id != HOME_ASSISTANT_AGENT:
            parsed, attempted_agents = await self._async_ai_calendar_create_request(
                context.text, now, context, service_context
            )
        if parsed is None:
            try:
                parsed = self._deterministic_calendar_create_request(
                    context.text, now
                )
            except ReminderParseError as err:
                if not attempted_agents:
                    parsed, attempted_agents = await self._async_ai_calendar_create_request(
                        context.text, now, context, service_context
                    )
                if parsed is None:
                    message = (
                        f"Tôi chưa tách được đầy đủ nội dung và thời gian sự kiện. {err} "
                        "Ví dụ: **tạo sự kiện họp nhóm lúc 18h30 ngày mai**; "
                        "hoặc **thêm sự kiện sinh nhật cả ngày 15/08/2026**."
                    )
                    return self._append_ai_attempt_summary(
                        message,
                        attempted_agents,
                        language=_request_language(context.text),
                        zalo=True,
                    )

        self._zalo_pending_calendar_events[context.owner_key] = (
            PendingZaloCalendarEvent(
                request=parsed,
                calendars=calendars,
                expires_at=dt_util.now()
                + timedelta(minutes=PENDING_SELECTION_TIMEOUT_MINUTES),
                ai_attempted_agents=attempted_agents,
            )
        )
        prompt = self._calendar_selection_prompt(parsed, calendars)
        return self._append_ai_attempt_summary(
            prompt,
            attempted_agents,
            language=_request_language(context.text),
            zalo=True,
        )

    async def _async_zalo_pending_calendar_event_reply(
        self,
        context: ZaloWebhookContext,
        pending: PendingZaloCalendarEvent,
        service_context: Context | None,
    ) -> str:
        """Create a pending event after the user selects one or more calendars."""
        if self._is_cancel_pending_text(context.text):
            self._zalo_pending_calendar_events.pop(context.owner_key, None)
            return "Đã hủy yêu cầu tạo sự kiện."

        indexes = parse_target_selection(
            context.text,
            [calendar.display_name for calendar in pending.calendars],
        )
        if not indexes:
            pending.expires_at = dt_util.now() + timedelta(
                minutes=PENDING_SELECTION_TIMEOUT_MINUTES
            )
            return self._calendar_selection_prompt(
                pending.request, pending.calendars, invalid=True
            )

        selected = [pending.calendars[index] for index in indexes]
        created: list[str] = []
        failed: list[str] = []
        for target in selected:
            try:
                await self.hass.services.async_call(
                    "calendar",
                    "create_event",
                    self._calendar_create_service_data(
                        pending.request, target.entity_id
                    ),
                    blocking=True,
                    context=service_context,
                )
            except Exception:  # noqa: BLE001 - report each failed calendar
                failed.append(target.display_name)
                _LOGGER.exception(
                    "Failed creating event in calendar %s", target.entity_id
                )
            else:
                created.append(target.display_name)

        if not created:
            pending.expires_at = dt_util.now() + timedelta(
                minutes=PENDING_SELECTION_TIMEOUT_MINUTES
            )
            return (
                "⚠️ Chưa tạo được sự kiện trong lịch đã chọn: "
                + ", ".join(failed)
                + ". Hãy kiểm tra quyền ghi của lịch hoặc chọn lịch khác.\n\n"
                + self._calendar_selection_prompt(
                    pending.request, pending.calendars
                )
            )

        self._zalo_pending_calendar_events.pop(context.owner_key, None)
        lines = [
            "✅ **Đã tạo sự kiện thành công**",
            f"\n{format_calendar_create_request(pending.request)}",
            f"\n**Đã thêm vào:** {', '.join(created)}",
        ]
        if failed:
            lines.append(f"**Không thêm được vào:** {', '.join(failed)}")
        return self._append_ai_attempt_summary(
            "\n".join(lines),
            pending.ai_attempted_agents,
            language=_request_language(context.text),
            zalo=True,
        )

    async def _async_read_calendar_from_zalo(
        self,
        context: ZaloWebhookContext,
        service_context: Context | None,
    ) -> str:
        """Read all exposed calendar events from now to an explicit horizon."""
        states = self._zalo_exposed_calendar_states(context.text)
        if not states:
            return (
                "Chưa có lịch nào được expose cho Assist. Hãy vào Cài đặt > "
                "Voice assistants > Expose để cho phép các entity calendar."
            )

        now = dt_util.now()
        window = calendar_window_from_text(context.text, now)
        attempted_agents: list[str] = []
        has_time_reference = calendar_has_time_reference(context.text)
        if window is None and has_time_reference:
            window, attempted_agents = await self._async_ai_calendar_window(
                context.text, now, context, service_context
            )
        if window is None:
            if has_time_reference:
                heading = (
                    "🕒 **Mốc thời gian chưa hợp lệ, đã qua hoặc chưa đủ rõ.**"
                )
            else:
                heading = (
                    "🕒 **Bạn chưa nêu mốc thời gian cụ thể để tra lịch.**"
                )
            message = (
                f"{heading}\n\n"
                "Hãy thêm mốc như **hôm nay**, **ngày mai**, **ngày kia**, "
                "**2 hôm nữa**, **15 ngày nữa**, **1 tuần nữa**, "
                "**1 tháng nữa** hoặc một ngày cụ thể như **15/08/2026**.\n\n"
                "Ví dụ: **sự kiện trong 15 ngày nữa**."
            )
            return self._append_ai_attempt_summary(
                message,
                attempted_agents,
                language=_request_language(context.text),
                zalo=True,
            )

        events = []
        service_available = self.hass.services.has_service(
            "calendar", "get_events"
        )
        for state in states:
            calendar_name = str(state.name or state.entity_id)
            calendar_events = []
            if service_available:
                try:
                    response = await self.hass.services.async_call(
                        "calendar",
                        "get_events",
                        {
                            "entity_id": state.entity_id,
                            "start_date_time": window.start.isoformat(),
                            "end_date_time": window.end.isoformat(),
                        },
                        blocking=True,
                        context=service_context,
                        return_response=True,
                    )
                    calendar_events = extract_calendar_events(
                        response, state.entity_id, calendar_name
                    )
                except Exception:  # noqa: BLE001 - continue other calendars
                    _LOGGER.exception(
                        "Failed reading events from %s", state.entity_id
                    )

            if not calendar_events:
                fallback = event_from_calendar_state(
                    dict(state.attributes), state.entity_id, calendar_name
                )
                if fallback is not None:
                    calendar_events.append(fallback)
            events.extend(calendar_events)

        reply = format_calendar_events(events, window, now)
        return self._append_ai_attempt_summary(
            reply,
            attempted_agents,
            language=_request_language(context.text),
            zalo=True,
        )

    async def _async_calendar_from_zalo(
        self,
        context: ZaloWebhookContext,
        service_context: Context | None,
    ) -> str:
        """Read calendar events or start the event-creation flow."""
        if calendar_request_action(context.text) == "create":
            return await self._async_create_calendar_event_from_zalo(
                context, service_context
            )
        return await self._async_read_calendar_from_zalo(
            context, service_context
        )

    async def _async_process_home_assistant_from_zalo(
        self,
        context: ZaloWebhookContext,
        request_kind: str,
        service_context: Context | None,
    ) -> str:
        """Process one calendar or Conversation command from Zalo."""
        self._clear_zalo_pending_for_owner(context.owner_key)
        if request_kind == "camera":
            return await self._async_camera_from_zalo(context)
        if request_kind == "calendar":
            return await self._async_calendar_from_zalo(
                context, service_context
            )
        return await self._async_home_assistant_conversation_from_zalo(
            context, service_context
        )

    async def _async_process_zalo_message(
        self,
        context: ZaloWebhookContext,
        service_context: Context | None = None,
    ) -> str | ZaloDirectResponse | None:
        """Route one inbound Zalo text message to reminder actions."""
        command = self._zalo_command_kind(context.text)
        learned_match = None
        if command is None:
            learned_match = match_learned_command(
                context.text, list(self.learned_commands.values())
            )
            if learned_match is not None:
                command = learned_match.command.action
                replacement_text = canonical_text(
                    command,
                    learned_match.request,
                    learned_match.command.target_text,
                )
                if replacement_text:
                    context = replace(context, text=replacement_text)
        explicit_ha_kind = (
            explicit_home_assistant_request_kind(context.text)
            if self.zalo_home_assistant_enabled
            else None
        )
        pending_note = self._zalo_pending_note(context.owner_key)
        pending_creation = self._zalo_pending_creation(context.owner_key)
        pending_deletion = self._zalo_pending_deletion(context.owner_key)
        pending_camera = self._zalo_pending_camera(context.owner_key)
        pending_calendar = self._zalo_pending_calendar_event(context.owner_key)
        if (
            pending_calendar is not None
            and command is None
            and explicit_ha_kind is None
        ):
            return await self._async_zalo_pending_calendar_event_reply(
                context, pending_calendar, service_context
            )
        if (
            pending_camera is not None
            and command is None
            and explicit_ha_kind in {None, "camera"}
        ):
            return await self._async_zalo_pending_camera_reply(
                context, pending_camera, service_context
            )
        if (
            pending_note is not None
            and command is None
            and explicit_ha_kind is None
        ):
            return await self._async_pending_note_reply_from_zalo(
                context, pending_note
            )
        if (
            pending_creation is not None
            and command is None
            and explicit_ha_kind is None
        ):
            return await self._async_zalo_pending_creation_reply(
                context, pending_creation
            )
        if (
            pending_deletion is not None
            and command is None
            and explicit_ha_kind is None
        ):
            return await self._async_zalo_pending_deletion_reply(
                context, pending_deletion
            )

        if command == "command_learn":
            self._clear_zalo_pending_for_owner(context.owner_key)
            return self._learn_command_text(context.text)
        if command == "command_list":
            self._clear_zalo_pending_for_owner(context.owner_key)
            return self._learned_commands_text()
        if command == "command_delete":
            self._clear_zalo_pending_for_owner(context.owner_key)
            return self._delete_learned_command_text(context.text)

        if command and command.startswith("note_"):
            self._zalo_pending_creations.pop(context.owner_key, None)
            self._zalo_pending_deletions.pop(context.owner_key, None)
            self._zalo_pending_cameras.pop(context.owner_key, None)
            self._zalo_pending_calendar_events.pop(context.owner_key, None)
            return await self._async_process_note_zalo_command(
                context, command
            )
        if command == ACTION_SEARCH:
            self._clear_zalo_pending_for_owner(context.owner_key)
            return await self._async_search_from_zalo(
                context, service_context
            )
        if command == ACTION_IMAGE_GENERATION:
            self._clear_zalo_pending_for_owner(context.owner_key)
            return await self._async_generate_image_from_zalo(
                context, service_context
            )
        if command == "create":
            self._zalo_pending_notes.pop(context.owner_key, None)
            self._zalo_pending_creations.pop(context.owner_key, None)
            self._zalo_pending_deletions.pop(context.owner_key, None)
            self._zalo_pending_cameras.pop(context.owner_key, None)
            self._zalo_pending_calendar_events.pop(context.owner_key, None)
            return await self._async_create_from_zalo(context)
        if command == "list":
            self._zalo_pending_notes.pop(context.owner_key, None)
            self._zalo_pending_cameras.pop(context.owner_key, None)
            self._zalo_pending_calendar_events.pop(context.owner_key, None)
            return await self._async_list_from_zalo(context)
        if command == "delete":
            self._zalo_pending_notes.pop(context.owner_key, None)
            self._zalo_pending_creations.pop(context.owner_key, None)
            self._zalo_pending_cameras.pop(context.owner_key, None)
            self._zalo_pending_calendar_events.pop(context.owner_key, None)
            return await self._async_delete_from_zalo(context)
        if command == "help":
            self._clear_zalo_pending_for_owner(context.owner_key)
            return self._integration_help_text()
        if command == ACTION_CAMERA:
            self._clear_zalo_pending_for_owner(context.owner_key)
            return await self._async_camera_from_zalo(context)

        if explicit_ha_kind is not None:
            return await self._async_process_home_assistant_from_zalo(
                context, explicit_ha_kind, service_context
            )

        normalized = normalize_text(context.text)
        if (
            context.thread_type == ZALO_TYPE_USER
            and normalized in {"chao", "xin chao", "hi", "hello"}
        ):
            return self._integration_help_text()

        if (
            self.zalo_home_assistant_enabled
            and context.thread_type == ZALO_TYPE_USER
        ):
            return await self._async_process_home_assistant_from_zalo(
                context, "conversation", service_context
            )
        return None

    def _zalo_long_running_action(self, text: str) -> str | None:
        """Return a slow action only when the request has usable content."""
        command = self._zalo_command_kind(text)
        effective_text = text
        if command is None:
            learned_match = match_learned_command(
                text, list(self.learned_commands.values())
            )
            if learned_match is not None:
                command = learned_match.command.action
                effective_text = canonical_text(
                    command,
                    learned_match.request,
                    learned_match.command.target_text,
                )

        if command == ACTION_SEARCH:
            query = _search_request(effective_text)
            return ACTION_SEARCH if query and query.strip() else None
        if command == ACTION_IMAGE_GENERATION:
            instructions = _image_generation_request(effective_text)
            return (
                ACTION_IMAGE_GENERATION
                if instructions and instructions.strip()
                else None
            )
        if (
            self.zalo_home_assistant_enabled
            and explicit_home_assistant_request_kind(effective_text) == "calendar"
        ):
            if (
                calendar_request_action(effective_text) == "create"
                and self.zalo_conversation_agent_id != HOME_ASSISTANT_AGENT
            ):
                return ACTION_CALENDAR
            if (
                calendar_has_time_reference(effective_text)
                and calendar_window_from_text(effective_text, dt_util.now()) is None
            ):
                return ACTION_CALENDAR
        return None

    @staticmethod
    def _zalo_processing_text(language: str) -> str:
        """Return the immediate acknowledgement for a slow request."""
        if language == "en":
            return "⏳ Processing your request. Please wait for the response."
        return "⏳ Đang xử lý thông tin yêu cầu. Hãy chờ phản hồi."

    @staticmethod
    def _zalo_timeout_text(action: str, language: str) -> str:
        """Return a final timeout message for a stalled slow request."""
        if language == "en":
            feature = (
                "image generation"
                if action == ACTION_IMAGE_GENERATION
                else "calendar analysis"
                if action == ACTION_CALENDAR
                else "search"
            )
            return (
                f"⌛ **The {feature} request took too long**\n\n"
                "The AI service did not respond in time. Please try again."
            )
        feature = (
            "tạo ảnh"
            if action == ACTION_IMAGE_GENERATION
            else "phân tích lịch"
            if action == ACTION_CALENDAR
            else "tìm kiếm"
        )
        return (
            f"⌛ **Yêu cầu {feature} đã chờ quá lâu**\n\n"
            "Dịch vụ AI chưa phản hồi kịp. Hãy thử lại nhé."
        )

    @staticmethod
    def _zalo_background_error_text(language: str) -> str:
        """Return a final error when an unexpected background failure occurs."""
        if language == "en":
            return (
                "⚠️ **The request could not be completed**\n\n"
                "An unexpected error occurred. Check the Home Assistant log "
                "and try again."
            )
        return (
            "⚠️ **Chưa thể hoàn thành yêu cầu**\n\n"
            "Đã xảy ra lỗi ngoài dự kiến. Hãy kiểm tra nhật ký Home Assistant "
            "và thử lại."
        )

    async def _async_process_zalo_long_running_message(
        self,
        context: ZaloWebhookContext,
        service_context: Context | None,
        action: str,
    ) -> None:
        """Finish a slow Zalo request after the webhook action has returned."""
        language = _request_language(context.text)
        per_agent_timeout_seconds = (
            ZALO_IMAGE_TIMEOUT_SECONDS
            if action == ACTION_IMAGE_GENERATION
            else ZALO_SEARCH_TIMEOUT_SECONDS
        )
        candidate_count = self._ai_long_running_candidate_count(action)
        # Each candidate receives its own complete timeout window. The outer
        # timeout is only a final safety net for delivery/cleanup overhead.
        timeout_seconds = per_agent_timeout_seconds * candidate_count + 120
        await self._async_send_zalo_typing_event(context, service_context)
        typing_stop = asyncio.Event()
        typing_task = self.hass.async_create_task(
            self._async_keep_zalo_typing_active(
                context, service_context, typing_stop
            )
        )
        try:
            async with asyncio.timeout(timeout_seconds):
                reply = await self._async_process_zalo_message(
                    context, service_context
                )
                if isinstance(reply, ZaloDirectResponse):
                    if not reply.sent:
                        await self._async_send_zalo_webhook_reply(
                            context, self._zalo_background_error_text(language)
                        )
                    return
                if reply is None:
                    await self._async_send_zalo_webhook_reply(
                        context, self._zalo_background_error_text(language)
                    )
                    return
                await self._async_send_zalo_webhook_reply(context, reply)
        except TimeoutError:
            _LOGGER.error(
                "Safety timeout processing Zalo %s request for thread %s after %s "
                "seconds across %s AI candidate(s)",
                action,
                context.thread_id,
                timeout_seconds,
                candidate_count,
            )
            await self._async_send_zalo_webhook_reply(
                context, self._zalo_timeout_text(action, language)
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - never fail silently in background
            _LOGGER.exception(
                "Unexpected failure processing background Zalo request for thread %s",
                context.thread_id,
            )
            await self._async_send_zalo_webhook_reply(
                context, self._zalo_background_error_text(language)
            )
        finally:
            typing_stop.set()
            try:
                await typing_task
            except asyncio.CancelledError:
                typing_task.cancel()
                raise

    def _start_zalo_background_task(
        self,
        context: ZaloWebhookContext,
        service_context: Context | None,
        action: str,
    ) -> None:
        """Start and retain a slow Zalo task until it completes."""
        task = self.hass.async_create_task(
            self._async_process_zalo_long_running_message(
                context, service_context, action
            )
        )
        self._zalo_background_tasks.add(task)
        task.add_done_callback(self._zalo_background_tasks.discard)

    async def async_process_zalo_webhook_payload(
        self,
        payload: Any,
        service_context: Context | None = None,
    ) -> dict[str, Any]:
        """Process one Zalo payload supplied by an existing webhook flow."""
        if not self.zalo_webhook_enabled:
            return {"ok": True, "handled": False, "reason": "disabled"}
        if not isinstance(payload, dict):
            return {
                "ok": False,
                "handled": False,
                "reason": "invalid_payload",
            }

        context, reason = self._normalize_zalo_webhook_context(payload)
        if context is None:
            return {"ok": True, "handled": False, "reason": reason}
        if self._is_duplicate_zalo_message(context.message_id):
            return {"ok": True, "handled": False, "reason": "duplicate"}

        long_action = self._zalo_long_running_action(context.text)
        if long_action is not None:
            processing_message_sent = await self._async_send_zalo_webhook_reply(
                context,
                self._zalo_processing_text(_request_language(context.text)),
            )
            self._start_zalo_background_task(
                context, service_context, long_action
            )
            return {
                "ok": True,
                "handled": True,
                "accepted": True,
                "background": True,
                "processing_message_sent": processing_message_sent,
            }

        # Start typing immediately and keep refreshing it for normal Zalo
        # features until the final text/image response has actually been sent.
        await self._async_send_zalo_typing_event(context, service_context)
        typing_stop = asyncio.Event()
        typing_task = self.hass.async_create_task(
            self._async_keep_zalo_typing_active(
                context, service_context, typing_stop
            )
        )
        try:
            reply = await self._async_process_zalo_message(
                context, service_context
            )
            if isinstance(reply, ZaloDirectResponse):
                return {
                    "ok": True,
                    "handled": True,
                    "reply_sent": reply.sent,
                    "response_type": reply.response_type,
                }
            if reply is None:
                return {
                    "ok": True,
                    "handled": False,
                    "reason": "not_a_command",
                }

            reply_sent = await self._async_send_zalo_webhook_reply(
                context, reply
            )
            return {
                "ok": True,
                "handled": True,
                "reply_sent": reply_sent,
            }
        finally:
            typing_stop.set()
            await typing_task

    def _discovered_mobile_targets(self) -> list[NotificationTarget]:
        """Auto-discover Mobile App devices lazily with a short cache."""
        now = monotonic()
        if (
            self._mobile_targets_cache is not None
            and now < self._mobile_targets_cache_until
        ):
            return list(self._mobile_targets_cache)

        # Resolve usable Mobile App config entries once, instead of resolving
        # config entries and notify services again for every device in the
        # registry.  This changes discovery from repeated nested lookups to one
        # linear registry pass.
        usable_mobile_entry_ids: set[str] = set()
        for config_entry in self.hass.config_entries.async_entries(
            "mobile_app"
        ):
            webhook_id = config_entry.data.get(ATTR_WEBHOOK_ID)
            if not webhook_id:
                continue
            try:
                service = get_notify_service(self.hass, webhook_id)
            except (KeyError, TypeError):
                service = None
            if service and self.hass.services.has_service("notify", service):
                usable_mobile_entry_ids.add(config_entry.entry_id)

        registry = dr.async_get(self.hass)
        targets: list[NotificationTarget] = []
        devices = sorted(
            registry.devices.values(),
            key=lambda device: (
                (device.name_by_user or device.name or device.id).casefold(),
                device.id,
            ),
        )
        for device in devices:
            if not usable_mobile_entry_ids.intersection(
                device.config_entries
            ):
                continue
            name = device.name_by_user or device.name or device.id
            targets.append(
                NotificationTarget(
                    target_id=f"mobile:{device.id}",
                    kind="mobile",
                    display_name=f"Điện thoại {name}",
                    mobile_device_id=device.id,
                )
            )
        self._mobile_targets_cache = targets
        self._mobile_targets_cache_until = now + DISCOVERY_CACHE_SECONDS
        return list(targets)

    def _configured_zalo_selection_targets(self) -> list[NotificationTarget]:
        """Return selectable Zalo destinations."""
        targets: list[NotificationTarget] = []
        for zalo in self._configured_zalo_targets():
            name = str(zalo[CONF_ZALO_TARGET_NAME])
            prefix = (
                "Zalo nhóm"
                if str(zalo[CONF_ZALO_TYPE]) == ZALO_TYPE_GROUP
                else "Zalo người dùng"
            )
            targets.append(
                NotificationTarget(
                    target_id=f"zalo:{zalo[CONF_ZALO_TARGET_ID]}",
                    kind="zalo",
                    display_name=f"{prefix} {name}",
                    zalo=dict(zalo),
                )
            )
        return targets

    def _configured_tts_entity_id(self) -> str | None:
        """Return the configured TTS entity or auto-select an available one."""
        configured = str(self._option(CONF_TTS_ENTITY_ID, "") or "").strip()
        if configured and self.hass.states.get(configured) is not None:
            return configured

        now = monotonic()
        if (
            self._tts_entity_id_cache_set
            and now < self._tts_entity_id_cache_until
        ):
            return self._tts_entity_id_cache

        states = sorted(
            self.hass.states.async_all(TTS_DOMAIN),
            key=lambda state: state.entity_id,
        )
        for state in states:
            if state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                self._tts_entity_id_cache = state.entity_id
                break
        else:
            self._tts_entity_id_cache = (
                states[0].entity_id if states else None
            )
        self._tts_entity_id_cache_set = True
        self._tts_entity_id_cache_until = now + DISCOVERY_CACHE_SECONDS
        return self._tts_entity_id_cache

    def _configured_speaker_targets(self) -> list[NotificationTarget]:
        """Auto-discover announcement speakers lazily with a short cache."""
        if not bool(
            self._option(CONF_SPEAKER_ENABLED, DEFAULT_SPEAKER_ENABLED)
        ):
            return []
        if self._configured_tts_entity_id() is None:
            return []
        if not self.hass.services.has_service(TTS_DOMAIN, TTS_SERVICE_SPEAK):
            return []

        now = monotonic()
        if (
            self._speaker_targets_cache is not None
            and now < self._speaker_targets_cache_until
        ):
            return list(self._speaker_targets_cache)

        targets: list[NotificationTarget] = []
        states = sorted(
            self.hass.states.async_all(MEDIA_PLAYER_DOMAIN),
            key=lambda state: (state.name.casefold(), state.entity_id),
        )
        for state in states:
            if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            try:
                supported_features = int(
                    state.attributes.get(ATTR_SUPPORTED_FEATURES, 0) or 0
                )
            except (TypeError, ValueError):
                supported_features = 0
            if not supported_features & int(MediaPlayerEntityFeature.PLAY_MEDIA):
                continue

            # TVs and projectors may expose play_media but should not normally
            # be offered as household announcement speakers.
            device_class = str(
                state.attributes.get("device_class", "") or ""
            ).casefold()
            if device_class in {"tv", "projector"}:
                continue

            speaker_name = state.name
            display_name = (
                speaker_name
                if speaker_name.casefold().startswith("loa ")
                else f"Loa {speaker_name}"
            )
            targets.append(
                NotificationTarget(
                    target_id=f"speaker:{state.entity_id}",
                    kind="speaker",
                    display_name=display_name,
                    speaker_entity_id=state.entity_id,
                )
            )
        self._speaker_targets_cache = targets
        self._speaker_targets_cache_until = now + DISCOVERY_CACHE_SECONDS
        return list(targets)

    def _available_targets(self) -> list[NotificationTarget]:
        """Return all notification destinations selectable for a reminder."""
        return [
            *self._discovered_mobile_targets(),
            *self._configured_zalo_selection_targets(),
            *self._configured_speaker_targets(),
        ]

    def _webhook_ids_for_device_ids(self, device_ids: list[str]) -> list[str]:
        """Resolve Home Assistant devices to mobile app webhook IDs."""
        device_registry = dr.async_get(self.hass)
        webhook_ids: list[str] = []

        for device_id in device_ids:
            device = device_registry.async_get(device_id)
            if device is None:
                continue
            for config_entry_id in device.config_entries:
                config_entry = self.hass.config_entries.async_get_entry(
                    config_entry_id
                )
                if config_entry is None or config_entry.domain != "mobile_app":
                    continue
                webhook_id = config_entry.data.get(ATTR_WEBHOOK_ID)
                if webhook_id and webhook_id not in webhook_ids:
                    webhook_ids.append(webhook_id)
        return webhook_ids

    def _notification_services_for_device_ids(
        self, device_ids: list[str]
    ) -> list[str]:
        """Resolve mobile app device IDs to notify service names."""
        services: list[str] = []
        for webhook_id in self._webhook_ids_for_device_ids(device_ids):
            try:
                service = get_notify_service(self.hass, webhook_id)
            except (KeyError, TypeError):
                service = None
            if (
                service
                and service not in services
                and self.hass.services.has_service("notify", service)
            ):
                services.append(service)
        return services

    def _mobile_device_ids_for_reminder(self, reminder: Reminder) -> list[str]:
        """Return the mobile devices assigned to a reminder."""
        if reminder.mobile_device_ids is None:
            return self._discovered_mobile_device_ids()
        return list(reminder.mobile_device_ids)

    def _zalo_targets_for_reminder(
        self, reminder: Reminder
    ) -> list[dict[str, Any]]:
        """Return exact Zalo destinations assigned to a reminder."""
        if reminder.zalo_targets is None:
            return self._configured_zalo_targets()
        return [dict(item) for item in reminder.zalo_targets]

    def _speaker_entity_ids_for_reminder(
        self, reminder: Reminder
    ) -> list[str]:
        """Return speakers explicitly assigned to this reminder."""
        # Reminders created before speaker support must not start speaking on
        # every newly discovered speaker after an upgrade.
        if reminder.speaker_entity_ids is None:
            return []
        return list(reminder.speaker_entity_ids)

    def _tag(self, reminder: Reminder) -> str:
        """Return notification tag."""
        return f"conversational_assistant_{self.entry.entry_id}_{reminder.reminder_id}"

    def _action_id(self, action: str, reminder: Reminder) -> str:
        """Return unique notification action ID."""
        return f"{action}_{self.entry.entry_id}_{reminder.reminder_id}"

    async def _async_send_mobile_notification(self, reminder: Reminder) -> bool:
        """Send an actionable notification to assigned mobile devices."""
        services = self._notification_services_for_device_ids(
            self._mobile_device_ids_for_reminder(reminder)
        )
        tag = self._tag(reminder)
        data = {
            "tag": tag,
            "reminder_id": reminder.reminder_id,
            "conversational_assistant_entry_id": self.entry.entry_id,
            "actions": [
                {
                    "action": self._action_id(ACTION_SNOOZE, reminder),
                    "title": f"Nhắc lại {DEFAULT_SNOOZE_MINUTES} phút",
                },
                {
                    "action": self._action_id(ACTION_DISMISS, reminder),
                    "title": "Bỏ qua",
                    "destructive": True,
                },
            ],
        }

        sent = False
        for service in services:
            try:
                await self.hass.services.async_call(
                    "notify",
                    service,
                    {
                        "title": "⏰ Nhắc nhở",
                        "message": f"📝 {reminder.message.strip()}",
                        "data": data,
                    },
                    blocking=True,
                )
                sent = True
            except Exception:  # noqa: BLE001 - keep other targets working
                _LOGGER.exception(
                    "Failed to send Conversational Assistant notification "
                    "via notify.%s",
                    service,
                )
        return sent

    async def _async_send_zalo_notification(self, reminder: Reminder) -> bool:
        """Send a formatted reminder to every assigned Zalo destination."""
        targets = self._zalo_targets_for_reminder(reminder)
        if not targets:
            return False

        if not self.hass.services.has_service(
            ZALO_DOMAIN, ZALO_SERVICE_SEND_MESSAGE
        ):
            _LOGGER.error(
                "Service %s.%s is not available",
                ZALO_DOMAIN,
                ZALO_SERVICE_SEND_MESSAGE,
            )
            return False

        sent = False
        for target in targets:
            thread_id = str(target.get(CONF_ZALO_THREAD_ID, "")).strip()
            account_selection = str(
                target.get(CONF_ZALO_ACCOUNT_SELECTION, "")
            ).strip()
            zalo_type = str(
                target.get(CONF_ZALO_TYPE, DEFAULT_ZALO_TYPE)
            ).strip()
            if not thread_id or not account_selection:
                _LOGGER.error("Skipping invalid stored Zalo target: %s", target)
                continue
            try:
                # Scheduled reminders are also Zalo features, so briefly show
                # typing before delivering the reminder to each destination.
                await self._async_send_zalo_typing_to_target(
                    thread_id, account_selection
                )
                await self.hass.services.async_call(
                    ZALO_DOMAIN,
                    ZALO_SERVICE_SEND_MESSAGE,
                    {
                        "type": zalo_type,
                        "ttl": 0,
                        "message": (
                            "⏰ Nhắc nhở:\n"
                            f"📝 **{reminder.message.strip()}**"
                        ),
                        "thread_id": thread_id,
                        "account_selection": account_selection,
                    },
                    blocking=True,
                )
                sent = True
            except Exception:  # noqa: BLE001 - keep other targets working
                _LOGGER.exception(
                    "Failed to send Conversational Assistant via %s.%s to thread %s",
                    ZALO_DOMAIN,
                    ZALO_SERVICE_SEND_MESSAGE,
                    thread_id,
                )
        return sent

    async def _async_send_speaker_notification(
        self, reminder: Reminder
    ) -> bool:
        """Speak the reminder on every assigned media player."""
        speaker_entity_ids = self._speaker_entity_ids_for_reminder(reminder)
        if not speaker_entity_ids:
            return False

        tts_entity_id = self._configured_tts_entity_id()
        if tts_entity_id is None:
            _LOGGER.error(
                "No TTS entity is available for Conversational Assistant speaker output"
            )
            return False
        if not self.hass.services.has_service(TTS_DOMAIN, TTS_SERVICE_SPEAK):
            _LOGGER.error(
                "Service %s.%s is not available",
                TTS_DOMAIN,
                TTS_SERVICE_SPEAK,
            )
            return False

        sent = False
        spoken_message = _sanitize_spoken_text(
            f"Bạn có lời nhắc {reminder.message}"
        )
        if not spoken_message:
            _LOGGER.error(
                "Conversational Assistant message became empty after TTS sanitization"
            )
            return False
        for speaker_entity_id in speaker_entity_ids:
            state = self.hass.states.get(speaker_entity_id)
            if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                _LOGGER.warning(
                    "Skipping unavailable Conversational Assistant speaker %s",
                    speaker_entity_id,
                )
                continue
            try:
                await self.hass.services.async_call(
                    TTS_DOMAIN,
                    TTS_SERVICE_SPEAK,
                    {
                        "media_player_entity_id": speaker_entity_id,
                        "message": spoken_message,
                        "cache": True,
                    },
                    blocking=True,
                    target={"entity_id": tts_entity_id},
                )
                sent = True
            except Exception:  # noqa: BLE001 - keep other targets working
                _LOGGER.exception(
                    "Failed to speak Conversational Assistant on %s using %s",
                    speaker_entity_id,
                    tts_entity_id,
                )
        return sent

    async def _async_send_notification(self, reminder: Reminder) -> None:
        """Send reminder through every assigned notification channel."""
        mobile_sent = await self._async_send_mobile_notification(reminder)
        zalo_sent = await self._async_send_zalo_notification(reminder)
        speaker_sent = await self._async_send_speaker_notification(reminder)

        if mobile_sent or zalo_sent or speaker_sent:
            return

        _LOGGER.warning(
            "No assigned Conversational Assistant notification channel was available; "
            "using a persistent notification"
        )
        persistent_notification.async_create(
            self.hass,
            f"📝 {reminder.message.strip()}",
            title="⏰ Nhắc nhở",
            notification_id=self._tag(reminder),
        )

    async def _async_clear_notification(self, reminder: Reminder) -> None:
        """Clear a notification from phones assigned to this reminder."""
        tag = self._tag(reminder)
        services = self._notification_services_for_device_ids(
            self._mobile_device_ids_for_reminder(reminder)
        )
        for service in services:
            try:
                await self.hass.services.async_call(
                    "notify",
                    service,
                    {
                        "message": "clear_notification",
                        "data": {"tag": tag},
                    },
                    blocking=True,
                )
            except Exception:  # noqa: BLE001 - clearing is best effort
                _LOGGER.exception(
                    "Failed to clear Conversational Assistant notification "
                    "via notify.%s",
                    service,
                )
        persistent_notification.async_dismiss(self.hass, tag)

    @staticmethod
    def _request_from_text(text: str) -> str:
        """Extract the reminder or deletion request from natural text."""
        text = text.strip().casefold()
        if text.startswith("hãy "):
            text = text[4:]
        elif text.startswith("please "):
            text = text[7:]
        normalized = normalize_text(text)
        if re.fullmatch(
            r"(?:delete|remove|cancel|clear) (?:all )?reminders?",
            normalized,
        ):
            return "all"
        if re.fullmatch(
            r"(?:delete|remove|cancel) (?:a |my )?reminder",
            normalized,
        ):
            return ""
        if re.fullmatch(
            r"(?:xoa|huy) (?:tat ca|toan bo) "
            r"(?:nhac hen|nhac nho|lich nhac|hen gio)",
            normalized,
        ):
            return "tất cả"
        if re.fullmatch(
            r"(?:xoa|huy) (?:nhac hen|nhac nho|lich nhac|hen gio)",
            normalized,
        ):
            return ""

        prefixes = (
            "remind me to ",
            "remind me ",
            "set a reminder to ",
            "set a reminder ",
            "set reminder to ",
            "set reminder ",
            "create a reminder to ",
            "create a reminder ",
            "add a reminder to ",
            "add a reminder ",
            "schedule a reminder to ",
            "schedule a reminder ",
            "delete a reminder ",
            "delete reminder ",
            "remove a reminder ",
            "remove reminder ",
            "cancel a reminder ",
            "cancel reminder ",
            "tạo hẹn giờ nhắc tôi ",
            "hẹn giờ nhắc tôi ",
            "thêm nhắc hẹn ",
            "thêm nhắc nhở ",
            "thêm lịch nhắc ",
            "tạo nhắc hẹn ",
            "tạo nhắc nhở ",
            "tạo lịch nhắc ",
            "đặt nhắc hẹn ",
            "đặt nhắc nhở ",
            "đặt lịch nhắc ",
            "hủy nhắc hẹn ",
            "huỷ nhắc hẹn ",
            "xóa nhắc hẹn ",
            "xoá nhắc hẹn ",
            "hủy nhắc nhở ",
            "huỷ nhắc nhở ",
            "xóa nhắc nhở ",
            "xoá nhắc nhở ",
            "hủy lịch nhắc ",
            "huỷ lịch nhắc ",
            "xóa lịch nhắc ",
            "xoá lịch nhắc ",
            "hủy hẹn giờ ",
            "huỷ hẹn giờ ",
            "xóa hẹn giờ ",
            "xoá hẹn giờ ",
            "nhắc tôi ",
            "hẹn tôi ",
            "nhắc ",
            "hẹn ",
            "thêm ",
            "tạo ",
            "đặt ",
        )
        for prefix in prefixes:
            if text.startswith(prefix):
                return text[len(prefix) :].strip()
        return text

    @staticmethod
    def _request_slot(
        user_input: ConversationInput, result: RecognizeResult
    ) -> str:
        """Get wildcard request text from a conversation result."""
        entity = result.entities.get("request")
        if entity is not None:
            value = entity.text or entity.value
            if value:
                return str(value).strip()
        return ConversationalAssistantManager._request_from_text(user_input.text)

    @staticmethod
    def _selection_slot(
        user_input: ConversationInput, result: RecognizeResult
    ) -> str:
        """Get target selection text from a conversation result."""
        entity = result.entities.get("selection")
        if entity is not None:
            value = entity.text or entity.value
            if value:
                return str(value).strip()

        text = user_input.text.strip().casefold()
        for prefix in (
            "select ",
            "choose ",
            "confirm ",
            "send to ",
            "notify ",
            "i select ",
            "i choose ",
            "please send to ",
            "chọn ",
            "xác nhận ",
            "gửi đến ",
            "thông báo đến ",
            "tôi chọn ",
            "hãy gửi đến ",
        ):
            if text.startswith(prefix):
                return text[len(prefix) :].strip()
        return text

    @staticmethod
    def _source_keys(user_input: ConversationInput) -> set[str]:
        """Build identifiers used to match a follow-up voice turn."""
        keys: set[str] = set()
        if user_input.conversation_id:
            keys.add(f"conversation:{user_input.conversation_id}")
        if user_input.context.user_id:
            keys.add(f"user:{user_input.context.user_id}")
        if user_input.satellite_id:
            keys.add(f"satellite:{user_input.satellite_id}")
        if user_input.device_id:
            keys.add(f"device:{user_input.device_id}")
        return keys or {"global"}

    @callback
    def _schedule_pending_expiry(self) -> None:
        """Schedule cleanup for the earliest pending confirmation."""
        if self._unsub_pending_expiry_timer is not None:
            self._unsub_pending_expiry_timer()
            self._unsub_pending_expiry_timer = None

        pending_items = [
            *self._pending.values(),
            *self._pending_deletions.values(),
            *self._pending_voice_cameras.values(),
            *self._note_pending_items(),
        ]
        if not pending_items:
            return

        expires_at = min(item.expires_at for item in pending_items)
        self._unsub_pending_expiry_timer = async_track_point_in_time(
            self.hass,
            self._async_pending_expired,
            expires_at,
        )

    @callback
    def _sync_pending_followup_trigger(self) -> None:
        """Enable a catch-all trigger while a confirmation is pending."""
        has_pending = bool(
            self._pending
            or self._pending_deletions
            or self._pending_voice_cameras
            or self._has_pending_notes()
        )
        if has_pending and self._unsub_pending_trigger is None:
            self._unsub_pending_trigger = get_agent_manager(
                self.hass
            ).register_trigger(
                PENDING_FOLLOWUP_SENTENCES,
                self._async_pending_followup_from_voice,
            )
        elif not has_pending and self._unsub_pending_trigger is not None:
            self._unsub_pending_trigger()
            self._unsub_pending_trigger = None

        self._schedule_pending_expiry()

    @callback
    def _async_pending_expired(self, _now: datetime) -> None:
        """Remove expired confirmations and disable the temporary trigger."""
        self._unsub_pending_expiry_timer = None
        self._purge_expired_pending()

    def _purge_expired_pending(self) -> None:
        """Remove expired creation, deletion, camera, and note requests."""
        self._purge_expired_note_pending()
        now = dt_util.now()
        for pending_id, pending in list(self._pending.items()):
            if pending.expires_at <= now:
                del self._pending[pending_id]
        for pending_id, pending in list(self._pending_deletions.items()):
            if pending.expires_at <= now:
                del self._pending_deletions[pending_id]
        for pending_id, pending in list(self._pending_voice_cameras.items()):
            if pending.expires_at <= now:
                del self._pending_voice_cameras[pending_id]
        self._sync_pending_followup_trigger()

    def _clear_pending_for_source(self, source_keys: set[str]) -> None:
        """Remove older pending actions from the same user or satellite."""
        self._clear_note_pending_for_source(source_keys)
        for pending_id, pending in list(self._pending.items()):
            if source_keys & pending.source_keys:
                del self._pending[pending_id]
        for pending_id, pending in list(self._pending_deletions.items()):
            if source_keys & pending.source_keys:
                del self._pending_deletions[pending_id]
        for pending_id, pending in list(self._pending_voice_cameras.items()):
            if source_keys & pending.source_keys:
                del self._pending_voice_cameras[pending_id]

    def _set_pending(
        self,
        user_input: ConversationInput,
        parsed: ParsedReminder,
        targets: list[NotificationTarget],
    ) -> PendingReminder:
        """Store one pending reminder, replacing an older action from same source."""
        self._purge_expired_pending()
        source_keys = self._source_keys(user_input)
        self._clear_pending_for_source(source_keys)

        now = dt_util.now()
        pending = PendingReminder(
            pending_id=uuid.uuid4().hex,
            parsed=parsed,
            targets=targets,
            source_keys=source_keys,
            created_at=now,
            expires_at=now
            + timedelta(minutes=PENDING_SELECTION_TIMEOUT_MINUTES),
        )
        self._pending[pending.pending_id] = pending
        self._sync_pending_followup_trigger()
        return pending

    def _set_pending_deletion(
        self,
        user_input: ConversationInput,
        reminders: list[tuple[datetime, Reminder]],
    ) -> PendingDeletion:
        """Store a numbered deletion request for a user or satellite."""
        self._purge_expired_pending()
        source_keys = self._source_keys(user_input)
        self._clear_pending_for_source(source_keys)
        now = dt_util.now()
        pending = PendingDeletion(
            pending_id=uuid.uuid4().hex,
            reminders=reminders,
            source_keys=source_keys,
            created_at=now,
            expires_at=now
            + timedelta(minutes=PENDING_SELECTION_TIMEOUT_MINUTES),
        )
        self._pending_deletions[pending.pending_id] = pending
        self._sync_pending_followup_trigger()
        return pending

    def _set_pending_voice_camera(
        self,
        user_input: ConversationInput,
        cameras: list[CameraTarget],
        zalo_targets: list[dict[str, Any]],
    ) -> PendingVoiceCamera:
        """Store a voice camera request waiting for selection."""
        self._purge_expired_pending()
        source_keys = self._source_keys(user_input)
        self._clear_pending_for_source(source_keys)
        now = dt_util.now()
        pending = PendingVoiceCamera(
            pending_id=uuid.uuid4().hex,
            cameras=cameras,
            zalo_targets=[dict(target) for target in zalo_targets],
            source_keys=source_keys,
            selected_cameras=[],
            phase="selection",
            created_at=now,
            expires_at=now
            + timedelta(minutes=PENDING_SELECTION_TIMEOUT_MINUTES),
        )
        self._pending_voice_cameras[pending.pending_id] = pending
        self._sync_pending_followup_trigger()
        return pending

    def _find_pending(
        self, user_input: ConversationInput
    ) -> PendingReminder | None:
        """Find a pending creation belonging to this follow-up turn."""
        self._purge_expired_pending()
        source_keys = self._source_keys(user_input)
        matching = [
            pending
            for pending in self._pending.values()
            if source_keys & pending.source_keys
        ]
        if matching:
            return max(matching, key=lambda item: item.created_at)
        if (
            len(self._pending) == 1
            and not self._pending_deletions
            and not self._pending_voice_cameras
            and not self._has_pending_notes()
        ):
            return next(iter(self._pending.values()))
        return None

    def _find_pending_deletion(
        self, user_input: ConversationInput
    ) -> PendingDeletion | None:
        """Find a pending deletion belonging to this follow-up turn."""
        self._purge_expired_pending()
        source_keys = self._source_keys(user_input)
        matching = [
            pending
            for pending in self._pending_deletions.values()
            if source_keys & pending.source_keys
        ]
        if matching:
            return max(matching, key=lambda item: item.created_at)
        if (
            len(self._pending_deletions) == 1
            and not self._pending
            and not self._pending_voice_cameras
            and not self._has_pending_notes()
        ):
            return next(iter(self._pending_deletions.values()))
        return None

    def _find_pending_voice_camera(
        self, user_input: ConversationInput
    ) -> PendingVoiceCamera | None:
        """Find a pending voice camera request for this source."""
        self._purge_expired_pending()
        source_keys = self._source_keys(user_input)
        matching = [
            pending
            for pending in self._pending_voice_cameras.values()
            if source_keys & pending.source_keys
        ]
        if matching:
            return max(matching, key=lambda item: item.created_at)
        if (
            len(self._pending_voice_cameras) == 1
            and not self._pending
            and not self._pending_deletions
            and not self._has_pending_notes()
        ):
            return next(iter(self._pending_voice_cameras.values()))
        return None

    @staticmethod
    def _target_prompt_text(
        parsed: ParsedReminder,
        targets: list[NotificationTarget],
        invalid: bool = False,
    ) -> str:
        """Build a target-selection prompt with one option per line."""
        option_lines: list[str] = []
        target_count = len(targets)
        for index, target in enumerate(targets, start=1):
            ending = "." if index == target_count else ";"
            option_lines.append(
                f"{index} - {target.display_name}{ending}"
            )
        options = "\n".join(option_lines)

        understood = parsed.confirmation
        if understood.startswith("Đã tạo "):
            understood = "Tôi đã hiểu " + understood[len("Đã tạo ") :]

        if invalid:
            prefix = (
                "Lựa chọn chưa hợp lệ nên tôi vẫn chưa tạo nhắc nhở.\n"
                "Vui lòng nhập đúng số hoặc tên trong danh sách và thử lại.\n"
            )
        else:
            prefix = f"{understood}\nTôi chưa lưu lịch.\n"

        return (
            f"{prefix}Các nơi nhận là:\n{options}\n"
            "Bạn có thể trả lời 1 và 3, 1 phẩy 3, chọn 1 và 3, "
            "chọn tất cả loa, chọn tất cả, hoặc bỏ yêu cầu vừa rồi."
        )

    @staticmethod
    def _target_prompt(pending: PendingReminder, invalid: bool = False) -> str:
        """Build the voice target-selection prompt."""
        return ConversationalAssistantManager._target_prompt_text(
            pending.parsed, pending.targets, invalid
        )

    @staticmethod
    def _deletion_prompt(
        pending: PendingDeletion, invalid: bool = False
    ) -> str:
        """Build a numbered reminder deletion prompt."""
        lines: list[str] = []
        count = len(pending.reminders)
        for index, (due, reminder) in enumerate(pending.reminders, start=1):
            ending = "." if index == count else ";"
            if reminder.is_recurring:
                status = " - lặp lại"
            elif reminder.delivered and due <= dt_util.now():
                status = " - đã gửi"
            else:
                status = ""
            lines.append(
                f"{index} - {due.strftime('%H:%M ngày %d/%m/%Y')} - "
                f"{reminder.message}{status}{ending}"
            )
        prefix = (
            "Lựa chọn xóa chưa hợp lệ. Vui lòng nhập đúng số trong danh sách.\n"
            if invalid
            else "Các nhắc hẹn đang có là:\n"
        )
        return (
            f"{prefix}{chr(10).join(lines)}\n"
            "Hãy trả lời số cần xóa, ví dụ 1, 1 và 3, hoặc tất cả. "
            "Nói bỏ yêu cầu vừa rồi để không xóa."
        )

    def _request_satellite_entity_id(
        self, user_input: ConversationInput
    ) -> str | None:
        """Resolve the Assist satellite that received the voice command."""
        def supports_announce(entity_id: str) -> bool:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                return False
            try:
                features = int(
                    state.attributes.get(ATTR_SUPPORTED_FEATURES, 0) or 0
                )
            except (TypeError, ValueError):
                return False
            # AssistSatelliteEntityFeature.ANNOUNCE == 1. Keeping the numeric
            # feature check avoids a hard dependency on the integration module.
            return bool(features & 1)

        satellite_id = user_input.satellite_id
        if satellite_id and supports_announce(satellite_id):
            return satellite_id

        if not user_input.device_id:
            return None
        registry = er.async_get(self.hass)
        for entry in er.async_entries_for_device(registry, user_input.device_id):
            if (
                entry.domain == ASSIST_SATELLITE_DOMAIN
                and entry.disabled_by is None
                and supports_announce(entry.entity_id)
            ):
                return entry.entity_id
        return None

    @staticmethod
    def _spoken_response_text(text: str) -> str:
        """Turn a multiline chat response into smooth satellite speech."""
        lines = []
        for raw_line in text.splitlines():
            line = _sanitize_spoken_text(raw_line)
            if line:
                lines.append(line)
        return ". ".join(lines)

    async def _async_delayed_satellite_announce(
        self, satellite_entity_id: str, text: str
    ) -> None:
        """Announce after the active pipeline has released the satellite."""
        spoken = self._spoken_response_text(text)
        if not spoken:
            return
        # The trigger callback runs while the satellite is still processing.
        # Retry after short delays instead of failing with SatelliteBusyError.
        for delay in (0.8, 1.5, 3.0):
            await asyncio.sleep(delay)
            try:
                await self.hass.services.async_call(
                    ASSIST_SATELLITE_DOMAIN,
                    ASSIST_SATELLITE_SERVICE_ANNOUNCE,
                    {"message": spoken, "preannounce": False},
                    blocking=True,
                    target={"entity_id": satellite_entity_id},
                )
                return
            except Exception:  # noqa: BLE001 - retry while satellite is busy
                _LOGGER.debug(
                    "Could not announce Conversational Assistant response on %s yet",
                    satellite_entity_id,
                    exc_info=True,
                )
        _LOGGER.warning(
            "Unable to announce Conversational Assistant response on %s",
            satellite_entity_id,
        )

    async def _async_voice_response(
        self, user_input: ConversationInput, text: str
    ) -> str:
        """Return chat text or explicitly speak it on the requesting satellite."""
        satellite_entity_id = self._request_satellite_entity_id(user_input)
        if (
            satellite_entity_id
            and self.hass.services.has_service(
                ASSIST_SATELLITE_DOMAIN,
                ASSIST_SATELLITE_SERVICE_ANNOUNCE,
            )
        ):
            self.hass.async_create_task(
                self._async_delayed_satellite_announce(
                    satellite_entity_id,
                    text,
                )
            )
            # Suppress the normal pipeline speech to avoid double playback.
            # The explicit announcement above is used for voice satellites.
            return ""
        return text

    @staticmethod
    def _reminder_from_targets(
        parsed: ParsedReminder,
        targets: list[NotificationTarget],
        owner_key: str | None = None,
    ) -> Reminder:
        """Create a reminder with an immutable snapshot of selected targets."""
        mobile_device_ids = [
            target.mobile_device_id
            for target in targets
            if target.kind == "mobile" and target.mobile_device_id
        ]
        zalo_targets = [
            dict(target.zalo)
            for target in targets
            if target.kind == "zalo" and target.zalo is not None
        ]
        speaker_entity_ids = [
            target.speaker_entity_id
            for target in targets
            if target.kind == "speaker" and target.speaker_entity_id
        ]
        return Reminder(
            reminder_id=uuid.uuid4().hex,
            message=parsed.message,
            created_at=dt_util.now(),
            next_run=parsed.first_run,
            recurrence=parsed.recurrence,
            mobile_device_ids=mobile_device_ids,
            zalo_targets=zalo_targets,
            speaker_entity_ids=speaker_entity_ids,
            owner_key=owner_key,
        )

    async def _async_create_from_voice(
        self, user_input: ConversationInput, result: RecognizeResult
    ) -> str:
        """Parse a reminder and optionally ask which targets should receive it."""
        # Parse the complete utterance instead of only the wildcard slot.
        # English slots such as "take medicine at 8" may not contain an
        # explicit language marker after Hassil removes "remind me". Keeping
        # the original command lets the parser select the English branch,
        # while the Vietnamese parser already knows how to strip its prefixes.
        request = user_input.text or self._request_slot(user_input, result)
        try:
            parsed = parse_reminder_request(request)
        except ReminderParseError as err:
            response = (
                f"Tôi chưa tạo được nhắc nhở. {err} "
                "Ví dụ: hẹn 18h30 đi tắm; nhắc 1830 ngày mai uống thuốc; "
                "hoặc nhắc 18h30 t3 t5 hàng tuần uống thuốc bổ."
            )
            return await self._async_voice_response(user_input, response)

        targets = self._available_targets()
        if not targets:
            response = (
                "Chưa có Mobile App, Zalo hoặc loa có thể nhận nhắc nhở. "
                "Hãy kiểm tra tùy chọn Conversational Assistant, TTS và các loa trong "
                "Home Assistant."
            )
            return await self._async_voice_response(user_input, response)

        confirm_targets = bool(
            self._option(CONF_CONFIRM_TARGETS, DEFAULT_CONFIRM_TARGETS)
        )
        if confirm_targets:
            pending = self._set_pending(user_input, parsed, targets)
            return await self._async_voice_response(
                user_input, self._target_prompt(pending)
            )

        reminder = self._reminder_from_targets(parsed, targets)
        await self.async_add_reminder(reminder)
        target_names = ", ".join(target.display_name for target in targets)
        response = f"{parsed.confirmation} Sẽ thông báo đến {target_names}."
        return await self._async_voice_response(user_input, response)

    async def _async_search_from_voice(
        self, user_input: ConversationInput, result: RecognizeResult
    ) -> str:
        """Search the Internet through the configured AI Search agent."""
        self._clear_pending_for_source(self._source_keys(user_input))
        self._sync_pending_followup_trigger()
        query = self._request_slot(user_input, result)
        parsed_query = _search_request(user_input.text)
        if parsed_query is not None:
            query = parsed_query
        reply, _conversation_id = await self._async_ai_search(
            query,
            conversation_id=user_input.conversation_id,
            service_context=user_input.context,
            zalo=False,
            language_hint=_request_language(user_input.text),
        )
        return await self._async_voice_response(user_input, reply)

    async def _async_help_from_voice(
        self, user_input: ConversationInput, _result: RecognizeResult
    ) -> str:
        """Return the integration usage guide through Assist."""
        source_keys = self._source_keys(user_input)
        self._clear_pending_for_source(source_keys)
        self._sync_pending_followup_trigger()
        return await self._async_voice_response(
            user_input, self._integration_help_text()
        )

    async def _async_learn_command_from_voice(
        self, user_input: ConversationInput, _result: RecognizeResult
    ) -> str:
        """Teach one persistent alternative phrase through Assist."""
        source_keys = self._source_keys(user_input)
        self._clear_pending_for_source(source_keys)
        self._sync_pending_followup_trigger()
        return await self._async_voice_response(
            user_input, self._learn_command_text(user_input.text)
        )

    async def _async_list_learned_commands_from_voice(
        self, user_input: ConversationInput, _result: RecognizeResult
    ) -> str:
        """List persistent learned phrases through Assist."""
        source_keys = self._source_keys(user_input)
        self._clear_pending_for_source(source_keys)
        self._sync_pending_followup_trigger()
        return await self._async_voice_response(
            user_input, self._learned_commands_text()
        )

    async def _async_delete_learned_command_from_voice(
        self, user_input: ConversationInput, _result: RecognizeResult
    ) -> str:
        """Delete one or all persistent learned phrases through Assist."""
        source_keys = self._source_keys(user_input)
        self._clear_pending_for_source(source_keys)
        self._sync_pending_followup_trigger()
        return await self._async_voice_response(
            user_input, self._delete_learned_command_text(user_input.text)
        )

    async def _async_execute_learned_command_from_voice(
        self,
        user_input: ConversationInput,
        result: RecognizeResult,
        *,
        command_id: str,
    ) -> str | None:
        """Run one learned alias through its existing integration workflow."""
        command = self.learned_commands.get(command_id)
        if command is None:
            return None

        self._clear_pending_for_source(self._source_keys(user_input))
        self._sync_pending_followup_trigger()

        request = ""
        entity = result.entities.get("request")
        if entity is not None:
            value = entity.text or entity.value
            if value:
                request = str(value).strip()
        transformed_text = canonical_text(
            command.action, request, command.target_text
        )
        transformed_input: ConversationInput | _ConversationInputTextProxy
        transformed_input = (
            _ConversationInputTextProxy(user_input, transformed_text)
            if transformed_text
            else user_input
        )

        if command.action == ACTION_CAMERA:
            return await self._async_camera_from_voice(user_input, result)
        if command.action == ACTION_REMINDER_CREATE:
            return await self._async_create_from_voice(
                transformed_input, result
            )
        if command.action == ACTION_REMINDER_LIST:
            return await self._async_list_from_voice(user_input, result)
        if command.action == ACTION_REMINDER_DELETE:
            return await self._async_cancel_from_voice(
                transformed_input, result
            )
        if command.action == ACTION_NOTE_CREATE:
            return await self._async_create_note_from_voice(
                transformed_input, result
            )
        if command.action == ACTION_NOTE_LIST:
            return await self._async_list_notes_from_voice(user_input, result)
        if command.action == ACTION_NOTE_EDIT:
            return await self._async_edit_note_from_voice(user_input, result)
        if command.action == ACTION_NOTE_DELETE:
            return await self._async_delete_note_from_voice(user_input, result)
        if command.action == ACTION_NOTE_VIEW:
            return await self._async_view_note_from_voice(
                transformed_input, result
            )
        if command.action == ACTION_HELP:
            response = self._integration_help_text()
            return await self._async_voice_response(user_input, response)
        if command.action == ACTION_SEARCH:
            query = _search_request(transformed_text)
            reply, _conversation_id = await self._async_ai_search(
                query or "",
                conversation_id=user_input.conversation_id,
                service_context=user_input.context,
                zalo=False,
                language_hint=_request_language(request or user_input.text),
            )
            return await self._async_voice_response(user_input, reply)
        if command.action == ACTION_IMAGE_GENERATION:
            return await self._async_voice_response(
                user_input,
                (
                    "Tính năng tạo ảnh AI hiện tạo và gửi ảnh trong cuộc trò chuyện "
                    "Zalo. Hãy dùng câu lệnh này trên Zalo để nhận ảnh."
                ),
            )
        if command.action in {ACTION_HOME_ASSISTANT, ACTION_CALENDAR}:
            if not transformed_text:
                return await self._async_voice_response(
                    user_input,
                    "Câu lệnh đã học thiếu nội dung Home Assistant đích.",
                )
            return await self._async_home_assistant_conversation_from_voice(
                user_input, transformed_text
            )
        return None

    def _is_primary_voice_command(self, text: str) -> bool:
        """Return whether another Conversational Assistant trigger handles text."""
        if _is_integration_help_request(text):
            return True
        if _search_request(text) is not None:
            return True
        if management_command_kind(text) is not None:
            return True
        if match_learned_command(
            text, list(self.learned_commands.values())
        ) is not None:
            return True
        if is_primary_note_voice_command(text):
            return True
        normalized = normalize_text(text)
        if normalized.startswith(
            (
                "take a camera photo",
                "take camera photo",
                "take a photo from camera",
                "capture camera image",
                "capture a camera image",
                "camera snapshot",
                "chup anh camera",
                "chup hinh camera",
                "lay anh camera",
                "lay hinh camera",
                "chup camera",
                "chup anh may quay",
                "lay anh may quay",
            )
        ):
            return True
        prefixes = (
            "remind me ",
            "please remind me ",
            "set reminder ",
            "set a reminder ",
            "create reminder ",
            "create a reminder ",
            "add reminder ",
            "add a reminder ",
            "schedule reminder ",
            "schedule a reminder ",
            "delete reminder ",
            "delete a reminder ",
            "remove reminder ",
            "cancel reminder ",
            "nhac ",
            "hen ",
            "them ",
            "tao ",
            "dat ",
            "huy nhac hen ",
            "xoa nhac hen ",
            "huy nhac nho ",
            "xoa nhac nho ",
            "huy lich nhac ",
            "xoa lich nhac ",
            "huy hen gio ",
            "xoa hen gio ",
        )
        exact = {
            "list reminders",
            "list my reminders",
            "show reminders",
            "show my reminders",
            "show reminder list",
            "what reminders do i have",
            "what is my next reminder",
            "whats my next reminder",
            "next reminder",
            "delete reminder",
            "delete a reminder",
            "remove reminder",
            "cancel reminder",
            "delete all reminders",
            "remove all reminders",
            "cancel all reminders",
            "clear all reminders",
            "liet ke nhac nho",
            "liet ke nhac hen",
            "doc danh sach nhac nho",
            "doc danh sach nhac hen",
            "xem danh sach nhac nho",
            "xem danh sach nhac hen",
            "danh sach nhac nho",
            "danh sach nhac hen",
            "cho toi danh sach nhac nho",
            "cho toi danh sach nhac hen",
            "toi co nhung nhac nho nao",
            "toi co nhung nhac hen nao",
            "nhac nho tiep theo la gi",
            "nhac hen tiep theo la gi",
            "huy nhac hen",
            "xoa nhac hen",
            "huy nhac nho",
            "xoa nhac nho",
            "huy lich nhac",
            "xoa lich nhac",
            "huy hen gio",
            "xoa hen gio",
            "huy tat ca nhac nho",
            "xoa tat ca nhac nho",
            "huy toan bo nhac nho",
            "xoa toan bo nhac nho",
        }
        return normalized in exact or normalized.startswith(prefixes)

    @staticmethod
    def _is_cancel_pending_text(text: str) -> bool:
        """Return True for natural cancellation of a pending action."""
        normalized = normalize_text(text)
        return normalized in {
            "cancel",
            "cancel the last request",
            "stop",
            "stop this request",
            "do not save",
            "dont save",
            "don t save",
            "do not save this reminder",
            "dont save this reminder",
            "don t save this reminder",
            "do not delete",
            "dont delete",
            "don t delete",
            "cancel deletion",
            "do not capture",
            "dont capture",
            "don t capture",
            "do not take a photo",
            "dont take a photo",
            "don t take a photo",
            "never mind",
            "bo yeu cau vua roi",
            "khong luu nhac nho nay",
            "dung tao nhac nho",
            "khong xoa",
            "huy xoa",
            "thoi khong xoa",
            "khong chup",
            "khong chup anh",
            "huy chup",
            "thoi khong chup",
        }

    async def _async_pending_followup_from_voice(
        self, user_input: ConversationInput, result: RecognizeResult
    ) -> str | None:
        """Handle follow-up selections for creation or deletion."""
        if self._is_primary_voice_command(user_input.text):
            # Let the dedicated create/list/delete sentence trigger respond.
            return None

        note_pending = self._find_pending_note(user_input)
        camera_pending = self._find_pending_voice_camera(user_input)
        creation = self._find_pending(user_input)
        deletion = self._find_pending_deletion(user_input)
        if note_pending is not None:
            return await self._async_pending_note_followup_from_voice(
                user_input, result, note_pending
            )
        if camera_pending is None and creation is None and deletion is None:
            self._sync_pending_followup_trigger()
            return None

        if (
            camera_pending is not None
            and self._is_voice_camera_cancellation(user_input.text)
        ) or self._is_cancel_pending_text(user_input.text):
            if camera_pending is not None:
                self._pending_voice_cameras.pop(
                    camera_pending.pending_id, None
                )
                response = "Đã hủy yêu cầu chụp ảnh camera."
            elif creation is not None:
                self._pending.pop(creation.pending_id, None)
                response = "Đã hủy nhắc nhở đang tạo."
            else:
                assert deletion is not None
                self._pending_deletions.pop(deletion.pending_id, None)
                response = "Đã hủy yêu cầu xóa nhắc hẹn."
            self._sync_pending_followup_trigger()
            return await self._async_voice_response(user_input, response)

        if camera_pending is not None:
            return await self._async_confirm_camera_from_voice(
                user_input, result, camera_pending
            )
        if deletion is not None:
            return await self._async_confirm_deletion_from_voice(
                user_input, result
            )
        return await self._async_confirm_targets_from_voice(user_input, result)

    async def _async_confirm_camera_from_voice(
        self,
        user_input: ConversationInput,
        result: RecognizeResult,
        pending: PendingVoiceCamera,
    ) -> str:
        """Handle camera selection and final voice confirmation."""
        if pending.phase == "selection":
            selection = self._selection_slot(user_input, result)
            indexes = parse_target_selection(
                selection,
                [camera.display_name for camera in pending.cameras],
            )
            selected = [pending.cameras[index] for index in indexes]
            available = [camera for camera in selected if camera.available]
            if not available:
                pending.expires_at = dt_util.now() + timedelta(
                    minutes=PENDING_SELECTION_TIMEOUT_MINUTES
                )
                self._sync_pending_followup_trigger()
                return await self._async_voice_response(
                    user_input,
                    self._voice_camera_selection_prompt(
                        pending.cameras, invalid=True
                    ),
                )

            pending.selected_cameras = available
            pending.phase = "confirmation"
            pending.expires_at = dt_util.now() + timedelta(
                minutes=PENDING_SELECTION_TIMEOUT_MINUTES
            )
            self._sync_pending_followup_trigger()
            response = self._voice_camera_confirmation_prompt(
                available, pending.zalo_targets
            )
            unavailable = [
                camera.display_name for camera in selected if not camera.available
            ]
            if unavailable:
                response = (
                    "Đã bỏ qua camera không khả dụng: "
                    + ", ".join(unavailable)
                    + ". "
                    + response
                )
            return await self._async_voice_response(user_input, response)

        if not self._is_voice_camera_confirmation(user_input.text):
            pending.expires_at = dt_util.now() + timedelta(
                minutes=PENDING_SELECTION_TIMEOUT_MINUTES
            )
            self._sync_pending_followup_trigger()
            return await self._async_voice_response(
                user_input,
                self._voice_camera_confirmation_prompt(
                    pending.selected_cameras,
                    pending.zalo_targets,
                    invalid=True,
                ),
            )

        zalo_targets = self._current_voice_camera_zalo_targets(pending)
        self._pending_voice_cameras.pop(pending.pending_id, None)
        self._sync_pending_followup_trigger()
        if not zalo_targets:
            return await self._async_voice_response(
                user_input,
                "Zalo destination đã bị xóa hoặc tắt trước khi chụp. Hãy mở "
                "cấu hình Conversational Assistant, thêm hoặc bật lại Zalo "
                "destination, sau đó thực hiện lại yêu cầu.",
            )

        response = await self._async_capture_voice_cameras(
            user_input, pending, zalo_targets
        )
        return await self._async_voice_response(user_input, response)

    async def _async_confirm_targets_from_voice(
        self, user_input: ConversationInput, result: RecognizeResult
    ) -> str:
        """Complete a pending reminder after the user chooses targets."""
        pending = self._find_pending(user_input)
        if pending is None:
            response = (
                "Không có nhắc nhở nào đang chờ chọn nơi nhận. "
                "Hãy nói lại yêu cầu tạo nhắc nhở."
            )
            return await self._async_voice_response(user_input, response)

        selection = self._selection_slot(user_input, result)
        indexes = parse_target_selection(
            selection,
            [target.display_name for target in pending.targets],
        )
        if not indexes:
            pending.expires_at = dt_util.now() + timedelta(
                minutes=PENDING_SELECTION_TIMEOUT_MINUTES
            )
            self._sync_pending_followup_trigger()
            return await self._async_voice_response(
                user_input, self._target_prompt(pending, invalid=True)
            )

        selected = [pending.targets[index] for index in indexes]
        reminder = self._reminder_from_targets(pending.parsed, selected)
        await self.async_add_reminder(reminder)
        self._pending.pop(pending.pending_id, None)
        self._sync_pending_followup_trigger()

        target_names = ", ".join(target.display_name for target in selected)
        response = (
            f"{pending.parsed.confirmation} "
            f"Sẽ thông báo đến {target_names}."
        )
        return await self._async_voice_response(user_input, response)

    async def _async_confirm_deletion_from_voice(
        self, user_input: ConversationInput, result: RecognizeResult
    ) -> str:
        """Delete one or more reminders selected from the numbered list."""
        pending = self._find_pending_deletion(user_input)
        if pending is None:
            response = (
                "Không có danh sách nhắc hẹn nào đang chờ chọn để xóa. "
                "Hãy nói xóa nhắc hẹn để mở lại danh sách."
            )
            return await self._async_voice_response(user_input, response)

        selection = self._selection_slot(user_input, result)
        labels = [
            f"{due.strftime('%H:%M ngày %d/%m/%Y')} {reminder.message}"
            for due, reminder in pending.reminders
        ]
        indexes = parse_target_selection(selection, labels)
        if not indexes:
            pending.expires_at = dt_util.now() + timedelta(
                minutes=PENDING_SELECTION_TIMEOUT_MINUTES
            )
            self._sync_pending_followup_trigger()
            return await self._async_voice_response(
                user_input, self._deletion_prompt(pending, invalid=True)
            )

        selected = [pending.reminders[index][1] for index in indexes]
        self._pending_deletions.pop(pending.pending_id, None)
        self._sync_pending_followup_trigger()
        deleted_names: list[str] = []
        for reminder in selected:
            if await self.async_delete(reminder.reminder_id):
                deleted_names.append(reminder.message)

        if not deleted_names:
            response = "Các nhắc hẹn đã thay đổi nên không còn mục nào để xóa."
        elif len(deleted_names) == 1:
            response = f"Đã xóa nhắc hẹn {deleted_names[0]}."
        else:
            response = (
                f"Đã xóa {len(deleted_names)} nhắc hẹn: "
                + "; ".join(deleted_names)
                + "."
            )
        return await self._async_voice_response(user_input, response)

    async def _async_cancel_pending_from_voice(
        self, user_input: ConversationInput, _result: RecognizeResult
    ) -> str:
        """Cancel a pending creation, deletion, or camera request."""
        camera = self._find_pending_voice_camera(user_input)
        creation = self._find_pending(user_input)
        deletion = self._find_pending_deletion(user_input)
        if camera is None and creation is None and deletion is None:
            return await self._async_voice_response(
                user_input, "Không có yêu cầu nào đang chờ xác nhận."
            )
        if camera is not None:
            self._pending_voice_cameras.pop(camera.pending_id, None)
            response = "Đã hủy yêu cầu chụp ảnh camera."
        elif creation is not None:
            self._pending.pop(creation.pending_id, None)
            response = "Đã hủy nhắc nhở đang tạo."
        else:
            assert deletion is not None
            self._pending_deletions.pop(deletion.pending_id, None)
            response = "Đã hủy yêu cầu xóa nhắc hẹn."
        self._sync_pending_followup_trigger()
        return await self._async_voice_response(user_input, response)

    async def _async_list_from_voice(
        self, user_input: ConversationInput, _result: RecognizeResult
    ) -> str:
        """List upcoming reminders through Assist."""
        upcoming = self.upcoming_reminders
        if not upcoming:
            return await self._async_voice_response(
                user_input, "Bạn không có nhắc nhở nào đang chờ."
            )

        lines = ["Các nhắc hẹn sắp tới là:"]
        for index, (due, reminder) in enumerate(upcoming[:10], start=1):
            recurrence = " - lặp lại" if reminder.is_recurring else ""
            lines.append(
                f"{index} - {due.strftime('%H:%M ngày %d/%m/%Y')} - "
                f"{reminder.message}{recurrence}"
            )
        if len(upcoming) > 10:
            lines.append(f"Còn {len(upcoming) - 10} nhắc hẹn khác.")
        response = "\n".join(lines)
        return await self._async_voice_response(user_input, response)

    async def _async_cancel_from_voice(
        self, user_input: ConversationInput, result: RecognizeResult
    ) -> str:
        """Open deletion selection or delete a directly named reminder."""
        request = self._request_slot(user_input, result).strip().casefold()

        if not request:
            reminders = self.deletable_reminders
            if not reminders:
                return await self._async_voice_response(
                    user_input, "Bạn không có nhắc hẹn nào để xóa."
                )
            pending = self._set_pending_deletion(user_input, reminders)
            return await self._async_voice_response(
                user_input, self._deletion_prompt(pending)
            )

        if normalize_text(request) in {
            "all",
            "everything",
            "tat ca",
            "toan bo",
            "het",
        }:
            reminders = list(self.reminders.values())
            self.reminders.clear()
            for reminder in reminders:
                await self._async_clear_notification(reminder)
            self._save_later()
            self._schedule_next()
            self._notify_update()
            return await self._async_voice_response(
                user_input, "Đã xóa tất cả nhắc nhở."
            )

        stored_reminders = [item[1] for item in self.deletable_reminders]
        candidates = [
            reminder
            for reminder in stored_reminders
            if request in reminder.message.casefold()
            or reminder.message.casefold() in request
        ]
        if not candidates:
            return await self._async_voice_response(
                user_input,
                f"Tôi không tìm thấy nhắc nhở có nội dung {request}.",
            )

        reminder = sorted(
            candidates,
            key=lambda item: item.snooze_until
            or item.next_run
            or (dt_util.now() + timedelta(days=365000)),
        )[0]
        await self.async_delete(reminder.reminder_id)
        return await self._async_voice_response(
            user_input, f"Đã xóa nhắc nhở {reminder.message}."
        )

    async def _async_notification_action(self, event: Event) -> None:
        """Handle mobile actionable notification button presses."""
        action = str(event.data.get("action", ""))
        snooze_prefix = f"{ACTION_SNOOZE}_{self.entry.entry_id}_"
        dismiss_prefix = f"{ACTION_DISMISS}_{self.entry.entry_id}_"

        if action.startswith(snooze_prefix):
            reminder_id = action[len(snooze_prefix) :]
            reminder = self.reminders.get(reminder_id)
            if reminder and await self.async_snooze(
                reminder_id, DEFAULT_SNOOZE_MINUTES
            ):
                await self._async_clear_notification(reminder)
            return

        if action.startswith(dismiss_prefix):
            reminder_id = action[len(dismiss_prefix) :]
            reminder = self.reminders.get(reminder_id)
            if reminder and await self.async_dismiss(reminder_id):
                await self._async_clear_notification(reminder)

    async def _async_notification_cleared(self, event: Event) -> None:
        """Optionally treat Android swipe-away as dismiss."""
        enabled = bool(
            self._option(CONF_DISMISS_ON_CLEAR, DEFAULT_DISMISS_ON_CLEAR)
        )
        if not enabled:
            return

        nested_data = event.data.get("data")
        tag = event.data.get("tag")
        if not tag and isinstance(nested_data, dict):
            tag = nested_data.get("tag")
        if not isinstance(tag, str):
            return

        prefix = f"conversational_assistant_{self.entry.entry_id}_"
        if not tag.startswith(prefix):
            return
        reminder_id = tag[len(prefix) :]
        await self.async_dismiss(reminder_id)
