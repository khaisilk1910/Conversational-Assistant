"""Sensors for Conversational Assistant."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, INTEGRATION_NAME
from .manager import ConversationalAssistantManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Conversational Assistant sensors."""
    manager: ConversationalAssistantManager = entry.runtime_data
    async_add_entities(
        [
            ConversationalAssistantCountSensor(manager, entry),
            ConversationalAssistantNextSensor(manager, entry),
            ConversationalAssistantNoteCountSensor(manager, entry),
            ConversationalAssistantLearnedCommandCountSensor(manager, entry),
        ]
    )


class ConversationalAssistantSensorBase(SensorEntity):
    """Base sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        manager: ConversationalAssistantManager,
        entry: ConfigEntry,
    ) -> None:
        """Initialize sensor."""
        self.manager = manager
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=INTEGRATION_NAME,
            manufacturer="Custom integration",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to manager updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self.manager.update_signal,
                self._async_handle_update,
            )
        )

    @callback
    def _async_handle_update(self) -> None:
        """Write updated state."""
        self.async_write_ha_state()


class ConversationalAssistantCountSensor(ConversationalAssistantSensorBase):
    """Stored reminder count."""

    _attr_name = "Số nhắc nhở"
    _attr_icon = "mdi:reminder"

    def __init__(
        self,
        manager: ConversationalAssistantManager,
        entry: ConfigEntry,
    ) -> None:
        """Initialize count sensor."""
        super().__init__(manager, entry)
        self._attr_unique_id = f"{entry.entry_id}_count"

    @property
    def native_value(self) -> int:
        """Return reminder count."""
        return self.manager.active_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the ordered list of upcoming reminders."""
        upcoming = self.manager.upcoming_reminders
        lines: list[str] = []
        details: list[dict[str, Any]] = []

        for index, (due, reminder) in enumerate(upcoming, start=1):
            lines.append(
                f"{index} - {due.strftime('%H:%M %d/%m/%Y')} : "
                f"{reminder.message}"
            )
            details.append(
                {
                    "stt": index,
                    "thoi_gian": due.isoformat(),
                    "noi_dung": reminder.message,
                    "lap_lai": reminder.recurrence.kind,
                    "reminder_id": reminder.reminder_id,
                }
            )

        return {
            "list_nhac_nho": "\n".join(lines),
            "nhac_nho_sap_toi": details,
            "zalo_webhook_enabled": self.manager.zalo_webhook_enabled,
            "zalo_webhook_action": self.manager.zalo_webhook_action,
            "zalo_webhook_mode": "existing_webhook",
            "zalo_bot_account_id": self.manager.zalo_webhook_bot_account_id,
            "zalo_home_assistant_enabled": (
                self.manager.zalo_home_assistant_enabled
            ),
            "zalo_conversation_agent_id": (
                self.manager.zalo_conversation_agent_id
            ),
        }


class ConversationalAssistantNextSensor(ConversationalAssistantSensorBase):
    """Next reminder timestamp."""

    _attr_name = "Nhắc nhở tiếp theo"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        manager: ConversationalAssistantManager,
        entry: ConfigEntry,
    ) -> None:
        """Initialize next reminder sensor."""
        super().__init__(manager, entry)
        self._attr_unique_id = f"{entry.entry_id}_next"

    @property
    def native_value(self):
        """Return next reminder timestamp."""
        return self.manager.next_due

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details of next reminder."""
        reminder = self.manager.next_reminder
        if reminder is None:
            return {}
        return {
            "reminder_id": reminder.reminder_id,
            "message": reminder.message,
            "recurrence": reminder.recurrence.kind,
            "snoozed": reminder.snooze_until is not None,
        }


class ConversationalAssistantNoteCountSensor(ConversationalAssistantSensorBase):
    """Stored note count with a redacted note list."""

    _attr_name = "Số ghi chú"
    _attr_icon = "mdi:notebook-lock"

    def __init__(
        self,
        manager: ConversationalAssistantManager,
        entry: ConfigEntry,
    ) -> None:
        """Initialize note count sensor."""
        super().__init__(manager, entry)
        self._attr_unique_id = f"{entry.entry_id}_note_count"

    @property
    def native_value(self) -> int:
        """Return note count."""
        return self.manager.note_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return only safe note metadata and public content."""
        rows = self.manager.note_sensor_rows
        lines = [
            f"{row['stt']} - {row['noi_dung']}"
            for row in rows
        ]
        return {
            "list_ghi_chu": "\n".join(lines),
            "ghi_chu": rows,
            "so_ghi_chu_bao_mat": sum(
                1 for row in rows if row["muc_bao_mat"] == 1
            ),
            "so_ghi_chu_cong_khai": sum(
                1 for row in rows if row["muc_bao_mat"] == 2
            ),
            "bao_mat": (
                "Nội dung Mức 1 được mã hóa và không xuất hiện trong sensor."
            ),
        }


class ConversationalAssistantLearnedCommandCountSensor(
    ConversationalAssistantSensorBase
):
    """Persistent learned command count and safe alias list."""

    _attr_name = "Số câu lệnh đã học"
    _attr_icon = "mdi:head-cog-outline"

    def __init__(
        self,
        manager: ConversationalAssistantManager,
        entry: ConfigEntry,
    ) -> None:
        """Initialize learned command sensor."""
        super().__init__(manager, entry)
        self._attr_unique_id = f"{entry.entry_id}_learned_command_count"

    @property
    def native_value(self) -> int:
        """Return learned command count."""
        return self.manager.learned_command_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return phrases and mapped functions."""
        rows = self.manager.learned_command_sensor_rows
        return {
            "list_cau_lenh": "\n".join(
                f"{row['stt']} - {row['cau_lenh']} : {row['lenh_dich']}"
                for row in rows
            ),
            "cau_lenh_da_hoc": rows,
            "luu_tru": "Home Assistant Store",
            "ap_dung": "Voice Assist và Zalo",
        }
