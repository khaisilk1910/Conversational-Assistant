"""Persistent learned command aliases for Conversational Assistant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any
import unicodedata
import uuid

from homeassistant.util import dt as dt_util

from .targeting import normalize_text

# Internal actions are intentionally limited to workflows implemented by this
# integration. A learned phrase is an alias, not arbitrary executable code.
ACTION_CAMERA = "camera"
ACTION_REMINDER_CREATE = "create"
ACTION_REMINDER_LIST = "list"
ACTION_REMINDER_DELETE = "delete"
ACTION_NOTE_CREATE = "note_create"
ACTION_NOTE_LIST = "note_list"
ACTION_NOTE_EDIT = "note_edit"
ACTION_NOTE_DELETE = "note_delete"
ACTION_NOTE_VIEW = "note_view"
ACTION_HELP = "help"
ACTION_HOME_ASSISTANT = "home_assistant"
ACTION_CALENDAR = "calendar"

SUPPORTED_ACTIONS = {
    ACTION_CAMERA,
    ACTION_REMINDER_CREATE,
    ACTION_REMINDER_LIST,
    ACTION_REMINDER_DELETE,
    ACTION_NOTE_CREATE,
    ACTION_NOTE_LIST,
    ACTION_NOTE_EDIT,
    ACTION_NOTE_DELETE,
    ACTION_NOTE_VIEW,
    ACTION_HELP,
    ACTION_HOME_ASSISTANT,
    ACTION_CALENDAR,
}

MAX_LEARNED_COMMANDS = 100

REQUEST_ACTIONS = {
    ACTION_REMINDER_CREATE,
    ACTION_REMINDER_DELETE,
    ACTION_NOTE_CREATE,
    ACTION_NOTE_VIEW,
}

ACTION_LABELS = {
    ACTION_CAMERA: "chụp ảnh camera",
    ACTION_REMINDER_CREATE: "tạo nhắc hẹn",
    ACTION_REMINDER_LIST: "xem danh sách nhắc hẹn",
    ACTION_REMINDER_DELETE: "xóa nhắc hẹn",
    ACTION_NOTE_CREATE: "tạo ghi chú",
    ACTION_NOTE_LIST: "xem danh sách ghi chú",
    ACTION_NOTE_EDIT: "sửa ghi chú",
    ACTION_NOTE_DELETE: "xóa ghi chú",
    ACTION_NOTE_VIEW: "mở ghi chú",
    ACTION_HELP: "xem hướng dẫn",
    ACTION_HOME_ASSISTANT: "thực hiện lệnh Home Assistant",
    ACTION_CALENDAR: "xem lịch Home Assistant",
}

# Explicit labels also let users teach short targets such as "để camera" or
# "để tạo nhắc hẹn", which may not be classified by the normal command parser.
_TARGET_LABELS = {
    "camera": ACTION_CAMERA,
    "chup camera": ACTION_CAMERA,
    "chup anh camera": ACTION_CAMERA,
    "lay anh camera": ACTION_CAMERA,
    "tao nhac hen": ACTION_REMINDER_CREATE,
    "tao nhac nho": ACTION_REMINDER_CREATE,
    "dat nhac hen": ACTION_REMINDER_CREATE,
    "nhac hen": ACTION_REMINDER_CREATE,
    "danh sach nhac hen": ACTION_REMINDER_LIST,
    "xem nhac hen": ACTION_REMINDER_LIST,
    "xem danh sach nhac hen": ACTION_REMINDER_LIST,
    "liet ke nhac hen": ACTION_REMINDER_LIST,
    "xoa nhac hen": ACTION_REMINDER_DELETE,
    "huy nhac hen": ACTION_REMINDER_DELETE,
    "tao ghi chu": ACTION_NOTE_CREATE,
    "them ghi chu": ACTION_NOTE_CREATE,
    "ghi chu": ACTION_NOTE_CREATE,
    "danh sach ghi chu": ACTION_NOTE_LIST,
    "xem danh sach ghi chu": ACTION_NOTE_LIST,
    "liet ke ghi chu": ACTION_NOTE_LIST,
    "sua ghi chu": ACTION_NOTE_EDIT,
    "chinh sua ghi chu": ACTION_NOTE_EDIT,
    "xoa ghi chu": ACTION_NOTE_DELETE,
    "huy ghi chu": ACTION_NOTE_DELETE,
    "mo ghi chu": ACTION_NOTE_VIEW,
    "doc ghi chu": ACTION_NOTE_VIEW,
    "xem noi dung ghi chu": ACTION_NOTE_VIEW,
    "tro giup": ACTION_HELP,
    "huong dan": ACTION_HELP,
    "xem huong dan": ACTION_HELP,
    "huong dan su dung": ACTION_HELP,
    "huong dan su dung tich hop": ACTION_HELP,
    "su dung tich hop": ACTION_HELP,
    "cach su dung tich hop": ACTION_HELP,
    "huong dan tich hop": ACTION_HELP,
    "hoc cach su dung tich hop": ACTION_HELP,
    "cac tinh nang": ACTION_HELP,
}

_RESERVED_PHRASES = {
    "co",
    "khong",
    "ok",
    "okay",
    "u",
    "uh",
    "um",
    "duoc",
    "dung",
    "dung roi",
    "dong y",
    "toi dong y",
    "xac nhan",
    "xac nhan chup",
    "huy",
    "thoi",
    "lam di",
    "gui di",
    "chup di",
    "chup ngay",
    "tat ca",
    "toan bo",
    "het",
    "ca hai",
    "mot",
    "hai",
    "ba",
    "bon",
    "tu",
    "nam",
    "sau",
    "bay",
    "tam",
    "chin",
    "muoi",
}

_LEARN_PREFIXES = (
    "hoc cau lenh",
    "day cau lenh",
    "them cau lenh",
    "them cau lenh tuy chinh",
    "them cach noi",
    "day cach noi",
)
_DELETE_PREFIXES = (
    "xoa cau lenh da hoc",
    "xoa cau lenh tuy chinh",
    "xoa cau lenh",
    "quen cau lenh",
)
_LIST_PHRASES = {
    "danh sach cau lenh da hoc",
    "liet ke cau lenh da hoc",
    "xem cau lenh da hoc",
    "cac cau lenh da hoc",
    "toi da day nhung cau lenh nao",
    "bo nho cau lenh",
}
_CLEAR_PHRASES = {
    "tat ca",
    "toan bo",
    "het",
    "tat ca cau lenh da hoc",
    "toan bo cau lenh da hoc",
}
_CLEAR_COMMAND_PHRASES = {
    "xoa tat ca cau lenh da hoc",
    "xoa toan bo cau lenh da hoc",
    "quen tat ca cau lenh da hoc",
    "quen toan bo cau lenh da hoc",
}


class CommandMemoryError(ValueError):
    """Raised when a learned command request is invalid."""


@dataclass(slots=True)
class LearnedCommand:
    """One persistent spoken phrase mapped to a supported action."""

    command_id: str
    phrase: str
    normalized_phrase: str
    action: str
    created_at: datetime
    updated_at: datetime
    target_text: str | None = None

    @property
    def action_label(self) -> str:
        """Return a Vietnamese display label."""
        return ACTION_LABELS.get(self.action, self.action)

    @property
    def target_label(self) -> str:
        """Return the concrete action or Home Assistant command text."""
        return self.target_text or self.action_label

    @property
    def accepts_request(self) -> bool:
        """Return whether text after the alias is passed as a request."""
        return self.action in REQUEST_ACTIONS

    def as_dict(self) -> dict[str, Any]:
        """Serialize for Home Assistant Store."""
        return {
            "command_id": self.command_id,
            "phrase": self.phrase,
            "normalized_phrase": self.normalized_phrase,
            "action": self.action,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "target_text": self.target_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearnedCommand":
        """Deserialize and validate a stored alias."""
        phrase = clean_command_phrase(str(data.get("phrase", "")))
        action = str(data.get("action", "")).strip()
        if action not in SUPPORTED_ACTIONS:
            raise CommandMemoryError("Loại câu lệnh không được hỗ trợ.")
        target_text = str(data.get("target_text", "")).strip() or None
        if action in {ACTION_HOME_ASSISTANT, ACTION_CALENDAR}:
            if not target_text:
                raise CommandMemoryError("Câu lệnh Home Assistant thiếu lệnh đích.")
        else:
            target_text = None

        def parse_datetime(value: Any) -> datetime:
            parsed = dt_util.parse_datetime(str(value or ""))
            return dt_util.as_local(parsed) if parsed else dt_util.now()

        created_at = parse_datetime(data.get("created_at"))
        return cls(
            command_id=str(data.get("command_id") or uuid.uuid4().hex),
            phrase=phrase,
            normalized_phrase=normalize_text(phrase),
            action=action,
            created_at=created_at,
            updated_at=parse_datetime(data.get("updated_at")) or created_at,
            target_text=target_text,
        )


@dataclass(slots=True, frozen=True)
class LearnedCommandMatch:
    """A learned alias matched against one incoming command."""

    command: LearnedCommand
    request: str


def clean_command_phrase(value: str) -> str:
    """Return a safe literal phrase suitable for a Hassil sentence."""
    value = unicodedata.normalize("NFC", str(value or "").strip())
    value = value.strip(" \t\r\n'\"“”‘’`.,;:!?-")
    characters: list[str] = []
    for character in value:
        category = unicodedata.category(character)
        if character.isspace():
            characters.append(" ")
        elif category.startswith(("L", "N")):
            characters.append(character.casefold())
        else:
            characters.append(" ")
    phrase = re.sub(r"\s+", " ", "".join(characters)).strip()
    if normalize_text(phrase).startswith("hay "):
        phrase = " ".join(phrase.split()[1:]).strip()
    normalized = normalize_text(phrase)
    if not phrase or not normalized:
        raise CommandMemoryError("Câu lệnh mới đang để trống.")
    if len(normalized) < 2:
        raise CommandMemoryError("Câu lệnh mới quá ngắn.")
    if len(phrase) > 80 or len(phrase.split()) > 12:
        raise CommandMemoryError("Câu lệnh mới quá dài; tối đa 12 từ.")
    if normalized in _RESERVED_PHRASES:
        raise CommandMemoryError(
            "Câu này quá chung và có thể làm sai bước xác nhận. "
            "Hãy dùng cách nói cụ thể hơn."
        )
    if management_command_kind(phrase) is not None:
        raise CommandMemoryError(
            "Không thể dùng chính câu quản lý bộ nhớ làm câu lệnh tùy chỉnh."
        )
    return phrase


def explicit_target_action(text: str) -> str | None:
    """Resolve explicit action labels used after the word 'để'."""
    return _TARGET_LABELS.get(normalize_text(text))


def _normalized_management_text(text: str) -> str:
    """Normalize management text and ignore one polite leading 'hãy'."""
    normalized = normalize_text(text)
    if normalized.startswith("hay "):
        return normalized[4:].strip()
    return normalized


def management_command_kind(text: str) -> str | None:
    """Classify command-memory management requests."""
    normalized = _normalized_management_text(text)
    if not normalized:
        return None
    if normalized in _LIST_PHRASES:
        return "command_list"
    if normalized in _CLEAR_COMMAND_PHRASES:
        return "command_delete"
    if any(
        normalized == prefix or normalized.startswith(f"{prefix} ")
        for prefix in _LEARN_PREFIXES
    ):
        return "command_learn"
    if any(
        normalized == prefix or normalized.startswith(f"{prefix} ")
        for prefix in _DELETE_PREFIXES
    ):
        return "command_delete"
    return None


def strip_management_prefix(text: str, kind: str) -> str:
    """Strip a management command prefix while preserving accented content."""
    words = str(text or "").strip().split()
    normalized_words = [normalize_text(word) for word in words]
    if normalized_words and normalized_words[0] == "hay":
        words = words[1:]
        normalized_words = normalized_words[1:]
    prefixes = _LEARN_PREFIXES if kind == "command_learn" else _DELETE_PREFIXES
    for prefix in sorted(prefixes, key=lambda item: len(item.split()), reverse=True):
        prefix_words = prefix.split()
        if normalized_words[: len(prefix_words)] == prefix_words:
            return " ".join(words[len(prefix_words) :]).strip()
    return " ".join(words).strip()


def parse_learn_request(text: str) -> tuple[str, str]:
    """Split '<new phrase> để <existing command>' into two parts."""
    value = strip_management_prefix(text, "command_learn")
    value = value.strip()
    if not value:
        raise CommandMemoryError(
            "Hãy nói theo mẫu: học câu lệnh xem cổng để chụp ảnh camera."
        )

    words = value.split()
    normalized_words = [normalize_text(word) for word in words]
    connectors = (
        ("de",),
        ("thay", "cho"),
        ("tuong", "duong", "voi"),
        ("co", "nghia", "la"),
    )
    split_at: tuple[int, int] | None = None
    for index in range(1, len(words)):
        for connector in connectors:
            end = index + len(connector)
            if tuple(normalized_words[index:end]) == connector:
                split_at = (index, end)
                break
        if split_at is not None:
            break
    if split_at is None:
        raise CommandMemoryError(
            "Chưa biết câu mới dùng cho chức năng nào. Ví dụ: "
            "học câu lệnh xem cổng để chụp ảnh camera."
        )
    index, end = split_at
    phrase = clean_command_phrase(" ".join(words[:index]))
    target = " ".join(words[end:]).strip(" \t\r\n'\"“”‘’`.,;:!?")
    if not target:
        raise CommandMemoryError("Chức năng đích đang để trống.")
    if len(target) > 240 or len(target.split()) > 40:
        raise CommandMemoryError("Chức năng đích quá dài; tối đa 40 từ.")
    return phrase, target


def parse_delete_request(text: str) -> tuple[bool, str]:
    """Return (clear_all, phrase) for a delete management request."""
    if _normalized_management_text(text) in _CLEAR_COMMAND_PHRASES:
        return True, ""
    value = strip_management_prefix(text, "command_delete")
    normalized = normalize_text(value)
    if not normalized:
        raise CommandMemoryError(
            "Hãy nói tên câu cần xóa, ví dụ: xóa câu lệnh xem cổng."
        )
    if normalized in _CLEAR_PHRASES:
        return True, ""
    return False, clean_command_phrase(value)


def hassil_sentences(command: LearnedCommand) -> list[str]:
    """Build literal Assist sentences for one learned command."""
    variants = [command.phrase]
    folded = normalize_text(command.phrase)
    if folded and folded != command.phrase:
        variants.append(folded)

    sentences: list[str] = []
    for phrase in variants:
        optional_hay = "hay" if phrase == folded else "hãy"
        base = (
            phrase
            if normalize_text(phrase).startswith("hay ")
            else f"[{optional_hay} ]{phrase}"
        )
        sentences.append(base)
        if command.accepts_request:
            sentences.append(f"{base} {{request}}")
    return sentences


def match_learned_command(
    text: str, commands: list[LearnedCommand]
) -> LearnedCommandMatch | None:
    """Match an exact alias or request-prefix alias, longest phrase first."""
    normalized = normalize_text(text)
    if not normalized:
        return None
    without_hay = normalized[4:] if normalized.startswith("hay ") else normalized
    original_words = str(text or "").strip().split()
    if original_words and normalize_text(original_words[0]) == "hay":
        original_words = original_words[1:]

    for command in sorted(
        commands, key=lambda item: len(item.normalized_phrase), reverse=True
    ):
        phrase = command.normalized_phrase
        if without_hay == phrase:
            return LearnedCommandMatch(command=command, request="")
        if command.accepts_request and without_hay.startswith(f"{phrase} "):
            word_count = len(phrase.split())
            request = " ".join(original_words[word_count:]).strip()
            return LearnedCommandMatch(command=command, request=request)
    return None


def canonical_text(
    action: str, request: str = "", target_text: str | None = None
) -> str:
    """Build text understood by the integration's existing handlers."""
    if action in {ACTION_HOME_ASSISTANT, ACTION_CALENDAR}:
        return str(target_text or "").strip()
    request = request.strip()
    prefixes = {
        ACTION_REMINDER_CREATE: "nhắc tôi",
        ACTION_REMINDER_DELETE: "xóa nhắc hẹn",
        ACTION_NOTE_CREATE: "ghi chú",
        ACTION_NOTE_VIEW: "mở ghi chú",
    }
    prefix = prefixes.get(action, "")
    return f"{prefix} {request}".strip() if prefix else request
