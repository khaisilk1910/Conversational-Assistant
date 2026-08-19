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
            ConversationalAssistantCalendarEventCountSensor(manager, entry),
            ConversationalAssistantCameraScheduleCountSensor(manager, entry),
            ConversationalAssistantNoteCountSensor(manager, entry),
            ConversationalAssistantLearnedCommandCountSensor(manager, entry),
        ]
    )


class ConversationalAssistantSensorBase(SensorEntity):
    """Base sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

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
            "ai_search_agent_id": self.manager.ai_search_agent_id,
            "weather_entity_id": self.manager.weather_entity_id,
            "weather_location": self.manager.weather_location,
            "weather_forecast_enabled": self.manager.weather_forecast_enabled,
            "weather_forecast_times": [
                item.strftime("%H:%M:%S")
                for item in self.manager.weather_forecast_times
            ],
            "weather_forecast_days": self.manager.weather_forecast_days,
            "weather_forecast_zalo_targets": (
                self.manager.weather_forecast_zalo_target_ids
            ),
            "weather_last_forecast_at": (
                self.manager.weather_last_forecast_at.isoformat()
                if self.manager.weather_last_forecast_at is not None
                else None
            ),
            "weather_last_forecast_result": (
                self.manager.weather_last_forecast_result
            ),
            "weather_storm_enabled": self.manager.weather_storm_enabled,
            "weather_storm_times": [
                item.strftime("%H:%M:%S")
                for item in self.manager.weather_storm_times
            ],
            "weather_storm_zalo_targets": (
                self.manager.weather_storm_zalo_target_ids
            ),
            "weather_last_storm_at": (
                self.manager.weather_last_storm_at.isoformat()
                if self.manager.weather_last_storm_at is not None
                else None
            ),
            "weather_last_storm_result": self.manager.weather_last_storm_result,
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


class ConversationalAssistantCalendarEventCountSensor(
    ConversationalAssistantSensorBase
):
    """Upcoming calendar event count across selected calendar entities."""

    _attr_name = "Số sự kiện sắp diễn ra"
    _attr_icon = "mdi:calendar-multiple-check"

    def __init__(
        self,
        manager: ConversationalAssistantManager,
        entry: ConfigEntry,
    ) -> None:
        """Initialize calendar event count sensor."""
        super().__init__(manager, entry)
        self._attr_unique_id = f"{entry.entry_id}_calendar_event_count"

    @property
    def native_value(self) -> int:
        """Return the number of events in the configured look-ahead window."""
        return self.manager.calendar_event_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return normalized event details and calendar monitor metadata."""
        rows = self.manager.calendar_event_sensor_rows
        return {
            "so_ngay_tra_cuu": self.manager.calendar_lookahead_days,
            "tu_thoi_gian": (
                self.manager.calendar_window_start.isoformat()
                if self.manager.calendar_window_start is not None
                else None
            ),
            "den_thoi_gian": (
                self.manager.calendar_window_end.isoformat()
                if self.manager.calendar_window_end is not None
                else None
            ),
            "cap_nhat_luc": (
                self.manager.calendar_last_update.isoformat()
                if self.manager.calendar_last_update is not None
                else None
            ),
            "list_su_kien": self.manager.calendar_event_list_text,
            "su_kien_sap_toi": rows,
            "lich_cau_hinh": (
                self.manager.calendar_configured_entity_ids
                if self.manager.calendar_configured_entity_ids is not None
                else "tat_ca_lich"
            ),
            "lich_dang_quan_sat": self.manager.calendar_monitored_entity_ids,
            "duong_lich_mac_dinh": self.manager.calendar_solar_entity_id or None,
            "am_lich_mac_dinh": self.manager.calendar_lunar_entity_id or None,
            "thong_bao_bat": self.manager.calendar_notification_enabled,
            "gio_thong_bao": (
                self.manager.calendar_notification_time.strftime("%H:%M:%S")
            ),
            "mobile_da_chon": (
                self.manager.calendar_notification_mobile_device_ids
            ),
            "zalo_da_chon": (
                self.manager.calendar_notification_zalo_target_ids
            ),
            "lan_gui_thong_bao_cuoi": (
                self.manager.calendar_last_notification_at.isoformat()
                if self.manager.calendar_last_notification_at is not None
                else None
            ),
            "ket_qua_gui_thong_bao": (
                self.manager.calendar_last_notification_result
            ),
            "loi_gui_thong_bao": (
                self.manager.calendar_last_notification_error
            ),
            "loi_cap_nhat": self.manager.calendar_refresh_error,
        }


class ConversationalAssistantCameraScheduleCountSensor(
    ConversationalAssistantSensorBase
):
    """Active scheduled camera snapshot count and details."""

    _attr_name = "Số lịch chụp camera"
    _attr_icon = "mdi:camera-timer"

    def __init__(
        self,
        manager: ConversationalAssistantManager,
        entry: ConfigEntry,
    ) -> None:
        """Initialize camera schedule count sensor."""
        super().__init__(manager, entry)
        self._attr_unique_id = f"{entry.entry_id}_camera_schedule_count"

    @property
    def native_value(self) -> int:
        """Return active camera snapshot schedule count."""
        return self.manager.camera_schedule_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return scheduled camera snapshot details."""
        return {
            "list_lich_chup_camera": self.manager.camera_schedule_list_text,
            "lich_chup_camera": self.manager.camera_schedule_sensor_rows,
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
