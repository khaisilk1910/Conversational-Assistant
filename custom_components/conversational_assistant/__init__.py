"""Conversational Assistant integration."""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_ZALO_PAYLOAD,
    CONF_NOTIFICATION_DEVICES,
    DOMAIN,
    INTEGRATION_NAME,
    PLATFORMS,
    SERVICE_PROCESS_ZALO_WEBHOOK,
)
from .manager import ConversationalAssistantManager

_LOGGER = logging.getLogger(__name__)

_PROCESS_ZALO_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ZALO_PAYLOAD): vol.Any(dict, str),
        vol.Optional(ATTR_CONFIG_ENTRY_ID): str,
    }
)


def _loaded_manager(
    hass: HomeAssistant, config_entry_id: str | None
) -> ConversationalAssistantManager:
    """Return the requested loaded manager, or the sole loaded instance."""
    if config_entry_id:
        entry = hass.config_entries.async_get_entry(config_entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(
                "Không tìm thấy cấu hình Conversational Assistant được yêu cầu"
            )
        entries = [entry]
    else:
        entries = hass.config_entries.async_entries(DOMAIN)

    loaded = [
        entry for entry in entries if entry.state is ConfigEntryState.LOADED
    ]
    if not loaded:
        raise ServiceValidationError(
            "Conversational Assistant chưa được tải hoặc chưa được cấu hình"
        )
    if len(loaded) > 1:
        raise ServiceValidationError(
            "Có nhiều cấu hình Conversational Assistant; hãy truyền config_entry_id"
        )

    manager = loaded[0].runtime_data
    if not isinstance(manager, ConversationalAssistantManager):
        raise ServiceValidationError("Conversational Assistant chưa sẵn sàng")
    return manager


def _normalize_payload(value: Any) -> dict[str, Any]:
    """Accept either trigger.json as an object or a JSON string."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as err:
            raise ServiceValidationError("Payload không phải JSON hợp lệ") from err
        if isinstance(decoded, dict):
            return decoded
    raise ServiceValidationError("Payload Zalo phải là một JSON object")


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Register core integration actions; optional HTTP helpers must never block setup."""

    async def async_process_zalo_webhook(call: ServiceCall) -> None:
        manager = _loaded_manager(
            hass,
            str(call.data.get(ATTR_CONFIG_ENTRY_ID, "")).strip() or None,
        )
        payload = _normalize_payload(call.data[ATTR_ZALO_PAYLOAD])
        result = await manager.async_process_zalo_webhook_payload(
            payload, call.context
        )
        _LOGGER.debug("Processed existing Zalo webhook payload: %s", result)

    # Register the critical Zalo action first.  Optional YouTube HTTP proxy
    # setup must never be able to remove the integration's core actions.
    hass.services.async_register(
        DOMAIN,
        SERVICE_PROCESS_ZALO_WEBHOOK,
        async_process_zalo_webhook,
        schema=_PROCESS_ZALO_SCHEMA,
    )

    try:
        from .youtube_proxy import async_setup_youtube_audio_proxy

        async_setup_youtube_audio_proxy(hass)
    except Exception:  # noqa: BLE001 - optional helper must not block integration
        _LOGGER.exception(
            "YouTube audio proxy setup failed; core Conversational Assistant "
            "services will remain available"
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Conversational Assistant from a config entry."""
    updated_data = dict(entry.data)
    updated_options = dict(entry.options)
    changed = False
    for obsolete_key in ("zalo_webhook_id", CONF_NOTIFICATION_DEVICES):
        if obsolete_key in updated_data:
            updated_data.pop(obsolete_key, None)
            changed = True
        if obsolete_key in updated_options:
            updated_options.pop(obsolete_key, None)
            changed = True
    if changed or entry.title != INTEGRATION_NAME:
        hass.config_entries.async_update_entry(
            entry,
            data=updated_data,
            options=updated_options,
            title=INTEGRATION_NAME,
        )

    manager = ConversationalAssistantManager(hass, entry)
    entry.runtime_data = manager
    try:
        await manager.async_setup()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        # Do not leave listeners, timers, entities, or background tasks behind
        # when a config-entry setup fails part-way through. Cleanup failures
        # must not hide the original setup exception.
        try:
            await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        except Exception:  # noqa: BLE001 - best effort after setup failure
            _LOGGER.debug(
                "Failed unloading partially set up platforms for %s",
                entry.entry_id,
                exc_info=True,
            )
        try:
            await manager.async_unload()
        except Exception:  # noqa: BLE001 - preserve original setup exception
            _LOGGER.debug(
                "Failed cleaning up manager after setup error for %s",
                entry.entry_id,
                exc_info=True,
            )
        raise
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Conversational Assistant config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False
    manager: ConversationalAssistantManager = entry.runtime_data
    await manager.async_unload()
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Schedule one race-safe reload after options change."""
    hass.config_entries.async_schedule_reload(entry.entry_id)
