"""Config flow for Conversational Assistant."""

from __future__ import annotations

from copy import deepcopy
from datetime import time
from typing import Any
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
    CONF_AI_CAMERA_TASK_ENTITY_ID,
    CONF_AI_IMAGE_TASK_ENTITY_ID,
    CONF_AI_SEARCH_AGENT_ID,
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
    DEFAULT_AI_AGENT_FAILOVER_ENABLED,
    DEFAULT_AI_CAMERA_TASK_ENTITY_ID,
    DEFAULT_AI_IMAGE_TASK_ENTITY_ID,
    DEFAULT_AI_SEARCH_AGENT_ID,
    DEFAULT_CALENDAR_LOOKAHEAD_DAYS,
    DEFAULT_CALENDAR_NOTIFICATION_ENABLED,
    DEFAULT_CALENDAR_NOTIFICATION_TIME,
    DEFAULT_CONFIRM_TARGETS,
    DEFAULT_DISMISS_ON_CLEAR,
    DEFAULT_SPEAKER_ENABLED,
    DEFAULT_ZALO_ENABLED,
    DEFAULT_ZALO_CONVERSATION_AGENT_ID,
    DEFAULT_ZALO_HOME_ASSISTANT_ENABLED,
    DEFAULT_ZALO_TYPE,
    DEFAULT_ZALO_WEBHOOK_BOT_ACCOUNT_ID,
    DEFAULT_ZALO_WEBHOOK_ENABLED,
    DOMAIN,
    INTEGRATION_NAME,
    MAX_CALENDAR_LOOKAHEAD_DAYS,
    ZALO_TYPE_GROUP,
    ZALO_TYPE_USER,
)

CONF_SELECTED_ZALO_TARGET = "selected_zalo_target"


def _general_settings_schema(
    dismiss_on_clear: bool,
    confirm_targets: bool,
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
        }
    )


def _zalo_settings_schema(
    zalo_webhook_enabled: bool,
    zalo_webhook_bot_account_id: str,
    zalo_webhook_account_selection: str,
    zalo_home_assistant_enabled: bool,
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
    return vol.Schema(fields)


def _tts_settings_schema(
    speaker_enabled: bool,
    tts_entity_id: str | None,
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
    notification_enabled: bool,
    notification_time: str,
    selected_mobile_devices: list[str],
    selected_zalo_targets: list[str],
    mobile_choices: dict[str, str],
    zalo_choices: dict[str, str],
) -> vol.Schema:
    """Build calendar sensor and scheduled notification settings."""
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
        CONF_CALENDAR_NOTIFICATION_MOBILE_DEVICES,
        CONF_CALENDAR_NOTIFICATION_ZALO_TARGETS,
    ):
        value = normalized.get(key, [])
        if isinstance(value, (list, tuple, set)):
            normalized[key] = [
                str(item).strip() for item in value if str(item).strip()
            ]
        elif value:
            normalized[key] = [str(value).strip()]
        else:
            normalized[key] = []
    return normalized


def _merge_schemas(*schemas: vol.Schema) -> vol.Schema:
    """Merge multiple Voluptuous schemas while preserving field order."""
    fields: dict[Any, Any] = {}
    for schema in schemas:
        fields.update(schema.schema)
    return vol.Schema(fields)


def _initial_schema(
    dismiss_on_clear: bool,
    confirm_targets: bool,
    speaker_enabled: bool,
    tts_entity_id: str | None,
    zalo_webhook_enabled: bool,
    zalo_webhook_bot_account_id: str,
    zalo_webhook_account_selection: str,
    zalo_home_assistant_enabled: bool,
    zalo_conversation_agent_id: str,
    ai_search_agent_id: str,
    ai_image_task_entity_id: str,
    ai_camera_task_entity_id: str,
    ai_agent_failover_enabled: bool,
) -> vol.Schema:
    """Build the initial installation form with all setting groups."""
    return _merge_schemas(
        _general_settings_schema(dismiss_on_clear, confirm_targets),
        _zalo_settings_schema(
            zalo_webhook_enabled,
            zalo_webhook_bot_account_id,
            zalo_webhook_account_selection,
            zalo_home_assistant_enabled,
        ),
        _ai_settings_schema(
            zalo_conversation_agent_id,
            ai_search_agent_id,
            ai_image_task_entity_id,
            ai_camera_task_entity_id,
            ai_agent_failover_enabled,
        ),
        _tts_settings_schema(speaker_enabled, tts_entity_id),
    )


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
    normalized[CONF_AI_AGENT_FAILOVER_ENABLED] = bool(
        normalized.get(
            CONF_AI_AGENT_FAILOVER_ENABLED,
            DEFAULT_AI_AGENT_FAILOVER_ENABLED,
        )
    )
    return normalized


def _normalize_initial(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize all text values from the initial installation form."""
    return _normalize_ai_settings(_normalize_zalo_settings(user_input))


def _first_tts_entity_id(hass) -> str | None:
    """Return the first currently registered TTS entity, if any."""
    entity_ids = sorted(state.entity_id for state in hass.states.async_all("tts"))
    return entity_ids[0] if entity_ids else None


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


def _validate_zalo(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate a Zalo destination."""
    errors: dict[str, str] = {}
    if not str(user_input.get(CONF_ZALO_TARGET_NAME, "")).strip():
        errors[CONF_ZALO_TARGET_NAME] = "required"
    if not str(user_input.get(CONF_ZALO_THREAD_ID, "")).strip():
        errors[CONF_ZALO_THREAD_ID] = "required"
    if not str(user_input.get(CONF_ZALO_ACCOUNT_SELECTION, "")).strip():
        errors[CONF_ZALO_ACCOUNT_SELECTION] = "required"
    return errors


def _make_zalo_target(
    user_input: dict[str, Any], target_id: str | None = None
) -> dict[str, Any]:
    """Normalize a Zalo target for config entry options."""
    return {
        CONF_ZALO_TARGET_ID: target_id or uuid.uuid4().hex,
        CONF_ZALO_TARGET_NAME: str(
            user_input[CONF_ZALO_TARGET_NAME]
        ).strip(),
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
                bool(
                    values.get(
                        CONF_SPEAKER_ENABLED,
                        DEFAULT_SPEAKER_ENABLED,
                    )
                ),
                str(values.get(CONF_TTS_ENTITY_ID) or "").strip()
                or _first_tts_entity_id(self.hass),
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
            CONF_TTS_ENTITY_ID,
            self.config_entry.data.get(
                CONF_TTS_ENTITY_ID, _first_tts_entity_id(self.hass)
            ),
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
            CONF_AI_AGENT_FAILOVER_ENABLED,
            self.config_entry.data.get(
                CONF_AI_AGENT_FAILOVER_ENABLED,
                DEFAULT_AI_AGENT_FAILOVER_ENABLED,
            ),
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

    async def async_step_init(
        self, _user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options navigation menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["general", "calendar", "zalo", "ai", "tts", "finish"],
            description_placeholders={
                "zalo_count": str(len(self._zalo_targets()))
            },
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit general discovery and voice-confirmation settings."""
        options = self._ensure_options()
        if user_input is not None:
            options.update(user_input)
            return await self.async_step_init()

        values = user_input or options

        return self.async_show_form(
            step_id="general",
            data_schema=_general_settings_schema(
                bool(
                    values.get(
                        CONF_DISMISS_ON_CLEAR, DEFAULT_DISMISS_ON_CLEAR
                    )
                ),
                bool(
                    values.get(CONF_CONFIRM_TARGETS, DEFAULT_CONFIRM_TARGETS)
                ),
            ),
        )

    async def async_step_calendar(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit calendar sensor horizon and scheduled alert destinations."""
        options = self._ensure_options()
        if user_input is not None:
            options.update(_normalize_calendar_settings(user_input))
            return await self.async_step_init()

        mobile_choices = _mobile_device_choices(self.hass)
        zalo_choices = _zalo_target_choices(self._zalo_targets())
        values = _normalize_calendar_settings(options)
        return self.async_show_form(
            step_id="calendar",
            data_schema=_calendar_settings_schema(
                int(values[CONF_CALENDAR_LOOKAHEAD_DAYS]),
                bool(values[CONF_CALENDAR_NOTIFICATION_ENABLED]),
                str(values[CONF_CALENDAR_NOTIFICATION_TIME]),
                list(values[CONF_CALENDAR_NOTIFICATION_MOBILE_DEVICES]),
                list(values[CONF_CALENDAR_NOTIFICATION_ZALO_TARGETS]),
                mobile_choices,
                zalo_choices,
            ),
            description_placeholders={
                "mobile_count": str(len(mobile_choices)),
                "zalo_count": str(len(zalo_choices)),
            },
        )

    async def async_step_zalo(
        self, _user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show all Zalo-related settings in one submenu."""
        menu_options = ["zalo_webhook", "add_zalo"]
        if self._zalo_targets():
            menu_options.extend(["edit_zalo_select", "delete_zalo"])
        menu_options.append("init")
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
            options.update(user_input)
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
            ),
        )

    async def async_step_add_zalo(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add one named Zalo destination."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_zalo(user_input)
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
            errors = _validate_zalo(user_input)
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
