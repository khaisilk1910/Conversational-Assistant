"""Reminder manager for Conversational Assistant."""

from __future__ import annotations

import asyncio
import calendar
import json
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
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
from homeassistant.components.calendar.const import (
    DATA_COMPONENT as CALENDAR_DATA_COMPONENT,
    CalendarEntityFeature,
)
from homeassistant.components.mobile_app.const import ATTR_WEBHOOK_ID
from homeassistant.components.mobile_app.util import get_notify_service
from homeassistant.components.media_player.const import MediaPlayerEntityFeature
from homeassistant.components.conversation.agent_manager import (
    async_converse,
    get_agent_manager,
)
from homeassistant.components.conversation.chat_log import ChatLog
from homeassistant.components.conversation.const import HOME_ASSISTANT_AGENT
from homeassistant.components.conversation.models import (
    ConversationInput,
    ConversationResult,
)
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
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import intent
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ACTION_CHAT,
    ACTION_DISMISS,
    ACTION_SNOOZE,
    AI_TASK_DOMAIN,
    AI_TASK_SERVICE_GENERATE_DATA,
    AI_TASK_SERVICE_GENERATE_IMAGE,
    CAMERA_ANALYSIS_SENTENCES,
    CAMERA_ANALYSIS_TIMEOUT_SECONDS,
    CALENDAR_REFRESH_INTERVAL_MINUTES,
    CAMERA_SENTENCES,
    CONF_AI_AGENT_FAILOVER_ENABLED,
    CONF_AI_CAMERA_INSTRUCTIONS,
    CONF_AI_CAMERA_TASK_ENTITY_ID,
    CONF_AI_IMAGE_TASK_ENTITY_ID,
    CONF_AI_SEARCH_AGENT_ID,
    CANCEL_SENTENCES,
    COMMAND_DELETE_SENTENCES,
    COMMAND_LEARN_SENTENCES,
    COMMAND_LIST_SENTENCES,
    CONF_CALENDAR_ENTITIES,
    CONF_CALENDAR_LOOKAHEAD_DAYS,
    CONF_CALENDAR_NOTIFICATION_ENABLED,
    CONF_CALENDAR_NOTIFICATION_MOBILE_DEVICES,
    CONF_CALENDAR_NOTIFICATION_TIME,
    CONF_CALENDAR_NOTIFICATION_ZALO_TARGETS,
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
    DEFAULT_AI_CAMERA_INSTRUCTIONS,
    DEFAULT_AI_CAMERA_TASK_ENTITY_ID,
    DEFAULT_AI_IMAGE_TASK_ENTITY_ID,
    DEFAULT_AI_SEARCH_AGENT_ID,
    DEFAULT_CALENDAR_LOOKAHEAD_DAYS,
    DEFAULT_CALENDAR_NOTIFICATION_ENABLED,
    DEFAULT_CALENDAR_NOTIFICATION_TIME,
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
    MAX_CALENDAR_LOOKAHEAD_DAYS,
    MEDIA_PLAYER_DOMAIN,
    PENDING_FOLLOWUP_SENTENCES,
    PENDING_CONFIRMATION_TIMEOUT_SECONDS,
    SEARCH_SENTENCES,
    WEATHER_SENTENCES,
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
    ZALO_TEXT_CHUNK_MAX_CHARS,
    ZALO_CHAT_IDLE_TIMEOUT_SECONDS,
    ZALO_CHAT_REENGAGE_TIMEOUT_SECONDS,
    ZALO_IMAGE_TIMEOUT_SECONDS,
    ZALO_SEARCH_TIMEOUT_SECONDS,
    ZALO_TYPING_REFRESH_SECONDS,
    ZALO_TYPE_GROUP,
    ZALO_TYPE_USER,
    ZALO_WEBHOOK_SEEN_MESSAGE_LIMIT,
)
from .chat_flow import (
    chat_start_request,
    contains_inappropriate_language,
    sanitize_chat_reply,
)
from .command_memory import (
    ACTION_CAMERA,
    ACTION_CAMERA_ANALYSIS,
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
    ACTION_WEATHER,
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
from .device_control import (
    DevicePowerInterpretation,
    DevicePowerTarget,
    POWER_CONTROL_DOMAINS,
    device_power_request_hint,
    exact_power_targets,
    explicit_power_action,
    interpretation_from_payload,
    is_rolling_door_target,
    rank_power_targets,
    rolling_door_open_request_hint,
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
    CalendarDisplayEvent,
    CalendarWindow,
    calendar_create_request_from_ai_payload,
    calendar_event_display_summary,
    calendar_event_should_be_skipped,
    calendar_events_for_display,
    calendar_has_time_reference,
    calendar_matches_query,
    calendar_request_action,
    calendar_window_from_text,
    event_from_calendar_state,
    explicit_home_assistant_request_kind,
    extract_calendar_events,
    format_calendar_create_request,
    format_calendar_events,
    weather_search_request,
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
        "cac lenh cua tich hop",
        "danh sach lenh cua tich hop",
        "xem cac lenh cua tich hop",
        "cac tinh nang",
        "cac tinh nang cua tich hop",
        "danh sach tinh nang cua tich hop",
        "xem cac tinh nang cua tich hop",
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
            "commands",
            "features",
            "usage",
            "huong dan",
            "xem huong dan",
            "cach su dung",
            "cach dung",
            "xem cach su dung",
            "xem cach dung",
            "hoc cach",
            "gioi thieu",
            "cac lenh",
            "danh sach lenh",
            "lenh ho tro",
            "cac tinh nang",
            "danh sach tinh nang",
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


@dataclass(slots=True, frozen=True)
class CameraAnalysisResult:
    """Captured image and AI description for one selected camera."""

    camera: CameraTarget
    image_path: str
    analysis: str
    attempted_agents: tuple[str, ...]


@dataclass(slots=True)
class PendingZaloCamera:
    """Camera list waiting for a selection in one Zalo chat."""

    cameras: list[CameraTarget]
    expires_at: datetime
    mode: str = "capture"


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
class PendingZaloCalendarManagement:
    """Calendar events waiting for a safe edit/delete conversation."""

    events: list[CalendarDisplayEvent]
    expires_at: datetime
    phase: str = "action"
    selected_event: CalendarDisplayEvent | None = None
    ai_attempted_agents: list[str] | None = None


@dataclass(slots=True)
class PendingVoiceCamera:
    """Voice camera request waiting for camera, destination, or confirmation."""

    pending_id: str
    cameras: list[CameraTarget]
    zalo_targets: list[dict[str, Any]]
    source_keys: set[str]
    selected_cameras: list[CameraTarget]
    phase: str
    created_at: datetime
    expires_at: datetime
    mode: str = "capture"
    analysis_items: list[CameraAnalysisResult] | None = None


@dataclass(slots=True)
class PendingZaloDevicePower:
    """Rolling-door open command waiting for confirmation in one Zalo chat."""

    action: str
    targets: list[DevicePowerTarget]
    expires_at: datetime
    attempted_agents: list[str]


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


@dataclass(slots=True)
class ActiveZaloChat:
    """One ongoing AI chat bound to a Zalo thread."""

    context: ZaloWebhookContext
    conversation_id: str | None
    phase: str
    generation: int
    expires_at: datetime


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


def _assist_speech_text(value: str) -> str:
    """Return complete plain speech for the Home Assistant Assist pipeline.

    Every Voice Assist callback returns this text as the conversation speech
    field. Removing only presentation markup and decorative emoji keeps dates,
    times, punctuation, entity names, and numbered choices understandable to
    both the user and the TTS engine.
    """
    text = unicodedata.normalize("NFC", str(value or "").strip())
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"__(.*?)__", r"\1", text, flags=re.DOTALL)
    text = text.replace("`", "")
    text = re.sub(r"(?m)^\s*(?:[•▪◦]|[-*+]\s+)\s*", "", text)

    characters: list[str] = []
    for character in text:
        codepoint = ord(character)
        if character in {"\ufe0f", "\u200d", "\u20e3"}:
            continue
        if (
            0x1F000 <= codepoint <= 0x1FAFF
            or 0x2600 <= codepoint <= 0x27BF
        ):
            continue
        characters.append(character)

    text = "".join(characters)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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
        self._zalo_pending_device_powers: dict[
            str, PendingZaloDevicePower
        ] = {}
        self._zalo_pending_calendar_events: dict[
            str, PendingZaloCalendarEvent
        ] = {}
        self._zalo_pending_calendar_managements: dict[
            str, PendingZaloCalendarManagement
        ] = {}
        self._zalo_seen_message_ids: deque[str] = deque()
        self._zalo_seen_message_id_set: set[str] = set()
        self._zalo_ha_conversation_ids: dict[str, str] = {}
        self._zalo_search_conversation_ids: dict[str, str] = {}
        self._zalo_chat_sessions: dict[str, ActiveZaloChat] = {}
        self._zalo_chat_timeout_tasks: dict[str, asyncio.Task[Any]] = {}
        self._zalo_chat_locks: dict[str, asyncio.Lock] = {}
        self._zalo_background_tasks: set[asyncio.Task[Any]] = set()
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}.{entry.entry_id}",
        )
        self._unsub_timer: Callable[[], None] | None = None
        self._unsub_pending_trigger: Callable[[], None] | None = None
        self._unsub_pending_expiry_timer: Callable[[], None] | None = None
        self._unsub_calendar_refresh_interval: Callable[[], None] | None = None
        self._unsub_calendar_notification_timer: Callable[[], None] | None = None
        self._calendar_refresh_task: asyncio.Task[Any] | None = None
        self._calendar_refresh_lock = asyncio.Lock()
        self._calendar_events: list[CalendarDisplayEvent] = []
        self._calendar_window_start: datetime | None = None
        self._calendar_window_end: datetime | None = None
        self._calendar_last_update: datetime | None = None
        self._calendar_refresh_error: str | None = None
        self._calendar_last_notification_at: datetime | None = None
        self._calendar_last_notification_result: str | None = None
        self._calendar_last_notification_error: str | None = None
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
    def ai_camera_task_entity_id(self) -> str:
        """Return the optional AI Task entity used for camera analysis."""
        configured = str(
            self._option(
                CONF_AI_CAMERA_TASK_ENTITY_ID,
                DEFAULT_AI_CAMERA_TASK_ENTITY_ID,
            )
            or ""
        ).strip()
        # Preserve upgrades from 1.6.3: the image AI Task is a practical
        # fallback until a dedicated camera-analysis entity is selected.
        return configured or self.ai_image_task_entity_id

    @property
    def ai_camera_instructions(self) -> str:
        """Return configurable instructions used for every camera analysis."""
        configured = str(
            self._option(
                CONF_AI_CAMERA_INSTRUCTIONS,
                DEFAULT_AI_CAMERA_INSTRUCTIONS,
            )
            or ""
        ).strip()
        return configured or DEFAULT_AI_CAMERA_INSTRUCTIONS

    @property
    def ai_agent_failover_enabled(self) -> bool:
        """Return whether failed AI requests rotate through available agents."""
        return bool(
            self._option(
                CONF_AI_AGENT_FAILOVER_ENABLED,
                DEFAULT_AI_AGENT_FAILOVER_ENABLED,
            )
        )

    @property
    def calendar_lookahead_days(self) -> int:
        """Return the configured number of future calendar days to scan."""
        try:
            days = int(
                float(
                    self._option(
                        CONF_CALENDAR_LOOKAHEAD_DAYS,
                        DEFAULT_CALENDAR_LOOKAHEAD_DAYS,
                    )
                )
            )
        except (TypeError, ValueError):
            days = DEFAULT_CALENDAR_LOOKAHEAD_DAYS
        return max(1, min(MAX_CALENDAR_LOOKAHEAD_DAYS, days))

    @property
    def calendar_configured_entity_ids(self) -> list[str] | None:
        """Return selected calendar IDs, or None for legacy scan-all mode."""
        if CONF_CALENDAR_ENTITIES in self.entry.options:
            value = self.entry.options.get(CONF_CALENDAR_ENTITIES)
        elif CONF_CALENDAR_ENTITIES in self.entry.data:
            value = self.entry.data.get(CONF_CALENDAR_ENTITIES)
        else:
            return None
        return self._normalized_option_list(value)

    @property
    def calendar_monitored_entity_ids(self) -> list[str]:
        """Return currently available calendar IDs included in the scan."""
        return [state.entity_id for state in self._all_calendar_states()]

    @property
    def calendar_notification_enabled(self) -> bool:
        """Return whether the daily calendar summary is enabled."""
        return bool(
            self._option(
                CONF_CALENDAR_NOTIFICATION_ENABLED,
                DEFAULT_CALENDAR_NOTIFICATION_ENABLED,
            )
        )

    @property
    def calendar_notification_time(self) -> time:
        """Return the configured local daily calendar notification time."""
        raw_value = self._option(
            CONF_CALENDAR_NOTIFICATION_TIME,
            DEFAULT_CALENDAR_NOTIFICATION_TIME,
        )
        if isinstance(raw_value, time):
            return raw_value.replace(tzinfo=None)
        parsed = dt_util.parse_time(str(raw_value or ""))
        return parsed or time(7, 0)

    @staticmethod
    def _normalized_option_list(value: Any) -> list[str]:
        """Return a de-duplicated list of non-empty option identifiers."""
        if isinstance(value, str):
            raw_values = [value]
        elif isinstance(value, (list, tuple, set)):
            raw_values = list(value)
        else:
            raw_values = []
        result: list[str] = []
        for item in raw_values:
            normalized = str(item or "").strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    @property
    def calendar_notification_mobile_device_ids(self) -> list[str]:
        """Return fixed Mobile App device IDs for calendar summaries."""
        return self._normalized_option_list(
            self._option(CONF_CALENDAR_NOTIFICATION_MOBILE_DEVICES, [])
        )

    @property
    def calendar_notification_zalo_target_ids(self) -> list[str]:
        """Return fixed configured Zalo target IDs for calendar summaries."""
        return self._normalized_option_list(
            self._option(CONF_CALENDAR_NOTIFICATION_ZALO_TARGETS, [])
        )

    @property
    def calendar_event_count(self) -> int:
        """Return events currently cached in the configured future window."""
        return len(self._calendar_events)

    @property
    def calendar_window_start(self) -> datetime | None:
        """Return the start of the latest successful calendar scan."""
        return self._calendar_window_start

    @property
    def calendar_window_end(self) -> datetime | None:
        """Return the exclusive end of the latest calendar scan."""
        return self._calendar_window_end

    @property
    def calendar_last_update(self) -> datetime | None:
        """Return when calendar data was most recently refreshed."""
        return self._calendar_last_update

    @property
    def calendar_refresh_error(self) -> str | None:
        """Return the last calendar refresh error, if any."""
        return self._calendar_refresh_error

    @property
    def calendar_last_notification_at(self) -> datetime | None:
        """Return when the scheduled calendar notification last ran."""
        return self._calendar_last_notification_at

    @property
    def calendar_last_notification_result(self) -> str | None:
        """Return a concise delivery result for diagnostics."""
        return self._calendar_last_notification_result

    @property
    def calendar_last_notification_error(self) -> str | None:
        """Return the most recent delivery error, if any."""
        return self._calendar_last_notification_error

    @property
    def calendar_upcoming_events(self) -> list[CalendarDisplayEvent]:
        """Return a copy of the cached, chronologically ordered events."""
        return list(self._calendar_events)

    @staticmethod
    def _calendar_event_time_text(event: CalendarDisplayEvent) -> str:
        """Format one normalized calendar event for sensors and messages."""
        start = dt_util.as_local(event.start)
        end = dt_util.as_local(event.end) if event.end is not None else None
        if event.all_day:
            if end is not None and end.date() > start.date() + timedelta(days=1):
                inclusive_end = end.date() - timedelta(days=1)
                return (
                    f"Cả ngày từ {start.strftime('%d/%m/%Y')} đến "
                    f"{inclusive_end.strftime('%d/%m/%Y')}"
                )
            return f"Cả ngày {start.strftime('%d/%m/%Y')}"
        if end is not None:
            if end.date() == start.date():
                return (
                    f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')} "
                    f"ngày {start.strftime('%d/%m/%Y')}"
                )
            return (
                f"{start.strftime('%H:%M %d/%m/%Y')} - "
                f"{end.strftime('%H:%M %d/%m/%Y')}"
            )
        return start.strftime("%H:%M ngày %d/%m/%Y")

    @staticmethod
    def _calendar_days_remaining(event: CalendarDisplayEvent) -> int:
        """Return whole local days until an event starts."""
        local_start = dt_util.as_local(event.start)
        local_now = dt_util.now()
        return max(0, (local_start.date() - local_now.date()).days)

    @property
    def calendar_event_sensor_rows(self) -> list[dict[str, Any]]:
        """Return normalized event attributes for the calendar count sensor."""
        rows: list[dict[str, Any]] = []
        for index, event in enumerate(self._calendar_events, start=1):
            local_start = dt_util.as_local(event.start)
            local_end = (
                dt_util.as_local(event.end)
                if event.end is not None
                else None
            )
            rows.append(
                {
                    "stt": index,
                    "lich": event.calendar_name,
                    "calendar_entity_id": event.calendar_entity_id,
                    "noi_dung": event.summary,
                    "bat_dau": local_start.isoformat(),
                    "ket_thuc": local_end.isoformat() if local_end else None,
                    "ca_ngay": event.all_day,
                    "thoi_gian_hien_thi": self._calendar_event_time_text(event),
                    "con_lai_ngay": self._calendar_days_remaining(event),
                    "dia_diem": event.location or None,
                    "chi_tiet": event.description or None,
                    "uid": event.uid or None,
                }
            )
        return rows

    @property
    def calendar_event_list_text(self) -> str:
        """Return a readable one-attribute list of cached calendar events."""
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in self.calendar_event_sensor_rows:
            calendar_name = str(row["lich"] or "Lịch không tên")
            grouped.setdefault(calendar_name, []).append(row)

        lines: list[str] = []
        item_index = 0
        for calendar_name, rows in grouped.items():
            if lines:
                lines.append("")
            lines.append(f"🗓️ {calendar_name}")
            for row in rows:
                item_index += 1
                lines.append(
                    f"{item_index}. 📌 {row['noi_dung']} — "
                    f"🕒 {row['thoi_gian_hien_thi']} — "
                    f"⏳ còn {row['con_lai_ngay']} ngày"
                )
        return "\n".join(lines)

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

    def _ai_camera_agent_candidates(
        self, primary_entity_id: str
    ) -> list[tuple[str, str]]:
        """Return preferred camera AI Task then compatible failover tasks."""
        entity_ids: list[str] = []

        def add(entity_id: str | None) -> None:
            normalized = str(entity_id or "").strip()
            if normalized and normalized not in entity_ids:
                entity_ids.append(normalized)

        add(primary_entity_id)
        if self.ai_agent_failover_enabled:
            try:
                states = sorted(
                    self.hass.states.async_all(AI_TASK_DOMAIN),
                    key=lambda item: (
                        str(item.attributes.get("friendly_name", "")).casefold(),
                        item.entity_id,
                    ),
                )
            except Exception:  # noqa: BLE001 - keep the selected task usable
                _LOGGER.exception(
                    "Failed listing AI Task entities for camera failover"
                )
                states = []
            for state in states:
                if state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
                    continue
                raw_features = state.attributes.get(ATTR_SUPPORTED_FEATURES)
                if raw_features is not None:
                    try:
                        # GENERATE_DATA (1) and SUPPORT_ATTACHMENTS (2).
                        if (int(raw_features) & 3) != 3:
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

    @staticmethod
    def _zalo_emphasize_important_text(text: str) -> str:
        """Apply one idempotent Markdown formatter to every Zalo message.

        The formatter deliberately distinguishes a confirmation command from
        the same word used in a normal sentence. For example, ``có`` in
        ``có thể gửi Tất cả`` is left untouched, while ``Có`` in
        ``Trả lời Có hoặc Không`` is emphasized. Existing valid Markdown is
        preserved, stray markers are removed, and wrongly emphasized command
        words are repaired before the common rules are applied.
        """
        message = str(text or "").replace("\r\n", "\n").strip()
        if not message:
            return message

        confirmation_commands = (
            "xác nhận xóa",
            "xác nhận xoá",
            "xác nhận sửa",
            "xác nhận cập nhật",
            "xác nhận lưu",
            "xác nhận gửi",
            "xác nhận chụp",
            "xác nhận tạo",
            "xac nhan xoa",
            "xac nhan sua",
            "xac nhan cap nhat",
            "xac nhan luu",
            "xac nhan gui",
            "xac nhan chup",
            "xac nhan tao",
            "không xóa",
            "không xoá",
            "không chụp",
            "không gửi",
            "không lưu",
            "không sửa",
            "không tạo",
            "khong xoa",
            "khong chup",
            "khong gui",
            "khong luu",
            "khong sua",
            "khong tao",
            "bỏ yêu cầu vừa rồi",
            "bỏ yêu cầu",
            "bỏ qua",
            "bo yeu cau vua roi",
            "bo yeu cau",
            "bo qua",
            "giữ nguyên",
            "đồng ý",
            "tất cả",
            "tiếp tục",
            "giu nguyen",
            "dong y",
            "tat ca",
            "tiep tuc",
            "hủy",
            "huỷ",
            "huy",
            "sửa",
            "xóa",
            "xoá",
            "có",
            "không",
            "confirm delete",
            "confirm edit",
            "confirm update",
            "confirm save",
            "confirm send",
            "confirm capture",
            "confirm create",
            "never mind",
            "cancel request",
            "cancel",
            "skip",
            "yes",
            "no",
            "edit",
            "update",
            "delete",
            "remove",
            "confirm",
            "continue",
            "stop",
            "all",
        )
        normalized_commands = {
            normalize_text(command) for command in confirmation_commands
        }

        instruction_terms = (
            "trả lời",
            "hãy trả lời",
            "vui lòng trả lời",
            "phản hồi",
            "hãy phản hồi",
            "vui lòng phản hồi",
            "gửi",
            "hãy gửi",
            "vui lòng gửi",
            "nhập",
            "hãy nhập",
            "vui lòng nhập",
            "nói",
            "hãy nói",
            "vui lòng nói",
            "chọn",
            "hãy chọn",
            "vui lòng chọn",
            "reply",
            "please reply",
            "respond",
            "please respond",
            "send",
            "please send",
            "type",
            "please type",
            "say",
            "please say",
            "choose",
            "please choose",
            "enter",
            "please enter",
        )
        repair_instruction_terms = (
            *instruction_terms,
            "để",
            "như",
            "ví dụ",
            "to",
            "such as",
            "for example",
        )
        instruction_pattern = "|".join(
            sorted(
                (re.escape(item) for item in instruction_terms),
                key=len,
                reverse=True,
            )
        )
        repair_instruction_pattern = "|".join(
            sorted(
                (re.escape(item) for item in repair_instruction_terms),
                key=len,
                reverse=True,
            )
        )
        connector_pattern = r"hoặc|hay|và|or|and"
        prefix_pattern = re.compile(
            rf"(?:^|(?:{repair_instruction_pattern})\s+|"
            rf"(?:{connector_pattern})\s+|[,;:/|\(\[\"'“‘]\s*)$",
            re.IGNORECASE,
        )
        suffix_pattern = re.compile(
            rf"^\s*(?:$|[.,;:!?/|\)\]\"'”’]|"
            rf"(?:{connector_pattern}|để|nếu|then|if)\b)",
            re.IGNORECASE,
        )

        def is_command_context(line: str, start: int, end: int) -> bool:
            """Return whether one exact command is presented as a choice."""
            return bool(prefix_pattern.search(line[:start])) and bool(
                suffix_pattern.search(line[end:])
            )

        def repair_existing_bold(line: str) -> str:
            """Keep valid spans, unbold misplaced commands, remove stray **."""
            protected: list[str] = []

            def replace(match: re.Match[str]) -> str:
                body = match.group("body").strip()
                if (
                    normalize_text(body) in normalized_commands
                    and not is_command_context(line, match.start(), match.end())
                ):
                    return body
                protected.append(f"**{body}**")
                return f"\x00CA_BOLD_{len(protected) - 1}\x00"

            working = re.sub(
                r"\*\*(?P<body>[^*\n]+?)\*\*",
                replace,
                line,
            )
            # Any markers left here were unmatched or nested incorrectly.
            working = working.replace("**", "")
            working = re.sub(r"(?<=\w)\*(?=\s|$|[.,;:!?])", "", working)
            working = re.sub(r"(?<!\S)\*(?=\S)", "", working)
            for index, original in enumerate(protected):
                working = working.replace(
                    f"\x00CA_BOLD_{index}\x00", original
                )
            return working

        lines = [repair_existing_bold(line) for line in message.split("\n")]
        message = "\n".join(lines)

        labels = (
            "Ngày diễn ra",
            "Nội dung",
            "Còn",
            "Địa điểm",
            "Chi tiết",
            "Lịch",
            "Sự kiện",
            "Đã thêm vào",
            "Không thêm được vào",
            "Đã sửa",
            "Đã xóa",
            "Cần xác nhận",
            "Lưu ý",
            "Kết quả",
            "Trạng thái",
            "Thời gian",
            "Nơi nhận",
            "Camera",
            "Ghi chú",
            "Nhắc hẹn",
            "Calendar",
            "Event",
            "Date",
            "Content",
            "Remaining",
            "Location",
            "Details",
            "Warning",
            "Result",
            "Status",
        )
        label_pattern = "|".join(
            sorted((re.escape(label) for label in labels), key=len, reverse=True)
        )
        message = re.sub(
            rf"(?mi)^(?P<prefix>\s*(?:[-•]\s*|\d+[.)]\s*)?)"
            rf"(?P<label>{label_pattern})(?P<colon>\s*:)",
            lambda match: (
                f"{match.group('prefix')}**{match.group('label')}**"
                f"{match.group('colon')}"
            ),
            message,
        )

        command_pattern = "|".join(
            sorted(
                (re.escape(item) for item in confirmation_commands),
                key=len,
                reverse=True,
            )
        )
        choice_pattern = re.compile(
            rf"(?P<prefix>^|(?:{instruction_pattern})\s+|"
            rf"(?:{connector_pattern})\s+|[,;:/|\(\[\"'“‘]\s*)"
            rf"(?P<command>{command_pattern})"
            rf"(?P<suffix>(?=\s*(?:$|[.,;:!?/|\)\]\"'”’]|"
            rf"(?:{connector_pattern}|để|nếu|then|if)\b)))",
            re.IGNORECASE,
        )
        cancel_after_purpose_pattern = re.compile(
            r"(?P<prefix>\b(?:để|to)\s+)"
            r"(?P<command>hủy|huỷ|huy|cancel|skip|never mind)"
            r"(?=\s*(?:$|[.,;:!?]))",
            re.IGNORECASE,
        )

        def emphasize_choices(line: str) -> str:
            protected: list[str] = []

            def protect(match: re.Match[str]) -> str:
                protected.append(match.group(0))
                return f"\x00CA_BOLD_{len(protected) - 1}\x00"

            working = re.sub(r"\*\*[^*\n]+?\*\*", protect, line)
            working = choice_pattern.sub(
                lambda match: (
                    f"{match.group('prefix')}**{match.group('command')}**"
                ),
                working,
            )
            working = cancel_after_purpose_pattern.sub(
                lambda match: (
                    f"{match.group('prefix')}**{match.group('command')}**"
                ),
                working,
            )
            for index, original in enumerate(protected):
                working = working.replace(
                    f"\x00CA_BOLD_{index}\x00", original
                )
            return working

        return "\n".join(
            emphasize_choices(line) for line in message.split("\n")
        )

    def _zalo_owner_has_pending_confirmation(self, owner_key: str) -> bool:
        """Return whether one Zalo chat is waiting for another user turn."""
        now = dt_util.now()
        pending_items = (
            self._zalo_pending_notes.get(owner_key),
            self._zalo_pending_creations.get(owner_key),
            self._zalo_pending_deletions.get(owner_key),
            self._zalo_pending_cameras.get(owner_key),
            self._zalo_pending_device_powers.get(owner_key),
            self._zalo_pending_calendar_events.get(owner_key),
            self._zalo_pending_calendar_managements.get(owner_key),
        )
        return any(
            item is not None and item.expires_at > now for item in pending_items
        )

    def _append_zalo_confirmation_timeout_notice(
        self, context: ZaloWebhookContext, message: str
    ) -> str:
        """Append the common 120-second validity notice to pending prompts."""
        response = str(message or "").rstrip()
        if not response or not self._zalo_owner_has_pending_confirmation(
            context.owner_key
        ):
            return response
        if _request_language(context.text) == "en":
            notice = (
                "⏱️ Each confirmation step is valid for **120 seconds**. "
                "After that, the pending request is cancelled automatically."
            )
        else:
            notice = (
                "⏱️ Mỗi bước xác nhận có hiệu lực trong **120 giây**. "
                "Quá thời gian, yêu cầu đang chờ sẽ tự hủy."
            )
        if notice in response:
            return response
        return f"{response}\n\n{notice}"

    @staticmethod
    def _response_integrity_tokens(text: str) -> set[str]:
        """Return factual tokens that an AI rewrite must preserve verbatim."""
        value = str(text or "")
        patterns = (
            r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
            r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b",
            r"\b[a-z_]+\.[a-z0-9_]+\b",
            r"(?m)^\s*\d+[.)]",
        )
        tokens: set[str] = set()
        for pattern in patterns:
            tokens.update(
                match.group(0).strip() for match in re.finditer(pattern, value)
            )

        # Confirmation commands must remain exactly typeable after an AI
        # rewrite. If an editor replaces "Sửa" with a synonym, the user could
        # follow the displayed instruction but the deterministic state machine
        # would no longer recognize it.
        confirmation_commands = (
            "Xác nhận xóa",
            "Xác nhận xoá",
            "Xác nhận sửa",
            "Xác nhận lưu",
            "Bỏ qua",
            "Bỏ yêu cầu",
            "Không xóa",
            "Không xoá",
            "Không chụp",
            "Giữ nguyên",
            "Đồng ý",
            "Tiếp tục",
            "Tất cả",
            "Sửa",
            "Xóa",
            "Xoá",
            "Hủy",
            "Huỷ",
            "Có",
            "Không",
            "Confirm delete",
            "Confirm edit",
            "Cancel",
            "Skip",
            "Yes",
            "No",
        )
        for command in confirmation_commands:
            match = re.search(
                rf"(?<!\w){re.escape(command)}(?!\w)", value, re.IGNORECASE
            )
            if match is not None:
                tokens.add(match.group(0))
        return tokens

    async def _async_ai_polish_response(
        self,
        request_text: str,
        draft: str,
        *,
        language: str,
        zalo: bool,
        service_context: Context | None,
    ) -> tuple[str, list[str]]:
        """Use configured external AI to improve wording without changing facts."""
        original = str(draft or "").strip()
        primary = self.zalo_conversation_agent_id
        if not original or primary == HOME_ASSISTANT_AGENT:
            return original, []

        candidates = [
            candidate
            for candidate in self._conversation_agent_candidates(primary)
            if candidate[0] != HOME_ASSISTANT_AGENT
        ]
        if not candidates:
            return original, []

        channel_rules = (
            "Use Zalo-friendly Markdown. Put ** before and after important "
            "headings, warnings, dates, times, choices, and results. "
            "Do not remove existing numbering or selection instructions."
            if zalo
            else
            "Return plain natural speech suitable for Home Assistant TTS. "
            "Do not use Markdown symbols, tables, or emoji-only wording."
        )
        prompt = (
            "You are a response editor, not an action agent. Rewrite the draft "
            "to be clear, natural, friendly, and professional. Preserve every "
            "fact, date, time, number, entity name, calendar name, event name, "
            "status, warning, and requested next step exactly. Never invent, "
            "omit, reorder numbered choices, or claim an action not present in "
            "the draft. Keep the same language as the draft. Return only the "
            f"rewritten response. {channel_rules}\n\n"
            f"User request: {request_text!r}\n\nDraft response:\n{original}"
        )
        required_tokens = self._response_integrity_tokens(original)
        attempted: list[str] = []
        for agent_id, agent_name in candidates:
            attempted.append(agent_name)
            try:
                async with asyncio.timeout(15):
                    result = await async_converse(
                        hass=self.hass,
                        text=prompt,
                        conversation_id=None,
                        context=service_context or Context(),
                        language=language,
                        agent_id=agent_id,
                    )
            except TimeoutError:
                _LOGGER.warning("AI response editor %s timed out", agent_id)
                continue
            except Exception:  # noqa: BLE001 - retain the deterministic draft
                _LOGGER.exception("AI response editor %s failed", agent_id)
                continue

            if self._conversation_result_error_code(result):
                continue
            candidate = self._conversation_reply_text(result).strip()
            if not candidate or candidate.startswith("```"):
                continue
            if any(token not in candidate for token in required_tokens):
                _LOGGER.warning(
                    "Rejected AI response rewrite from %s because facts changed",
                    agent_id,
                )
                continue
            lower_bound = max(12, int(len(original) * 0.45))
            upper_bound = max(500, int(len(original) * 2.5))
            if not lower_bound <= len(candidate) <= upper_bound:
                continue
            if not zalo:
                candidate = candidate.replace("**", "").replace("__", "")
            return candidate, attempted
        return original, attempted

    async def _async_prepare_zalo_reply(
        self,
        context: ZaloWebhookContext,
        reply: str,
        service_context: Context | None,
        *,
        ai_generated: bool = False,
    ) -> str:
        """Optionally enrich a deterministic Zalo response with configured AI."""
        text = str(reply or "").strip()
        if ai_generated:
            return text

        # These responses are intentionally deterministic. The usage guide
        # must be returned immediately from the built-in content, while
        # calendar layouts and multi-turn confirmation prompts must preserve
        # exact emoji, numbering, Markdown, and typeable command keywords.
        # AI is still available inside the actual search/calendar/camera
        # workflows where it is needed; only the final structured wording is
        # protected from a second rewrite pass here.
        if (
            text == self._integration_help_text()
            or _is_integration_help_request(context.text)
            or chat_start_request(context.text) is not None
            or self._zalo_owner_has_pending_confirmation(context.owner_key)
            or explicit_home_assistant_request_kind(context.text) == "calendar"
        ):
            return text

        polished, attempted = await self._async_ai_polish_response(
            context.text,
            text,
            language=_request_language(context.text),
            zalo=True,
            service_context=service_context,
        )
        return self._append_ai_attempt_summary(
            polished,
            attempted,
            language=_request_language(context.text),
            zalo=True,
        )

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
                "chat": "chat",
                "calendar": "calendar analysis",
                "camera": "camera analysis",
                "weather": "weather lookup",
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
                "chat": "trò chuyện",
                "calendar": "phân tích lịch",
                "camera": "phân tích camera",
                "weather": "tra cứu thời tiết",
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
        elif action == ACTION_CAMERA_ANALYSIS:
            candidates = self._ai_camera_agent_candidates(
                self.ai_camera_task_entity_id
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
                    CAMERA_ANALYSIS_SENTENCES,
                    self._async_camera_analysis_from_voice,
                ),
                agent_manager.register_trigger(
                    CAMERA_SENTENCES, self._async_camera_from_voice
                ),
                agent_manager.register_trigger(
                    WEATHER_SENTENCES, self._async_weather_from_voice
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
        """Start reminder and calendar scheduling after Home Assistant is ready."""
        self._schedule_next()
        self._start_calendar_monitoring()

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
        if self._unsub_calendar_refresh_interval is not None:
            self._unsub_calendar_refresh_interval()
            self._unsub_calendar_refresh_interval = None
        if self._unsub_calendar_notification_timer is not None:
            self._unsub_calendar_notification_timer()
            self._unsub_calendar_notification_timer = None
        calendar_refresh_task = self._calendar_refresh_task
        if calendar_refresh_task is not None:
            calendar_refresh_task.cancel()
            await asyncio.gather(calendar_refresh_task, return_exceptions=True)
            self._calendar_refresh_task = None
        self._clear_learned_command_triggers()
        for unsub in self._unsubs:
            unsub()
        self._zalo_ha_conversation_ids.clear()
        self._zalo_search_conversation_ids.clear()
        chat_timeout_tasks = tuple(self._zalo_chat_timeout_tasks.values())
        for task in chat_timeout_tasks:
            task.cancel()
        if chat_timeout_tasks:
            await asyncio.gather(*chat_timeout_tasks, return_exceptions=True)
        self._zalo_chat_timeout_tasks.clear()
        self._zalo_chat_sessions.clear()
        self._zalo_chat_locks.clear()
        self._unsubs.clear()
        self._pending.clear()
        self._pending_deletions.clear()
        self._pending_voice_cameras.clear()
        self._zalo_pending_creations.clear()
        self._zalo_pending_deletions.clear()
        self._zalo_pending_cameras.clear()
        self._zalo_pending_device_powers.clear()
        self._zalo_pending_calendar_events.clear()
        self._zalo_pending_calendar_managements.clear()
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
            ACTION_WEATHER,
            ACTION_IMAGE_GENERATION,
        }:
            return builtin

        ha_kind = explicit_home_assistant_request_kind(text)
        if ha_kind == "camera_analysis":
            return ACTION_CAMERA_ANALYSIS
        if ha_kind == "camera":
            return ACTION_CAMERA
        if ha_kind == "calendar":
            return ACTION_CALENDAR
        if ha_kind == "weather":
            return ACTION_WEATHER
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
        if weather_search_request(text) is not None:
            return ACTION_WEATHER
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
        """Return the shared concise guide for Voice Assist and Zalo."""
        return (
            "📘 **HƯỚNG DẪN SỬ DỤNG CONVERSATIONAL ASSISTANT**\n"
            "🇻🇳 Dùng tiếng Việt hoặc 🇬🇧 English trên Voice Assist và Zalo.\n\n"
            "1️⃣ **🏠 NHÀ THÔNG MINH**\n"
            "• Điều khiển bật/tắt/mở/đóng của integration chỉ chạy trong "
            "Zalo; Voice Assist dùng trực tiếp tính năng sẵn có của Home "
            "Assistant để tránh xung đột.\n"
            "• Trên Zalo, lệnh thiết bị hợp lệ được thực hiện ngay. Chỉ lệnh "
            "**mở cửa cuốn/cửa gara** mới yêu cầu **Đồng ý** hoặc **Hủy** "
            "trong 120 giây.\n"
            "• Ví dụ: `Bật đèn phòng khách`; `Tắtquạt phòng ngủ`; "
            "`Mở cửa cuốn`; `Kiểm tra thiết bị đang bật ở tầng 2`.\n\n"
            "2️⃣ **🌦️ THỜI TIẾT BẰNG AI SEARCH**\n"
            "• AI Search tự hiểu đúng địa điểm và mốc thời gian, rồi tra cứu dự báo Internet mới nhất.\n"
            "• Ví dụ: `Thời tiết Hà Nội chiều mai`; `Will it rain in Bangkok this weekend?`.\n\n"
            "3️⃣ **📅 LỊCH VÀ SỰ KIỆN**\n"
            "• Tra cứu, tạo, sửa hoặc xóa sự kiện; kết quả được nhóm theo từng lịch.\n"
            "• Ví dụ: `Sự kiện trong 15 ngày tới`; `Tạo sự kiện họp lúc 18h30 ngày mai`.\n"
            "• Sau tra cứu, phản hồi **Sửa**, **Xóa** hoặc **Bỏ qua** khi được hỏi.\n\n"
            "4️⃣ **🔔 SENSOR VÀ THÔNG BÁO LỊCH**\n"
            "• Calendar settings cho phép chọn lịch, số ngày quét, giờ gửi và nơi nhận Mobile/Zalo.\n"
            "• Ví dụ: chọn 30 ngày, giờ 07:00 và bật thông báo khi có sự kiện.\n\n"
            "5️⃣ **⏰ NHẮC HẸN**\n"
            "• Tạo một lần hoặc lặp lại; gửi tới Mobile, Zalo và loa TTS; có thể xem hoặc xóa.\n"
            "• Ví dụ: `Nhắc tôi uống thuốc sau 30 phút`; `Nhắc tập thể dục mỗi thứ Hai lúc 7 giờ`.\n\n"
            "6️⃣ **📝 GHI CHÚ BẢO MẬT**\n"
            "• Thêm, xem, sửa, xóa; chọn Mức 1 bảo mật bằng pass hoặc Mức 2 công khai.\n"
            "• Ví dụ: `Ghi nhớ mã tủ đồ là 2468`; `Danh sách ghi chú`; `Sửa ghi chú`.\n\n"
            "7️⃣ **📸 CHỤP ẢNH CAMERA**\n"
            "• Chọn một hoặc nhiều camera, chọn đúng Zalo nhận ảnh, rồi xác nhận chụp và gửi.\n"
            "• Ví dụ: `Chụp camera`; chọn `1 3`, chọn Zalo `2`, rồi nói **Đồng ý**.\n\n"
            "8️⃣ **🧠 PHÂN TÍCH CAMERA BẰNG AI**\n"
            "• Chụp và phân tích nhiều camera; instructions có thể sửa tại AI settings.\n"
            "• Ví dụ: `Phân tích camera`; `Analyze camera`; sau đó chọn camera cần xem.\n\n"
            "9️⃣ **🔎 TÌM KIẾM INTERNET**\n"
            "• Dùng AI Agent Search riêng để tìm và tổng hợp thông tin Việt/Anh.\n"
            "• Ví dụ: `Tìm thông tin giá vàng hôm nay`; `Search for the latest Home Assistant news`.\n\n"
            "🔟 **💬 TRÒ CHUYỆN HỎI ĐÁP TRÊN ZALO**\n"
            "• Bắt đầu bằng `Trò chuyện đi`, `Tám đi` hoặc `Buôn đi`; mọi câu hỏi trong phiên dùng AI Search khi cần kiểm chứng.\n"
            "• Sau 120 giây không phản hồi, integration hỏi lại; im lặng thêm 10 giây sẽ tự dừng trò chuyện.\n\n"
            "1️⃣1️⃣ **🎨 TẠO ẢNH AI TRÊN ZALO**\n"
            "• Tạo ảnh từ mô tả và gửi lại đúng cuộc trò chuyện Zalo.\n"
            "• Ví dụ: `Tạo ảnh một chú mèo phi hành gia`; `Generate an image of a smart home`.\n\n"
            "1️⃣2️⃣ **🧩 BỘ NHỚ CÂU LỆNH**\n"
            "• Dạy alias mới, xem danh sách hoặc xóa câu lệnh đã học.\n"
            "• Ví dụ: `Học câu lệnh xem cổng để chụp ảnh camera`; `Xóa câu lệnh xem cổng`.\n\n"
            "1️⃣3️⃣ **🤖 AI DỰ PHÒNG VÀ TRẠNG THÁI XỬ LÝ**\n"
            "• Agent đã chọn luôn được thử trước; khi lỗi có thể tự chuyển agent khác.\n"
            "• Yêu cầu lâu sẽ báo: ⏳ **Đang xử lý thông tin yêu cầu. Hãy chờ phản hồi.**\n\n"
            "1️⃣4️⃣ **✅ CHỌN VÀ XÁC NHẬN**\n"
            "• Có thể chọn nhiều mục bằng `1 3 10`, tên mục hoặc **Tất cả**.\n"
            "• Dùng đúng từ khóa bôi đậm như **Có**, **Không**, **Hủy**, **Bỏ qua**; mỗi bước có hiệu lực 120 giây.\n\n"
            "💡 Gửi `Hướng dẫn sử dụng tích hợp` để xem lại nội dung này."
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
            "Trả lời số cần xóa, ví dụ 1, 1 và 3, hoặc **tất cả**. "
            "Gửi **không xóa** để **hủy**."
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

    def _zalo_pending_device_power(
        self, owner_key: str
    ) -> PendingZaloDevicePower | None:
        """Return a non-expired device-control confirmation for a Zalo chat."""
        pending = self._zalo_pending_device_powers.get(owner_key)
        if pending is None:
            return None
        if pending.expires_at <= dt_util.now():
            self._zalo_pending_device_powers.pop(owner_key, None)
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

    def _zalo_pending_calendar_management(
        self, owner_key: str
    ) -> PendingZaloCalendarManagement | None:
        """Return a non-expired calendar edit/delete flow."""
        pending = self._zalo_pending_calendar_managements.get(owner_key)
        if pending is None:
            return None
        if pending.expires_at <= dt_util.now():
            self._zalo_pending_calendar_managements.pop(owner_key, None)
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
        message = self._zalo_emphasize_important_text(message)
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

        chunks = self._split_zalo_text(message)
        for index, chunk in enumerate(chunks, start=1):
            try:
                await self.hass.services.async_call(
                    ZALO_DOMAIN,
                    ZALO_SERVICE_SEND_MESSAGE,
                    {
                        "type": context.thread_type,
                        "ttl": 0,
                        "message": chunk,
                        "thread_id": context.thread_id,
                        "account_selection": account_selection,
                    },
                    blocking=True,
                )
            except Exception:  # noqa: BLE001 - webhook must still return HTTP 200
                _LOGGER.exception(
                    "Failed to reply to Zalo webhook thread %s "
                    "while sending text chunk %s/%s",
                    context.thread_id,
                    index,
                    len(chunks),
                )
                return False
        return True

    @staticmethod
    def _split_zalo_text(
        message: str, max_chars: int = ZALO_TEXT_CHUNK_MAX_CHARS
    ) -> list[str]:
        """Split long Zalo text without breaking normal Markdown lines.

        Paragraph boundaries are preferred so the built-in guide keeps each
        numbered feature together. A paragraph that is itself too long (for
        example a large camera list) is split at line boundaries, then at a
        nearby whitespace boundary only as a final fallback.
        """
        text = str(message or "").strip()
        if not text:
            return [""]
        if max_chars <= 0 or len(text) <= max_chars:
            return [text]

        def split_long_block(block: str) -> list[str]:
            pieces: list[str] = []
            current = ""
            for line in block.splitlines():
                candidate = line if not current else f"{current}\n{line}"
                if len(candidate) <= max_chars:
                    current = candidate
                    continue
                if current:
                    pieces.append(current.rstrip())
                    current = ""

                remaining = line
                while len(remaining) > max_chars:
                    cut = remaining.rfind(" ", 0, max_chars + 1)
                    if cut <= 0:
                        cut = max_chars
                    pieces.append(remaining[:cut].rstrip())
                    remaining = remaining[cut:].lstrip()
                current = remaining
            if current:
                pieces.append(current.rstrip())
            return [piece for piece in pieces if piece]

        chunks: list[str] = []
        current = ""
        for paragraph in text.split("\n\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            candidate = paragraph if not current else f"{current}\n\n{paragraph}"
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                chunks.append(current.rstrip())
                current = ""
            if len(paragraph) <= max_chars:
                current = paragraph
            else:
                block_pieces = split_long_block(paragraph)
                if block_pieces:
                    chunks.extend(block_pieces[:-1])
                    current = block_pieces[-1]
        if current:
            chunks.append(current.rstrip())
        return chunks or [text]

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
                    + timedelta(seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS),
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
                seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
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
                    + timedelta(seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS),
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
                seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
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
            "\n📝 **Cách chọn camera:**\n"
            "• Gửi một hoặc nhiều số hoặc tên camera, ví dụ: `1 3 10`.\n"
            "• Gửi **Tất cả** để chụp mọi camera khả dụng.\n"
            "• Gửi **Không chụp** hoặc **Hủy** để dừng."
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
            "Bạn cũng có thể nói **tất cả**, hoặc nói **không chụp** "
            "để **hủy**."
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
            "Hãy nói **đồng ý** để chụp và gửi, hoặc nói "
            "**không chụp** để **hủy**."
        )

    @staticmethod
    def _voice_camera_destination_prompt(
        cameras: list[CameraTarget],
        targets: list[dict[str, Any]],
        invalid: bool = False,
    ) -> str:
        """Ask which configured Zalo destinations should receive snapshots."""
        camera_names = ", ".join(
            camera.display_name for camera in cameras
        )
        lines: list[str] = []
        for index, target in enumerate(targets, start=1):
            name = (
                str(target.get(CONF_ZALO_TARGET_NAME, "")).strip()
                or str(target.get(CONF_ZALO_THREAD_ID, "")).strip()
                or "Zalo"
            )
            lines.append(f"{index} - {name}")
        prefix = (
            "Lựa chọn nơi gửi chưa hợp lệ. " if invalid else ""
        )
        return (
            f"{prefix}Bạn đã chọn camera {camera_names}.\n"
            "Hãy chọn Zalo sẽ nhận ảnh:\n"
            f"{chr(10).join(lines)}\n"
            "Hãy nói một hoặc nhiều số hoặc tên nơi nhận, nói **tất cả** "
            "để chọn mọi nơi, hoặc nói **không gửi** hay **hủy** để dừng."
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
            + timedelta(seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS),
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
    def _camera_analysis_selection_prompt(
        cameras: list[CameraTarget], invalid: bool = False
    ) -> str:
        """Build a numbered multi-camera analysis prompt for Zalo."""
        lines = []
        for index, camera in enumerate(cameras, start=1):
            status = " — không khả dụng" if not camera.available else ""
            lines.append(f"{index} - {camera.display_name}{status}")
        prefix = (
            "Lựa chọn chưa hợp lệ. Hãy chọn ít nhất một camera.\n"
            if invalid
            else "Các camera có thể phân tích trên Home Assistant:\n"
        )
        return (
            f"{prefix}{chr(10).join(lines)}\n"
            "\n📝 **Cách chọn camera:**\n"
            "• Gửi một hoặc nhiều số hoặc tên camera, ví dụ: `1 3 10`.\n"
            "• Gửi **Tất cả** để phân tích mọi camera khả dụng.\n"
            "• Gửi **Hủy** để dừng."
        )

    @staticmethod
    def _voice_camera_analysis_selection_prompt(
        cameras: list[CameraTarget], invalid: bool = False
    ) -> str:
        """Build a numbered camera-analysis prompt for Voice Assist."""
        lines = []
        for index, camera in enumerate(cameras, start=1):
            status = " - không khả dụng" if not camera.available else ""
            lines.append(f"{index} - {camera.display_name}{status}")
        prefix = (
            "Lựa chọn chưa hợp lệ. Hãy chọn ít nhất một camera khả dụng.\n"
            if invalid
            else "Các camera có thể phân tích trên Home Assistant:\n"
        )
        return (
            f"{prefix}{chr(10).join(lines)}\n"
            "Hãy nói một hoặc nhiều số hoặc tên camera, ví dụ 1 và 3. "
            "Bạn cũng có thể nói **tất cả**, hoặc nói **hủy**."
        )

    @staticmethod
    def _voice_camera_analysis_destination_prompt(
        targets: list[dict[str, Any]], invalid: bool = False
    ) -> str:
        """Ask which Zalo destinations should receive analysis results."""
        lines = []
        for index, target in enumerate(targets, start=1):
            name = (
                str(target.get(CONF_ZALO_TARGET_NAME, "")).strip()
                or str(target.get(CONF_ZALO_THREAD_ID, "")).strip()
                or "Zalo"
            )
            lines.append(f"{index} - {name}")
        prefix = "Lựa chọn nơi gửi chưa hợp lệ. " if invalid else ""
        return (
            f"{prefix}Bạn có muốn gửi ảnh và nội dung phân tích lên Zalo không?\n"
            f"{chr(10).join(lines)}\n"
            "Hãy nói một hoặc nhiều số hoặc tên nơi nhận, nói **tất cả** "
            "để gửi mọi nơi, hoặc nói **không gửi** để kết thúc."
        )

    def _camera_analysis_unavailable_text(self) -> str:
        """Return a clear setup error for camera analysis."""
        if not self.hass.services.has_service(
            AI_TASK_DOMAIN, AI_TASK_SERVICE_GENERATE_DATA
        ):
            return (
                "Action ai_task.generate_data chưa sẵn sàng trên Home Assistant. "
                "Hãy kiểm tra tích hợp AI Task."
            )
        if not self._ai_camera_agent_candidates(
            self.ai_camera_task_entity_id
        ):
            return (
                "Chưa có AI Task agent phù hợp để phân tích camera. Hãy mở "
                "Cấu hình Conversational Assistant, mục AI, rồi chọn AI Task "
                "agent hỗ trợ generate_data và camera attachments."
            )
        return ""

    async def _async_camera_analysis_from_zalo(
        self, context: ZaloWebhookContext
    ) -> str:
        """Start multi-camera AI analysis from Zalo."""
        self._clear_zalo_pending_for_owner(context.owner_key)
        unavailable = self._camera_analysis_unavailable_text()
        if unavailable:
            return unavailable
        cameras = self._discovered_camera_targets()
        if not cameras:
            return (
                "Chưa tìm thấy camera nào trên Home Assistant. Hãy kiểm tra "
                "tích hợp camera và trạng thái các entity camera."
            )
        self._zalo_pending_cameras[context.owner_key] = PendingZaloCamera(
            cameras=cameras,
            expires_at=dt_util.now()
            + timedelta(seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS),
            mode="analysis",
        )
        return self._camera_analysis_selection_prompt(cameras)

    async def _async_camera_analysis_from_voice(
        self, user_input: ConversationInput, _result: RecognizeResult
    ) -> str:
        """Start multi-camera AI analysis from Voice Assist."""
        unavailable = self._camera_analysis_unavailable_text()
        if unavailable:
            return await self._async_voice_response(user_input, unavailable)
        cameras = self._discovered_camera_targets()
        if not cameras:
            return await self._async_voice_response(
                user_input,
                "Chưa tìm thấy camera nào trên Home Assistant. Hãy kiểm tra "
                "tích hợp camera và trạng thái các entity camera.",
            )
        self._set_pending_voice_camera(
            user_input,
            cameras,
            self._configured_zalo_targets(),
            mode="analysis",
        )
        return await self._async_voice_response(
            user_input, self._voice_camera_analysis_selection_prompt(cameras)
        )

    def _camera_ai_attachment(self, camera: CameraTarget) -> dict[str, Any]:
        """Build the dynamic media selector payload requested by AI Task."""
        return {
            "media_content_id": f"media-source://camera/{camera.entity_id}",
            "media_content_type": "application/vnd.apple.mpegurl",
            "metadata": {
                "title": camera.display_name,
                "thumbnail": f"/api/camera_proxy/{camera.entity_id}",
                "media_class": "video",
                "children_media_class": None,
                "navigateIds": [
                    {},
                    {
                        "media_content_type": "app",
                        "media_content_id": "media-source://camera",
                    },
                ],
            },
        }

    @staticmethod
    def _camera_analysis_response_text(response: Any) -> str:
        """Extract and normalize the one-line generate_data response."""
        result = response if isinstance(response, dict) else {}
        nested = result.get("response")
        if "data" not in result and isinstance(nested, dict):
            result = nested
        data = result.get("data")
        if isinstance(data, str):
            text = data
        elif data is None:
            text = ""
        else:
            try:
                text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            except (TypeError, ValueError):
                text = str(data)
        return re.sub(r"\s+", " ", text).strip()

    async def _async_analyze_camera_with_ai(
        self,
        camera: CameraTarget,
        service_context: Context | None,
        zalo_context: ZaloWebhookContext | None = None,
    ) -> tuple[str | None, list[str]]:
        """Analyze one camera with per-agent timeout and failover."""
        candidates = self._ai_camera_agent_candidates(
            self.ai_camera_task_entity_id
        )
        attempted: list[str] = []
        total_attempts = len(candidates)
        for index, (entity_id, agent_name) in enumerate(candidates):
            attempted.append(agent_name)
            try:
                async with asyncio.timeout(CAMERA_ANALYSIS_TIMEOUT_SECONDS):
                    response = await self.hass.services.async_call(
                        AI_TASK_DOMAIN,
                        AI_TASK_SERVICE_GENERATE_DATA,
                        {
                            "task_name": f"Phân tích cam - {camera.display_name}",
                            "entity_id": entity_id,
                            "attachments": self._camera_ai_attachment(camera),
                            "instructions": self.ai_camera_instructions,
                        },
                        blocking=True,
                        context=service_context,
                        return_response=True,
                    )
                text = self._camera_analysis_response_text(response)
                if not text:
                    raise RuntimeError("AI Task returned empty analysis")
                return text, attempted
            except TimeoutError:
                _LOGGER.warning(
                    "AI Task %s timed out analyzing camera %s",
                    entity_id,
                    camera.entity_id,
                )
            except Exception:  # noqa: BLE001 - fail over per camera
                _LOGGER.exception(
                    "AI Task %s failed analyzing camera %s",
                    entity_id,
                    camera.entity_id,
                )
            if index + 1 < total_attempts:
                await self._async_send_ai_failover_notice(
                    zalo_context,
                    service_context,
                    failed_agent=agent_name,
                    next_agent=candidates[index + 1][1],
                    next_attempt=index + 2,
                    total_attempts=total_attempts,
                    feature="camera",
                    language="vi",
                )
        return None, attempted

    async def _async_capture_and_analyze_cameras(
        self,
        owner_key: str,
        cameras: list[CameraTarget],
        service_context: Context | None,
        zalo_context: ZaloWebhookContext | None = None,
    ) -> tuple[list[CameraAnalysisResult], list[str]]:
        """Capture and analyze each camera independently."""
        items: list[CameraAnalysisResult] = []
        failures: list[str] = []
        for camera in cameras:
            try:
                image_path, capture_error = (
                    await self._async_capture_camera_snapshot(
                        owner_key, camera, service_context
                    )
                )
                if image_path is None:
                    failures.append(
                        capture_error or f"{camera.display_name}: lỗi chụp ảnh"
                    )
                    continue
                analysis, attempted = await self._async_analyze_camera_with_ai(
                    camera, service_context, zalo_context
                )
                if analysis is None:
                    analysis = (
                        "Không thể phân tích camera bằng các AI Task agent hiện có."
                    )
                    failures.append(f"{camera.display_name}: phân tích AI thất bại")
                if len(attempted) > 1:
                    analysis = (
                        f"{analysis} (Đã thử {len(attempted)} AI agent: "
                        + " → ".join(attempted)
                        + ")"
                    )
                items.append(
                    CameraAnalysisResult(
                        camera=camera,
                        image_path=image_path,
                        analysis=re.sub(r"\s+", " ", analysis).strip(),
                        attempted_agents=tuple(attempted),
                    )
                )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - isolate failures per camera
                _LOGGER.exception(
                    "Unexpected camera analysis failure for %s", camera.entity_id
                )
                failures.append(
                    f"{camera.display_name}: lỗi ngoài dự kiến khi xử lý"
                )
        return items, failures

    @staticmethod
    def _camera_analysis_voice_text(
        items: list[CameraAnalysisResult], failures: list[str]
    ) -> str:
        """Format analysis results for Voice Assist."""
        lines = [
            f"{item.camera.display_name}: {item.analysis}" for item in items
        ]
        if failures:
            lines.append("Một số mục không hoàn tất: " + "; ".join(failures) + ".")
        return "\n".join(lines)

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
        try:
            await self.hass.async_add_executor_job(
                _prepare_camera_snapshot_path, filename
            )
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
            snapshot_exists = await self.hass.async_add_executor_job(
                os.path.isfile, filename
            )
        except Exception:  # noqa: BLE001 - continue with other cameras
            _LOGGER.exception(
                "Failed to capture snapshot from %s", camera.entity_id
            )
            return None, f"{camera.display_name}: không chụp được ảnh"
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
                        "message": self._zalo_emphasize_important_text(
                            f"📷 **Đã chụp ảnh:** {camera_name}"
                        ),
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
                            "message": self._zalo_emphasize_important_text(
                            f"📷 **Đã chụp ảnh:** {camera_name}"
                        ),
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
    def _camera_analysis_zalo_message(item: CameraAnalysisResult) -> str:
        """Pair one captured image with its camera analysis."""
        return (
            f"📷 **{item.camera.display_name}**\n"
            f"🔎 **Phân tích:** {item.analysis}"
        )

    async def _async_send_camera_analysis_to_zalo(
        self,
        context: ZaloWebhookContext,
        items: list[CameraAnalysisResult],
        service_context: Context | None,
    ) -> tuple[int, list[str]]:
        """Send each analyzed image back to the originating Zalo chat."""
        account_selection = self._zalo_webhook_account_selection()
        if not account_selection:
            return 0, ["Chưa cấu hình tài khoản Zalo trả lời webhook"]
        if not self.hass.services.has_service(
            ZALO_DOMAIN, ZALO_SERVICE_SEND_IMAGE
        ):
            return 0, [f"Action {ZALO_DOMAIN}.{ZALO_SERVICE_SEND_IMAGE} chưa sẵn sàng"]

        sent = 0
        failures: list[str] = []
        for item in items:
            try:
                await self._async_send_zalo_typing_event(context, service_context)
                await self.hass.services.async_call(
                    ZALO_DOMAIN,
                    ZALO_SERVICE_SEND_IMAGE,
                    {
                        "type": context.thread_type,
                        "ttl": 0,
                        "image_path": item.image_path,
                        "message": self._zalo_emphasize_important_text(
                            self._camera_analysis_zalo_message(item)
                        ),
                        "thread_id": context.thread_id,
                        "account_selection": account_selection,
                    },
                    blocking=True,
                    context=service_context,
                )
                sent += 1
            except Exception:  # noqa: BLE001 - continue remaining cameras
                _LOGGER.exception(
                    "Failed sending camera analysis for %s to Zalo thread %s",
                    item.camera.entity_id,
                    context.thread_id,
                )
                failures.append(f"{item.camera.display_name}: gửi Zalo thất bại")
        return sent, failures

    async def _async_send_camera_analysis_to_configured_zalo(
        self,
        items: list[CameraAnalysisResult],
        zalo_targets: list[dict[str, Any]],
        service_context: Context | None,
    ) -> tuple[list[str], list[str]]:
        """Send analyzed images and matching text to selected Zalo targets."""
        sent_targets: list[str] = []
        failures: list[str] = []
        if not self.hass.services.has_service(
            ZALO_DOMAIN, ZALO_SERVICE_SEND_IMAGE
        ):
            return [], [f"Action {ZALO_DOMAIN}.{ZALO_SERVICE_SEND_IMAGE} chưa sẵn sàng"]

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

            target_ok = True
            for item in items:
                try:
                    await self._async_send_zalo_typing_to_target(
                        thread_id, account_selection, service_context
                    )
                    await self.hass.services.async_call(
                        ZALO_DOMAIN,
                        ZALO_SERVICE_SEND_IMAGE,
                        {
                            "type": thread_type,
                            "ttl": 0,
                            "image_path": item.image_path,
                            "message": self._zalo_emphasize_important_text(
                                self._camera_analysis_zalo_message(item)
                            ),
                            "thread_id": thread_id,
                            "account_selection": account_selection,
                        },
                        blocking=True,
                        context=service_context,
                    )
                except Exception:  # noqa: BLE001 - continue other targets
                    _LOGGER.exception(
                        "Failed sending camera analysis to Zalo target %s",
                        thread_id,
                    )
                    failures.append(
                        f"{target_name}: lỗi gửi {item.camera.display_name}"
                    )
                    target_ok = False
                    break
            if target_ok:
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
            "do not send",
            "dont send",
            "don t send",
            "never mind",
            "khong",
            "khong dong y",
            "khong chup",
            "khong chup anh",
            "khong gui",
            "khong gui zalo",
            "huy",
            "huy chup",
            "huy gui",
            "thoi",
            "thoi khong chup",
            "thoi khong gui",
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

    async def _async_analyze_cameras_to_zalo(
        self,
        context: ZaloWebhookContext,
        cameras: list[CameraTarget],
        service_context: Context | None,
    ) -> ZaloDirectResponse | str:
        """Capture, analyze, and return each selected camera to Zalo."""
        if not self.hass.services.has_service("camera", "snapshot"):
            return "Action camera.snapshot chưa sẵn sàng trên Home Assistant."
        unavailable = self._camera_analysis_unavailable_text()
        if unavailable:
            return unavailable

        items, failures = await self._async_capture_and_analyze_cameras(
            context.owner_key,
            cameras,
            service_context,
            context,
        )
        if not items:
            details = "; ".join(failures)
            return (
                "Không chụp hoặc phân tích được các camera đã chọn. "
                + (details or "Hãy kiểm tra camera và AI Task agent.")
            )
        sent_count, send_failures = await self._async_send_camera_analysis_to_zalo(
            context, items, service_context
        )
        failures.extend(send_failures)
        if sent_count == 0:
            return (
                "Đã xử lý camera nhưng không gửi được ảnh và kết quả lên Zalo. "
                + "; ".join(failures)
            )
        if failures:
            await self._async_send_zalo_webhook_reply(
                context,
                f"✅ Đã gửi kết quả cho {sent_count} camera. "
                "Một số mục không hoàn tất: " + "; ".join(failures) + ".",
            )
        return ZaloDirectResponse(sent=True, response_type="camera_analysis")

    async def _async_zalo_pending_camera_reply(
        self,
        context: ZaloWebhookContext,
        pending: PendingZaloCamera,
        service_context: Context | None,
    ) -> ZaloDirectResponse | str:
        """Handle one or more camera selections from Zalo."""
        normalized = normalize_text(context.text)
        cancel_phrases = {
            "no", "cancel", "stop", "skip", "do not capture",
            "dont capture", "don t capture", "do not take a photo",
            "dont take a photo", "don t take a photo", "never mind",
            "khong", "huy", "bo qua", "khong chup", "khong chup anh",
            "khong lay anh", "khong phan tich",
        }
        if normalized in cancel_phrases:
            self._zalo_pending_cameras.pop(context.owner_key, None)
            self._zalo_pending_calendar_events.pop(context.owner_key, None)
            return (
                "Đã hủy yêu cầu phân tích camera."
                if pending.mode == "analysis"
                else "Đã hủy yêu cầu chụp ảnh camera."
            )

        selected = parse_target_selection(
            context.text, [camera.display_name for camera in pending.cameras]
        )
        prompt = (
            self._camera_analysis_selection_prompt
            if pending.mode == "analysis"
            else self._camera_selection_prompt
        )
        if not selected:
            pending.expires_at = dt_util.now() + timedelta(
                seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
            )
            return prompt(pending.cameras, invalid=True)

        cameras = [pending.cameras[index] for index in selected]
        unavailable = [
            camera.display_name for camera in cameras if not camera.available
        ]
        available = [camera for camera in cameras if camera.available]
        if not available:
            pending.expires_at = dt_util.now() + timedelta(
                seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
            )
            return (
                "Các camera đã chọn hiện không khả dụng: "
                + ", ".join(unavailable)
                + ". Hãy chọn camera khác.\n"
                + prompt(pending.cameras)
            )

        self._zalo_pending_cameras.pop(context.owner_key, None)
        self._zalo_pending_calendar_events.pop(context.owner_key, None)
        if pending.mode == "analysis":
            result = await self._async_analyze_cameras_to_zalo(
                context, available, service_context
            )
        else:
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
        self._zalo_pending_device_powers.pop(owner_key, None)
        self._zalo_pending_calendar_events.pop(owner_key, None)
        self._zalo_pending_calendar_managements.pop(owner_key, None)

    def _cancel_zalo_chat_timeout(self, owner_key: str) -> None:
        """Cancel the current inactivity timer for one Zalo chat."""
        task = self._zalo_chat_timeout_tasks.pop(owner_key, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    def _schedule_zalo_chat_timeout(self, session: ActiveZaloChat) -> None:
        """Start a fresh 120-second inactivity timer for one chat session."""
        owner_key = session.context.owner_key
        self._cancel_zalo_chat_timeout(owner_key)
        generation = session.generation
        task = self.hass.async_create_task(
            self._async_zalo_chat_inactivity_sequence(owner_key, generation)
        )
        self._zalo_chat_timeout_tasks[owner_key] = task

        def _remove_finished(done_task: asyncio.Task[Any]) -> None:
            if self._zalo_chat_timeout_tasks.get(owner_key) is done_task:
                self._zalo_chat_timeout_tasks.pop(owner_key, None)
            if done_task.cancelled():
                return
            try:
                done_task.result()
            except Exception:  # noqa: BLE001 - log timer delivery failures
                _LOGGER.exception(
                    "Zalo chat inactivity timer failed for %s", owner_key
                )

        task.add_done_callback(_remove_finished)

    def _start_zalo_chat(self, context: ZaloWebhookContext) -> ActiveZaloChat:
        """Open a fresh AI chat and discard any old provider conversation ID."""
        previous = self._zalo_chat_sessions.get(context.owner_key)
        generation = previous.generation + 1 if previous is not None else 1
        session = ActiveZaloChat(
            context=context,
            conversation_id=None,
            phase="active",
            generation=generation,
            expires_at=dt_util.now()
            + timedelta(seconds=ZALO_CHAT_IDLE_TIMEOUT_SECONDS),
        )
        self._zalo_chat_sessions[context.owner_key] = session
        self._schedule_zalo_chat_timeout(session)
        return session

    def _touch_zalo_chat_activity(
        self, context: ZaloWebhookContext
    ) -> ActiveZaloChat | None:
        """Reactivate an existing chat whenever its Zalo thread sends a message."""
        session = self._zalo_chat_sessions.get(context.owner_key)
        if session is None:
            return None
        session.context = context
        session.phase = "active"
        session.generation += 1
        session.expires_at = dt_util.now() + timedelta(
            seconds=ZALO_CHAT_IDLE_TIMEOUT_SECONDS
        )
        self._schedule_zalo_chat_timeout(session)
        return session

    def _pause_zalo_chat_timeout_for_processing(
        self, context: ZaloWebhookContext
    ) -> ActiveZaloChat:
        """Pause inactivity countdown while an AI response is being generated."""
        session = self._zalo_chat_sessions.get(context.owner_key)
        if session is None:
            session = self._start_zalo_chat(context)
        self._cancel_zalo_chat_timeout(context.owner_key)
        session.context = context
        session.phase = "processing"
        session.generation += 1
        session.expires_at = dt_util.now() + timedelta(
            seconds=ZALO_SEARCH_TIMEOUT_SECONDS
        )
        return session

    def _pause_existing_zalo_chat_for_request(
        self, context: ZaloWebhookContext
    ) -> bool:
        """Pause an already-open chat while another integration action runs."""
        if context.owner_key not in self._zalo_chat_sessions:
            return False
        self._pause_zalo_chat_timeout_for_processing(context)
        return True

    def _resume_zalo_chat_after_request(
        self, context: ZaloWebhookContext
    ) -> None:
        """Restart inactivity timing after a non-chat response is delivered."""
        session = self._zalo_chat_sessions.get(context.owner_key)
        if (
            session is None
            or session.phase != "processing"
            or session.context is not context
        ):
            return
        session.phase = "active"
        session.expires_at = dt_util.now() + timedelta(
            seconds=ZALO_CHAT_IDLE_TIMEOUT_SECONDS
        )
        self._schedule_zalo_chat_timeout(session)

    @staticmethod
    def _zalo_chat_yields_to_home_assistant(
        text: str, request_kind: str | None
    ) -> bool:
        """Keep explicit smart-home work available inside an active chat."""
        if request_kind in {
            "camera",
            "camera_analysis",
            "calendar",
            "weather",
        }:
            return True
        if request_kind != "conversation":
            return False
        if device_power_request_hint(text):
            return True

        normalized = normalize_text(text)
        action_cues = (
            "kiem tra",
            "xem trang thai",
            "trang thai",
            "bao cao",
            "check",
            "show status",
            "status of",
            "report",
        )
        target_cues = (
            "thiet bi",
            "den",
            "quat",
            "dieu hoa",
            "may lanh",
            "cua cuon",
            "cua gara",
            "khoa cua",
            "cam bien",
            "media player",
            "light",
            "fan",
            "air conditioner",
            "garage door",
            "rolling door",
            "sensor",
            "device",
            "home assistant",
        )
        return any(cue in normalized for cue in action_cues) and any(
            cue in normalized for cue in target_cues
        )

    @staticmethod
    def _zalo_chat_welcome_text() -> str:
        """Return the deterministic opening message for chat mode."""
        return (
            "💬 **Mở phòng trò chuyện rồi nè!**\n\n"
            "Bạn cứ hỏi hoặc kể bất kỳ chuyện gì. Mình sẽ dùng **AI Search** "
            "khi cần kiểm chứng thông tin, nói rõ khi chưa chắc chắn, dùng đúng "
            "thuật ngữ chuyên ngành nhưng vẫn giải thích dễ hiểu.\n\n"
            "Mình sẽ giữ cuộc trò chuyện trong **120 giây** sau mỗi phản hồi. "
            "Im lặng lâu quá thì mình sẽ hỏi lại một lần trước khi đóng phòng 😄"
        )

    @staticmethod
    def _zalo_chat_reengagement_text() -> str:
        """Ask once whether an inactive user wants to keep chatting."""
        return (
            "👋 **Bạn còn muốn trò chuyện tiếp không?**\n\n"
            "Phản hồi trong **10 giây** nhé. Chỉ cần nhắn một câu bất kỳ là "
            "cuộc trò chuyện sẽ tiếp tục."
        )

    @staticmethod
    def _zalo_chat_closed_text() -> str:
        """Return the final message after the 10-second grace period."""
        return (
            "🛑 **Đã dừng trò chuyện hỏi đáp**\n\n"
            "Phòng tám tạm đóng vì chưa thấy bạn phản hồi. Khi muốn mở lại, "
            "hãy nhắn **Trò chuyện đi**, **Tám đi** hoặc **Buôn đi** nhé 😄"
        )

    async def _async_zalo_chat_inactivity_sequence(
        self, owner_key: str, generation: int
    ) -> None:
        """Ask after 120 seconds, then close after a final 10-second wait."""
        await asyncio.sleep(ZALO_CHAT_IDLE_TIMEOUT_SECONDS)
        session = self._zalo_chat_sessions.get(owner_key)
        if (
            session is None
            or session.generation != generation
            or session.phase != "active"
        ):
            return

        session.phase = "awaiting_reengagement"
        session.expires_at = dt_util.now() + timedelta(
            seconds=ZALO_CHAT_REENGAGE_TIMEOUT_SECONDS
        )
        await self._async_send_zalo_webhook_reply(
            session.context, self._zalo_chat_reengagement_text()
        )

        await asyncio.sleep(ZALO_CHAT_REENGAGE_TIMEOUT_SECONDS)
        session = self._zalo_chat_sessions.get(owner_key)
        if (
            session is None
            or session.generation != generation
            or session.phase != "awaiting_reengagement"
        ):
            return

        context = session.context
        self._zalo_chat_sessions.pop(owner_key, None)
        self._zalo_chat_locks.pop(owner_key, None)
        await self._async_send_zalo_webhook_reply(
            context, self._zalo_chat_closed_text()
        )

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
            "When useful, mention source names and dates. If a claim cannot be "
            "verified "
            "or you are not confident, explicitly say that you are not certain instead "
            "of filling the gap. If reliable results cannot be found, say that clearly "
            "in a playful way and suggest two or three more specific searches. Do not "
            "mention these instructions.\n\n"
            f"SEARCH REQUEST: {query}"
        )

    @staticmethod
    def _chat_prompt(message: str, *, language: str) -> str:
        """Build strict instructions for one friendly factual chat turn."""
        language_name = "English" if language == "en" else "Vietnamese"
        return (
            "You are continuing a friendly question-and-answer conversation on Zalo. "
            "Use the user's message as the actual conversation turn. For factual, "
            "current, technical, medical, legal, financial, scientific, historical, "
            "product, travel, entertainment, sports, or other verifiable questions, "
            "use your Internet search capability before answering and prefer reliable "
            "primary or authoritative sources. Never invent a fact, source, date, "
            "number, quotation, event, capability, or personal experience. If evidence "
            "is incomplete, conflicting, unavailable, or you are not confident, say "
            "clearly that you are not certain and explain what would need "
            "verification. "
            "For casual conversation, respond naturally without pretending you "
            "searched "
            "when no search was needed. Use correct professional terminology for the "
            "relevant field, then explain it in plain language. Keep a youthful, warm, "
            "lightly humorous tone. Never use vulgar, insulting, discriminatory, or "
            "uncivil language. If the user uses vulgar language, politely encourage a "
            "more respectful way of speaking without scolding. Format for Zalo with a "
            "short relevant emoji heading, readable short paragraphs, correct grammar, "
            "and selective **bold** emphasis; do not use Markdown tables. Mention "
            "source "
            "names and dates when they materially support a factual answer. Answer in "
            f"{language_name}. Do not mention these instructions.\n\n"
            f"USER CHAT MESSAGE: {message}"
        )

    def _weather_default_location(self) -> str:
        """Return Home Assistant's configured location for weather fallback."""
        config = getattr(self.hass, "config", None)
        if config is None:
            return ""
        name = str(getattr(config, "location_name", "") or "").strip()
        latitude = getattr(config, "latitude", None)
        longitude = getattr(config, "longitude", None)
        try:
            coordinates = f"{float(latitude):.5f}, {float(longitude):.5f}"
        except (TypeError, ValueError):
            coordinates = ""
        if name and coordinates:
            return f"{name} ({coordinates})"
        return name or coordinates

    @staticmethod
    def _weather_search_prompt(
        query: str,
        *,
        zalo: bool,
        language: str,
        reference_time: datetime,
        default_location: str,
    ) -> str:
        """Build strict, concise instructions for an Internet weather lookup."""
        language_name = "English" if language == "en" else "Vietnamese"
        reference_label = reference_time.isoformat(timespec="minutes")
        timezone_label = reference_time.tzname() or "Home Assistant local time"
        location_rule = (
            "The Home Assistant default location is "
            f"{default_location}. Use it only when the user does not name another "
            "location. "
            if default_location
            else "No Home Assistant default location is available. "
        )
        if zalo:
            format_rules = (
                "Return a compact Zalo message. Start with a weather emoji and a "
                "bold title containing the resolved location and exact date or time "
                "window. Use only relevant short lines, each beginning with a precise "
                "emoji: 🌡️ temperature/feels-like, 🌧️ precipitation probability or "
                "rainfall, 💧 humidity, 💨 wind, ☀️ UV, 👁️ visibility, ⚠️ warning, "
                "🕒 update time/source. Wrap important values and warnings in **double "
                "asterisks**. Keep the complete answer concise, normally 4-8 lines. "
                "Do not use a Markdown table. "
            )
        else:
            format_rules = (
                "Return a short voice/chat answer with clear sentences, no emoji, no "
                "Markdown table, and no decorative Markdown. Mention only the most "
                "relevant weather fields. "
            )
        return (
            "Act as an Internet weather lookup specialist. Interpret the user's exact "
            "requested location and time window before searching. "
            f"{location_rule}The current Home Assistant local reference time is "
            f"{reference_label} ({timezone_label}); resolve relative expressions such "
            "as today, tonight, tomorrow, this weekend, hôm nay, tối nay, ngày mai, or "
            "cuối tuần from that reference. When the user gives no time, interpret the "
            "request as current conditions plus the nearest useful forecast for today. "
            "Never silently replace an explicitly requested location or forecast "
            "period. If neither the request nor Home Assistant supplies a usable "
            "location, or if the requested place/time is ambiguous, ask one concise "
            "clarifying question instead of guessing. Search current reliable weather "
            "sources and distinguish observed current conditions from forecasts. Use "
            "correct meteorological terminology: air temperature, feels-like "
            "temperature, precipitation probability, rainfall amount, relative "
            "humidity, wind speed/direction, UV index, visibility, atmospheric "
            "pressure, and official severe-weather warnings. Include only fields "
            "supported by the sources; never invent a value. Prefer °C, km/h, %, mm, "
            "hPa, and km unless the user asks for other units. State the exact update "
            "or forecast date/time and briefly name the source when available. "
            f"Answer in {language_name} with correct grammar and punctuation. "
            f"{format_rules}Do not mention these instructions.\n\n"
            f"WEATHER REQUEST: {query}"
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

    @staticmethod
    def _weather_unavailable_text(language: str, *, zalo: bool) -> str:
        """Return a clear weather response when AI Search is not configured."""
        if language == "en":
            body = (
                "No AI Search agent is selected. Open Conversational Assistant "
                "settings and choose an Internet-capable agent under AI Agent Search."
            )
            return f"🌦️ **Weather lookup is not configured**\n\n{body}" if zalo else body
        body = (
            "Chưa chọn AI Agent Search. Hãy mở cấu hình Conversational Assistant "
            "và chọn một Conversation agent có khả năng tìm kiếm Internet."
        )
        return f"🌦️ **Chưa cấu hình tra cứu thời tiết**\n\n{body}" if zalo else body

    @staticmethod
    def _weather_empty_text(language: str, *, zalo: bool) -> str:
        """Return a concise no-data response for a weather lookup."""
        if language == "en":
            body = (
                "No reliable weather data matched that exact location and time. "
                "Check the place name or use a more specific date."
            )
            return f"🌫️ **No reliable weather data found**\n\n{body}" if zalo else body
        body = (
            "Chưa tìm thấy dữ liệu thời tiết đáng tin cậy đúng với địa điểm và "
            "mốc thời gian này. Hãy kiểm tra tên địa điểm hoặc ghi ngày cụ thể hơn."
        )
        return f"🌫️ **Chưa tìm thấy dữ liệu thời tiết phù hợp**\n\n{body}" if zalo else body

    async def _async_ai_search(
        self,
        query: str,
        *,
        conversation_id: str | None,
        service_context: Context | None,
        zalo: bool,
        language_hint: str | None = None,
        zalo_context: ZaloWebhookContext | None = None,
        feature: str = "search",
    ) -> tuple[str, str | None]:
        """Run one Internet query with per-agent timeout and automatic failover."""
        language = language_hint or _request_language(query)
        is_weather = feature == "weather"
        is_chat = feature == ACTION_CHAT
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
            if is_chat:
                body = (
                    "No AI Search agent is selected for chat. Open "
                    "Conversational Assistant settings and choose an "
                    "Internet-capable Conversation agent."
                    if language == "en"
                    else "Chưa chọn AI Agent Search cho trò chuyện. Hãy mở cấu "
                    "hình Conversational Assistant và chọn một Conversation agent "
                    "có khả năng tìm kiếm Internet."
                )
                unavailable = (
                    f"🤖 **AI chat is not configured**\n\n{body}"
                    if language == "en"
                    else f"🤖 **Chưa cấu hình AI trò chuyện**\n\n{body}"
                )
            else:
                unavailable = (
                    self._weather_unavailable_text(language, zalo=zalo)
                    if is_weather
                    else self._search_unavailable_text(language, zalo=zalo)
                )
            return unavailable, None

        attempted_agents: list[str] = []
        had_empty_response = False
        primary_agent_id = self.ai_search_agent_id
        total_attempts = len(candidates)
        if is_weather:
            prompt_text = self._weather_search_prompt(
                query,
                zalo=zalo,
                language=language,
                reference_time=dt_util.now(),
                default_location=self._weather_default_location(),
            )
        elif is_chat:
            prompt_text = self._chat_prompt(query, language=language)
        else:
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
                    "AI Search agent %s timed out after %s seconds for %s query %s",
                    agent_id,
                    ZALO_SEARCH_TIMEOUT_SECONDS,
                    feature,
                    query,
                )
            except Exception:  # noqa: BLE001 - rotate instead of failing silently
                _LOGGER.exception(
                    "AI Search agent %s failed for %s query %s",
                    agent_id,
                    feature,
                    query,
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
                        if is_weather:
                            heading = (
                                "🌦️ **Weather lookup**"
                                if language == "en"
                                else "🌦️ **Kết quả tra cứu thời tiết**"
                            )
                            allowed_headings = (
                                "🌦️", "☀️", "🌤️", "⛅", "☁️", "🌧️",
                                "⛈️", "🌩️", "🌨️", "❄️", "🌫️", "🌪️",
                            )
                        elif is_chat:
                            heading = (
                                "💬 **Let’s chat**"
                                if language == "en"
                                else "💬 **Mình tám tiếp nhé**"
                            )
                            allowed_headings = (
                                "💬", "🤝", "😄", "🧠", "📚", "💡",
                                "🔎", "🌐", "🎯", "✨", "🧐", "🤔",
                            )
                        else:
                            heading = (
                                "🔎 **Search results**"
                                if language == "en"
                                else "🔎 **Kết quả tìm kiếm**"
                            )
                            allowed_headings = (
                                "🔎", "🌐", "📰", "📌", "💡", "🧭"
                            )
                        if "**" not in reply or not reply.startswith(allowed_headings):
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
                    feature=feature,
                    failed_agent=agent_name,
                    next_agent=candidates[index + 1][1],
                    next_attempt=index + 2,
                    total_attempts=total_attempts,
                    language=language,
                )

        if had_empty_response:
            if is_chat:
                body = (
                    "I do not have a sufficiently reliable answer for that yet. "
                    "Please add a little more context or ask in a more specific way."
                    if language == "en"
                    else "Mình chưa có câu trả lời đủ đáng tin cho nội dung này. "
                    "Bạn thêm một chút bối cảnh hoặc hỏi cụ thể hơn nhé."
                )
                message = (
                    f"🤔 **I’m not certain yet**\n\n{body}"
                    if language == "en"
                    else f"🤔 **Mình chưa chắc chắn**\n\n{body}"
                )
            else:
                message = (
                    self._weather_empty_text(language, zalo=zalo)
                    if is_weather
                    else self._search_empty_text(language, zalo=zalo)
                )
        else:
            message = (
                "All available search agents failed or timed out. Check the AI "
                "agents configured in Home Assistant and try again."
                if language == "en"
                else "Tất cả AI agent tìm kiếm khả dụng đều lỗi hoặc hết thời gian "
                "chờ. Hãy kiểm tra các AI agent trong Home Assistant rồi thử lại."
            )
            if zalo:
                if is_weather:
                    message = (
                        f"⚠️ **Weather agents unavailable**\n\n{message}"
                        if language == "en"
                        else f"⚠️ **AI tra cứu thời tiết chưa phản hồi**\n\n{message}"
                    )
                elif is_chat:
                    message = (
                        f"⚠️ **Chat agents unavailable**\n\n{message}"
                        if language == "en"
                        else f"⚠️ **AI trò chuyện chưa phản hồi**\n\n{message}"
                    )
                else:
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

    async def _async_chat_from_zalo(
        self,
        context: ZaloWebhookContext,
        service_context: Context | None,
    ) -> str:
        """Answer one ongoing Zalo chat turn through the AI Search agent."""
        lock = self._zalo_chat_locks.setdefault(
            context.owner_key, asyncio.Lock()
        )
        async with lock:
            session = self._pause_zalo_chat_timeout_for_processing(context)
            generation = session.generation
            conversation_id = session.conversation_id
            language = _request_language(context.text)
            next_conversation_id: str | None = None
            try:
                reply, next_conversation_id = await self._async_ai_search(
                    context.text,
                    conversation_id=conversation_id,
                    service_context=service_context,
                    zalo=True,
                    language_hint=language,
                    zalo_context=context,
                    feature=ACTION_CHAT,
                )
                reply = sanitize_chat_reply(reply)
                if contains_inappropriate_language(context.text):
                    warning = (
                        "🌿 **A gentle reminder:** Let’s keep the wording "
                        "respectful so the conversation stays fun and useful."
                        if language == "en"
                        else "🌿 **Nhắc nhẹ nè:** Mình trò chuyện vui hết cỡ, "
                        "nhưng mình giữ lời lẽ văn minh nhé. Đổi sang cách nói "
                        "lịch sự hơn thì cuộc tám sẽ mượt như Wi‑Fi full vạch 😄"
                    )
                    reply = f"{warning}\n\n{reply}"
                return reply
            finally:
                current = self._zalo_chat_sessions.get(context.owner_key)
                if current is not None:
                    if next_conversation_id:
                        current.conversation_id = next_conversation_id
                    current.context = context
                    if current.generation == generation:
                        current.phase = "active"
                        current.expires_at = dt_util.now() + timedelta(
                            seconds=ZALO_CHAT_IDLE_TIMEOUT_SECONDS
                        )
                        self._schedule_zalo_chat_timeout(current)

    async def _async_weather_from_zalo(
        self,
        context: ZaloWebhookContext,
        service_context: Context | None,
    ) -> str:
        """Look up weather through the configured Internet AI Search agent."""
        query = weather_search_request(context.text) or context.text
        reply, _conversation_id = await self._async_ai_search(
            query,
            conversation_id=None,
            service_context=service_context,
            zalo=True,
            language_hint=_request_language(context.text),
            zalo_context=context,
            feature="weather",
        )
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
                    "message": self._zalo_emphasize_important_text(message),
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

    def _device_power_targets(self) -> list[DevicePowerTarget]:
        """Return exposed entities with live Zalo device-control services."""
        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)
        area_registry = ar.async_get(self.hass)
        targets: list[DevicePowerTarget] = []

        for state in self.hass.states.async_all():
            domain = state.entity_id.partition(".")[0]
            if domain not in POWER_CONTROL_DOMAINS:
                continue
            if state.state == STATE_UNAVAILABLE:
                continue

            supports_turn_on = domain != "cover" and (
                self.hass.services.has_service(domain, "turn_on")
            )
            supports_turn_off = domain != "cover" and (
                self.hass.services.has_service(domain, "turn_off")
            )
            supports_open_cover = (
                domain == "cover"
                and self.hass.services.has_service("cover", "open_cover")
            )
            supports_close_cover = (
                domain == "cover"
                and self.hass.services.has_service("cover", "close_cover")
            )
            if not any(
                (
                    supports_turn_on,
                    supports_turn_off,
                    supports_open_cover,
                    supports_close_cover,
                )
            ):
                continue

            try:
                exposed = async_should_expose(
                    self.hass, "conversation", state.entity_id
                )
            except Exception:  # noqa: BLE001 - never expose on uncertainty
                _LOGGER.exception(
                    "Failed checking Assist exposure for %s", state.entity_id
                )
                exposed = False
            if not exposed:
                continue

            display_name = str(state.name or state.entity_id).strip()
            device_class = str(
                state.attributes.get("device_class", "") or ""
            ).strip()
            aliases = {
                display_name,
                state.entity_id,
                state.entity_id.split(".", 1)[1],
            }
            area_name = ""
            registry_entry = entity_registry.async_get(state.entity_id)
            if registry_entry is not None:
                alias_getter = getattr(er, "async_get_entity_aliases", None)
                if alias_getter is not None:
                    try:
                        registry_aliases = alias_getter(
                            self.hass, registry_entry
                        )
                    except Exception:  # noqa: BLE001 - aliases are optional
                        _LOGGER.debug(
                            "Failed resolving aliases for %s",
                            state.entity_id,
                            exc_info=True,
                        )
                        registry_aliases = []
                else:
                    registry_aliases = getattr(
                        registry_entry, "aliases", ()
                    ) or ()
                for alias in registry_aliases:
                    # Newer Home Assistant releases may store a computed-name
                    # sentinel in RegistryEntry.aliases. Only resolved strings
                    # are safe to send to an AI parser.
                    if not isinstance(alias, str):
                        continue
                    alias_text = alias.strip()
                    if alias_text:
                        aliases.add(alias_text)

                area_id = getattr(registry_entry, "area_id", None)
                if not area_id and getattr(registry_entry, "device_id", None):
                    device = device_registry.async_get(registry_entry.device_id)
                    if device is not None:
                        area_id = device.area_id
                if area_id:
                    area = area_registry.async_get_area(area_id)
                    if area is not None:
                        area_name = str(area.name or "").strip()
                        if area_name:
                            aliases.add(f"{display_name} {area_name}")

            targets.append(
                DevicePowerTarget(
                    entity_id=state.entity_id,
                    display_name=display_name,
                    domain=domain,
                    aliases=tuple(sorted(aliases, key=str.casefold)),
                    supports_turn_on=supports_turn_on,
                    supports_turn_off=supports_turn_off,
                    supports_open_cover=supports_open_cover,
                    supports_close_cover=supports_close_cover,
                    area_name=area_name,
                    device_class=device_class,
                )
            )

        return sorted(
            targets,
            key=lambda target: (
                target.display_name.casefold(),
                target.entity_id,
            ),
        )

    async def _async_native_home_assistant_converse(
        self,
        text: str,
        *,
        context: Context,
        language: str,
        conversation_id: str | None = None,
        device_id: str | None = None,
        satellite_id: str | None = None,
    ) -> tuple[Any | None, str | None]:
        """Run Home Assistant's built-in intents for a Zalo device command.

        Calling the default agent's native intent handler directly avoids
        sending the command back through this integration's sentence triggers.
        """
        agent_manager = get_agent_manager(self.hass)
        default_agent = getattr(agent_manager, "default_agent", None)
        native_handler = getattr(default_agent, "async_handle_intents", None)
        if default_agent is None or not callable(native_handler):
            _LOGGER.error(
                "Home Assistant default agent does not expose native intent handling"
            )
            return None, "error"

        native_conversation_id = (
            conversation_id or f"native-device-{uuid.uuid4().hex}"
        )
        native_input = ConversationInput(
            text=text,
            context=context,
            conversation_id=conversation_id,
            device_id=device_id,
            satellite_id=satellite_id,
            language=language,
            agent_id=HOME_ASSISTANT_AGENT,
        )
        chat_log = ChatLog(self.hass, native_conversation_id)

        try:
            async with asyncio.timeout(10):
                response = await native_handler(native_input, chat_log)
        except TimeoutError:
            _LOGGER.warning(
                "Home Assistant native intent handling timed out for %s", text
            )
            return None, "timeout"
        except Exception:  # noqa: BLE001 - return a safe local-agent error
            _LOGGER.exception(
                "Home Assistant native intent handling failed for %s", text
            )
            return None, "error"

        if response is None:
            response = intent.IntentResponse(language=language)
            response.async_set_error(
                intent.IntentResponseErrorCode.NO_INTENT_MATCH,
                "",
            )

        return (
            ConversationResult(
                response=response,
                conversation_id=conversation_id,
            ),
            None,
        )

    async def _async_ai_device_power_interpretation(
        self,
        text: str,
        targets: list[DevicePowerTarget],
        *,
        service_context: Context | None,
        language: str,
    ) -> tuple[DevicePowerInterpretation | None, list[str]]:
        """Use AI only to recover a malformed action and exact entity IDs."""
        candidates = [
            candidate
            for candidate in self._conversation_agent_candidates(
                self.zalo_conversation_agent_id
            )
            if candidate[0] != HOME_ASSISTANT_AGENT
        ]
        if not candidates or not targets:
            return None, []

        ranked_targets = rank_power_targets(text, targets)
        inventory = [
            {
                "entity_id": target.entity_id,
                "name": target.display_name,
                "domain": target.domain,
                "aliases": list(target.aliases),
                "area": target.area_name,
                "turn_on": target.supports_turn_on,
                "turn_off": target.supports_turn_off,
                "open_cover": target.supports("open_cover"),
                "close_cover": target.supports("close_cover"),
                "device_class": target.device_class,
            }
            for target in ranked_targets
        ]
        prompt = (
            "You are a strict Home Assistant device-command parser. Do not "
            "execute any tool or action. The user text may contain spelling "
            "errors, repeated letters, missing spaces, or joined Vietnamese "
            "words. Choose only exact entity_id values from the inventory. "
            "Return exactly one JSON object and no explanation with fields: "
            "action ('turn_on', 'turn_off', 'open_cover', or 'close_cover'), "
            "entity_ids (array), and confidence (0 to 1). If the action or "
            "target is ambiguous, return entity_ids=[]. Confirmation policy "
            "is decided only by the integration. "
            "Never invent an entity_id. Select multiple entities only when the "
            "request clearly refers to all matching devices in a room, area, "
            "category, or plural group.\n\n"
            f"User text: {text!r}\n"
            "Entity inventory:\n"
            + json.dumps(inventory, ensure_ascii=False, separators=(",", ":"))
        )

        attempted_agents: list[str] = []
        explicit_action = explicit_power_action(text)
        for agent_id, agent_name in candidates:
            attempted_agents.append(agent_name)
            try:
                async with asyncio.timeout(30):
                    result = await async_converse(
                        hass=self.hass,
                        text=prompt,
                        conversation_id=None,
                        context=service_context or Context(),
                        language=language,
                        agent_id=agent_id,
                    )
            except TimeoutError:
                _LOGGER.warning("Device parser AI %s timed out", agent_id)
                continue
            except Exception:  # noqa: BLE001 - rotate to the next parser
                _LOGGER.exception("Device parser AI %s failed", agent_id)
                continue

            if self._conversation_result_error_code(result):
                continue
            payload = self._calendar_json_object(
                self._conversation_reply_text(result)
            )
            if payload is None:
                continue
            interpretation = interpretation_from_payload(
                payload, ranked_targets
            )
            if interpretation is None:
                continue
            if explicit_action and interpretation.action != explicit_action:
                _LOGGER.warning(
                    "Rejected AI device parse because action changed from %s to %s",
                    explicit_action,
                    interpretation.action,
                )
                continue
            return interpretation, attempted_agents
        return None, attempted_agents

    @staticmethod
    def _device_power_action_label(action: str, language: str) -> str:
        """Return a readable device action label."""
        if language == "en":
            return {
                "turn_on": "Turn on",
                "turn_off": "Turn off",
                "open_cover": "Open",
                "close_cover": "Close",
            }.get(action, action)
        return {
            "turn_on": "Bật",
            "turn_off": "Tắt",
            "open_cover": "Mở",
            "close_cover": "Đóng",
        }.get(action, action)

    def _device_power_confirmation_text(
        self,
        action: str,
        targets: list[DevicePowerTarget],
        *,
        language: str,
        invalid: bool = False,
    ) -> str:
        """Build the Zalo-only rolling-door opening confirmation prompt."""
        action_label = self._device_power_action_label(action, language)
        names = ", ".join(target.display_name for target in targets)
        if language == "en":
            prefix = "I still need a clear confirmation.\n" if invalid else ""
            return (
                f"⚠️ **Rolling-door opening confirmation required**\n\n"
                f"{prefix}"
                f"**Action:** {action_label}\n"
                f"**Device:** {names}\n\n"
                "Reply **Agree** to execute or **Cancel** to stop."
            )
        prefix = "Tôi vẫn cần bạn xác nhận rõ.\n" if invalid else ""
        return (
            f"⚠️ **Cần xác nhận mở cửa cuốn**\n\n{prefix}"
            f"**Thao tác:** {action_label}\n"
            f"**Thiết bị:** {names}\n\n"
            "Trả lời **Đồng ý** để thực hiện hoặc **Hủy** để dừng."
        )

    @staticmethod
    def _is_device_power_confirmation(text: str) -> bool:
        """Return whether a reply clearly approves a pending power action."""
        return normalize_text(text) in {
            "agree",
            "approved",
            "confirm",
            "confirmed",
            "go ahead",
            "proceed",
            "yes",
            "dong y",
            "toi dong y",
            "xac nhan",
            "toi xac nhan",
            "co",
            "duoc",
            "duoc roi",
            "vang",
            "ok",
            "oke",
            "tien hanh",
            "thuc hien",
        }

    async def _async_execute_device_power(
        self,
        action: str,
        targets: list[DevicePowerTarget],
        service_context: Context | None,
        *,
        language: str,
    ) -> tuple[list[DevicePowerTarget], list[str]]:
        """Execute validated entity IDs through Home Assistant services."""
        succeeded: list[DevicePowerTarget] = []
        failures: list[str] = []
        live_targets = {
            target.entity_id: target for target in self._device_power_targets()
        }

        for target in targets:
            current = live_targets.get(target.entity_id)
            if current is None or not current.supports(action):
                reason = (
                    "no longer available"
                    if language == "en"
                    else "không còn khả dụng"
                )
                failures.append(f"{target.display_name}: {reason}")
                continue
            domain = current.domain
            service_action = action
            if (
                action == "turn_on"
                and is_rolling_door_target(current)
                and current.supports_open_cover
            ):
                service_action = "open_cover"
            elif (
                action == "turn_off"
                and is_rolling_door_target(current)
                and current.supports_close_cover
            ):
                service_action = "close_cover"
            elif action == "open_cover" and not current.supports_open_cover:
                service_action = "turn_on"
            elif action == "close_cover" and not current.supports_close_cover:
                service_action = "turn_off"
            service_domain = (
                domain
                if self.hass.services.has_service(domain, service_action)
                else "homeassistant"
            )
            if not self.hass.services.has_service(
                service_domain, service_action
            ):
                reason = (
                    "does not support this action"
                    if language == "en"
                    else "không hỗ trợ thao tác này"
                )
                failures.append(f"{current.display_name}: {reason}")
                continue
            try:
                await self.hass.services.async_call(
                    service_domain,
                    service_action,
                    {"entity_id": current.entity_id},
                    blocking=True,
                    context=service_context,
                )
            except Exception:  # noqa: BLE001 - continue other exact targets
                _LOGGER.exception(
                    "Failed %s for %s", service_action, current.entity_id
                )
                reason = (
                    "action failed"
                    if language == "en"
                    else "thực hiện thất bại"
                )
                failures.append(f"{current.display_name}: {reason}")
                continue
            succeeded.append(current)
        return succeeded, failures

    def _device_power_result_text(
        self,
        action: str,
        succeeded: list[DevicePowerTarget],
        failures: list[str],
        *,
        language: str,
    ) -> str:
        """Format a Zalo result without claiming failed actions succeeded."""
        action_label = self._device_power_action_label(action, language)
        if language == "en":
            if succeeded:
                message = (
                    f"✅ **{action_label} completed**: "
                    + ", ".join(target.display_name for target in succeeded)
                    + "."
                )
            else:
                message = "The device action could not be completed."
            if failures:
                message += " Failed: " + "; ".join(failures) + "."
            return message

        if succeeded:
            message = (
                f"✅ **Đã {action_label.lower()} thiết bị**\n\n"
                + ", ".join(target.display_name for target in succeeded)
                + "."
            )
        else:
            message = "Chưa thể thực hiện thao tác với thiết bị."
        if failures:
            message += " Không hoàn tất: " + "; ".join(failures) + "."
        return message

    @staticmethod
    def _can_execute_ai_device_power(
        text: str,
        interpretation: DevicePowerInterpretation,
    ) -> bool:
        """Allow a validated Zalo interpretation to execute without a prompt."""
        return bool(
            interpretation.targets
            and interpretation.confidence >= 0.80
            and explicit_power_action(text) == interpretation.action
        )

    @staticmethod
    def _device_power_requires_confirmation(
        action: str,
        targets: list[DevicePowerTarget],
    ) -> bool:
        """Require confirmation only when Zalo is opening a rolling door."""
        return action in {"open_cover", "turn_on"} and any(
            is_rolling_door_target(target) for target in targets
        )

    @staticmethod
    def _device_power_clarification_text(language: str) -> str:
        """Ask for a clearer target without creating a confirmation flow."""
        if language == "en":
            return (
                "I could not identify the device confidently enough to control "
                "it. Please include the exact device or room name."
            )
        return (
            "Tôi chưa xác định đủ chắc chắn thiết bị cần điều khiển. Hãy nhập "
            "đúng tên thiết bị hoặc kèm tên phòng/khu vực."
        )

    async def _async_execute_or_confirm_zalo_device_power(
        self,
        context: ZaloWebhookContext,
        action: str,
        targets: list[DevicePowerTarget],
        attempted_agents: list[str],
        service_context: Context | None,
        *,
        language: str,
    ) -> str:
        """Execute immediately, except when Zalo is opening a rolling door."""
        if self._device_power_requires_confirmation(action, targets):
            self._zalo_pending_device_powers[context.owner_key] = (
                PendingZaloDevicePower(
                    action=action,
                    targets=list(targets),
                    expires_at=dt_util.now()
                    + timedelta(seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS),
                    attempted_agents=list(attempted_agents),
                )
            )
            return self._append_ai_attempt_summary(
                self._device_power_confirmation_text(
                    action,
                    targets,
                    language=language,
                ),
                attempted_agents,
                language=language,
                zalo=True,
            )

        succeeded, failures = await self._async_execute_device_power(
            action,
            targets,
            service_context,
            language=language,
        )
        return self._append_ai_attempt_summary(
            self._device_power_result_text(
                action,
                succeeded,
                failures,
                language=language,
            ),
            attempted_agents,
            language=language,
            zalo=True,
        )

    async def _async_device_power_from_zalo(
        self,
        context: ZaloWebhookContext,
        service_context: Context | None,
    ) -> str:
        """Control devices from Zalo without duplicating Voice Assist logic."""
        language = _request_language(context.text)
        targets = self._device_power_targets()
        explicit_action = explicit_power_action(context.text)
        if explicit_action is not None:
            exact_targets = exact_power_targets(
                context.text,
                explicit_action,
                targets,
            )
            if exact_targets:
                return await self._async_execute_or_confirm_zalo_device_power(
                    context,
                    explicit_action,
                    exact_targets,
                    [],
                    service_context,
                    language=language,
                )

        # Never let the native agent open a rolling door before this
        # integration has applied its explicit Zalo confirmation policy.
        if rolling_door_open_request_hint(context.text):
            interpretation, attempted = (
                await self._async_ai_device_power_interpretation(
                    context.text,
                    targets,
                    service_context=service_context,
                    language=language,
                )
            )
            if interpretation is None or not self._can_execute_ai_device_power(
                context.text, interpretation
            ):
                return self._append_ai_attempt_summary(
                    self._device_power_clarification_text(language),
                    attempted,
                    language=language,
                    zalo=True,
                )
            return await self._async_execute_or_confirm_zalo_device_power(
                context,
                interpretation.action,
                list(interpretation.targets),
                attempted,
                service_context,
                language=language,
            )

        native_result, native_failure = (
            await self._async_native_home_assistant_converse(
                context.text,
                context=service_context or Context(),
                language=language,
            )
        )
        if native_result is None:
            if language == "en":
                return (
                    "The local Home Assistant agent timed out. AI was not used "
                    "to avoid running the device action twice."
                    if native_failure == "timeout"
                    else "The local Home Assistant agent failed. AI was not "
                    "used because the device action status is unknown."
                )
            return (
                "Home Assistant cục bộ phản hồi quá lâu. Tôi không dùng AI để "
                "tránh thực hiện lặp thao tác thiết bị."
                if native_failure == "timeout"
                else "Home Assistant cục bộ gặp lỗi. Tôi không dùng AI vì "
                "chưa xác định được trạng thái thao tác thiết bị."
            )

        native_error = self._conversation_result_error_code(native_result)
        native_reply = self._conversation_reply_text(native_result)
        if not native_error:
            return native_reply or (
                "Home Assistant completed the device action."
                if language == "en"
                else "Home Assistant đã thực hiện thao tác thiết bị."
            )
        if native_error and native_error not in {
            "no_intent_match",
            "no_valid_targets",
        }:
            return native_reply or (
                "Home Assistant could not complete the device action."
                if language == "en"
                else "Home Assistant chưa thể hoàn tất thao tác thiết bị."
            )

        interpretation, attempted = (
            await self._async_ai_device_power_interpretation(
                context.text,
                targets,
                service_context=service_context,
                language=language,
            )
        )
        if interpretation is None or not self._can_execute_ai_device_power(
            context.text, interpretation
        ):
            return self._append_ai_attempt_summary(
                self._device_power_clarification_text(language),
                attempted,
                language=language,
                zalo=True,
            )

        return await self._async_execute_or_confirm_zalo_device_power(
            context,
            interpretation.action,
            list(interpretation.targets),
            attempted,
            service_context,
            language=language,
        )

    async def _async_zalo_pending_device_power_reply(
        self,
        context: ZaloWebhookContext,
        pending: PendingZaloDevicePower,
        service_context: Context | None,
    ) -> str:
        """Confirm or cancel one Zalo rolling-door opening command."""
        language = _request_language(context.text)
        if self._is_cancel_pending_text(context.text):
            self._zalo_pending_device_powers.pop(context.owner_key, None)
            return (
                "Cancelled the pending rolling-door opening."
                if language == "en"
                else "Đã hủy yêu cầu mở cửa cuốn đang chờ xác nhận."
            )

        if not self._is_device_power_confirmation(context.text):
            pending.expires_at = dt_util.now() + timedelta(
                seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
            )
            return self._device_power_confirmation_text(
                pending.action,
                pending.targets,
                language=language,
                invalid=True,
            )

        self._zalo_pending_device_powers.pop(context.owner_key, None)
        if not self._device_power_requires_confirmation(
            pending.action, pending.targets
        ):
            _LOGGER.warning(
                "Discarded unexpected non-door Zalo confirmation for %s",
                context.owner_key,
            )
            return self._device_power_clarification_text(language)
        succeeded, failures = await self._async_execute_device_power(
            pending.action,
            pending.targets,
            service_context,
            language=language,
        )
        return self._append_ai_attempt_summary(
            self._device_power_result_text(
                pending.action,
                succeeded,
                failures,
                language=language,
            ),
            pending.attempted_agents,
            language=language,
            zalo=True,
        )

    async def _async_home_assistant_conversation_from_zalo(
        self,
        context: ZaloWebhookContext,
        service_context: Context | None,
    ) -> str:
        """Send a Zalo command through HA Conversation with AI failover."""
        if device_power_request_hint(context.text):
            return await self._async_device_power_from_zalo(
                context, service_context
            )

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
                    return await self._async_voice_response(
                        user_input, reply, ai_generated=True
                    )

                if not error_code and reply:
                    reply = self._append_ai_attempt_summary(
                        reply,
                        attempted_agents,
                        language=language,
                        zalo=False,
                    )
                    return await self._async_voice_response(
                        user_input, reply, ai_generated=True
                    )

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
        return await self._async_voice_response(
                        user_input, reply, ai_generated=True
                    )

    def _all_calendar_states(self) -> list[Any]:
        """Return available calendar entities allowed by Calendar settings."""
        configured = self.calendar_configured_entity_ids
        selected = set(configured) if configured is not None else None
        return sorted(
            (
                state
                for state in self.hass.states.async_all("calendar")
                if state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)
                and (selected is None or state.entity_id in selected)
            ),
            key=lambda state: (
                str(state.name or state.entity_id).casefold(),
                state.entity_id,
            ),
        )

    @staticmethod
    def _calendar_event_in_window(
        event: CalendarDisplayEvent, window: CalendarWindow
    ) -> bool:
        """Return whether an event overlaps the configured future window."""
        if event.start >= window.end:
            return False
        if event.end is not None:
            return event.end > window.start
        return event.start >= window.start

    @staticmethod
    def _calendar_event_key(
        event: CalendarDisplayEvent,
    ) -> tuple[str, datetime, datetime | None, str, str, str]:
        """Return a stable de-duplication key for normalized events."""
        return (
            event.calendar_entity_id,
            event.start,
            event.end,
            event.summary.casefold(),
            event.uid,
            event.recurrence_id,
        )

    async def async_refresh_calendar_events(self) -> None:
        """Refresh the upcoming-event cache used by the sensor and alerts."""
        async with self._calendar_refresh_lock:
            now = dt_util.now()
            window = CalendarWindow(
                start=now,
                end=now + timedelta(days=self.calendar_lookahead_days),
                label=f"trong {self.calendar_lookahead_days} ngày tới",
            )
            events: list[CalendarDisplayEvent] = []
            failed_calendars: list[str] = []
            for state in self._all_calendar_states():
                try:
                    events.extend(
                        await self._async_calendar_events_for_state(
                            state, window, None
                        )
                    )
                except Exception:  # noqa: BLE001 - keep other calendars working
                    failed_calendars.append(str(state.name or state.entity_id))
                    _LOGGER.exception(
                        "Failed refreshing calendar sensor from %s",
                        state.entity_id,
                    )

            unique: dict[
                tuple[str, datetime, datetime | None, str, str, str],
                CalendarDisplayEvent,
            ] = {}
            for event in events:
                event_start = event.start
                if event_start.tzinfo is None:
                    event_start = event_start.replace(tzinfo=now.tzinfo)
                event_end = event.end
                if event_end is not None and event_end.tzinfo is None:
                    event_end = event_end.replace(tzinfo=now.tzinfo)
                normalized = replace(
                    event,
                    start=dt_util.as_local(event_start),
                    end=dt_util.as_local(event_end) if event_end else None,
                )
                if not self._calendar_event_in_window(normalized, window):
                    continue
                if calendar_event_should_be_skipped(normalized):
                    continue
                normalized = replace(
                    normalized,
                    summary=calendar_event_display_summary(normalized),
                )
                unique[self._calendar_event_key(normalized)] = normalized

            self._calendar_events = sorted(
                unique.values(),
                key=lambda event: (
                    event.start,
                    event.calendar_name.casefold(),
                    event.summary.casefold(),
                ),
            )
            self._calendar_window_start = window.start
            self._calendar_window_end = window.end
            self._calendar_last_update = dt_util.now()
            self._calendar_refresh_error = (
                "Không đọc được: " + ", ".join(failed_calendars)
                if failed_calendars
                else None
            )
            self._notify_update()

    async def _async_calendar_refresh_interval(self, _now: datetime) -> bool:
        """Refresh the calendar sensor and report whether the cycle completed."""
        try:
            await self.async_refresh_calendar_events()
            return True
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 - keep future refreshes alive
            self._calendar_refresh_error = str(err) or err.__class__.__name__
            self._calendar_last_update = dt_util.now()
            self._notify_update()
            _LOGGER.exception("Unexpected calendar sensor refresh failure")
            return False

    @callback
    def _start_calendar_monitoring(self) -> None:
        """Start calendar refresh and daily notification scheduling."""
        if self._unsub_calendar_refresh_interval is None:
            self._unsub_calendar_refresh_interval = async_track_time_interval(
                self.hass,
                self._async_calendar_refresh_interval,
                timedelta(minutes=CALENDAR_REFRESH_INTERVAL_MINUTES),
            )
        if (
            self._calendar_refresh_task is None
            or self._calendar_refresh_task.done()
        ):
            task = self.hass.async_create_task(
                self._async_calendar_refresh_interval(dt_util.now())
            )
            self._calendar_refresh_task = task
            task.add_done_callback(self._calendar_refresh_task_finished)
        self._schedule_calendar_notification()

    @callback
    def _calendar_refresh_task_finished(
        self, task: asyncio.Task[Any]
    ) -> None:
        """Release the tracked startup calendar refresh task."""
        if self._calendar_refresh_task is task:
            self._calendar_refresh_task = None
        if task.cancelled():
            return
        try:
            task.exception()
        except asyncio.CancelledError:
            return

    @callback
    def _schedule_calendar_notification(self) -> None:
        """Register a reliable recurring local-time calendar notification."""
        if self._unsub_calendar_notification_timer is not None:
            self._unsub_calendar_notification_timer()
            self._unsub_calendar_notification_timer = None
        if not self.calendar_notification_enabled:
            return

        configured_time = self.calendar_notification_time
        self._unsub_calendar_notification_timer = async_track_time_change(
            self.hass,
            self._async_calendar_notification_due,
            hour=configured_time.hour,
            minute=configured_time.minute,
            second=configured_time.second,
        )
        _LOGGER.debug(
            "Calendar notification scheduled daily at %s",
            configured_time.strftime("%H:%M:%S"),
        )

    async def _async_calendar_notification_due(self, _now: datetime) -> None:
        """Refresh calendars and send the daily summary when events exist."""
        if not self.calendar_notification_enabled:
            return
        refresh_completed = await self._async_calendar_refresh_interval(
            dt_util.now()
        )
        if not refresh_completed:
            self._calendar_last_notification_at = dt_util.now()
            self._calendar_last_notification_result = (
                "Không gửi vì làm mới lịch thất bại"
            )
            self._calendar_last_notification_error = self._calendar_refresh_error
            self._notify_update()
            return
        if self.calendar_event_count <= 0:
            self._calendar_last_notification_at = dt_util.now()
            self._calendar_last_notification_result = (
                "Không gửi vì không có sự kiện phù hợp"
            )
            self._calendar_last_notification_error = None
            self._notify_update()
            return

        # A failure from one calendar must not suppress valid events fetched
        # from the remaining selected calendars. The partial refresh error stays
        # visible in the sensor attributes for diagnostics.
        await self._async_send_calendar_notifications()

    @staticmethod
    def _calendar_remaining_text(days: int) -> str:
        """Return a natural Vietnamese remaining-days label."""
        if days <= 0:
            return "Hôm nay"
        if days == 1:
            return "1 ngày"
        return f"{days} ngày"

    def _format_calendar_notification(self, *, markdown: bool) -> str:
        """Format the current event cache for Mobile App or Zalo."""
        def label(value: str) -> str:
            return f"**{value}**" if markdown else value

        lines = [
            (
                f"📅 {label(f'{self.calendar_event_count} sự kiện sắp diễn ra')} "
                f"trong {label(f'{self.calendar_lookahead_days} ngày tới')}"
            )
        ]
        grouped: dict[str, list[CalendarDisplayEvent]] = {}
        for event in self._calendar_events:
            grouped.setdefault(event.calendar_name or "Lịch không tên", []).append(
                event
            )

        item_index = 0
        for calendar_name in sorted(grouped, key=str.casefold):
            lines.append("")
            lines.append(f"🗓️ {label(calendar_name)}")
            for event in grouped[calendar_name]:
                item_index += 1
                summary = event.summary.strip() or "Sự kiện không tên"
                lines.append(f"{item_index}. 📌 {label('Nội dung:')} {summary}")
                lines.append(
                    f"   🕒 {label('Thời gian:')} "
                    f"{self._calendar_event_time_text(event)}"
                )
                lines.append(
                    f"   ⏳ {label('Còn:')} "
                    f"{self._calendar_remaining_text(self._calendar_days_remaining(event))}"
                )
                if event.location:
                    lines.append(f"   📍 {label('Địa điểm:')} {event.location}")
                if (
                    event.description
                    and normalize_text(event.description)
                    != normalize_text(summary)
                ):
                    lines.append(f"   📝 {label('Chi tiết:')} {event.description}")
        return "\n".join(lines)

    async def _async_send_calendar_mobile_notification(
        self, message: str
    ) -> tuple[int, list[str]]:
        """Send the daily calendar summary to fixed Mobile App devices."""
        device_ids = self.calendar_notification_mobile_device_ids
        if not device_ids:
            return 0, []
        services = self._notification_services_for_device_ids(device_ids)
        errors: list[str] = []
        if not services:
            errors.append(
                "Không tìm thấy notify service cho Mobile App đã chọn"
            )
            return 0, errors

        sent_count = 0
        for service in services:
            try:
                await self.hass.services.async_call(
                    "notify",
                    service,
                    {
                        "title": "📅 Sự kiện sắp diễn ra",
                        "message": message,
                        "data": {
                            "conversational_assistant_entry_id": self.entry.entry_id,
                            "calendar_event_count": self.calendar_event_count,
                            "calendar_lookahead_days": self.calendar_lookahead_days,
                        },
                    },
                    blocking=True,
                )
                sent_count += 1
            except Exception as err:  # noqa: BLE001 - keep other devices working
                errors.append(
                    f"notify.{service}: {str(err) or err.__class__.__name__}"
                )
                _LOGGER.exception(
                    "Failed sending calendar summary via notify.%s", service
                )
        return sent_count, errors

    def _calendar_notification_zalo_targets(self) -> list[dict[str, Any]]:
        """Resolve fixed calendar Zalo IDs against current enabled targets."""
        selected = set(self.calendar_notification_zalo_target_ids)
        if not selected:
            return []
        return [
            target
            for target in self._configured_zalo_targets()
            if str(target.get(CONF_ZALO_TARGET_ID, "")) in selected
        ]

    async def _async_send_calendar_zalo_notification(
        self, message: str
    ) -> tuple[int, list[str]]:
        """Send the daily calendar summary to fixed Zalo destinations."""
        selected_ids = self.calendar_notification_zalo_target_ids
        if not selected_ids:
            return 0, []
        targets = self._calendar_notification_zalo_targets()
        errors: list[str] = []
        if not targets:
            errors.append(
                "Không tìm thấy nơi nhận Zalo đã chọn hoặc nơi nhận đang tắt"
            )
            return 0, errors
        if not self.hass.services.has_service(
            ZALO_DOMAIN, ZALO_SERVICE_SEND_MESSAGE
        ):
            message_error = (
                f"Service {ZALO_DOMAIN}.{ZALO_SERVICE_SEND_MESSAGE} không khả dụng"
            )
            _LOGGER.error(message_error)
            return 0, [message_error]

        message = self._zalo_emphasize_important_text(message)
        sent_count = 0
        for target in targets:
            thread_id = str(target.get(CONF_ZALO_THREAD_ID, "") or "").strip()
            account_selection = str(
                target.get(CONF_ZALO_ACCOUNT_SELECTION, "") or ""
            ).strip()
            zalo_type = str(
                target.get(CONF_ZALO_TYPE, DEFAULT_ZALO_TYPE)
            ).strip()
            if not thread_id or not account_selection:
                errors.append("Nơi nhận Zalo thiếu thread_id hoặc tài khoản gửi")
                continue
            try:
                await self._async_send_zalo_typing_to_target(
                    thread_id, account_selection
                )
                await self.hass.services.async_call(
                    ZALO_DOMAIN,
                    ZALO_SERVICE_SEND_MESSAGE,
                    {
                        "type": zalo_type,
                        "ttl": 0,
                        "message": message,
                        "thread_id": thread_id,
                        "account_selection": account_selection,
                    },
                    blocking=True,
                )
                sent_count += 1
            except Exception as err:  # noqa: BLE001 - keep other targets working
                errors.append(
                    f"Zalo {thread_id}: {str(err) or err.__class__.__name__}"
                )
                _LOGGER.exception(
                    "Failed sending calendar summary to Zalo thread %s",
                    thread_id,
                )
        return sent_count, errors

    async def _async_send_calendar_notifications(self) -> None:
        """Send one refreshed calendar summary to all fixed destinations."""
        mobile_sent, mobile_errors = (
            await self._async_send_calendar_mobile_notification(
                self._format_calendar_notification(markdown=False)
            )
        )
        zalo_sent, zalo_errors = (
            await self._async_send_calendar_zalo_notification(
                self._format_calendar_notification(markdown=True)
            )
        )
        requested_mobile = len(self.calendar_notification_mobile_device_ids)
        requested_zalo = len(self.calendar_notification_zalo_target_ids)
        self._calendar_last_notification_at = dt_util.now()
        self._calendar_last_notification_result = (
            f"Mobile: {mobile_sent}/{requested_mobile}; "
            f"Zalo: {zalo_sent}/{requested_zalo}"
        )
        all_errors = [*mobile_errors, *zalo_errors]
        if requested_mobile == 0 and requested_zalo == 0:
            all_errors.append("Chưa chọn Mobile App hoặc Zalo nhận thông báo")
        self._calendar_last_notification_error = (
            "; ".join(all_errors) if all_errors else None
        )
        self._notify_update()

        if mobile_sent == 0 and zalo_sent == 0:
            _LOGGER.warning(
                "Calendar notification had %s event(s) but was not delivered: %s",
                self.calendar_event_count,
                self._calendar_last_notification_error or "unknown reason",
            )

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

    def _calendar_entity(self, entity_id: str) -> Any | None:
        """Return the loaded CalendarEntity behind an entity ID."""
        component = self.hass.data.get(CALENDAR_DATA_COMPONENT)
        if component is None:
            return None
        try:
            return component.get_entity(entity_id)
        except Exception:  # noqa: BLE001 - internal API varies by HA release
            _LOGGER.exception("Failed resolving calendar entity %s", entity_id)
            return None

    async def _async_calendar_events_for_state(
        self,
        state: Any,
        window: CalendarWindow,
        service_context: Context | None,
    ) -> list[CalendarDisplayEvent]:
        """Fetch events, preserving UID data needed for safe mutations."""
        calendar_name = str(state.name or state.entity_id)
        try:
            supported_features = int(
                state.attributes.get(ATTR_SUPPORTED_FEATURES, 0) or 0
            )
        except (TypeError, ValueError):
            supported_features = 0

        entity = self._calendar_entity(state.entity_id)
        if entity is not None and hasattr(entity, "async_get_events"):
            try:
                raw_events = await entity.async_get_events(
                    self.hass, window.start, window.end
                )
                payload = []
                for raw_event in raw_events:
                    if hasattr(raw_event, "as_dict"):
                        item = raw_event.as_dict()
                    elif hasattr(raw_event, "__dict__"):
                        item = dict(raw_event.__dict__)
                    else:
                        continue
                    if isinstance(item, dict):
                        payload.append(item)
                events = extract_calendar_events(
                    payload,
                    state.entity_id,
                    calendar_name,
                    supported_features=supported_features,
                )
                if events:
                    return events
            except Exception:  # noqa: BLE001 - use service fallback below
                _LOGGER.exception(
                    "Direct calendar event fetch failed for %s",
                    state.entity_id,
                )

        if self.hass.services.has_service("calendar", "get_events"):
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
                events = extract_calendar_events(
                    response,
                    state.entity_id,
                    calendar_name,
                    supported_features=supported_features,
                )
                if events:
                    return events
            except Exception:  # noqa: BLE001 - state fallback below
                _LOGGER.exception(
                    "Failed reading events from %s", state.entity_id
                )

        fallback = event_from_calendar_state(
            dict(state.attributes), state.entity_id, calendar_name
        )
        return [fallback] if fallback is not None else []

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
                + timedelta(seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS),
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
                seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
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
                seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
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
        """Read exposed calendars and retain exact mutable events for follow-up."""
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
            heading = (
                "🕒 **Mốc thời gian chưa hợp lệ, đã qua hoặc chưa đủ rõ.**"
                if has_time_reference
                else "🕒 **Bạn chưa nêu mốc thời gian cụ thể để tra lịch.**"
            )
            message = (
                f"{heading}\n\n"
                "Hãy thêm mốc như **hôm nay**, **ngày mai**, **ngày kia**, "
                "**2 hôm nữa**, **15 ngày nữa**, **75 ngày nữa**, "
                "**115 ngày nữa**, **1 tuần nữa**, **1 tháng nữa** hoặc "
                "một ngày cụ thể như **15/08/2026**.\n\n"
                "Ví dụ: **sự kiện 115 ngày nữa**."
            )
            return self._append_ai_attempt_summary(
                message, attempted_agents,
                language=_request_language(context.text), zalo=True
            )

        events: list[CalendarDisplayEvent] = []
        for state in states:
            events.extend(
                await self._async_calendar_events_for_state(
                    state, window, service_context
                )
            )

        displayed, _skipped = calendar_events_for_display(events, window)
        reply = format_calendar_events(events, window, now)
        manageable = [
            event for event in displayed
            if event.uid and (event.can_update or event.can_delete)
        ]
        if manageable:
            self._zalo_pending_calendar_managements[context.owner_key] = (
                PendingZaloCalendarManagement(
                    events=manageable,
                    expires_at=dt_util.now() + timedelta(
                        seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
                    ),
                    ai_attempted_agents=attempted_agents,
                )
            )
            reply += (
                "\n\n🛠️ **Bạn có muốn quản lý sự kiện vừa tra cứu không?**\n"
                "Trả lời **Sửa**, **Xóa** hoặc **Bỏ qua**."
            )
        else:
            self._zalo_pending_calendar_managements.pop(context.owner_key, None)

        return self._append_ai_attempt_summary(
            reply, attempted_agents,
            language=_request_language(context.text), zalo=True
        )

    @staticmethod
    def _calendar_management_event_prompt(
        events: list[CalendarDisplayEvent], action: str, *, invalid: bool = False
    ) -> str:
        """List only events that support the selected safe mutation."""
        title = "sửa" if action == "update" else "xóa"
        lines = []
        if invalid:
            lines.append("⚠️ **Lựa chọn chưa hợp lệ.**\n")
        lines.append(f"Chọn **sự kiện muốn {title}** bằng số:")
        for index, event in enumerate(events, 1):
            when = dt_util.as_local(event.start)
            time_text = when.strftime("%d/%m/%Y")
            if not event.all_day:
                time_text += when.strftime(" lúc %H:%M")
            lines.append(
                f"{index}. **{event.summary}** — {time_text} "
                f"({event.calendar_name})"
            )
        lines.append("\nTrả lời **Hủy** để dừng.")
        return "\n".join(lines)

    @staticmethod
    def _calendar_event_update_payload(
        request: CalendarCreateRequest, event: CalendarDisplayEvent
    ) -> dict[str, Any]:
        """Build RFC5545-compatible event fields for CalendarEntity update."""
        payload: dict[str, Any] = {
            "summary": request.summary,
            "description": request.description,
            "location": request.location,
        }
        if request.all_day:
            payload["start"] = dt_util.as_local(request.start).date()
            payload["end"] = dt_util.as_local(request.end).date()
        else:
            payload["start"] = request.start
            payload["end"] = request.end
        if event.rrule:
            payload["rrule"] = event.rrule
        return payload

    async def _async_ai_calendar_update_request(
        self,
        text: str,
        event: CalendarDisplayEvent,
        context: ZaloWebhookContext,
        service_context: Context | None,
    ) -> tuple[CalendarCreateRequest | None, list[str]]:
        """Use configured AI to merge natural edits with the current event."""
        if self.zalo_conversation_agent_id == HOME_ASSISTANT_AGENT:
            return None, []
        current_start = dt_util.as_local(event.start)
        current_end = dt_util.as_local(event.end) if event.end else current_start + timedelta(hours=1)
        prompt = (
            "You are a strict calendar event update parser. Return one JSON "
            "object only. Merge the user's requested changes into the current "
            "event and preserve every field not explicitly changed. Current "
            f"local datetime: {dt_util.as_local(dt_util.now()).isoformat()}. "
            f"Current event: summary={event.summary!r}, all_day={event.all_day}, "
            f"start={current_start.isoformat()}, end={current_end.isoformat()}, "
            f"description={event.description!r}, location={event.location!r}. "
            f"User edit: {text!r}. Fields: summary, all_day, start_date and "
            "end_date for all-day, or start_date_time and end_date_time for "
            "timed events, description, location. End is exclusive. Never "
            "invent unrelated details. If the request is ambiguous return "
            "{\"error\":\"missing_information\"}."
        )
        attempted: list[str] = []
        candidates = [c for c in self._conversation_agent_candidates(
            self.zalo_conversation_agent_id
        ) if c[0] != HOME_ASSISTANT_AGENT]
        for agent_id, agent_name in candidates:
            attempted.append(agent_name)
            try:
                async with asyncio.timeout(min(30, ZALO_SEARCH_TIMEOUT_SECONDS)):
                    result = await async_converse(
                        hass=self.hass, text=prompt, conversation_id=None,
                        context=service_context or Context(),
                        language=_request_language(text), agent_id=agent_id,
                    )
            except Exception:  # noqa: BLE001 - fail over and retain safe flow
                _LOGGER.exception("Calendar update parser %s failed", agent_id)
                continue
            if self._conversation_result_error_code(result):
                continue
            payload = self._calendar_json_object(
                self._conversation_reply_text(result)
            )
            if payload and not payload.get("error"):
                parsed = calendar_create_request_from_ai_payload(
                    payload, dt_util.now()
                )
                if parsed is not None:
                    return parsed, attempted
        return None, attempted

    async def _async_zalo_pending_calendar_management_reply(
        self,
        context: ZaloWebhookContext,
        pending: PendingZaloCalendarManagement,
        service_context: Context | None,
    ) -> str:
        """Safely select, confirm, update, or delete an exact calendar event."""
        text = normalize_text(context.text)
        if self._is_cancel_pending_text(context.text) or text in {
            "bo qua", "khong", "no", "skip"
        }:
            self._zalo_pending_calendar_managements.pop(context.owner_key, None)
            return "Đã đóng phần quản lý sự kiện."

        pending.expires_at = dt_util.now() + timedelta(
            seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
        )
        if pending.phase == "action":
            if any(word in text for word in ("sua", "chinh sua", "edit", "update")):
                candidates = [event for event in pending.events if event.can_update]
                if not candidates:
                    return "Lịch của các sự kiện này không hỗ trợ sửa."
                pending.events = candidates
                pending.phase = "select_update"
                return self._calendar_management_event_prompt(candidates, "update")
            if any(word in text for word in ("xoa", "delete", "remove")):
                candidates = [event for event in pending.events if event.can_delete]
                if not candidates:
                    return "Lịch của các sự kiện này không hỗ trợ xóa."
                pending.events = candidates
                pending.phase = "select_delete"
                return self._calendar_management_event_prompt(candidates, "delete")
            return (
                "Hãy trả lời **Sửa**, **Xóa** hoặc **Bỏ qua** để tôi thao tác "
                "đúng sự kiện."
            )

        if pending.phase in {"select_update", "select_delete"}:
            indexes = parse_target_selection(
                context.text, [event.summary for event in pending.events]
            )
            if len(indexes) != 1:
                action = "update" if pending.phase == "select_update" else "delete"
                return self._calendar_management_event_prompt(
                    pending.events, action, invalid=True
                )
            event = pending.events[indexes[0]]
            pending.selected_event = event
            if pending.phase == "select_delete":
                pending.phase = "confirm_delete"
                return (
                    f"⚠️ **Xác nhận xóa sự kiện**\n"
                    f"**Nội dung:** {event.summary}\n"
                    f"**Lịch:** {event.calendar_name}\n\n"
                    "Trả lời **Xác nhận xóa** để thực hiện hoặc **Hủy**."
                )
            pending.phase = "edit_details"
            return (
                f"✏️ **Đang sửa:** {event.summary}\n"
                "Hãy nhập nội dung muốn thay đổi bằng ngôn ngữ tự nhiên. "
                "Ví dụ: **đổi tên thành Họp dự án và chuyển sang 19h ngày mai**. "
                "Thông tin không nhắc tới sẽ được giữ nguyên."
            )

        event = pending.selected_event
        if event is None or not event.uid:
            self._zalo_pending_calendar_managements.pop(context.owner_key, None)
            return "Không còn đủ dữ liệu định danh sự kiện. Hãy tra cứu lại lịch."
        entity = self._calendar_entity(event.calendar_entity_id)
        if entity is None:
            self._zalo_pending_calendar_managements.pop(context.owner_key, None)
            return "Không tìm thấy calendar entity đang quản lý sự kiện này."

        if pending.phase == "confirm_delete":
            if text not in {"xac nhan xoa", "dong y xoa", "yes delete", "confirm delete"}:
                return "Hãy trả lời **Xác nhận xóa** hoặc **Hủy**."
            try:
                await entity.async_delete_event(
                    event.uid, event.recurrence_id or None, None
                )
                if hasattr(entity, "async_update_event_listeners"):
                    listener_result = entity.async_update_event_listeners()
                    if asyncio.iscoroutine(listener_result):
                        await listener_result
            except Exception:  # noqa: BLE001 - never claim success on failure
                _LOGGER.exception("Failed deleting calendar event %s", event.uid)
                return "⚠️ **Xóa sự kiện thất bại.** Hãy kiểm tra quyền của lịch."
            self._zalo_pending_calendar_managements.pop(context.owner_key, None)
            return (
                "✅ **Đã xóa sự kiện**\n"
                f"**Nội dung:** {event.summary}\n"
                f"**Lịch:** {event.calendar_name}"
            )

        if pending.phase == "edit_details":
            request, attempted = await self._async_ai_calendar_update_request(
                context.text, event, context, service_context
            )
            if request is None:
                try:
                    request = self._deterministic_calendar_create_request(
                        "tạo sự kiện " + context.text, dt_util.now()
                    )
                except ReminderParseError:
                    return self._append_ai_attempt_summary(
                        "Tôi chưa hiểu đủ thay đổi. Hãy nêu **nội dung mới** và "
                        "**mốc thời gian mới** rõ hơn, hoặc trả lời **Hủy**.",
                        attempted, language=_request_language(context.text),
                        zalo=True,
                    )
            try:
                await entity.async_update_event(
                    event.uid,
                    self._calendar_event_update_payload(request, event),
                    event.recurrence_id or None,
                    None,
                )
                if hasattr(entity, "async_update_event_listeners"):
                    listener_result = entity.async_update_event_listeners()
                    if asyncio.iscoroutine(listener_result):
                        await listener_result
            except Exception:  # noqa: BLE001 - preserve exact failure state
                _LOGGER.exception("Failed updating calendar event %s", event.uid)
                return "⚠️ **Sửa sự kiện thất bại.** Hãy kiểm tra quyền của lịch."
            self._zalo_pending_calendar_managements.pop(context.owner_key, None)
            return self._append_ai_attempt_summary(
                "✅ **Đã sửa sự kiện thành công**\n"
                f"**Lịch:** {event.calendar_name}\n"
                f"{format_calendar_create_request(request)}",
                attempted, language=_request_language(context.text), zalo=True,
            )

        self._zalo_pending_calendar_managements.pop(context.owner_key, None)
        return "Phiên quản lý sự kiện không còn hợp lệ. Hãy tra cứu lại lịch."

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
        if request_kind == "camera_analysis":
            return await self._async_camera_analysis_from_zalo(context)
        if request_kind == "camera":
            return await self._async_camera_from_zalo(context)
        if request_kind == "calendar":
            return await self._async_calendar_from_zalo(
                context, service_context
            )
        if request_kind == "weather":
            return await self._async_weather_from_zalo(
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
        first_chat_turn = chat_start_request(context.text)
        if first_chat_turn is not None:
            self._clear_zalo_pending_for_owner(context.owner_key)
            self._start_zalo_chat(context)
            if not first_chat_turn:
                return self._zalo_chat_welcome_text()
            context = replace(context, text=first_chat_turn)
            return await self._async_chat_from_zalo(
                context, service_context
            )

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
        if (
            context.owner_key in self._zalo_chat_sessions
            and not self._zalo_chat_yields_to_home_assistant(
                context.text, explicit_ha_kind
            )
        ):
            explicit_ha_kind = None
        pending_note = self._zalo_pending_note(context.owner_key)
        pending_creation = self._zalo_pending_creation(context.owner_key)
        pending_deletion = self._zalo_pending_deletion(context.owner_key)
        pending_camera = self._zalo_pending_camera(context.owner_key)
        pending_device_power = self._zalo_pending_device_power(
            context.owner_key
        )
        pending_calendar = self._zalo_pending_calendar_event(context.owner_key)
        pending_calendar_management = self._zalo_pending_calendar_management(
            context.owner_key
        )
        if (
            pending_calendar_management is not None
            and command is None
            and explicit_ha_kind is None
        ):
            return await self._async_zalo_pending_calendar_management_reply(
                context, pending_calendar_management, service_context
            )
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
            and explicit_ha_kind in {None, "camera", "camera_analysis"}
        ):
            return await self._async_zalo_pending_camera_reply(
                context, pending_camera, service_context
            )
        if (
            pending_device_power is not None
            and command is None
            and explicit_ha_kind is None
        ):
            return await self._async_zalo_pending_device_power_reply(
                context, pending_device_power, service_context
            )
        if pending_device_power is not None and (
            command is not None or explicit_ha_kind is not None
        ):
            # A new explicit request replaces the older unconfirmed device
            # action. This prevents a later generic "Đồng ý" from executing a
            # stale command after the user has already moved on.
            self._zalo_pending_device_powers.pop(context.owner_key, None)
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
        if command == ACTION_WEATHER:
            self._clear_zalo_pending_for_owner(context.owner_key)
            return await self._async_weather_from_zalo(
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
        if command == ACTION_CAMERA_ANALYSIS:
            self._clear_zalo_pending_for_owner(context.owner_key)
            return await self._async_camera_analysis_from_zalo(context)
        if command == ACTION_CAMERA:
            self._clear_zalo_pending_for_owner(context.owner_key)
            return await self._async_camera_from_zalo(context)

        if explicit_ha_kind is not None:
            return await self._async_process_home_assistant_from_zalo(
                context, explicit_ha_kind, service_context
            )

        if context.owner_key in self._zalo_chat_sessions:
            return await self._async_chat_from_zalo(
                context, service_context
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

    def _zalo_long_running_action(
        self, context: ZaloWebhookContext
    ) -> str | None:
        """Return a slow action only when the request has usable content."""
        text = context.text
        pending_camera = self._zalo_pending_camera(context.owner_key)
        if pending_camera is not None and pending_camera.mode == "analysis":
            selected = parse_target_selection(
                text,
                [camera.display_name for camera in pending_camera.cameras],
            )
            if selected:
                return ACTION_CAMERA_ANALYSIS

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
        if command == ACTION_WEATHER:
            query = weather_search_request(effective_text)
            return ACTION_WEATHER if query and query.strip() else None
        if command == ACTION_IMAGE_GENERATION:
            instructions = _image_generation_request(effective_text)
            return (
                ACTION_IMAGE_GENERATION
                if instructions and instructions.strip()
                else None
            )

        first_chat_turn = chat_start_request(effective_text)
        if first_chat_turn is not None:
            return ACTION_CHAT if first_chat_turn.strip() else None

        explicit_ha_kind = (
            explicit_home_assistant_request_kind(effective_text)
            if self.zalo_home_assistant_enabled
            else None
        )
        if (
            context.owner_key in self._zalo_chat_sessions
            and not self._zalo_chat_yields_to_home_assistant(
                effective_text, explicit_ha_kind
            )
        ):
            explicit_ha_kind = None
        if (
            self.zalo_home_assistant_enabled
            and explicit_ha_kind == "calendar"
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

        if (
            context.owner_key in self._zalo_chat_sessions
            and command is None
            and explicit_ha_kind is None
            and not self._zalo_owner_has_pending_confirmation(
                context.owner_key
            )
        ):
            return ACTION_CHAT
        return None

    @staticmethod
    def _zalo_processing_text(language: str) -> str:
        """Return the immediate acknowledgement for a slow request."""
        if language == "en":
            return "⏳ **Processing your request. Please wait for the response.**"
        return "⏳ **Đang xử lý thông tin yêu cầu. Hãy chờ phản hồi.**"

    @staticmethod
    def _zalo_timeout_text(action: str, language: str) -> str:
        """Return a final timeout message for a stalled slow request."""
        if language == "en":
            feature = (
                "image generation"
                if action == ACTION_IMAGE_GENERATION
                else "camera analysis"
                if action == ACTION_CAMERA_ANALYSIS
                else "calendar analysis"
                if action == ACTION_CALENDAR
                else "weather lookup"
                if action == ACTION_WEATHER
                else "chat response"
                if action == ACTION_CHAT
                else "search"
            )
            return (
                f"⌛ **The {feature} request took too long**\n\n"
                "The AI service did not respond in time. Please try again."
            )
        feature = (
            "tạo ảnh"
            if action == ACTION_IMAGE_GENERATION
            else "phân tích camera"
            if action == ACTION_CAMERA_ANALYSIS
            else "phân tích lịch"
            if action == ACTION_CALENDAR
            else "tra cứu thời tiết"
            if action == ACTION_WEATHER
            else "trò chuyện"
            if action == ACTION_CHAT
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
            else CAMERA_ANALYSIS_TIMEOUT_SECONDS
            if action == ACTION_CAMERA_ANALYSIS
            else ZALO_SEARCH_TIMEOUT_SECONDS
        )
        candidate_count = self._ai_long_running_candidate_count(action)
        camera_count = 1
        if action == ACTION_CAMERA_ANALYSIS:
            pending_camera = self._zalo_pending_camera(context.owner_key)
            if pending_camera is not None:
                selected = parse_target_selection(
                    context.text,
                    [camera.display_name for camera in pending_camera.cameras],
                )
                camera_count = max(1, len(selected))
        # Each candidate and selected camera receives a complete timeout window.
        # The outer timeout is only a final safety net for delivery/cleanup.
        timeout_seconds = (
            per_agent_timeout_seconds * candidate_count * camera_count + 120
        )
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
                reply = await self._async_prepare_zalo_reply(
                    context,
                    reply,
                    service_context,
                    ai_generated=action in {
                        ACTION_SEARCH,
                        ACTION_WEATHER,
                        ACTION_CHAT,
                    },
                )
                reply = self._append_zalo_confirmation_timeout_notice(
                    context, reply
                )
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
            if action != ACTION_CHAT:
                self._resume_zalo_chat_after_request(context)
            self._sync_pending_followup_trigger()
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

        if (
            context.owner_key in self._zalo_chat_sessions
            and chat_start_request(context.text) is None
        ):
            self._touch_zalo_chat_activity(context)

        long_action = self._zalo_long_running_action(context)
        if long_action is not None:
            if long_action != ACTION_CHAT:
                self._pause_existing_zalo_chat_for_request(context)
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
        self._pause_existing_zalo_chat_for_request(context)
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

            reply = await self._async_prepare_zalo_reply(
                context, reply, service_context
            )
            reply = self._append_zalo_confirmation_timeout_notice(
                context, reply
            )
            reply_sent = await self._async_send_zalo_webhook_reply(
                context, reply
            )
            return {
                "ok": True,
                "handled": True,
                "reply_sent": reply_sent,
            }
        finally:
            self._resume_zalo_chat_after_request(context)
            self._sync_pending_followup_trigger()
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
                        "message": self._zalo_emphasize_important_text(
                            "⏰ **Nhắc nhở**\n"
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
            *self._zalo_pending_notes.values(),
            *self._zalo_pending_creations.values(),
            *self._zalo_pending_deletions.values(),
            *self._zalo_pending_cameras.values(),
            *self._zalo_pending_device_powers.values(),
            *self._zalo_pending_calendar_events.values(),
            *self._zalo_pending_calendar_managements.values(),
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
        for owner_key, pending in list(self._zalo_pending_creations.items()):
            if pending.expires_at <= now:
                del self._zalo_pending_creations[owner_key]
        for owner_key, pending in list(self._zalo_pending_deletions.items()):
            if pending.expires_at <= now:
                del self._zalo_pending_deletions[owner_key]
        for owner_key, pending in list(self._zalo_pending_cameras.items()):
            if pending.expires_at <= now:
                del self._zalo_pending_cameras[owner_key]
        for owner_key, pending in list(
            self._zalo_pending_device_powers.items()
        ):
            if pending.expires_at <= now:
                del self._zalo_pending_device_powers[owner_key]
        for owner_key, pending in list(self._zalo_pending_calendar_events.items()):
            if pending.expires_at <= now:
                del self._zalo_pending_calendar_events[owner_key]
        for owner_key, pending in list(
            self._zalo_pending_calendar_managements.items()
        ):
            if pending.expires_at <= now:
                del self._zalo_pending_calendar_managements[owner_key]
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
            + timedelta(seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS),
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
            + timedelta(seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS),
        )
        self._pending_deletions[pending.pending_id] = pending
        self._sync_pending_followup_trigger()
        return pending

    def _set_pending_voice_camera(
        self,
        user_input: ConversationInput,
        cameras: list[CameraTarget],
        zalo_targets: list[dict[str, Any]],
        mode: str = "capture",
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
            + timedelta(seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS),
            mode=mode,
            analysis_items=[],
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
            "Bạn có thể trả lời **1 và 3**, **1 phẩy 3**, "
            "**chọn 1 và 3**, **chọn tất cả loa**, **chọn tất cả**, "
            "hoặc **bỏ yêu cầu vừa rồi**."
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
            "Hãy trả lời số cần xóa, ví dụ **1**, **1 và 3**, "
            "hoặc **tất cả**. Nói **bỏ yêu cầu vừa rồi** "
            "để **không xóa**."
        )

    async def _async_voice_response(
        self,
        user_input: ConversationInput,
        text: str,
        *,
        ai_generated: bool = False,
    ) -> str:
        """Return complete speech to Assist and optionally enrich deterministic text.

        Sentence-trigger callbacks become the ``speech`` field of the
        conversation response, so returning the real text keeps both the Assist
        chat transcript and pipeline TTS working for every feature.
        """
        response = str(text or "").strip()
        if not response:
            return response
        if ai_generated:
            return _assist_speech_text(response)
        language_code = str(getattr(user_input, "language", "vi") or "vi")
        language = (
            "en"
            if language_code.casefold().startswith("en")
            else _request_language(str(getattr(user_input, "text", "") or ""))
        )
        polished, attempted = await self._async_ai_polish_response(
            str(getattr(user_input, "text", "") or ""),
            response,
            language=language,
            zalo=False,
            service_context=getattr(user_input, "context", None),
        )
        return _assist_speech_text(
            self._append_ai_attempt_summary(
                polished,
                attempted,
                language=language,
                zalo=False,
            )
        )

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
        if weather_search_request(user_input.text) is not None:
            return await self._async_weather_from_voice(user_input, result)
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
        return await self._async_voice_response(
            user_input, reply, ai_generated=True
        )

    async def _async_weather_from_voice(
        self, user_input: ConversationInput, _result: RecognizeResult
    ) -> str:
        """Look up weather through the configured Internet AI Search agent."""
        self._clear_pending_for_source(self._source_keys(user_input))
        self._sync_pending_followup_trigger()
        query = weather_search_request(user_input.text)
        if query is None:
            return await self._async_home_assistant_conversation_from_voice(
                user_input, user_input.text
            )
        reply, _conversation_id = await self._async_ai_search(
            query,
            conversation_id=None,
            service_context=user_input.context,
            zalo=False,
            language_hint=_request_language(user_input.text),
            feature="weather",
        )
        return await self._async_voice_response(
            user_input, reply, ai_generated=True
        )

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

        if command.action == ACTION_CAMERA_ANALYSIS:
            return await self._async_camera_analysis_from_voice(
                user_input, result
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
            return await self._async_voice_response(
                user_input, reply, ai_generated=True
            )
        if command.action == ACTION_WEATHER:
            query = weather_search_request(transformed_text) or transformed_text
            reply, _conversation_id = await self._async_ai_search(
                query,
                conversation_id=None,
                service_context=user_input.context,
                zalo=False,
                language_hint=_request_language(request or user_input.text),
                feature="weather",
            )
            return await self._async_voice_response(
                user_input, reply, ai_generated=True
            )
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
        if weather_search_request(text) is not None:
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
                "analyze camera",
                "analyse camera",
                "check camera",
                "inspect camera",
                "phan tich cam",
                "phan tich camera",
                "kiem tra cam",
                "kiem tra camera",
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
            "never mind",
            "huy",
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
        if (
            camera_pending is None
            and creation is None
            and deletion is None
        ):
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
                if (
                    camera_pending.mode == "analysis"
                    and camera_pending.phase == "analysis_destination"
                ):
                    response = (
                        "Đã hoàn tất phân tích và không gửi ảnh, nội dung "
                        "phân tích lên Zalo."
                    )
                elif camera_pending.mode == "analysis":
                    response = "Đã hủy yêu cầu phân tích camera."
                else:
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
        """Select cameras, select Zalo destinations, then confirm capture."""
        if pending.mode == "analysis":
            return await self._async_confirm_camera_analysis_from_voice(
                user_input, result, pending
            )

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
                    seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
                )
                self._sync_pending_followup_trigger()
                return await self._async_voice_response(
                    user_input,
                    self._voice_camera_selection_prompt(
                        pending.cameras, invalid=True
                    ),
                )

            pending.selected_cameras = available
            current_targets = self._current_voice_camera_zalo_targets(pending)
            if not current_targets:
                self._pending_voice_cameras.pop(pending.pending_id, None)
                self._sync_pending_followup_trigger()
                return await self._async_voice_response(
                    user_input,
                    "Các Zalo destination đã bị xóa hoặc tắt. Hãy mở cấu "
                    "hình Conversational Assistant, thêm hoặc bật lại nơi "
                    "nhận, sau đó thực hiện lại yêu cầu.",
                )

            pending.zalo_targets = [dict(target) for target in current_targets]
            pending.phase = "destination"
            pending.expires_at = dt_util.now() + timedelta(
                seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
            )
            self._sync_pending_followup_trigger()
            response = self._voice_camera_destination_prompt(
                available, current_targets
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

        if pending.phase == "destination":
            current_targets = self._current_voice_camera_zalo_targets(pending)
            if not current_targets:
                self._pending_voice_cameras.pop(pending.pending_id, None)
                self._sync_pending_followup_trigger()
                return await self._async_voice_response(
                    user_input,
                    "Các Zalo destination đã bị xóa hoặc tắt trước khi chọn "
                    "nơi gửi. Hãy cấu hình lại rồi thực hiện lại yêu cầu.",
                )

            selection = self._selection_slot(user_input, result)
            target_names = [
                str(target.get(CONF_ZALO_TARGET_NAME, "")).strip()
                or str(target.get(CONF_ZALO_THREAD_ID, "")).strip()
                or "Zalo"
                for target in current_targets
            ]
            indexes = parse_target_selection(selection, target_names)
            if not indexes:
                pending.zalo_targets = [
                    dict(target) for target in current_targets
                ]
                pending.expires_at = dt_util.now() + timedelta(
                    seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
                )
                self._sync_pending_followup_trigger()
                return await self._async_voice_response(
                    user_input,
                    self._voice_camera_destination_prompt(
                        pending.selected_cameras,
                        current_targets,
                        invalid=True,
                    ),
                )

            selected_targets = [current_targets[index] for index in indexes]
            pending.zalo_targets = [
                dict(target) for target in selected_targets
            ]
            pending.phase = "confirmation"
            pending.expires_at = dt_util.now() + timedelta(
                seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
            )
            self._sync_pending_followup_trigger()
            return await self._async_voice_response(
                user_input,
                self._voice_camera_confirmation_prompt(
                    pending.selected_cameras,
                    selected_targets,
                ),
            )

        if pending.phase != "confirmation":
            self._pending_voice_cameras.pop(pending.pending_id, None)
            self._sync_pending_followup_trigger()
            return await self._async_voice_response(
                user_input,
                "Phiên chụp ảnh camera không còn hợp lệ. Hãy yêu cầu lại.",
            )

        if not self._is_voice_camera_confirmation(user_input.text):
            pending.expires_at = dt_util.now() + timedelta(
                seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
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

    async def _async_confirm_camera_analysis_from_voice(
        self,
        user_input: ConversationInput,
        result: RecognizeResult,
        pending: PendingVoiceCamera,
    ) -> str:
        """Analyze selected cameras, then optionally send results to Zalo."""
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
                    seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
                )
                self._sync_pending_followup_trigger()
                return await self._async_voice_response(
                    user_input,
                    self._voice_camera_analysis_selection_prompt(
                        pending.cameras, invalid=True
                    ),
                )

            pending.selected_cameras = available
            processing_seconds = (
                CAMERA_ANALYSIS_TIMEOUT_SECONDS
                * max(
                    1,
                    len(
                        self._ai_camera_agent_candidates(
                            self.ai_camera_task_entity_id
                        )
                    ),
                )
                * max(1, len(available))
                + 120
            )
            # Do not let the normal 120-second confirmation cleanup remove the
            # in-flight analysis. A fresh 120-second destination window is set
            # immediately after the results are ready.
            pending.expires_at = dt_util.now() + timedelta(
                seconds=processing_seconds
            )
            self._sync_pending_followup_trigger()
            owner_key = "voice-analysis:" + uuid.uuid5(
                uuid.NAMESPACE_URL,
                "|".join(sorted(pending.source_keys)),
            ).hex
            items, failures = await self._async_capture_and_analyze_cameras(
                owner_key,
                available,
                user_input.context,
            )
            if not items:
                self._pending_voice_cameras.pop(pending.pending_id, None)
                self._sync_pending_followup_trigger()
                details = "; ".join(failures)
                return await self._async_voice_response(
                    user_input,
                    "Không thể chụp và phân tích các camera đã chọn. "
                    + (details or "Hãy kiểm tra camera và AI Task agent."),
                )

            pending.analysis_items = items
            current_targets = self._configured_zalo_targets()
            pending.zalo_targets = [dict(target) for target in current_targets]
            analysis_text = self._camera_analysis_voice_text(items, failures)
            unavailable = [
                camera.display_name
                for camera in selected
                if not camera.available
            ]
            if unavailable:
                analysis_text += (
                    "\nĐã bỏ qua camera không khả dụng: "
                    + ", ".join(unavailable)
                    + "."
                )

            if not current_targets:
                self._pending_voice_cameras.pop(pending.pending_id, None)
                self._sync_pending_followup_trigger()
                analysis_text += (
                    "\nChưa có Zalo destination đang bật nên tôi không thể "
                    "gửi ảnh và nội dung phân tích lên Zalo."
                )
                return await self._async_voice_response(
                    user_input, analysis_text, ai_generated=True
                )

            pending.phase = "analysis_destination"
            pending.expires_at = dt_util.now() + timedelta(
                seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
            )
            self._sync_pending_followup_trigger()
            return await self._async_voice_response(
                user_input,
                analysis_text
                + "\n"
                + self._voice_camera_analysis_destination_prompt(
                    current_targets
                ),
                ai_generated=True,
            )

        if pending.phase != "analysis_destination":
            self._pending_voice_cameras.pop(pending.pending_id, None)
            self._sync_pending_followup_trigger()
            return await self._async_voice_response(
                user_input,
                "Phiên phân tích camera không còn hợp lệ. Hãy yêu cầu lại.",
            )

        current_targets = self._current_voice_camera_zalo_targets(pending)
        if not current_targets:
            self._pending_voice_cameras.pop(pending.pending_id, None)
            self._sync_pending_followup_trigger()
            return await self._async_voice_response(
                user_input,
                "Các Zalo destination đã bị xóa hoặc tắt trước khi gửi. "
                "Kết quả phân tích đã hoàn tất nhưng chưa gửi lên Zalo.",
            )

        selection = self._selection_slot(user_input, result)
        target_names = [
            str(target.get(CONF_ZALO_TARGET_NAME, "")).strip()
            or str(target.get(CONF_ZALO_THREAD_ID, "")).strip()
            or "Zalo"
            for target in current_targets
        ]
        indexes = parse_target_selection(selection, target_names)
        if not indexes:
            pending.zalo_targets = [dict(target) for target in current_targets]
            pending.expires_at = dt_util.now() + timedelta(
                seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
            )
            self._sync_pending_followup_trigger()
            return await self._async_voice_response(
                user_input,
                self._voice_camera_analysis_destination_prompt(
                    current_targets, invalid=True
                ),
            )

        selected_targets = [current_targets[index] for index in indexes]
        items = list(pending.analysis_items or [])
        self._pending_voice_cameras.pop(pending.pending_id, None)
        self._sync_pending_followup_trigger()
        if not items:
            return await self._async_voice_response(
                user_input,
                "Kết quả phân tích camera không còn trong phiên hiện tại. "
                "Hãy yêu cầu phân tích lại.",
            )

        sent_targets, send_failures = (
            await self._async_send_camera_analysis_to_configured_zalo(
                items,
                selected_targets,
                user_input.context,
            )
        )
        if not sent_targets:
            details = "; ".join(send_failures)
            response = (
                "Đã phân tích camera nhưng chưa gửi được lên Zalo. "
                + (details or "Hãy kiểm tra tích hợp zalo_bot.")
            )
        else:
            response = (
                f"Đã gửi ảnh và nội dung phân tích của {len(items)} camera "
                "lên Zalo đến "
                + ", ".join(sent_targets)
                + "."
            )
            if send_failures:
                response += (
                    " Một số mục không hoàn tất: "
                    + "; ".join(send_failures)
                    + "."
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
                seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
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
                seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
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
        if (
            camera is None
            and creation is None
            and deletion is None
        ):
            return await self._async_voice_response(
                user_input, "Không có yêu cầu nào đang chờ xác nhận."
            )
        if camera is not None:
            self._pending_voice_cameras.pop(camera.pending_id, None)
            if camera.mode == "analysis":
                response = "Đã hủy yêu cầu phân tích camera."
            else:
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
