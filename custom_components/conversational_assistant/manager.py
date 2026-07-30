"""Reminder manager for Conversational Assistant."""

from __future__ import annotations

import asyncio
import calendar
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from functools import partial
import logging
import os
import re
from time import monotonic
from typing import Any
import unicodedata
import uuid

from hassil.recognize import RecognizeResult

from homeassistant.components import persistent_notification
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
    ASSIST_SATELLITE_DOMAIN,
    ASSIST_SATELLITE_SERVICE_ANNOUNCE,
    CAMERA_SENTENCES,
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
    LIST_SENTENCES,
    MEDIA_PLAYER_DOMAIN,
    PENDING_FOLLOWUP_SENTENCES,
    PENDING_SELECTION_TIMEOUT_MINUTES,
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
    ACTION_LABELS,
    ACTION_NOTE_CREATE,
    ACTION_NOTE_DELETE,
    ACTION_NOTE_EDIT,
    ACTION_NOTE_LIST,
    ACTION_NOTE_VIEW,
    ACTION_REMINDER_CREATE,
    ACTION_REMINDER_DELETE,
    ACTION_REMINDER_LIST,
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
    calendar_matches_query,
    calendar_window_from_text,
    event_from_calendar_state,
    explicit_home_assistant_request_kind,
    extract_calendar_events,
    format_calendar_events,
)

_LOGGER = logging.getLogger(__name__)


_HELP_EXACT_PHRASES = frozenset(
    {
        "help",
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
    if not normalized:
        return False
    if normalized in _HELP_EXACT_PHRASES:
        return True

    mentions_subject = any(
        term in normalized
        for term in (
            "tich hop",
            "conversational assistant",
            "cac tinh nang",
            "tinh nang cua",
            "cac lenh ho tro",
        )
    )
    asks_for_guidance = any(
        term in normalized
        for term in (
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
        self._zalo_seen_message_ids: deque[str] = deque()
        self._zalo_seen_message_id_set: set[str] = set()
        self._zalo_ha_conversation_ids: dict[str, str] = {}
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
        self._clear_discovery_caches()
        self._clear_all_note_pending()
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

        list_phrases = {
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
        prefixes = (
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
        """Return a compact, structured guide for Voice Assist and Zalo."""
        return (
            "HƯỚNG DẪN CONVERSATIONAL ASSISTANT\n"
            "Các câu lệnh dưới đây dùng được trên Voice Assistant và Zalo.\n\n"
            "1. NHÀ THÔNG MINH\n"
            "Điều khiển hoặc kiểm tra thiết bị, phòng, khu vực và tầng.\n"
            "Ví dụ:\n"
            "• Bật đèn phòng khách.\n"
            "• Kiểm tra thiết bị nào đang bật ở tầng 2.\n\n"
            "2. THỜI TIẾT VÀ LỊCH\n"
            "Xem thời tiết, nhiệt độ và sự kiện từ Home Assistant.\n"
            "Ví dụ:\n"
            "• Thời tiết hôm nay thế nào?\n"
            "• Ngày mai tôi có lịch gì?\n\n"
            "3. CAMERA\n"
            "Chọn một hoặc nhiều camera, xác nhận rồi gửi ảnh đến Zalo; nếu chưa có destination, tích hợp sẽ yêu cầu cấu hình.\n"
            "Ví dụ:\n"
            "• Chụp camera.\n"
            "• Lấy ảnh camera sân trước.\n\n"
            "4. NHẮC HẸN\n"
            "Tạo, xem hoặc xóa nhắc hẹn; có thể chọn điện thoại, loa và Zalo nhận thông báo.\n"
            "Ví dụ:\n"
            "• Nhắc tôi 30 phút nữa uống thuốc.\n"
            "• Danh sách nhắc hẹn.\n\n"
            "5. GHI CHÚ\n"
            "Thêm, xem, sửa hoặc xóa ghi chú; hỗ trợ mức Bảo mật và Công khai.\n"
            "Ví dụ:\n"
            "• Ghi nhớ mã tủ đồ là 2468.\n"
            "• Danh sách ghi chú.\n\n"
            "6. BỘ NHỚ CÂU LỆNH\n"
            "Dạy cách nói mới cho chức năng có sẵn, xem lại hoặc xóa câu đã học.\n"
            "Ví dụ:\n"
            "• Học câu lệnh xem cổng để chụp ảnh camera.\n"
            "• Xóa câu lệnh xem cổng.\n\n"
            "Nói “hướng dẫn sử dụng tích hợp” bất cứ lúc nào để xem lại."
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

        if request in {"tat ca", "toan bo", "het"}:
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
            "khong",
            "huy",
            "bo qua",
            "khong chup",
            "khong chup anh",
            "khong lay anh",
        }
        if normalized in cancel_phrases:
            self._zalo_pending_cameras.pop(context.owner_key, None)
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

    async def _async_home_assistant_conversation_from_zalo(
        self,
        context: ZaloWebhookContext,
        service_context: Context | None,
    ) -> str:
        """Send a Zalo command through the configured HA Conversation agent."""
        try:
            result = await async_converse(
                hass=self.hass,
                text=context.text,
                conversation_id=self._zalo_ha_conversation_ids.get(
                    context.owner_key
                ),
                context=service_context or Context(),
                language="vi",
                agent_id=self.zalo_conversation_agent_id,
            )
        except Exception:  # noqa: BLE001 - always return a Zalo response
            _LOGGER.exception(
                "Conversation agent %s failed for Zalo thread %s",
                self.zalo_conversation_agent_id,
                context.thread_id,
            )
            return (
                "Home Assistant chưa xử lý được yêu cầu này. Hãy kiểm tra "
                "Conversation agent đã chọn và quyền expose thiết bị cho Assist."
            )

        conversation_id = str(
            getattr(result, "conversation_id", "") or ""
        ).strip()
        if conversation_id:
            self._zalo_ha_conversation_ids[context.owner_key] = conversation_id

        reply = self._conversation_reply_text(result)
        if reply:
            return reply

        response = getattr(result, "response", None)
        raw_error_code = getattr(response, "error_code", "") or ""
        error_code = str(getattr(raw_error_code, "value", raw_error_code))
        if error_code == "no_valid_targets":
            return (
                "Không tìm thấy thiết bị phù hợp. Hãy kiểm tra tên thiết bị, "
                "phòng/khu vực/sàn và bật expose cho Assist."
            )
        return (
            "Tôi chưa hiểu yêu cầu. Ví dụ: bật đèn phòng khách, kiểm tra "
            "trạng thái tầng 2, hoặc thời tiết hôm nay."
        )

    async def _async_home_assistant_conversation_from_voice(
        self,
        user_input: ConversationInput,
        text: str,
    ) -> str:
        """Run a learned Home Assistant macro from an Assist request."""
        try:
            result = await async_converse(
                hass=self.hass,
                text=text,
                conversation_id=user_input.conversation_id,
                context=user_input.context,
                language=str(getattr(user_input, "language", "vi") or "vi"),
                agent_id=self.zalo_conversation_agent_id,
            )
        except Exception:  # noqa: BLE001 - always return a voice response
            _LOGGER.exception(
                "Home Assistant conversation failed for learned command %s",
                text,
            )
            return await self._async_voice_response(
                user_input,
                "Home Assistant chưa xử lý được câu lệnh đã học. Hãy kiểm tra "
                "quyền expose thiết bị cho Assist.",
            )

        reply = self._conversation_reply_text(result)
        if not reply:
            reply = (
                "Tôi đã chuyển câu lệnh đã học cho Home Assistant nhưng chưa "
                "nhận được nội dung trả lời."
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
            if exposed:
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

    async def _async_calendar_from_zalo(
        self,
        context: ZaloWebhookContext,
        service_context: Context | None,
    ) -> str:
        """Read events from exposed Home Assistant calendar entities."""
        states = self._zalo_exposed_calendar_states(context.text)
        if not states:
            return (
                "Chưa có lịch nào được expose cho Assist. Hãy vào Cài đặt > "
                "Voice assistants > Expose để cho phép các entity calendar."
            )

        now = dt_util.now()
        window = calendar_window_from_text(context.text, now)
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
                    dict(state.attributes), calendar_name
                )
                if fallback is not None:
                    calendar_events.append(fallback)
            events.extend(calendar_events)

        return format_calendar_events(events, window, now)

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
            return await self._async_process_note_zalo_command(
                context, command
            )
        if command == "create":
            self._zalo_pending_notes.pop(context.owner_key, None)
            self._zalo_pending_creations.pop(context.owner_key, None)
            self._zalo_pending_deletions.pop(context.owner_key, None)
            self._zalo_pending_cameras.pop(context.owner_key, None)
            return await self._async_create_from_zalo(context)
        if command == "list":
            self._zalo_pending_notes.pop(context.owner_key, None)
            self._zalo_pending_cameras.pop(context.owner_key, None)
            return await self._async_list_from_zalo(context)
        if command == "delete":
            self._zalo_pending_notes.pop(context.owner_key, None)
            self._zalo_pending_creations.pop(context.owner_key, None)
            self._zalo_pending_cameras.pop(context.owner_key, None)
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

        # Start typing immediately and keep refreshing it for every Zalo
        # feature until its final text/image response has actually been sent.
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
        text = text.strip().casefold().removeprefix("hãy ")
        normalized = normalize_text(text)
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
        request = self._request_slot(user_input, result)
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

        if request in {"tất cả", "toàn bộ", "hết"}:
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
