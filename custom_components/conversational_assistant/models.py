"""Data models for Conversational Assistant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util


@dataclass(slots=True)
class Recurrence:
    """Recurrence rule."""

    kind: str = "none"
    day_of_month: int | None = None
    month: int | None = None
    weekday: int | None = None
    # New in 0.4.0. A weekly reminder can run on several weekdays.
    # The legacy ``weekday`` field remains for stored 0.3.x reminders.
    weekdays: list[int] | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialize recurrence."""
        return {
            "kind": self.kind,
            "day_of_month": self.day_of_month,
            "month": self.month,
            "weekday": self.weekday,
            "weekdays": self.weekdays,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Recurrence":
        """Deserialize recurrence."""
        data = data or {}
        raw_weekdays = data.get("weekdays")
        weekdays: list[int] | None = None
        if isinstance(raw_weekdays, list):
            weekdays = sorted(
                {
                    int(item)
                    for item in raw_weekdays
                    if isinstance(item, (int, str)) and str(item).isdigit()
                    and 0 <= int(item) <= 6
                }
            )
        weekday = data.get("weekday")
        if weekday is not None:
            try:
                weekday = int(weekday)
            except (TypeError, ValueError):
                weekday = None
        if weekdays is None and weekday is not None:
            weekdays = [weekday]
        return cls(
            kind=str(data.get("kind", "none")),
            day_of_month=data.get("day_of_month"),
            month=data.get("month"),
            weekday=weekday,
            weekdays=weekdays,
        )


@dataclass(slots=True)
class Reminder:
    """Stored reminder."""

    reminder_id: str
    message: str
    created_at: datetime
    next_run: datetime | None
    recurrence: Recurrence
    snooze_until: datetime | None = None
    last_notified: datetime | None = None
    delivered: bool = False
    # None means a reminder created before per-reminder targeting was added;
    # it uses all currently configured targets for backward compatibility.
    mobile_device_ids: list[str] | None = None
    zalo_targets: list[dict[str, Any]] | None = None
    # Speaker entity IDs selected when this reminder was confirmed.
    # Missing on reminders created before 0.3.0 means no speaker announcement.
    speaker_entity_ids: list[str] | None = None
    # Optional source scope. Zalo-created reminders use one owner key per
    # direct chat or group so users only list/delete reminders from that chat.
    owner_key: str | None = None

    @property
    def is_recurring(self) -> bool:
        """Return whether reminder recurs."""
        return self.recurrence.kind != "none"

    def as_dict(self) -> dict[str, Any]:
        """Serialize reminder."""
        return {
            "reminder_id": self.reminder_id,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "recurrence": self.recurrence.as_dict(),
            "snooze_until": (
                self.snooze_until.isoformat() if self.snooze_until else None
            ),
            "last_notified": (
                self.last_notified.isoformat() if self.last_notified else None
            ),
            "delivered": self.delivered,
            "mobile_device_ids": self.mobile_device_ids,
            "zalo_targets": self.zalo_targets,
            "speaker_entity_ids": self.speaker_entity_ids,
            "owner_key": self.owner_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Reminder":
        """Deserialize reminder."""

        def parse(value: str | None) -> datetime | None:
            if not value:
                return None
            parsed = dt_util.parse_datetime(value)
            return dt_util.as_local(parsed) if parsed else None

        def parse_ids(key: str) -> list[str] | None:
            if key not in data:
                return None
            value = data.get(key)
            if value is None:
                return None
            if isinstance(value, str):
                return [value]
            if isinstance(value, list):
                return [str(item) for item in value if item]
            return []

        created_at = parse(data.get("created_at")) or dt_util.now()
        return cls(
            reminder_id=str(data["reminder_id"]),
            message=str(data["message"]),
            created_at=created_at,
            next_run=parse(data.get("next_run")),
            recurrence=Recurrence.from_dict(data.get("recurrence")),
            snooze_until=parse(data.get("snooze_until")),
            last_notified=parse(data.get("last_notified")),
            delivered=bool(data.get("delivered", False)),
            mobile_device_ids=parse_ids("mobile_device_ids"),
            zalo_targets=(
                [
                    dict(item)
                    for item in data.get("zalo_targets", [])
                    if isinstance(item, dict)
                ]
                if "zalo_targets" in data
                and data.get("zalo_targets") is not None
                else None
            ),
            speaker_entity_ids=parse_ids("speaker_entity_ids"),
            owner_key=(
                str(data.get("owner_key")).strip()
                if data.get("owner_key")
                else None
            ),
        )


@dataclass(slots=True)
class CameraSnapshotSchedule:
    """Persistent camera snapshot schedule delivered to configured Zalo targets."""

    schedule_id: str
    camera_entity_ids: list[str]
    camera_names: dict[str, str]
    zalo_targets: list[dict[str, Any]]
    created_at: datetime
    next_run: datetime | None
    recurrence: Recurrence
    interval_minutes: int | None = None
    owner_key: str | None = None
    request_text: str = ""
    last_run: datetime | None = None
    last_result: str | None = None

    @property
    def is_recurring(self) -> bool:
        """Return whether this snapshot schedule repeats."""
        return bool(self.interval_minutes) or self.recurrence.kind != "none"

    def as_dict(self) -> dict[str, Any]:
        """Serialize the schedule for Home Assistant Store."""
        return {
            "schedule_id": self.schedule_id,
            "camera_entity_ids": list(self.camera_entity_ids),
            "camera_names": dict(self.camera_names),
            "zalo_targets": [dict(item) for item in self.zalo_targets],
            "created_at": self.created_at.isoformat(),
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "recurrence": self.recurrence.as_dict(),
            "interval_minutes": self.interval_minutes,
            "owner_key": self.owner_key,
            "request_text": self.request_text,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_result": self.last_result,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CameraSnapshotSchedule":
        """Deserialize and minimally validate one stored camera schedule."""

        def parse(value: str | None) -> datetime | None:
            if not value:
                return None
            parsed = dt_util.parse_datetime(value)
            return dt_util.as_local(parsed) if parsed else None

        schedule_id = str(data.get("schedule_id", "")).strip()
        if not schedule_id:
            raise ValueError("missing camera schedule id")

        raw_entities = data.get("camera_entity_ids", [])
        if not isinstance(raw_entities, list):
            raise ValueError("invalid camera entity list")
        camera_entity_ids = [
            str(item).strip() for item in raw_entities if str(item).strip()
        ]
        if not camera_entity_ids:
            raise ValueError("camera schedule has no camera entities")

        raw_names = data.get("camera_names", {})
        camera_names = (
            {
                str(key): str(value)
                for key, value in raw_names.items()
                if str(key).strip()
            }
            if isinstance(raw_names, dict)
            else {}
        )

        raw_targets = data.get("zalo_targets", [])
        if not isinstance(raw_targets, list):
            raise ValueError("invalid Zalo target list")
        zalo_targets = [
            dict(item) for item in raw_targets if isinstance(item, dict)
        ]
        if not zalo_targets:
            raise ValueError("camera schedule has no Zalo targets")

        interval_minutes: int | None = None
        raw_interval = data.get("interval_minutes")
        if raw_interval not in (None, ""):
            try:
                interval_minutes = int(raw_interval)
            except (TypeError, ValueError) as err:
                raise ValueError("invalid camera schedule interval") from err
            if interval_minutes <= 0:
                raise ValueError("camera schedule interval must be positive")

        created_at = parse(data.get("created_at")) or dt_util.now()
        return cls(
            schedule_id=schedule_id,
            camera_entity_ids=camera_entity_ids,
            camera_names=camera_names,
            zalo_targets=zalo_targets,
            created_at=created_at,
            next_run=parse(data.get("next_run")),
            recurrence=Recurrence.from_dict(data.get("recurrence")),
            interval_minutes=interval_minutes,
            owner_key=(
                str(data.get("owner_key")).strip()
                if data.get("owner_key")
                else None
            ),
            request_text=str(data.get("request_text", "") or ""),
            last_run=parse(data.get("last_run")),
            last_result=(
                str(data.get("last_result"))
                if data.get("last_result") is not None
                else None
            ),
        )


@dataclass(slots=True)
class Note:
    """Stored public or password-encrypted note."""

    note_id: str
    security_level: int
    created_at: datetime
    updated_at: datetime
    # Creation-source metadata only. Notes are shared across Voice Assist
    # and every Zalo chat; this field does not restrict note access.
    owner_key: str | None = None
    content: str | None = None
    encrypted_content: str | None = None
    encryption_salt: str | None = None
    encryption_nonce: str | None = None
    failed_attempts: int = 0
    locked_until: datetime | None = None

    @property
    def is_private(self) -> bool:
        """Return whether note content is password encrypted."""
        return self.security_level == 1

    def as_dict(self) -> dict[str, Any]:
        """Serialize note without ever adding a plaintext password."""
        return {
            "note_id": self.note_id,
            "security_level": self.security_level,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "owner_key": self.owner_key,
            "content": self.content if not self.is_private else None,
            "encrypted_content": (
                self.encrypted_content if self.is_private else None
            ),
            "encryption_salt": self.encryption_salt if self.is_private else None,
            "encryption_nonce": self.encryption_nonce if self.is_private else None,
            "failed_attempts": self.failed_attempts,
            "locked_until": (
                self.locked_until.isoformat() if self.locked_until else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Note":
        """Deserialize a stored note."""

        def parse(value: str | None) -> datetime | None:
            if not value:
                return None
            parsed = dt_util.parse_datetime(value)
            return dt_util.as_local(parsed) if parsed else None

        created_at = parse(data.get("created_at")) or dt_util.now()
        updated_at = parse(data.get("updated_at")) or created_at
        level = int(data.get("security_level", 2))
        if level not in (1, 2):
            level = 2
        return cls(
            note_id=str(data["note_id"]),
            security_level=level,
            created_at=created_at,
            updated_at=updated_at,
            owner_key=(
                str(data.get("owner_key")).strip()
                if data.get("owner_key")
                else None
            ),
            content=(
                str(data.get("content"))
                if level == 2 and data.get("content") is not None
                else None
            ),
            encrypted_content=(
                str(data.get("encrypted_content"))
                if level == 1 and data.get("encrypted_content")
                else None
            ),
            encryption_salt=(
                str(data.get("encryption_salt"))
                if level == 1 and data.get("encryption_salt")
                else None
            ),
            encryption_nonce=(
                str(data.get("encryption_nonce"))
                if level == 1 and data.get("encryption_nonce")
                else None
            ),
            failed_attempts=max(0, int(data.get("failed_attempts", 0) or 0)),
            locked_until=parse(data.get("locked_until")),
        )
