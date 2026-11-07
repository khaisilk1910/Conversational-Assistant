"""Privacy-safe diagnostics for Conversational Assistant."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .manager import ConversationalAssistantManager


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return operational counters only, never credentials or message text."""
    manager = entry.runtime_data
    if not isinstance(manager, ConversationalAssistantManager):
        return {"loaded": False, "config_entry_version": entry.version}

    return {
        "loaded": True,
        "config_entry_version": entry.version,
        "config_entry_minor_version": entry.minor_version,
        "home_assistant_state": str(hass.state),
        "storage": {
            "restored": manager._storage_loaded,
            "loading": manager._storage_load_task is not None,
            "last_error_type": manager._storage_error,
            "retry_count": manager._storage_load_retries,
        },
        "assist": {
            "ready": manager._assist_triggers_ready,
            "groups_registered": manager._assist_groups_registered,
            "groups_failed": manager._assist_groups_failed,
            "registration_duration_ms": manager._assist_setup_ms,
        },
        "counts": {
            "reminders": len(manager.reminders),
            "camera_schedules": len(manager.camera_snapshot_schedules),
            "learned_commands": len(manager.learned_commands),
            "notes": len(manager.notes),
            "scheduled_device_actions": len(manager._scheduled_device_actions),
        },
    }
