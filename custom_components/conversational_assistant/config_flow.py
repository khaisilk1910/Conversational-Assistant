"""Config flow for Conversational Assistant."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, time
from typing import Any
import re
import unicodedata
import uuid

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.mobile_app.const import ATTR_WEBHOOK_ID
from homeassistant.components.mobile_app.util import get_notify_service
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import selector

from .const import (
    AI_TASK_DOMAIN,
    CONF_AI_AGENT_FAILOVER_ENABLED,
    CONF_AI_CAMERA_INSTRUCTIONS,
    CONF_AI_CAMERA_TASK_ENTITY_ID,
    CONF_AI_IMAGE_TASK_ENTITY_ID,
    CONF_AI_SEARCH_AGENT_ID,
    CONF_CALENDAR_ENTITIES,
    CONF_CALENDAR_LOOKAHEAD_DAYS,
    CONF_CALENDAR_NOTIFICATION_ENABLED,
    CONF_CALENDAR_NOTIFICATION_MOBILE_DEVICES,
    CONF_CALENDAR_NOTIFICATION_TIME,
    CONF_CALENDAR_NOTIFICATION_ZALO_TARGETS,
    CONF_CAMERA_ENTITY_ID,
    CONF_CAMERA_TARGETS,
    CONF_WEATHER_ENTITY_ID,
    CONF_WEATHER_FORECAST_DAYS,
    CONF_WEATHER_FORECAST_ENABLED,
    CONF_WEATHER_FORECAST_TIMES,
    CONF_WEATHER_FORECAST_ZALO_TARGETS,
    CONF_WEATHER_LOCATION,
    CONF_WEATHER_STORM_ENABLED,
    CONF_WEATHER_STORM_TIMES,
    CONF_WEATHER_STORM_ZALO_TARGETS,
    CONF_CONFIRM_TARGETS,
    CONF_MOBILE_DEVICE_ID,
    CONF_MOBILE_TARGETS,
    CONF_NAMED_TARGET_ENABLED,
    CONF_NAMED_TARGET_ID,
    CONF_NAMED_TARGET_NAME,
    CONF_DISMISS_ON_CLEAR,
    CONF_SPEAKER_ENABLED,
    CONF_SPEAKER_ENTITY_ID,
    CONF_SPEAKER_TARGETS,
    CONF_TTS_ENTITY_ID,
    CONF_TTS_LANGUAGE,
    CONF_TTS_VOICE,
    CONF_USER_ADDRESS,
    CONF_ZALO_INVOCATION_KEYWORD,
    CONF_ZALO_INVOCATION_KEYWORD_ENABLED,
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
    DEFAULT_AI_AGENT_FAILOVER_ENABLED,
    DEFAULT_AI_CAMERA_INSTRUCTIONS,
    DEFAULT_AI_CAMERA_TASK_ENTITY_ID,
    DEFAULT_AI_IMAGE_TASK_ENTITY_ID,
    DEFAULT_AI_SEARCH_AGENT_ID,
    DEFAULT_CALENDAR_LOOKAHEAD_DAYS,
    DEFAULT_CALENDAR_NOTIFICATION_ENABLED,
    DEFAULT_CALENDAR_NOTIFICATION_TIME,
    DEFAULT_WEATHER_ENTITY_ID,
    DEFAULT_WEATHER_FORECAST_DAYS,
    DEFAULT_WEATHER_FORECAST_ENABLED,
    DEFAULT_WEATHER_FORECAST_TIMES,
    DEFAULT_WEATHER_LOCATION,
    DEFAULT_WEATHER_STORM_ENABLED,
    DEFAULT_WEATHER_STORM_TIMES,
    DEFAULT_CONFIRM_TARGETS,
    DEFAULT_DISMISS_ON_CLEAR,
    DEFAULT_SPEAKER_ENABLED,
    DEFAULT_TTS_LANGUAGE,
    DEFAULT_TTS_VOICE,
    DEFAULT_USER_ADDRESS,
    DEFAULT_ZALO_INVOCATION_KEYWORD,
    DEFAULT_ZALO_INVOCATION_KEYWORD_ENABLED,
    DEFAULT_ZALO_ENABLED,
    DEFAULT_ZALO_CONVERSATION_AGENT_ID,
    DEFAULT_ZALO_HOME_ASSISTANT_ENABLED,
    DEFAULT_ZALO_TYPE,
    DEFAULT_ZALO_WEBHOOK_BOT_ACCOUNT_ID,
    DEFAULT_ZALO_WEBHOOK_ENABLED,
    DOMAIN,
    INTEGRATION_NAME,
    MAX_CALENDAR_LOOKAHEAD_DAYS,
    MAX_WEATHER_FORECAST_DAYS,
    ZALO_TYPE_GROUP,
    ZALO_TYPE_USER,
)
from .named_targets import (
    make_named_target,
    named_target_errors,
    normalize_named_target_list,
    spoken_name_key,
)

CONF_SELECTED_ZALO_TARGET = "selected_zalo_target"
CONF_SELECTED_NAMED_TARGET = "selected_named_target"


def _general_settings_schema(
    dismiss_on_clear: bool,
    confirm_targets: bool,
    user_address: str = DEFAULT_USER_ADDRESS,
) -> vol.Schema:
    """Build the general options schema."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_DISMISS_ON_CLEAR,
                default=dismiss_on_clear,
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_CONFIRM_TARGETS,
                default=confirm_targets,
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_USER_ADDRESS,
                default=user_address or DEFAULT_USER_ADDRESS,
            ): selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.TEXT
                )
            ),
        }
    )


def _zalo_settings_schema(
    zalo_webhook_enabled: bool,
    zalo_webhook_bot_account_id: str,
    zalo_webhook_account_selection: str,
    zalo_home_assistant_enabled: bool,
    zalo_invocation_keyword_enabled: bool = (
        DEFAULT_ZALO_INVOCATION_KEYWORD_ENABLED
    ),
    zalo_invocation_keyword: str = DEFAULT_ZALO_INVOCATION_KEYWORD,
) -> vol.Schema:
    """Build the global Zalo settings schema."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_ZALO_WEBHOOK_ENABLED,
                default=zalo_webhook_enabled,
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_ZALO_HOME_ASSISTANT_ENABLED,
                default=zalo_home_assistant_enabled,
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_ZALO_INVOCATION_KEYWORD_ENABLED,
                default=zalo_invocation_keyword_enabled,
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_ZALO_INVOCATION_KEYWORD,
                default=(
                    zalo_invocation_keyword
                    or DEFAULT_ZALO_INVOCATION_KEYWORD
                ),
            ): selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.TEXT
                )
            ),
            vol.Optional(
                CONF_ZALO_WEBHOOK_BOT_ACCOUNT_ID,
                default=zalo_webhook_bot_account_id,
            ): selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.TEXT
                )
            ),
            vol.Optional(
                CONF_ZALO_WEBHOOK_ACCOUNT_SELECTION,
                default=zalo_webhook_account_selection,
            ): selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.TEXT
                )
            ),
        }
    )


def _ai_settings_schema(
    zalo_conversation_agent_id: str,
    ai_search_agent_id: str,
    ai_image_task_entity_id: str,
    ai_camera_task_entity_id: str,
    ai_camera_instructions: str,
    ai_agent_failover_enabled: bool,
) -> vol.Schema:
    """Build AI agent selectors."""
    fields: dict[Any, Any] = {
        vol.Optional(
            CONF_AI_AGENT_FAILOVER_ENABLED,
            default=ai_agent_failover_enabled,
        ): selector.BooleanSelector(),
    }
    conversation_selector = selector.ConversationAgentSelector(
        selector.ConversationAgentSelectorConfig(language="vi")
    )
    fields[
        vol.Optional(
            CONF_ZALO_CONVERSATION_AGENT_ID,
            default=zalo_conversation_agent_id,
        )
    ] = conversation_selector

    search_selector = selector.ConversationAgentSelector()
    if ai_search_agent_id:
        fields[
            vol.Optional(
                CONF_AI_SEARCH_AGENT_ID,
                default=ai_search_agent_id,
            )
        ] = search_selector
    else:
        fields[vol.Optional(CONF_AI_SEARCH_AGENT_ID)] = search_selector

    image_task_selector = selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain=AI_TASK_DOMAIN,
            multiple=False,
        )
    )
    if ai_image_task_entity_id:
        fields[
            vol.Optional(
                CONF_AI_IMAGE_TASK_ENTITY_ID,
                default=ai_image_task_entity_id,
            )
        ] = image_task_selector
    else:
        fields[vol.Optional(CONF_AI_IMAGE_TASK_ENTITY_ID)] = (
            image_task_selector
        )

    camera_task_selector = selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain=AI_TASK_DOMAIN,
            multiple=False,
        )
    )
    if ai_camera_task_entity_id:
        fields[
            vol.Optional(
                CONF_AI_CAMERA_TASK_ENTITY_ID,
                default=ai_camera_task_entity_id,
            )
        ] = camera_task_selector
    else:
        fields[vol.Optional(CONF_AI_CAMERA_TASK_ENTITY_ID)] = (
            camera_task_selector
        )

    fields[
        vol.Optional(
            CONF_AI_CAMERA_INSTRUCTIONS,
            default=ai_camera_instructions,
        )
    ] = selector.TextSelector(
        selector.TextSelectorConfig(
            type=selector.TextSelectorType.TEXT,
            multiline=True,
        )
    )
    return vol.Schema(fields)


def _tts_settings_schema(
    speaker_enabled: bool,
    tts_entity_id: str | None,
    tts_language: str,
    tts_voice: str,
) -> vol.Schema:
    """Build speaker and TTS settings."""
    fields: dict[Any, Any] = {
        vol.Optional(
            CONF_SPEAKER_ENABLED,
            default=speaker_enabled,
        ): selector.BooleanSelector(),
    }
    tts_selector = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="tts", multiple=False)
    )
    if tts_entity_id:
        fields[vol.Optional(CONF_TTS_ENTITY_ID, default=tts_entity_id)] = (
            tts_selector
        )
    else:
        fields[vol.Optional(CONF_TTS_ENTITY_ID)] = tts_selector
    fields[
        vol.Optional(
            CONF_TTS_LANGUAGE,
            default=tts_language,
        )
    ] = selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
    )
    fields[
        vol.Optional(
            CONF_TTS_VOICE,
            default=tts_voice,
        )
    ] = selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
    )
    return vol.Schema(fields)


def _select_multiple_schema(
    options: dict[str, str],
) -> selector.SelectSelector:
    """Build a stable multi-select field from dynamic Home Assistant data."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                {"value": value, "label": label}
                for value, label in options.items()
            ],
            multiple=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _mobile_device_choices(hass: HomeAssistant) -> dict[str, str]:
    """Return Mobile App devices that can be selected for calendar alerts."""
    mobile_entry_ids: set[str] = set()
    for entry in hass.config_entries.async_entries("mobile_app"):
        webhook_id = entry.data.get(ATTR_WEBHOOK_ID)
        if not webhook_id:
            continue
        try:
            service = get_notify_service(hass, webhook_id)
        except (KeyError, TypeError):
            service = None
        if service and hass.services.has_service("notify", service):
            mobile_entry_ids.add(entry.entry_id)
    if not mobile_entry_ids:
        return {}
    registry = dr.async_get(hass)
    devices = sorted(
        (
            device
            for device in registry.devices.values()
            if mobile_entry_ids.intersection(device.config_entries)
        ),
        key=lambda device: (
            str(device.name_by_user or device.name or device.id).casefold(),
            device.id,
        ),
    )
    return {
        device.id: str(device.name_by_user or device.name or device.id)
        for device in devices
    }


def _calendar_entity_choices(hass: HomeAssistant) -> dict[str, str]:
    """Return calendar entities selectable for monitoring and alerts."""
    states = sorted(
        hass.states.async_all("calendar"),
        key=lambda state: (
            str(state.name or state.entity_id).casefold(),
            state.entity_id,
        ),
    )
    return {
        state.entity_id: f"{state.name or state.entity_id} ({state.entity_id})"
        for state in states
    }


def _zalo_target_choices(
    targets: list[dict[str, Any]],
) -> dict[str, str]:
    """Return configured enabled Zalo destinations for calendar alerts."""
    choices: dict[str, str] = {}
    for target in targets:
        if not bool(target.get(CONF_ZALO_TARGET_ENABLED, True)):
            continue
        target_id = str(target.get(CONF_ZALO_TARGET_ID, "") or "").strip()
        thread_id = str(target.get(CONF_ZALO_THREAD_ID, "") or "").strip()
        account_selection = str(
            target.get(CONF_ZALO_ACCOUNT_SELECTION, "") or ""
        ).strip()
        if not target_id or not thread_id or not account_selection:
            continue
        name = str(
            target.get(CONF_ZALO_TARGET_NAME) or thread_id or target_id
        ).strip()
        recipient_type = (
            "Nhóm"
            if str(target.get(CONF_ZALO_TYPE, DEFAULT_ZALO_TYPE))
            == ZALO_TYPE_GROUP
            else "Người dùng"
        )
        choices[target_id] = f"{recipient_type}: {name}"
    return choices


def _calendar_settings_schema(
    lookahead_days: int,
    selected_calendar_entities: list[str],
    notification_enabled: bool,
    notification_time: str,
    selected_mobile_devices: list[str],
    selected_zalo_targets: list[str],
    calendar_choices: dict[str, str],
    mobile_choices: dict[str, str],
    zalo_choices: dict[str, str],
) -> vol.Schema:
    """Build calendar sensor and scheduled notification settings."""
    valid_calendars = [
        value
        for value in selected_calendar_entities
        if value in calendar_choices
    ]
    valid_mobile = [
        value for value in selected_mobile_devices if value in mobile_choices
    ]
    valid_zalo = [
        value for value in selected_zalo_targets if value in zalo_choices
    ]
    return vol.Schema(
        {
            vol.Optional(
                CONF_CALENDAR_LOOKAHEAD_DAYS,
                default=max(
                    1, min(MAX_CALENDAR_LOOKAHEAD_DAYS, int(lookahead_days))
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=MAX_CALENDAR_LOOKAHEAD_DAYS,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="ngày",
                )
            ),
            vol.Optional(
                CONF_CALENDAR_ENTITIES,
                default=valid_calendars,
            ): _select_multiple_schema(calendar_choices),
            vol.Optional(
                CONF_CALENDAR_NOTIFICATION_ENABLED,
                default=notification_enabled,
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_CALENDAR_NOTIFICATION_TIME,
                default=notification_time,
            ): selector.TimeSelector(),
            vol.Optional(
                CONF_CALENDAR_NOTIFICATION_MOBILE_DEVICES,
                default=valid_mobile,
            ): _select_multiple_schema(mobile_choices),
            vol.Optional(
                CONF_CALENDAR_NOTIFICATION_ZALO_TARGETS,
                default=valid_zalo,
            ): _select_multiple_schema(zalo_choices),
        }
    )


def _normalize_calendar_settings(
    user_input: dict[str, Any],
) -> dict[str, Any]:
    """Normalize calendar options to JSON-safe values."""
    normalized = dict(user_input)
    try:
        days = int(
            float(
                normalized.get(
                    CONF_CALENDAR_LOOKAHEAD_DAYS,
                    DEFAULT_CALENDAR_LOOKAHEAD_DAYS,
                )
            )
        )
    except (TypeError, ValueError):
        days = DEFAULT_CALENDAR_LOOKAHEAD_DAYS
    normalized[CONF_CALENDAR_LOOKAHEAD_DAYS] = max(
        1, min(MAX_CALENDAR_LOOKAHEAD_DAYS, days)
    )
    normalized[CONF_CALENDAR_NOTIFICATION_ENABLED] = bool(
        normalized.get(
            CONF_CALENDAR_NOTIFICATION_ENABLED,
            DEFAULT_CALENDAR_NOTIFICATION_ENABLED,
        )
    )
    raw_time = normalized.get(
        CONF_CALENDAR_NOTIFICATION_TIME,
        DEFAULT_CALENDAR_NOTIFICATION_TIME,
    )
    if isinstance(raw_time, time):
        normalized[CONF_CALENDAR_NOTIFICATION_TIME] = raw_time.strftime(
            "%H:%M:%S"
        )
    else:
        value = str(raw_time or DEFAULT_CALENDAR_NOTIFICATION_TIME).strip()
        normalized[CONF_CALENDAR_NOTIFICATION_TIME] = value or (
            DEFAULT_CALENDAR_NOTIFICATION_TIME
        )
    for key in (
        CONF_CALENDAR_ENTITIES,
        CONF_CALENDAR_NOTIFICATION_MOBILE_DEVICES,
        CONF_CALENDAR_NOTIFICATION_ZALO_TARGETS,
    ):
        value = normalized.get(key, [])
        if isinstance(value, (list, tuple, set)):
            normalized[key] = list(
                dict.fromkeys(
                    str(item).strip()
                    for item in value
                    if str(item).strip()
                )
            )
        elif value:
            normalized[key] = [str(value).strip()]
        else:
            normalized[key] = []
    return normalized


def _weather_times_text(value: Any) -> str:
    """Return one stored time per line for the multiline selector."""
    if isinstance(value, str):
        raw_values = re.split(r"[,;\n]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = []
    result: list[str] = []
    for raw in raw_values:
        item = str(raw or "").strip()
        if not item:
            continue
        for pattern in ("%H:%M:%S", "%H:%M"):
            try:
                parsed = datetime.strptime(item, pattern).time()
            except ValueError:
                continue
            canonical = parsed.strftime("%H:%M:%S")
            if canonical not in result:
                result.append(canonical)
            break
    return "\n".join(
        item[:5] if item.endswith(":00") else item for item in result
    )


def _weather_settings_schema(
    weather_entity_id: str,
    location: str,
    forecast_enabled: bool,
    forecast_times: Any,
    forecast_days: int,
    selected_forecast_zalo_targets: list[str],
    storm_enabled: bool,
    storm_times: Any,
    selected_storm_zalo_targets: list[str],
    zalo_choices: dict[str, str],
) -> vol.Schema:
    """Build scheduled forecast and Vietnam storm-alert settings."""
    valid_forecast_targets = [
        value for value in selected_forecast_zalo_targets if value in zalo_choices
    ]
    valid_storm_targets = [
        value for value in selected_storm_zalo_targets if value in zalo_choices
    ]
    fields: dict[Any, Any] = {}
    weather_selector = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="weather", multiple=False)
    )
    if weather_entity_id:
        fields[
            vol.Optional(
                CONF_WEATHER_ENTITY_ID,
                default=weather_entity_id,
            )
        ] = weather_selector
    else:
        fields[vol.Optional(CONF_WEATHER_ENTITY_ID)] = weather_selector
    fields.update(
        {
            vol.Optional(
                CONF_WEATHER_LOCATION,
                default=location,
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional(
                CONF_WEATHER_FORECAST_ENABLED,
                default=forecast_enabled,
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_WEATHER_FORECAST_TIMES,
                default=_weather_times_text(forecast_times),
            ): selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.TEXT,
                    multiline=True,
                )
            ),
            vol.Optional(
                CONF_WEATHER_FORECAST_DAYS,
                default=max(
                    1,
                    min(MAX_WEATHER_FORECAST_DAYS, int(forecast_days)),
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=MAX_WEATHER_FORECAST_DAYS,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="ngày",
                )
            ),
            vol.Optional(
                CONF_WEATHER_FORECAST_ZALO_TARGETS,
                default=valid_forecast_targets,
            ): _select_multiple_schema(zalo_choices),
            vol.Optional(
                CONF_WEATHER_STORM_ENABLED,
                default=storm_enabled,
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_WEATHER_STORM_TIMES,
                default=_weather_times_text(storm_times),
            ): selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.TEXT,
                    multiline=True,
                )
            ),
            vol.Optional(
                CONF_WEATHER_STORM_ZALO_TARGETS,
                default=valid_storm_targets,
            ): _select_multiple_schema(zalo_choices),
        }
    )
    return vol.Schema(fields)


def _parse_weather_times(value: Any) -> tuple[list[str], bool]:
    """Normalize a comma/newline-separated time list and report invalid input."""
    if isinstance(value, str):
        raw_values = re.split(r"[,;\n]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = []
    result: list[str] = []
    invalid = False
    for raw in raw_values:
        item = str(raw or "").strip()
        if not item:
            continue
        parsed = None
        for pattern in ("%H:%M:%S", "%H:%M"):
            try:
                parsed = datetime.strptime(item, pattern).time()
                break
            except ValueError:
                continue
        if parsed is None:
            invalid = True
            continue
        canonical = parsed.strftime("%H:%M:%S")
        if canonical not in result:
            result.append(canonical)
    return result[:24], invalid


def _normalize_weather_settings(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize Weather settings into JSON-safe option values."""
    normalized = dict(user_input)
    normalized[CONF_WEATHER_ENTITY_ID] = str(
        normalized.get(CONF_WEATHER_ENTITY_ID, DEFAULT_WEATHER_ENTITY_ID)
        or ""
    ).strip()
    normalized[CONF_WEATHER_LOCATION] = " ".join(
        str(
            normalized.get(
                CONF_WEATHER_LOCATION, DEFAULT_WEATHER_LOCATION
            )
            or ""
        ).split()
    )[:160]
    normalized[CONF_WEATHER_FORECAST_ENABLED] = bool(
        normalized.get(
            CONF_WEATHER_FORECAST_ENABLED,
            DEFAULT_WEATHER_FORECAST_ENABLED,
        )
    )
    forecast_times, _ = _parse_weather_times(
        normalized.get(
            CONF_WEATHER_FORECAST_TIMES,
            DEFAULT_WEATHER_FORECAST_TIMES,
        )
    )
    normalized[CONF_WEATHER_FORECAST_TIMES] = forecast_times
    try:
        forecast_days = int(
            float(
                normalized.get(
                    CONF_WEATHER_FORECAST_DAYS,
                    DEFAULT_WEATHER_FORECAST_DAYS,
                )
            )
        )
    except (TypeError, ValueError):
        forecast_days = DEFAULT_WEATHER_FORECAST_DAYS
    normalized[CONF_WEATHER_FORECAST_DAYS] = max(
        1, min(MAX_WEATHER_FORECAST_DAYS, forecast_days)
    )
    normalized[CONF_WEATHER_STORM_ENABLED] = bool(
        normalized.get(
            CONF_WEATHER_STORM_ENABLED,
            DEFAULT_WEATHER_STORM_ENABLED,
        )
    )
    storm_times, _ = _parse_weather_times(
        normalized.get(
            CONF_WEATHER_STORM_TIMES,
            DEFAULT_WEATHER_STORM_TIMES,
        )
    )
    normalized[CONF_WEATHER_STORM_TIMES] = storm_times
    for key in (
        CONF_WEATHER_FORECAST_ZALO_TARGETS,
        CONF_WEATHER_STORM_ZALO_TARGETS,
    ):
        value = normalized.get(key, [])
        if isinstance(value, (list, tuple, set)):
            normalized[key] = list(
                dict.fromkeys(
                    str(item).strip()
                    for item in value
                    if str(item).strip()
                )
            )
        elif value:
            normalized[key] = [str(value).strip()]
        else:
            normalized[key] = []
    return normalized


def _validate_weather_settings(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate scheduled Weather setting requirements."""
    errors: dict[str, str] = {}
    forecast_times, invalid_forecast = _parse_weather_times(
        user_input.get(
            CONF_WEATHER_FORECAST_TIMES,
            DEFAULT_WEATHER_FORECAST_TIMES,
        )
    )
    storm_times, invalid_storm = _parse_weather_times(
        user_input.get(
            CONF_WEATHER_STORM_TIMES,
            DEFAULT_WEATHER_STORM_TIMES,
        )
    )
    if invalid_forecast:
        errors[CONF_WEATHER_FORECAST_TIMES] = "invalid_time_list"
    if invalid_storm:
        errors[CONF_WEATHER_STORM_TIMES] = "invalid_time_list"
    if bool(user_input.get(CONF_WEATHER_FORECAST_ENABLED, False)):
        if not forecast_times:
            errors.setdefault(CONF_WEATHER_FORECAST_TIMES, "required")
        if not user_input.get(CONF_WEATHER_FORECAST_ZALO_TARGETS):
            errors[CONF_WEATHER_FORECAST_ZALO_TARGETS] = "required"
    if bool(user_input.get(CONF_WEATHER_STORM_ENABLED, False)):
        if not storm_times:
            errors.setdefault(CONF_WEATHER_STORM_TIMES, "required")
        if not user_input.get(CONF_WEATHER_STORM_ZALO_TARGETS):
            errors[CONF_WEATHER_STORM_ZALO_TARGETS] = "required"
    return errors


def _merge_schemas(*schemas: vol.Schema) -> vol.Schema:
    """Merge multiple Voluptuous schemas while preserving field order."""
    fields: dict[Any, Any] = {}
    for schema in schemas:
        fields.update(schema.schema)
    return vol.Schema(fields)


def _initial_schema(
    dismiss_on_clear: bool,
    confirm_targets: bool,
    user_address: str,
    zalo_invocation_keyword_enabled: bool,
    zalo_invocation_keyword: str,
    speaker_enabled: bool,
    tts_entity_id: str | None,
    tts_language: str,
    tts_voice: str,
    zalo_webhook_enabled: bool,
    zalo_webhook_bot_account_id: str,
    zalo_webhook_account_selection: str,
    zalo_home_assistant_enabled: bool,
    zalo_conversation_agent_id: str,
    ai_search_agent_id: str,
    ai_image_task_entity_id: str,
    ai_camera_task_entity_id: str,
    ai_camera_instructions: str,
    ai_agent_failover_enabled: bool,
) -> vol.Schema:
    """Build the initial installation form with all setting groups."""
    return _merge_schemas(
        _general_settings_schema(
            dismiss_on_clear,
            confirm_targets,
            user_address,
        ),
        _zalo_settings_schema(
            zalo_webhook_enabled,
            zalo_webhook_bot_account_id,
            zalo_webhook_account_selection,
            zalo_home_assistant_enabled,
            zalo_invocation_keyword_enabled,
            zalo_invocation_keyword,
        ),
        _ai_settings_schema(
            zalo_conversation_agent_id,
            ai_search_agent_id,
            ai_image_task_entity_id,
            ai_camera_task_entity_id,
            ai_camera_instructions,
            ai_agent_failover_enabled,
        ),
        _tts_settings_schema(
            speaker_enabled,
            tts_entity_id,
            tts_language,
            tts_voice,
        ),
    )


def _clean_zalo_invocation_keyword(value: Any) -> str:
    """Return a plain stored Zalo invocation keyword."""
    keyword = unicodedata.normalize("NFKC", str(value or ""))
    keyword = keyword.replace("\u00a0", " ")
    keyword = "".join(
        character
        for character in keyword
        if unicodedata.category(character) != "Cf"
    )
    keyword = " ".join(keyword.split()).strip()

    wrappers = (
        ("**", "**"),
        ("__", "__"),
        ("`", "`"),
        ('"', '"'),
        ("'", "'"),
        ("“", "”"),
        ("‘", "’"),
    )
    changed = True
    while keyword and changed:
        changed = False
        for opening, closing in wrappers:
            if (
                len(keyword) > len(opening) + len(closing)
                and keyword.startswith(opening)
                and keyword.endswith(closing)
            ):
                keyword = keyword[len(opening) : -len(closing)].strip()
                changed = True
                break
    return keyword[:80]


def _validate_zalo_settings(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate global Zalo configuration values."""
    errors: dict[str, str] = {}
    if bool(
        user_input.get(
            CONF_ZALO_WEBHOOK_ENABLED,
            DEFAULT_ZALO_WEBHOOK_ENABLED,
        )
    ) and not str(
        user_input.get(CONF_ZALO_WEBHOOK_BOT_ACCOUNT_ID, "") or ""
    ).strip():
        errors[CONF_ZALO_WEBHOOK_BOT_ACCOUNT_ID] = "required"

    keyword_enabled = bool(
        user_input.get(
            CONF_ZALO_INVOCATION_KEYWORD_ENABLED,
            DEFAULT_ZALO_INVOCATION_KEYWORD_ENABLED,
        )
    )
    keyword = _clean_zalo_invocation_keyword(
        user_input.get(
            CONF_ZALO_INVOCATION_KEYWORD,
            DEFAULT_ZALO_INVOCATION_KEYWORD,
        )
    )
    if keyword_enabled and not keyword:
        errors[CONF_ZALO_INVOCATION_KEYWORD] = "required"
    return errors

def _normalize_zalo_settings(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize global Zalo text values before storing them."""
    normalized = dict(user_input)
    normalized[CONF_ZALO_WEBHOOK_BOT_ACCOUNT_ID] = str(
        normalized.get(CONF_ZALO_WEBHOOK_BOT_ACCOUNT_ID, "") or ""
    ).strip()
    normalized[CONF_ZALO_WEBHOOK_ACCOUNT_SELECTION] = str(
        normalized.get(CONF_ZALO_WEBHOOK_ACCOUNT_SELECTION, "") or ""
    ).strip()
    normalized[CONF_ZALO_INVOCATION_KEYWORD_ENABLED] = bool(
        normalized.get(
            CONF_ZALO_INVOCATION_KEYWORD_ENABLED,
            DEFAULT_ZALO_INVOCATION_KEYWORD_ENABLED,
        )
    )
    keyword = _clean_zalo_invocation_keyword(
        normalized.get(
            CONF_ZALO_INVOCATION_KEYWORD,
            DEFAULT_ZALO_INVOCATION_KEYWORD,
        )
    )
    normalized[CONF_ZALO_INVOCATION_KEYWORD] = keyword
    return normalized


def _normalize_ai_settings(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize AI agent identifiers before storing them."""
    normalized = dict(user_input)
    normalized[CONF_ZALO_CONVERSATION_AGENT_ID] = str(
        normalized.get(
            CONF_ZALO_CONVERSATION_AGENT_ID,
            DEFAULT_ZALO_CONVERSATION_AGENT_ID,
        )
        or DEFAULT_ZALO_CONVERSATION_AGENT_ID
    ).strip()
    normalized[CONF_AI_SEARCH_AGENT_ID] = str(
        normalized.get(CONF_AI_SEARCH_AGENT_ID, "") or ""
    ).strip()
    normalized[CONF_AI_IMAGE_TASK_ENTITY_ID] = str(
        normalized.get(CONF_AI_IMAGE_TASK_ENTITY_ID, "") or ""
    ).strip()
    normalized[CONF_AI_CAMERA_TASK_ENTITY_ID] = str(
        normalized.get(CONF_AI_CAMERA_TASK_ENTITY_ID, "") or ""
    ).strip()
    normalized[CONF_AI_CAMERA_INSTRUCTIONS] = (
        str(
            normalized.get(
                CONF_AI_CAMERA_INSTRUCTIONS,
                DEFAULT_AI_CAMERA_INSTRUCTIONS,
            )
            or ""
        ).strip()
        or DEFAULT_AI_CAMERA_INSTRUCTIONS
    )
    normalized[CONF_AI_AGENT_FAILOVER_ENABLED] = bool(
        normalized.get(
            CONF_AI_AGENT_FAILOVER_ENABLED,
            DEFAULT_AI_AGENT_FAILOVER_ENABLED,
        )
    )
    return normalized


def _normalize_general_settings(
    user_input: dict[str, Any],
) -> dict[str, Any]:
    """Normalize user-facing general settings."""
    normalized = dict(user_input)
    address = " ".join(
        str(normalized.get(CONF_USER_ADDRESS, DEFAULT_USER_ADDRESS) or "").split()
    )
    normalized[CONF_USER_ADDRESS] = (address or DEFAULT_USER_ADDRESS)[:80]
    return normalized


def _normalize_tts_settings(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize optional TTS language and voice values."""
    normalized = dict(user_input)
    normalized[CONF_TTS_LANGUAGE] = str(
        normalized.get(CONF_TTS_LANGUAGE, DEFAULT_TTS_LANGUAGE) or ""
    ).strip()
    normalized[CONF_TTS_VOICE] = str(
        normalized.get(CONF_TTS_VOICE, DEFAULT_TTS_VOICE) or ""
    ).strip()
    return normalized


def _normalize_initial(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize all text values from the initial installation form."""
    return _normalize_general_settings(
        _normalize_tts_settings(
            _normalize_ai_settings(_normalize_zalo_settings(user_input))
        )
    )


def _first_tts_entity_id(hass) -> str | None:
    """Return the first currently registered TTS entity, if any."""
    entity_ids = sorted(state.entity_id for state in hass.states.async_all("tts"))
    return entity_ids[0] if entity_ids else None


def _first_weather_entity_id(hass: HomeAssistant) -> str | None:
    """Return the first currently registered weather entity, if any."""
    entity_ids = sorted(
        state.entity_id for state in hass.states.async_all("weather")
    )
    return entity_ids[0] if entity_ids else None


def _weather_entity_count(hass: HomeAssistant) -> int:
    """Return the number of currently registered weather entities."""
    return len(hass.states.async_all("weather"))


def _named_target_schema(
    reference_key: str,
    reference_selector: Any,
    target: dict[str, Any] | None = None,
) -> vol.Schema:
    """Build one add/edit form for a configured spoken target."""
    target = target or {}
    fields: dict[Any, Any] = {
        vol.Required(
            CONF_NAMED_TARGET_NAME,
            default=str(target.get(CONF_NAMED_TARGET_NAME, "")),
        ): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
        ),
        vol.Optional(
            CONF_NAMED_TARGET_ENABLED,
            default=bool(target.get(CONF_NAMED_TARGET_ENABLED, True)),
        ): selector.BooleanSelector(),
    }
    reference = str(target.get(reference_key, "") or "").strip()
    if reference:
        fields[vol.Required(reference_key, default=reference)] = (
            reference_selector
        )
    else:
        fields[vol.Required(reference_key)] = reference_selector
    return vol.Schema(fields)


def _mobile_target_schema(
    hass: HomeAssistant, target: dict[str, Any] | None = None
) -> vol.Schema:
    """Build a named Mobile App device form."""
    choices = _mobile_device_choices(hass)
    selected = str((target or {}).get(CONF_MOBILE_DEVICE_ID, "") or "")
    if selected and selected not in choices:
        choices[selected] = selected
    return _named_target_schema(
        CONF_MOBILE_DEVICE_ID, _select_single_schema(choices), target
    )


def _entity_target_schema(
    domain: str, reference_key: str, target: dict[str, Any] | None = None
) -> vol.Schema:
    """Build a named entity form for speakers or cameras."""
    return _named_target_schema(
        reference_key,
        selector.EntitySelector(
            selector.EntitySelectorConfig(domain=domain, multiple=False)
        ),
        target,
    )


def _select_single_schema(options: dict[str, str]) -> selector.SelectSelector:
    """Build a stable single-select dropdown from dynamic HA data."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                {"value": value, "label": label}
                for value, label in options.items()
            ],
            multiple=False,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _zalo_schema(target: dict[str, Any] | None = None) -> vol.Schema:
    """Build add/edit Zalo target schema."""
    target = target or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_ZALO_TARGET_NAME,
                default=str(target.get(CONF_ZALO_TARGET_NAME, "")),
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional(
                CONF_ZALO_TARGET_ENABLED,
                default=bool(target.get(CONF_ZALO_TARGET_ENABLED, True)),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_ZALO_TYPE,
                default=str(target.get(CONF_ZALO_TYPE, DEFAULT_ZALO_TYPE)),
            ): vol.In(
                {
                    ZALO_TYPE_USER: "Người dùng",
                    ZALO_TYPE_GROUP: "Nhóm",
                }
            ),
            vol.Required(
                CONF_ZALO_THREAD_ID,
                default=str(target.get(CONF_ZALO_THREAD_ID, "")),
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required(
                CONF_ZALO_ACCOUNT_SELECTION,
                default=str(target.get(CONF_ZALO_ACCOUNT_SELECTION, "")),
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
        }
    )


def _validate_zalo(
    user_input: dict[str, Any],
    *,
    existing: list[dict[str, Any]] | None = None,
    editing_target_id: str | None = None,
) -> dict[str, str]:
    """Validate a Zalo destination and its direct spoken name."""
    errors: dict[str, str] = {}
    name = " ".join(
        str(user_input.get(CONF_ZALO_TARGET_NAME, "") or "").split()
    )[:80]
    thread_id = str(user_input.get(CONF_ZALO_THREAD_ID, "")).strip()
    account = str(
        user_input.get(CONF_ZALO_ACCOUNT_SELECTION, "")
    ).strip()
    target_type = str(user_input.get(CONF_ZALO_TYPE, DEFAULT_ZALO_TYPE))
    if not name:
        errors[CONF_ZALO_TARGET_NAME] = "required"
    if not thread_id:
        errors[CONF_ZALO_THREAD_ID] = "required"
    if not account:
        errors[CONF_ZALO_ACCOUNT_SELECTION] = "required"
    for item in existing or []:
        if str(item.get(CONF_ZALO_TARGET_ID, "")) == str(
            editing_target_id or ""
        ):
            continue
        if name and spoken_name_key(
            str(item.get(CONF_ZALO_TARGET_NAME, "") or "")
        ) == spoken_name_key(name):
            errors[CONF_ZALO_TARGET_NAME] = "duplicate_name"
        if (
            thread_id
            and account
            and str(item.get(CONF_ZALO_TYPE, DEFAULT_ZALO_TYPE))
            == target_type
            and str(item.get(CONF_ZALO_THREAD_ID, "")).strip()
            == thread_id
            and str(item.get(CONF_ZALO_ACCOUNT_SELECTION, "")).strip()
            == account
        ):
            errors[CONF_ZALO_THREAD_ID] = "duplicate_target"
    return errors


def _make_zalo_target(
    user_input: dict[str, Any], target_id: str | None = None
) -> dict[str, Any]:
    """Normalize a Zalo target for config entry options."""
    return {
        CONF_ZALO_TARGET_ID: target_id or uuid.uuid4().hex,
        CONF_ZALO_TARGET_NAME: " ".join(
            str(user_input[CONF_ZALO_TARGET_NAME]).split()
        )[:80],
        CONF_ZALO_TARGET_ENABLED: bool(
            user_input.get(CONF_ZALO_TARGET_ENABLED, True)
        ),
        CONF_ZALO_TYPE: str(user_input[CONF_ZALO_TYPE]),
        CONF_ZALO_THREAD_ID: str(user_input[CONF_ZALO_THREAD_ID]).strip(),
        CONF_ZALO_ACCOUNT_SELECTION: str(
            user_input[CONF_ZALO_ACCOUNT_SELECTION]
        ).strip(),
    }


class ConversationalAssistantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Conversational Assistant."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial setup."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = _normalize_initial(user_input)
            errors = _validate_zalo_settings(user_input)
            if not errors:
                return self.async_create_entry(
                    title=INTEGRATION_NAME,
                    data=user_input,
                )

        values = user_input or {}

        return self.async_show_form(
            step_id="user",
            data_schema=_initial_schema(
                bool(
                    values.get(
                        CONF_DISMISS_ON_CLEAR,
                        DEFAULT_DISMISS_ON_CLEAR,
                    )
                ),
                bool(
                    values.get(
                        CONF_CONFIRM_TARGETS,
                        DEFAULT_CONFIRM_TARGETS,
                    )
                ),
                str(
                    values.get(CONF_USER_ADDRESS, DEFAULT_USER_ADDRESS)
                    or DEFAULT_USER_ADDRESS
                ).strip(),
                bool(
                    values.get(
                        CONF_ZALO_INVOCATION_KEYWORD_ENABLED,
                        DEFAULT_ZALO_INVOCATION_KEYWORD_ENABLED,
                    )
                ),
                str(
                    values.get(
                        CONF_ZALO_INVOCATION_KEYWORD,
                        DEFAULT_ZALO_INVOCATION_KEYWORD,
                    )
                    or ""
                ).strip(),
                bool(
                    values.get(
                        CONF_SPEAKER_ENABLED,
                        DEFAULT_SPEAKER_ENABLED,
                    )
                ),
                str(values.get(CONF_TTS_ENTITY_ID) or "").strip()
                or _first_tts_entity_id(self.hass),
                str(
                    values.get(CONF_TTS_LANGUAGE, DEFAULT_TTS_LANGUAGE)
                    or ""
                ).strip(),
                str(
                    values.get(CONF_TTS_VOICE, DEFAULT_TTS_VOICE)
                    or ""
                ).strip(),
                bool(
                    values.get(
                        CONF_ZALO_WEBHOOK_ENABLED,
                        DEFAULT_ZALO_WEBHOOK_ENABLED,
                    )
                ),
                str(
                    values.get(
                        CONF_ZALO_WEBHOOK_BOT_ACCOUNT_ID,
                        DEFAULT_ZALO_WEBHOOK_BOT_ACCOUNT_ID,
                    )
                    or ""
                ).strip(),
                str(
                    values.get(CONF_ZALO_WEBHOOK_ACCOUNT_SELECTION, "")
                    or ""
                ).strip(),
                bool(
                    values.get(
                        CONF_ZALO_HOME_ASSISTANT_ENABLED,
                        DEFAULT_ZALO_HOME_ASSISTANT_ENABLED,
                    )
                ),
                str(
                    values.get(
                        CONF_ZALO_CONVERSATION_AGENT_ID,
                        DEFAULT_ZALO_CONVERSATION_AGENT_ID,
                    )
                    or DEFAULT_ZALO_CONVERSATION_AGENT_ID
                ).strip(),
                str(
                    values.get(
                        CONF_AI_SEARCH_AGENT_ID,
                        DEFAULT_AI_SEARCH_AGENT_ID,
                    )
                    or ""
                ).strip(),
                str(
                    values.get(
                        CONF_AI_IMAGE_TASK_ENTITY_ID,
                        DEFAULT_AI_IMAGE_TASK_ENTITY_ID,
                    )
                    or ""
                ).strip(),
                str(
                    values.get(
                        CONF_AI_CAMERA_TASK_ENTITY_ID,
                        DEFAULT_AI_CAMERA_TASK_ENTITY_ID,
                    )
                    or ""
                ).strip(),
                str(
                    values.get(
                        CONF_AI_CAMERA_INSTRUCTIONS,
                        DEFAULT_AI_CAMERA_INSTRUCTIONS,
                    )
                    or DEFAULT_AI_CAMERA_INSTRUCTIONS
                ).strip(),
                bool(
                    values.get(
                        CONF_AI_AGENT_FAILOVER_ENABLED,
                        DEFAULT_AI_AGENT_FAILOVER_ENABLED,
                    )
                ),
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return options flow."""
        return ConversationalAssistantOptionsFlow()


class ConversationalAssistantOptionsFlow(config_entries.OptionsFlow):
    """Manage automatic destinations and named Zalo destinations."""

    def __init__(self) -> None:
        """Initialize options flow state."""
        self._options: dict[str, Any] | None = None
        self._editing_target_id: str | None = None
        self._editing_named_target_id: str | None = None

    def _current(self, key: str, default: Any) -> Any:
        """Return option value with config data fallback."""
        return self.config_entry.options.get(
            key,
            self.config_entry.data.get(key, default),
        )

    def _legacy_zalo_target(self) -> dict[str, Any] | None:
        """Migrate the old single-Zalo fields to the new target list."""
        if not bool(self._current(CONF_ZALO_ENABLED, DEFAULT_ZALO_ENABLED)):
            return None
        thread_id = str(self._current(CONF_ZALO_THREAD_ID, "")).strip()
        account_selection = str(
            self._current(CONF_ZALO_ACCOUNT_SELECTION, "")
        ).strip()
        zalo_type = str(self._current(CONF_ZALO_TYPE, DEFAULT_ZALO_TYPE))
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

    def _ensure_options(self) -> dict[str, Any]:
        """Create a mutable options snapshot once for this multi-step flow."""
        if self._options is not None:
            return self._options

        options = deepcopy(dict(self.config_entry.options))
        options.setdefault(
            CONF_DISMISS_ON_CLEAR,
            self.config_entry.data.get(
                CONF_DISMISS_ON_CLEAR, DEFAULT_DISMISS_ON_CLEAR
            ),
        )
        options.setdefault(
            CONF_CONFIRM_TARGETS,
            self.config_entry.data.get(
                CONF_CONFIRM_TARGETS, DEFAULT_CONFIRM_TARGETS
            ),
        )
        options.setdefault(
            CONF_USER_ADDRESS,
            self.config_entry.data.get(
                CONF_USER_ADDRESS, DEFAULT_USER_ADDRESS
            ),
        )
        options.setdefault(
            CONF_ZALO_INVOCATION_KEYWORD_ENABLED,
            self.config_entry.data.get(
                CONF_ZALO_INVOCATION_KEYWORD_ENABLED,
                DEFAULT_ZALO_INVOCATION_KEYWORD_ENABLED,
            ),
        )
        options.setdefault(
            CONF_ZALO_INVOCATION_KEYWORD,
            self.config_entry.data.get(
                CONF_ZALO_INVOCATION_KEYWORD,
                DEFAULT_ZALO_INVOCATION_KEYWORD,
            ),
        )
        options.setdefault(
            CONF_SPEAKER_ENABLED,
            self.config_entry.data.get(
                CONF_SPEAKER_ENABLED, DEFAULT_SPEAKER_ENABLED
            ),
        )
        options.setdefault(
            CONF_CALENDAR_LOOKAHEAD_DAYS,
            self.config_entry.data.get(
                CONF_CALENDAR_LOOKAHEAD_DAYS,
                DEFAULT_CALENDAR_LOOKAHEAD_DAYS,
            ),
        )
        options.setdefault(
            CONF_CALENDAR_ENTITIES,
            self.config_entry.data.get(
                CONF_CALENDAR_ENTITIES,
                list(_calendar_entity_choices(self.hass)),
            ),
        )
        options.setdefault(
            CONF_CALENDAR_NOTIFICATION_ENABLED,
            self.config_entry.data.get(
                CONF_CALENDAR_NOTIFICATION_ENABLED,
                DEFAULT_CALENDAR_NOTIFICATION_ENABLED,
            ),
        )
        options.setdefault(
            CONF_CALENDAR_NOTIFICATION_TIME,
            self.config_entry.data.get(
                CONF_CALENDAR_NOTIFICATION_TIME,
                DEFAULT_CALENDAR_NOTIFICATION_TIME,
            ),
        )
        options.setdefault(
            CONF_CALENDAR_NOTIFICATION_MOBILE_DEVICES,
            self.config_entry.data.get(
                CONF_CALENDAR_NOTIFICATION_MOBILE_DEVICES, []
            ),
        )
        options.setdefault(
            CONF_CALENDAR_NOTIFICATION_ZALO_TARGETS,
            self.config_entry.data.get(
                CONF_CALENDAR_NOTIFICATION_ZALO_TARGETS, []
            ),
        )
        options.setdefault(
            CONF_WEATHER_ENTITY_ID,
            self.config_entry.data.get(
                CONF_WEATHER_ENTITY_ID, DEFAULT_WEATHER_ENTITY_ID
            ),
        )
        options.setdefault(
            CONF_WEATHER_LOCATION,
            self.config_entry.data.get(
                CONF_WEATHER_LOCATION, DEFAULT_WEATHER_LOCATION
            ),
        )
        options.setdefault(
            CONF_WEATHER_FORECAST_ENABLED,
            self.config_entry.data.get(
                CONF_WEATHER_FORECAST_ENABLED,
                DEFAULT_WEATHER_FORECAST_ENABLED,
            ),
        )
        options.setdefault(
            CONF_WEATHER_FORECAST_TIMES,
            self.config_entry.data.get(
                CONF_WEATHER_FORECAST_TIMES,
                list(DEFAULT_WEATHER_FORECAST_TIMES),
            ),
        )
        options.setdefault(
            CONF_WEATHER_FORECAST_DAYS,
            self.config_entry.data.get(
                CONF_WEATHER_FORECAST_DAYS,
                DEFAULT_WEATHER_FORECAST_DAYS,
            ),
        )
        options.setdefault(
            CONF_WEATHER_FORECAST_ZALO_TARGETS,
            self.config_entry.data.get(
                CONF_WEATHER_FORECAST_ZALO_TARGETS, []
            ),
        )
        options.setdefault(
            CONF_WEATHER_STORM_ENABLED,
            self.config_entry.data.get(
                CONF_WEATHER_STORM_ENABLED,
                DEFAULT_WEATHER_STORM_ENABLED,
            ),
        )
        options.setdefault(
            CONF_WEATHER_STORM_TIMES,
            self.config_entry.data.get(
                CONF_WEATHER_STORM_TIMES,
                list(DEFAULT_WEATHER_STORM_TIMES),
            ),
        )
        options.setdefault(
            CONF_WEATHER_STORM_ZALO_TARGETS,
            self.config_entry.data.get(
                CONF_WEATHER_STORM_ZALO_TARGETS, []
            ),
        )
        options.setdefault(
            CONF_TTS_ENTITY_ID,
            self.config_entry.data.get(
                CONF_TTS_ENTITY_ID, _first_tts_entity_id(self.hass)
            ),
        )
        options.setdefault(
            CONF_TTS_LANGUAGE,
            self.config_entry.data.get(
                CONF_TTS_LANGUAGE, DEFAULT_TTS_LANGUAGE
            ),
        )
        options.setdefault(
            CONF_TTS_VOICE,
            self.config_entry.data.get(CONF_TTS_VOICE, DEFAULT_TTS_VOICE),
        )
        options.setdefault(
            CONF_ZALO_WEBHOOK_ENABLED,
            self.config_entry.data.get(
                CONF_ZALO_WEBHOOK_ENABLED, DEFAULT_ZALO_WEBHOOK_ENABLED
            ),
        )
        options.setdefault(
            CONF_ZALO_WEBHOOK_BOT_ACCOUNT_ID,
            self.config_entry.data.get(
                CONF_ZALO_WEBHOOK_BOT_ACCOUNT_ID,
                DEFAULT_ZALO_WEBHOOK_BOT_ACCOUNT_ID,
            ),
        )
        options.setdefault(
            CONF_ZALO_WEBHOOK_ACCOUNT_SELECTION,
            self.config_entry.data.get(
                CONF_ZALO_WEBHOOK_ACCOUNT_SELECTION, ""
            ),
        )
        options.setdefault(
            CONF_ZALO_HOME_ASSISTANT_ENABLED,
            self.config_entry.data.get(
                CONF_ZALO_HOME_ASSISTANT_ENABLED,
                DEFAULT_ZALO_HOME_ASSISTANT_ENABLED,
            ),
        )
        options.setdefault(
            CONF_ZALO_CONVERSATION_AGENT_ID,
            self.config_entry.data.get(
                CONF_ZALO_CONVERSATION_AGENT_ID,
                DEFAULT_ZALO_CONVERSATION_AGENT_ID,
            ),
        )
        options.setdefault(
            CONF_AI_SEARCH_AGENT_ID,
            self.config_entry.data.get(
                CONF_AI_SEARCH_AGENT_ID, DEFAULT_AI_SEARCH_AGENT_ID
            ),
        )
        options.setdefault(
            CONF_AI_IMAGE_TASK_ENTITY_ID,
            self.config_entry.data.get(
                CONF_AI_IMAGE_TASK_ENTITY_ID,
                DEFAULT_AI_IMAGE_TASK_ENTITY_ID,
            ),
        )
        options.setdefault(
            CONF_AI_CAMERA_TASK_ENTITY_ID,
            self.config_entry.data.get(
                CONF_AI_CAMERA_TASK_ENTITY_ID,
                DEFAULT_AI_CAMERA_TASK_ENTITY_ID,
            ),
        )
        options.setdefault(
            CONF_AI_CAMERA_INSTRUCTIONS,
            self.config_entry.data.get(
                CONF_AI_CAMERA_INSTRUCTIONS,
                DEFAULT_AI_CAMERA_INSTRUCTIONS,
            ),
        )
        options.setdefault(
            CONF_AI_AGENT_FAILOVER_ENABLED,
            self.config_entry.data.get(
                CONF_AI_AGENT_FAILOVER_ENABLED,
                DEFAULT_AI_AGENT_FAILOVER_ENABLED,
            ),
        )
        for list_key, reference_key in (
            (CONF_MOBILE_TARGETS, CONF_MOBILE_DEVICE_ID),
            (CONF_SPEAKER_TARGETS, CONF_SPEAKER_ENTITY_ID),
            (CONF_CAMERA_TARGETS, CONF_CAMERA_ENTITY_ID),
        ):
            if list_key in options:
                options[list_key] = normalize_named_target_list(
                    options[list_key], reference_key=reference_key
                )
                continue
            data_targets = self.config_entry.data.get(list_key)
            if isinstance(data_targets, list):
                options[list_key] = normalize_named_target_list(
                    deepcopy(data_targets), reference_key=reference_key
                )

        if CONF_ZALO_TARGETS not in options:
            data_targets = self.config_entry.data.get(CONF_ZALO_TARGETS)
            if isinstance(data_targets, list):
                options[CONF_ZALO_TARGETS] = deepcopy(data_targets)
            else:
                legacy = self._legacy_zalo_target()
                options[CONF_ZALO_TARGETS] = [legacy] if legacy else []

        self._options = options
        return options

    def _zalo_targets(self) -> list[dict[str, Any]]:
        """Return the mutable target list."""
        options = self._ensure_options()
        value = options.setdefault(CONF_ZALO_TARGETS, [])
        if not isinstance(value, list):
            value = []
            options[CONF_ZALO_TARGETS] = value
        return value

    @staticmethod
    def _named_target_spec(kind: str) -> tuple[str, str]:
        """Return list and reference keys for one configured target kind."""
        specs = {
            "mobile": (CONF_MOBILE_TARGETS, CONF_MOBILE_DEVICE_ID),
            "speaker": (CONF_SPEAKER_TARGETS, CONF_SPEAKER_ENTITY_ID),
            "camera": (CONF_CAMERA_TARGETS, CONF_CAMERA_ENTITY_ID),
        }
        return specs[kind]

    def _named_targets(
        self, kind: str, *, explicit: bool = True
    ) -> list[dict[str, Any]]:
        """Return configured targets; optionally mark the list explicit."""
        list_key, reference_key = self._named_target_spec(kind)
        options = self._ensure_options()
        if list_key not in options and not explicit:
            return []
        value = normalize_named_target_list(
            options.get(list_key, []), reference_key=reference_key
        )
        if explicit:
            options[list_key] = value
        return value

    def _named_target_schema_for_kind(
        self, kind: str, target: dict[str, Any] | None = None
    ) -> vol.Schema:
        """Return the correct selector form for a named target kind."""
        if kind == "mobile":
            return _mobile_target_schema(self.hass, target)
        if kind == "speaker":
            return _entity_target_schema(
                "media_player", CONF_SPEAKER_ENTITY_ID, target
            )
        return _entity_target_schema("camera", CONF_CAMERA_ENTITY_ID, target)

    async def _async_named_targets_menu(self, kind: str) -> ConfigFlowResult:
        """Show add/edit/delete navigation for one named target kind."""
        targets = self._named_targets(kind, explicit=False)
        menu_options = [f"add_{kind}_target"]
        if targets:
            menu_options.extend(
                [f"edit_{kind}_target_select", f"delete_{kind}_target"]
            )
        menu_options.append("general")
        return self.async_show_menu(
            step_id=f"{kind}_targets",
            menu_options=menu_options,
            description_placeholders={"target_count": str(len(targets))},
        )

    async def _async_add_named_target(
        self, kind: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Add one named Mobile, speaker, or camera target."""
        targets = self._named_targets(
            kind, explicit=user_input is not None
        )
        _list_key, reference_key = self._named_target_spec(kind)
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = named_target_errors(
                user_input, reference_key=reference_key, existing=targets
            )
            if not errors:
                targets.append(
                    make_named_target(user_input, reference_key=reference_key)
                )
                return await self._async_named_targets_menu(kind)
        return self.async_show_form(
            step_id=f"add_{kind}_target",
            data_schema=self._named_target_schema_for_kind(kind, user_input),
            errors=errors,
        )

    async def _async_select_named_target(
        self, kind: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Select one configured target to edit."""
        targets = self._named_targets(kind)
        choices = {
            str(item[CONF_NAMED_TARGET_ID]): str(item[CONF_NAMED_TARGET_NAME])
            for item in targets
        }
        if user_input is not None:
            self._editing_named_target_id = str(
                user_input[CONF_SELECTED_NAMED_TARGET]
            )
            return await self._async_edit_named_target(kind, None)
        return self.async_show_form(
            step_id=f"edit_{kind}_target_select",
            data_schema=vol.Schema(
                {vol.Required(CONF_SELECTED_NAMED_TARGET): vol.In(choices)}
            ),
        )

    async def _async_edit_named_target(
        self, kind: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Edit one configured named target."""
        targets = self._named_targets(kind)
        _list_key, reference_key = self._named_target_spec(kind)
        target = next(
            (
                item
                for item in targets
                if str(item.get(CONF_NAMED_TARGET_ID, ""))
                == str(self._editing_named_target_id or "")
            ),
            None,
        )
        if target is None:
            return await self._async_named_targets_menu(kind)
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = named_target_errors(
                user_input,
                reference_key=reference_key,
                existing=targets,
                editing_target_id=str(target[CONF_NAMED_TARGET_ID]),
            )
            if not errors:
                replacement = make_named_target(
                    user_input,
                    reference_key=reference_key,
                    target_id=str(target[CONF_NAMED_TARGET_ID]),
                )
                targets[targets.index(target)] = replacement
                self._editing_named_target_id = None
                return await self._async_named_targets_menu(kind)
        return self.async_show_form(
            step_id=f"edit_{kind}_target",
            data_schema=self._named_target_schema_for_kind(
                kind, target if user_input is None else user_input
            ),
            errors=errors,
        )

    async def _async_delete_named_target(
        self, kind: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Delete one configured named target."""
        targets = self._named_targets(kind)
        choices = {
            str(item[CONF_NAMED_TARGET_ID]): str(item[CONF_NAMED_TARGET_NAME])
            for item in targets
        }
        if user_input is not None:
            selected = str(user_input[CONF_SELECTED_NAMED_TARGET])
            list_key, _reference_key = self._named_target_spec(kind)
            self._ensure_options()[list_key] = [
                item
                for item in targets
                if str(item.get(CONF_NAMED_TARGET_ID, "")) != selected
            ]
            return await self._async_named_targets_menu(kind)
        return self.async_show_form(
            step_id=f"delete_{kind}_target",
            data_schema=vol.Schema(
                {vol.Required(CONF_SELECTED_NAMED_TARGET): vol.In(choices)}
            ),
        )

    async def async_step_init(
        self, _user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options navigation menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "general",
                "calendar",
                "weather",
                "zalo",
                "ai",
                "tts",
                "finish",
            ],
            description_placeholders={
                "zalo_count": str(len(self._zalo_targets()))
            },
        )

    async def async_step_general(
        self, _user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show shared behavior and named target configuration."""
        return self.async_show_menu(
            step_id="general",
            menu_options=[
                "general_behavior",
                "mobile_targets",
                "zalo",
                "speaker_targets",
                "camera_targets",
                "init",
            ],
            description_placeholders={
                "mobile_count": str(
                    len(self._named_targets("mobile", explicit=False))
                ),
                "zalo_count": str(len(self._zalo_targets())),
                "speaker_count": str(
                    len(self._named_targets("speaker", explicit=False))
                ),
                "camera_count": str(
                    len(self._named_targets("camera", explicit=False))
                ),
            },
        )

    async def async_step_general_behavior(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit shared confirmation and notification settings."""
        options = self._ensure_options()
        if user_input is not None:
            options.update(_normalize_general_settings(user_input))
            return await self.async_step_general()

        values = options
        return self.async_show_form(
            step_id="general_behavior",
            data_schema=_general_settings_schema(
                bool(
                    values.get(
                        CONF_DISMISS_ON_CLEAR, DEFAULT_DISMISS_ON_CLEAR
                    )
                ),
                bool(
                    values.get(CONF_CONFIRM_TARGETS, DEFAULT_CONFIRM_TARGETS)
                ),
                str(
                    values.get(CONF_USER_ADDRESS, DEFAULT_USER_ADDRESS)
                    or DEFAULT_USER_ADDRESS
                ).strip(),
            ),
        )

    async def async_step_mobile_targets(
        self, _user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_named_targets_menu("mobile")

    async def async_step_speaker_targets(
        self, _user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_named_targets_menu("speaker")

    async def async_step_camera_targets(
        self, _user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_named_targets_menu("camera")

    async def async_step_add_mobile_target(self, user_input=None):
        return await self._async_add_named_target("mobile", user_input)

    async def async_step_edit_mobile_target_select(self, user_input=None):
        return await self._async_select_named_target("mobile", user_input)

    async def async_step_edit_mobile_target(self, user_input=None):
        return await self._async_edit_named_target("mobile", user_input)

    async def async_step_delete_mobile_target(self, user_input=None):
        return await self._async_delete_named_target("mobile", user_input)

    async def async_step_add_speaker_target(self, user_input=None):
        return await self._async_add_named_target("speaker", user_input)

    async def async_step_edit_speaker_target_select(self, user_input=None):
        return await self._async_select_named_target("speaker", user_input)

    async def async_step_edit_speaker_target(self, user_input=None):
        return await self._async_edit_named_target("speaker", user_input)

    async def async_step_delete_speaker_target(self, user_input=None):
        return await self._async_delete_named_target("speaker", user_input)

    async def async_step_add_camera_target(self, user_input=None):
        return await self._async_add_named_target("camera", user_input)

    async def async_step_edit_camera_target_select(self, user_input=None):
        return await self._async_select_named_target("camera", user_input)

    async def async_step_edit_camera_target(self, user_input=None):
        return await self._async_edit_named_target("camera", user_input)

    async def async_step_delete_camera_target(self, user_input=None):
        return await self._async_delete_named_target("camera", user_input)

    async def async_step_calendar(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit calendar sensor horizon and scheduled alert destinations."""
        options = self._ensure_options()
        if user_input is not None:
            options.update(_normalize_calendar_settings(user_input))
            # Calendar scheduling is time-sensitive. Persist immediately so the
            # integration reloads and registers the new daily timer as soon as
            # the user presses Submit; no separate Finish step is required.
            return self.async_create_entry(title="", data=options)

        calendar_choices = _calendar_entity_choices(self.hass)
        if CONF_MOBILE_TARGETS in options:
            mobile_choices = {
                str(item.get(CONF_MOBILE_DEVICE_ID, "")): str(
                    item.get(CONF_NAMED_TARGET_NAME, "")
                )
                for item in self._named_targets("mobile", explicit=False)
                if bool(item.get(CONF_NAMED_TARGET_ENABLED, True))
                and str(item.get(CONF_MOBILE_DEVICE_ID, ""))
            }
        else:
            mobile_choices = _mobile_device_choices(self.hass)
        zalo_choices = _zalo_target_choices(self._zalo_targets())
        values = _normalize_calendar_settings(options)
        return self.async_show_form(
            step_id="calendar",
            data_schema=_calendar_settings_schema(
                int(values[CONF_CALENDAR_LOOKAHEAD_DAYS]),
                list(values[CONF_CALENDAR_ENTITIES]),
                bool(values[CONF_CALENDAR_NOTIFICATION_ENABLED]),
                str(values[CONF_CALENDAR_NOTIFICATION_TIME]),
                list(values[CONF_CALENDAR_NOTIFICATION_MOBILE_DEVICES]),
                list(values[CONF_CALENDAR_NOTIFICATION_ZALO_TARGETS]),
                calendar_choices,
                mobile_choices,
                zalo_choices,
            ),
            description_placeholders={
                "calendar_count": str(len(calendar_choices)),
                "mobile_count": str(len(mobile_choices)),
                "zalo_count": str(len(zalo_choices)),
            },
        )

    async def async_step_weather(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit scheduled forecast and Vietnam storm-alert settings."""
        options = self._ensure_options()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_weather_settings(user_input)
            if not errors:
                options.update(_normalize_weather_settings(user_input))
                # Scheduling changes must take effect immediately after Submit.
                return self.async_create_entry(title="", data=options)

        values = user_input or options
        normalized = _normalize_weather_settings(values)
        zalo_choices = _zalo_target_choices(self._zalo_targets())
        return self.async_show_form(
            step_id="weather",
            data_schema=_weather_settings_schema(
                str(
                    normalized.get(CONF_WEATHER_ENTITY_ID, "")
                    or _first_weather_entity_id(self.hass)
                    or ""
                ),
                str(normalized.get(CONF_WEATHER_LOCATION, "") or ""),
                bool(normalized[CONF_WEATHER_FORECAST_ENABLED]),
                values.get(
                    CONF_WEATHER_FORECAST_TIMES,
                    DEFAULT_WEATHER_FORECAST_TIMES,
                ),
                int(normalized[CONF_WEATHER_FORECAST_DAYS]),
                list(normalized[CONF_WEATHER_FORECAST_ZALO_TARGETS]),
                bool(normalized[CONF_WEATHER_STORM_ENABLED]),
                values.get(
                    CONF_WEATHER_STORM_TIMES,
                    DEFAULT_WEATHER_STORM_TIMES,
                ),
                list(normalized[CONF_WEATHER_STORM_ZALO_TARGETS]),
                zalo_choices,
            ),
            errors=errors,
            description_placeholders={
                "zalo_count": str(len(zalo_choices)),
                "weather_count": str(_weather_entity_count(self.hass)),
            },
        )

    async def async_step_zalo(
        self, _user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show all Zalo-related settings in one submenu."""
        menu_options = ["zalo_webhook", "add_zalo"]
        if self._zalo_targets():
            menu_options.extend(["edit_zalo_select", "delete_zalo"])
        menu_options.extend(["general", "init"])
        return self.async_show_menu(
            step_id="zalo",
            menu_options=menu_options,
            description_placeholders={
                "zalo_count": str(len(self._zalo_targets()))
            },
        )

    async def async_step_zalo_webhook(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit global Zalo webhook and Home Assistant routing settings."""
        options = self._ensure_options()
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = _normalize_zalo_settings(user_input)
            errors = _validate_zalo_settings(user_input)
            if not errors:
                options.update(user_input)
                return await self.async_step_zalo()

        values = user_input or options
        return self.async_show_form(
            step_id="zalo_webhook",
            data_schema=_zalo_settings_schema(
                bool(
                    values.get(
                        CONF_ZALO_WEBHOOK_ENABLED,
                        DEFAULT_ZALO_WEBHOOK_ENABLED,
                    )
                ),
                str(
                    values.get(
                        CONF_ZALO_WEBHOOK_BOT_ACCOUNT_ID,
                        DEFAULT_ZALO_WEBHOOK_BOT_ACCOUNT_ID,
                    )
                    or ""
                ).strip(),
                str(
                    values.get(CONF_ZALO_WEBHOOK_ACCOUNT_SELECTION, "")
                    or ""
                ).strip(),
                bool(
                    values.get(
                        CONF_ZALO_HOME_ASSISTANT_ENABLED,
                        DEFAULT_ZALO_HOME_ASSISTANT_ENABLED,
                    )
                ),
                bool(
                    values.get(
                        CONF_ZALO_INVOCATION_KEYWORD_ENABLED,
                        DEFAULT_ZALO_INVOCATION_KEYWORD_ENABLED,
                    )
                ),
                str(
                    values.get(
                        CONF_ZALO_INVOCATION_KEYWORD,
                        DEFAULT_ZALO_INVOCATION_KEYWORD,
                    )
                    or ""
                ).strip(),
            ),
            errors=errors,
        )

    async def async_step_ai(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit all AI agent settings."""
        options = self._ensure_options()
        if user_input is not None:
            user_input = _normalize_ai_settings(user_input)
            options.update(user_input)
            if not user_input.get(CONF_AI_SEARCH_AGENT_ID):
                options.pop(CONF_AI_SEARCH_AGENT_ID, None)
            if not user_input.get(CONF_AI_IMAGE_TASK_ENTITY_ID):
                options.pop(CONF_AI_IMAGE_TASK_ENTITY_ID, None)
            if not user_input.get(CONF_AI_CAMERA_TASK_ENTITY_ID):
                options.pop(CONF_AI_CAMERA_TASK_ENTITY_ID, None)
            return await self.async_step_init()

        values = user_input or options
        return self.async_show_form(
            step_id="ai",
            data_schema=_ai_settings_schema(
                str(
                    values.get(
                        CONF_ZALO_CONVERSATION_AGENT_ID,
                        DEFAULT_ZALO_CONVERSATION_AGENT_ID,
                    )
                    or DEFAULT_ZALO_CONVERSATION_AGENT_ID
                ).strip(),
                str(
                    values.get(
                        CONF_AI_SEARCH_AGENT_ID,
                        DEFAULT_AI_SEARCH_AGENT_ID,
                    )
                    or ""
                ).strip(),
                str(
                    values.get(
                        CONF_AI_IMAGE_TASK_ENTITY_ID,
                        DEFAULT_AI_IMAGE_TASK_ENTITY_ID,
                    )
                    or ""
                ).strip(),
                str(
                    values.get(
                        CONF_AI_CAMERA_TASK_ENTITY_ID,
                        DEFAULT_AI_CAMERA_TASK_ENTITY_ID,
                    )
                    or ""
                ).strip(),
                str(
                    values.get(
                        CONF_AI_CAMERA_INSTRUCTIONS,
                        DEFAULT_AI_CAMERA_INSTRUCTIONS,
                    )
                    or DEFAULT_AI_CAMERA_INSTRUCTIONS
                ).strip(),
                bool(
                    values.get(
                        CONF_AI_AGENT_FAILOVER_ENABLED,
                        DEFAULT_AI_AGENT_FAILOVER_ENABLED,
                    )
                ),
            ),
        )

    async def async_step_tts(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit speaker discovery and TTS settings."""
        options = self._ensure_options()
        if user_input is not None:
            normalized = _normalize_tts_settings(user_input)
            options.update(normalized)
            if CONF_TTS_ENTITY_ID not in user_input:
                options.pop(CONF_TTS_ENTITY_ID, None)
            return await self.async_step_init()

        values = user_input or options
        return self.async_show_form(
            step_id="tts",
            data_schema=_tts_settings_schema(
                bool(
                    values.get(
                        CONF_SPEAKER_ENABLED, DEFAULT_SPEAKER_ENABLED
                    )
                ),
                str(values.get(CONF_TTS_ENTITY_ID) or "").strip()
                or _first_tts_entity_id(self.hass),
                str(
                    values.get(CONF_TTS_LANGUAGE, DEFAULT_TTS_LANGUAGE)
                    or ""
                ).strip(),
                str(
                    values.get(CONF_TTS_VOICE, DEFAULT_TTS_VOICE)
                    or ""
                ).strip(),
            ),
        )

    async def async_step_add_zalo(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add one named Zalo destination."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_zalo(
                user_input, existing=self._zalo_targets()
            )
            if not errors:
                self._zalo_targets().append(_make_zalo_target(user_input))
                return await self.async_step_zalo()

        return self.async_show_form(
            step_id="add_zalo",
            data_schema=_zalo_schema(user_input),
            errors=errors,
        )

    async def async_step_edit_zalo_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a Zalo destination to edit."""
        targets = self._zalo_targets()
        choices = {
            str(target.get(CONF_ZALO_TARGET_ID)): str(
                target.get(CONF_ZALO_TARGET_NAME, target.get(CONF_ZALO_THREAD_ID))
            )
            for target in targets
        }
        if user_input is not None:
            self._editing_target_id = str(
                user_input[CONF_SELECTED_ZALO_TARGET]
            )
            return await self.async_step_edit_zalo()

        return self.async_show_form(
            step_id="edit_zalo_select",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SELECTED_ZALO_TARGET): vol.In(choices),
                }
            ),
        )

    async def async_step_edit_zalo(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit a selected Zalo destination."""
        target = next(
            (
                item
                for item in self._zalo_targets()
                if str(item.get(CONF_ZALO_TARGET_ID))
                == self._editing_target_id
            ),
            None,
        )
        if target is None:
            return await self.async_step_zalo()

        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_zalo(
                user_input,
                existing=self._zalo_targets(),
                editing_target_id=str(target[CONF_ZALO_TARGET_ID]),
            )
            if not errors:
                replacement = _make_zalo_target(
                    user_input, str(target[CONF_ZALO_TARGET_ID])
                )
                index = self._zalo_targets().index(target)
                self._zalo_targets()[index] = replacement
                self._editing_target_id = None
                return await self.async_step_zalo()

        return self.async_show_form(
            step_id="edit_zalo",
            data_schema=_zalo_schema(target if user_input is None else user_input),
            errors=errors,
        )

    async def async_step_delete_zalo(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Delete a Zalo destination."""
        targets = self._zalo_targets()
        choices = {
            str(target.get(CONF_ZALO_TARGET_ID)): str(
                target.get(CONF_ZALO_TARGET_NAME, target.get(CONF_ZALO_THREAD_ID))
            )
            for target in targets
        }
        if user_input is not None:
            selected = str(user_input[CONF_SELECTED_ZALO_TARGET])
            self._ensure_options()[CONF_ZALO_TARGETS] = [
                target
                for target in targets
                if str(target.get(CONF_ZALO_TARGET_ID)) != selected
            ]
            selected_calendar_targets = self._ensure_options().get(
                CONF_CALENDAR_NOTIFICATION_ZALO_TARGETS, []
            )
            if isinstance(selected_calendar_targets, list):
                self._ensure_options()[
                    CONF_CALENDAR_NOTIFICATION_ZALO_TARGETS
                ] = [
                    target_id
                    for target_id in selected_calendar_targets
                    if str(target_id) != selected
                ]
            return await self.async_step_zalo()

        return self.async_show_form(
            step_id="delete_zalo",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SELECTED_ZALO_TARGET): vol.In(choices),
                }
            ),
        )

    async def async_step_finish(
        self, _user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Persist all changes and reload the integration."""
        return self.async_create_entry(title="", data=self._ensure_options())
