"""Natural-language note workflows shared by Voice Assist and Zalo."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re
from typing import Any
import uuid

from hassil.recognize import RecognizeResult

from homeassistant.components.conversation.models import ConversationInput
from homeassistant.util import dt as dt_util

from .const import (
    NOTE_CREATE_SENTENCES,
    NOTE_DELETE_SENTENCES,
    NOTE_EDIT_SENTENCES,
    NOTE_LIST_SENTENCES,
    NOTE_VIEW_SENTENCES,
    PENDING_CONFIRMATION_TIMEOUT_SECONDS,
)
from .models import Note
from .notes import (
    NOTE_SECURITY_PRIVATE,
    NOTE_SECURITY_PUBLIC,
    NoteLockedError,
    NotePasswordError,
    clean_note_content,
    decrypt_note_content,
    encrypt_note_content,
    extract_password,
    is_affirmative,
    is_negative,
    parse_security_level,
    security_label,
)
from .targeting import normalize_text, parse_target_selection


@dataclass(slots=True)
class PendingNoteAction:
    """One multi-turn note operation."""

    pending_id: str
    action: str
    stage: str
    source_keys: set[str] = field(default_factory=set)
    owner_key: str | None = None
    note_ids: list[str] = field(default_factory=list)
    selected_note_id: str | None = None
    proposed_note_id: str | None = None
    content: str | None = None
    security_level: int | None = None
    encrypted_content: str | None = None
    encryption_salt: str | None = None
    encryption_nonce: str | None = None
    created_at: datetime = field(default_factory=dt_util.now)
    expires_at: datetime = field(default_factory=dt_util.now)


def _extract_note_request(text: str) -> str:
    """Strip common note command prefixes from arbitrary text."""
    value = str(text or "").strip()
    folded = normalize_text(value)
    if folded.startswith("please "):
        value = " ".join(value.split()[1:]).strip()
        folded = normalize_text(value)
    prefixes = (
        "please add note",
        "please create note",
        "please save note",
        "please write note",
        "please make note",
        "please remember",
        "add a note",
        "create a note",
        "save a note",
        "write a note",
        "make a note",
        "add note",
        "create note",
        "save note",
        "write note",
        "make note",
        "remember that",
        "remember",
        "note that",
        "note",
        "them ghi chu",
        "tao ghi chu",
        "luu ghi chu",
        "them ghi nho",
        "tao ghi nho",
        "luu ghi nho",
        "viet ghi chu",
        "viet ghi nho",
        "them note",
        "tao note",
        "luu note",
        "viet note",
        "hay ghi chu",
        "hay ghi nho",
        "hay nho giup toi",
        "hay nho rang",
        "hay ghi lai",
        "hay nho",
        "ghi chu",
        "ghi nho",
        "ghi lai",
        "note",
        "nho rang",
        "nho giup toi",
        "nho",
    )
    for prefix in prefixes:
        if folded == prefix:
            return ""
        if folded.startswith(f"{prefix} "):
            # Prefixes are accent-folded, so remove the same number of
            # whitespace-separated words from the original value.
            count = len(prefix.split())
            return " ".join(value.split()[count:]).strip()
    return value


def note_zalo_command_kind(text: str) -> str | None:
    """Classify natural Vietnamese note commands from Zalo."""
    normalized = normalize_text(text)
    if normalized.startswith("please "):
        normalized = normalized[7:].strip()
    if not normalized:
        return None

    list_phrases = {
        "list notes",
        "list my notes",
        "show notes",
        "show my notes",
        "read notes",
        "read my notes",
        "show note list",
        "show my note list",
        "what notes do i have",
        "my notes",
        "notes",
        "ghi chu cua toi",
        "ghi nho cua toi",
        "liet ke ghi chu",
        "liet ke ghi nho",
        "danh sach ghi chu",
        "danh sach ghi nho",
        "xem danh sach ghi chu",
        "xem danh sach ghi nho",
        "doc danh sach ghi chu",
        "doc danh sach ghi nho",
        "toi co ghi chu gi",
        "toi co nhung ghi chu nao",
        "xem ghi chu",
        "cac ghi chu",
        "cho toi xem ghi chu",
        "cho toi xem ghi nho",
        "doc ghi chu cua toi",
        "doc ghi nho cua toi",
    }
    if normalized in list_phrases:
        return "note_list"

    if normalized.startswith(
        (
            "edit note",
            "edit a note",
            "update note",
            "update a note",
            "change note",
            "change a note",
            "please edit note",
            "please update note",
            "sua ghi chu",
            "sua ghi nho",
            "chinh sua ghi chu",
            "cap nhat ghi chu",
            "doi ghi chu",
            "sua note",
            "chinh sua note",
            "cap nhat note",
        )
    ):
        return "note_edit"
    if normalized.startswith(
        (
            "delete note",
            "delete a note",
            "remove note",
            "remove a note",
            "please delete note",
            "please remove note",
            "xoa ghi chu",
            "xoa ghi nho",
            "huy ghi chu",
            "huy ghi nho",
            "xoa note",
            "huy note",
        )
    ):
        return "note_delete"
    if normalized.startswith(
        (
            "open note",
            "read note",
            "view note",
            "show note",
            "show note number",
            "please open note",
            "please read note",
            "mo ghi chu",
            "doc ghi chu so",
            "xem noi dung ghi chu",
            "xem ghi chu so",
        )
    ):
        return "note_view"
    if normalized in {
        "note",
        "add note",
        "add a note",
        "create note",
        "create a note",
        "save note",
        "save a note",
        "write note",
        "write a note",
        "make note",
        "make a note",
        "remember",
        "please remember",
        "please add note",
        "please create note",
        "ghi chu",
        "ghi nho",
        "nho",
        "them ghi chu",
        "tao ghi chu",
        "luu ghi chu",
        "viet ghi chu",
        "ghi lai",
        "note",
        "hay ghi chu",
        "hay ghi nho",
        "hay ghi lai",
        "hay nho",
        "nho rang",
        "nho giup toi",
    } or normalized.startswith(
        (
            "add note ",
            "add a note ",
            "create note ",
            "create a note ",
            "save note ",
            "save a note ",
            "write note ",
            "write a note ",
            "make note ",
            "make a note ",
            "remember ",
            "remember that ",
            "note that ",
            "please remember ",
            "please add note ",
            "please create note ",
            "them ghi chu ",
            "tao ghi chu ",
            "luu ghi chu ",
            "them ghi nho ",
            "tao ghi nho ",
            "luu ghi nho ",
            "viet ghi chu ",
            "viet ghi nho ",
            "them note ",
            "tao note ",
            "luu note ",
            "viet note ",
            "ghi chu ",
            "ghi nho ",
            "ghi lai ",
            "note ",
            "hay ghi chu ",
            "hay ghi nho ",
            "hay ghi lai ",
            "hay nho rang ",
            "hay nho giup toi ",
            "hay nho ",
            "nho rang ",
            "nho giup toi ",
            "nho ",
        )
    ):
        return "note_create"
    return None


def is_primary_note_voice_command(text: str) -> bool:
    """Return whether a new note trigger should own this voice turn."""
    return note_zalo_command_kind(text) is not None


class NoteManagerMixin:
    """Add encrypted note storage and multi-turn natural-language flows."""

    notes: dict[str, Note]
    _pending_notes: dict[str, PendingNoteAction]
    _zalo_pending_notes: dict[str, PendingNoteAction]

    def _initialize_note_state(self) -> None:
        self.notes = {}
        self._pending_notes = {}
        self._zalo_pending_notes = {}

    def _load_notes(self, stored: dict[str, Any]) -> None:
        for item in stored.get("notes", []):
            try:
                note = Note.from_dict(item)
            except (KeyError, TypeError, ValueError):
                continue
            # Reject malformed protected records instead of accidentally
            # exposing them as public notes.
            if note.is_private and not all(
                (
                    note.encrypted_content,
                    note.encryption_salt,
                    note.encryption_nonce,
                )
            ):
                continue
            if not note.is_private and not note.content:
                continue
            self.notes[note.note_id] = note

    def _serialize_notes(self) -> list[dict[str, Any]]:
        return [note.as_dict() for note in self.notes.values()]

    def _register_note_triggers(self, agent_manager: Any) -> list[Any]:
        return [
            agent_manager.register_trigger(
                NOTE_CREATE_SENTENCES, self._async_create_note_from_voice
            ),
            agent_manager.register_trigger(
                NOTE_LIST_SENTENCES, self._async_list_notes_from_voice
            ),
            agent_manager.register_trigger(
                NOTE_EDIT_SENTENCES, self._async_edit_note_from_voice
            ),
            agent_manager.register_trigger(
                NOTE_DELETE_SENTENCES, self._async_delete_note_from_voice
            ),
            agent_manager.register_trigger(
                NOTE_VIEW_SENTENCES, self._async_view_note_from_voice
            ),
        ]

    @property
    def note_count(self) -> int:
        """Return the total number of stored notes."""
        return len(self.notes)

    @property
    def note_sensor_rows(self) -> list[dict[str, Any]]:
        """Return safe note data for Home Assistant state attributes."""
        rows: list[dict[str, Any]] = []
        for index, note in enumerate(self._ordered_notes(), 1):
            rows.append(
                {
                    "stt": index,
                    "note_id": note.note_id,
                    "noi_dung": "Bảo mật" if note.is_private else note.content,
                    "muc_bao_mat": note.security_level,
                    "loai": "Bảo mật" if note.is_private else "Công khai",
                    "tao_luc": note.created_at.isoformat(),
                    "cap_nhat_luc": note.updated_at.isoformat(),
                    "nguon": "zalo" if note.owner_key else "voice_assist",
                    "dang_khoa": bool(
                        note.locked_until and note.locked_until > dt_util.now()
                    ),
                }
            )
        return rows

    def _ordered_notes(self) -> list[Note]:
        """Return the shared note list for every input channel.

        ``owner_key`` is retained only for source metadata and pending-chat
        isolation. It no longer limits which notes can be viewed, edited, or
        deleted. Existing 0.8.0 records therefore become globally available
        without a storage migration.
        """
        notes = list(self.notes.values())
        return sorted(
            notes,
            key=lambda item: (item.updated_at, item.created_at),
            reverse=True,
        )

    def _note_pending_items(self) -> list[PendingNoteAction]:
        return list(self._pending_notes.values())

    def _has_pending_notes(self) -> bool:
        return bool(self._pending_notes)

    def _purge_expired_note_pending(self) -> None:
        now = dt_util.now()
        for pending_id, pending in list(self._pending_notes.items()):
            if pending.expires_at <= now:
                del self._pending_notes[pending_id]
        for owner_key, pending in list(self._zalo_pending_notes.items()):
            if pending.expires_at <= now:
                del self._zalo_pending_notes[owner_key]

    def _clear_note_pending_for_source(self, source_keys: set[str]) -> None:
        for pending_id, pending in list(self._pending_notes.items()):
            if source_keys & pending.source_keys:
                del self._pending_notes[pending_id]

    def _clear_all_note_pending(self) -> None:
        self._pending_notes.clear()
        self._zalo_pending_notes.clear()

    def _new_note_pending(
        self,
        *,
        action: str,
        stage: str,
        owner_key: str | None,
        source_keys: set[str] | None = None,
        note_ids: list[str] | None = None,
        content: str | None = None,
    ) -> PendingNoteAction:
        now = dt_util.now()
        pending = PendingNoteAction(
            pending_id=uuid.uuid4().hex,
            action=action,
            stage=stage,
            source_keys=source_keys or set(),
            owner_key=owner_key,
            note_ids=note_ids or [],
            content=content,
            proposed_note_id=uuid.uuid4().hex if action == "create" else None,
            created_at=now,
            expires_at=now + timedelta(seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS),
        )
        return pending

    def _set_voice_note_pending(
        self, user_input: ConversationInput, pending: PendingNoteAction
    ) -> None:
        source_keys = self._source_keys(user_input)
        self._clear_pending_for_source(source_keys)
        pending.source_keys = source_keys
        self._pending_notes[pending.pending_id] = pending
        self._sync_pending_followup_trigger()

    def _set_zalo_note_pending(
        self, owner_key: str, pending: PendingNoteAction
    ) -> None:
        pending.owner_key = owner_key
        self._zalo_pending_notes[owner_key] = pending

    def _find_pending_note(
        self, user_input: ConversationInput
    ) -> PendingNoteAction | None:
        self._purge_expired_note_pending()
        source_keys = self._source_keys(user_input)
        matches = [
            pending
            for pending in self._pending_notes.values()
            if source_keys & pending.source_keys
        ]
        if matches:
            return max(matches, key=lambda item: item.created_at)
        if len(self._pending_notes) == 1:
            return next(iter(self._pending_notes.values()))
        return None

    def _zalo_pending_note(self, owner_key: str) -> PendingNoteAction | None:
        self._purge_expired_note_pending()
        return self._zalo_pending_notes.get(owner_key)

    def _remove_note_pending(self, pending: PendingNoteAction) -> None:
        self._pending_notes.pop(pending.pending_id, None)
        if pending.owner_key:
            current = self._zalo_pending_notes.get(pending.owner_key)
            if current is pending:
                self._zalo_pending_notes.pop(pending.owner_key, None)
        self._sync_pending_followup_trigger()

    def _touch_note_pending(self, pending: PendingNoteAction) -> None:
        pending.expires_at = dt_util.now() + timedelta(
            seconds=PENDING_CONFIRMATION_TIMEOUT_SECONDS
        )
        self._sync_pending_followup_trigger()

    @staticmethod
    def _safe_note_lines(notes: list[Note]) -> str:
        lines: list[str] = []
        for index, note in enumerate(notes, 1):
            if note.is_private:
                lines.append(f"{index} - Bảo mật")
            else:
                lines.append(f"{index} - {note.content}")
        return "\n".join(lines)

    def _note_list_prompt(
        self, notes: list[Note], *, action: str = "view", invalid: bool = False
    ) -> str:
        prefix = "Lựa chọn chưa hợp lệ.\n" if invalid else ""
        lines = self._safe_note_lines(notes)
        if action == "view":
            instruction = (
                "Ghi chú bảo mật không hiển thị nội dung. Để xem, trả lời "
                "số thứ tự và pass, ví dụ: số 2 pass 1234. Ghi chú công khai "
                "chỉ cần trả lời số thứ tự."
            )
        elif action == "edit":
            instruction = (
                "Chọn đúng một ghi chú và mức hiện tại, ví dụ: số 2 mức 1 "
                "hoặc số 3 mức 2."
            )
        else:
            instruction = (
                "Chọn đúng một ghi chú và mức hiện tại để xóa, ví dụ: "
                "số 2 mức 1 hoặc số 3 mức 2."
            )
        return f"{prefix}Danh sách ghi chú:\n{lines}\n{instruction}"

    @staticmethod
    def _security_prompt(action: str = "lưu") -> str:
        return (
            f"Chọn mức bảo mật cho ghi chú cần {action}:\n"
            "1 - Mức 1 Bảo mật, phải nhập pass khi xem;\n"
            "2 - Mức 2 Công khai, có thể xem trực tiếp."
        )

    @staticmethod
    def _confirmation_prompt(pending: PendingNoteAction) -> str:
        label = security_label(pending.security_level or NOTE_SECURITY_PUBLIC)
        if pending.action == "create":
            verb = "lưu ghi chú"
        elif pending.action == "edit":
            verb = "lưu thay đổi"
        else:
            verb = "xóa ghi chú"
        content = ""
        if pending.security_level == NOTE_SECURITY_PUBLIC and pending.content:
            content = f" Nội dung: {pending.content}."
        return (
            f"Xác nhận {verb} ở {label}?{content} "
            "Trả lời **có** hoặc **không**."
        )

    @staticmethod
    def _selection_index(text: str, notes: list[Note]) -> int | None:
        normalized = normalize_text(text)
        # Prefer an explicit note number so values in "mức 1" or in the
        # password are never mistaken for additional selected notes.
        match = re.search(r"(?:^|\b)(?:so|ghi chu)\s*(\d{1,3})\b", normalized)
        if match is None:
            match = re.match(r"\s*(\d{1,3})\b", normalized)
        if match is not None:
            index = int(match.group(1)) - 1
            return index if 0 <= index < len(notes) else None

        scrubbed = re.sub(r"\bmuc\s*[12]\b", " ", normalized)
        scrubbed = re.sub(r"\b(?:pass|password|mat khau)\b.*$", " ", scrubbed)
        labels = [
            "Bảo mật" if note.is_private else str(note.content or "")
            for note in notes
        ]
        indexes = parse_target_selection(scrubbed, labels)
        if len(indexes) != 1:
            return None
        return indexes[0]

    async def _async_add_note(self, note: Note) -> None:
        self.notes[note.note_id] = note
        self._save_later()
        self._notify_update()

    async def _async_delete_note_by_id(self, note_id: str) -> bool:
        if self.notes.pop(note_id, None) is None:
            return False
        self._save_later()
        self._notify_update()
        return True

    def _verify_note_password(self, note: Note, password: str) -> tuple[bool, str]:
        try:
            content = decrypt_note_content(note, password)
        except (NotePasswordError, NoteLockedError, ValueError) as err:
            self._save_later()
            self._notify_update()
            return False, str(err)
        self._save_later()
        self._notify_update()
        return True, content

    async def _async_process_note_pending_text(
        self, pending: PendingNoteAction, text: str
    ) -> str:
        self._touch_note_pending(pending)
        normalized = normalize_text(text)
        if normalized in {
            "bo yeu cau ghi chu",
            "huy yeu cau ghi chu",
            "dung thao tac ghi chu",
            "thoi khong lam nua",
        }:
            action = pending.action
            self._remove_note_pending(pending)
            return {
                "create": "Đã hủy lưu ghi chú.",
                "edit": "Đã hủy sửa ghi chú.",
                "delete": "Đã hủy xóa ghi chú.",
                "view": "Đã đóng danh sách ghi chú.",
            }.get(action, "Đã hủy yêu cầu ghi chú.")

        if pending.stage == "content":
            try:
                pending.content = clean_note_content(text)
            except ValueError as err:
                return str(err)
            pending.stage = "security"
            return self._security_prompt()

        if pending.stage == "security":
            level = parse_security_level(text)
            if level is None:
                return "Tôi chưa nhận ra mức bảo mật. " + self._security_prompt()
            pending.security_level = level
            if level == NOTE_SECURITY_PRIVATE:
                pending.stage = "new_password"
                return (
                    "Hãy nhập pass riêng cho ghi chú này, tối thiểu 4 ký tự. "
                    "Pass không được lưu dạng rõ."
                )
            pending.stage = "confirm"
            return self._confirmation_prompt(pending)

        if pending.stage == "select":
            notes = [
                self.notes[note_id]
                for note_id in pending.note_ids
                if note_id in self.notes
            ]
            if not notes:
                self._remove_note_pending(pending)
                return "Danh sách ghi chú đã thay đổi và hiện không còn mục nào."
            index = self._selection_index(text, notes)
            if index is None:
                return self._note_list_prompt(
                    notes, action=pending.action, invalid=True
                )
            note = notes[index]
            pending.selected_note_id = note.note_id

            if pending.action in {"edit", "delete"}:
                declared = parse_security_level(text)
                if declared is None:
                    return (
                        "Hãy ghi kèm mức hiện tại của ghi chú. "
                        f"Ghi chú số {index + 1} là "
                        f"{security_label(note.security_level)}."
                    )
                if declared != note.security_level:
                    pending.selected_note_id = None
                    return (
                        "Mức bảo mật bạn chọn không khớp với ghi chú. "
                        + self._note_list_prompt(notes, action=pending.action)
                    )

            supplied_password = extract_password(text)
            if note.is_private:
                if supplied_password:
                    # Keep the selected note so a wrong pass can be retried
                    # without repeating the number and security level.
                    pending.stage = "verify_password"
                    ok, result = self._verify_note_password(
                        note, supplied_password
                    )
                    if not ok:
                        return result
                    if pending.action == "view":
                        pending.selected_note_id = None
                        return (
                            f"Nội dung ghi chú số {index + 1}: {result}\n"
                            "Bạn có thể nhập số khác để xem tiếp."
                        )
                    if pending.action == "edit":
                        pending.stage = "new_content"
                        return "Đã xác thực. Hãy nhập nội dung mới cho ghi chú."
                    pending.security_level = note.security_level
                    pending.stage = "confirm"
                    return self._confirmation_prompt(pending)
                pending.stage = "verify_password"
                return f"Ghi chú số {index + 1} là Bảo mật. Hãy nhập pass."

            if pending.action == "view":
                pending.selected_note_id = None
                return (
                    f"Nội dung ghi chú số {index + 1}: {note.content}\n"
                    "Bạn có thể nhập số khác để xem tiếp."
                )
            if pending.action == "edit":
                pending.stage = "new_content"
                return "Hãy nhập nội dung mới cho ghi chú."
            pending.security_level = note.security_level
            pending.stage = "confirm"
            return self._confirmation_prompt(pending)

        if pending.stage == "verify_password":
            note = self.notes.get(pending.selected_note_id or "")
            if note is None:
                self._remove_note_pending(pending)
                return "Ghi chú đã thay đổi hoặc không còn tồn tại."
            password = extract_password(text, allow_whole_text=True)
            if password is None:
                return "Hãy nhập pass của ghi chú."
            ok, result = self._verify_note_password(note, password)
            if not ok:
                return result
            if pending.action == "view":
                pending.stage = "select"
                pending.selected_note_id = None
                return (
                    f"Nội dung ghi chú: {result}\n"
                    "Bạn có thể nhập số khác để xem tiếp."
                )
            if pending.action == "edit":
                pending.stage = "new_content"
                return "Đã xác thực. Hãy nhập nội dung mới cho ghi chú."
            pending.security_level = note.security_level
            pending.stage = "confirm"
            return self._confirmation_prompt(pending)

        if pending.stage == "new_content":
            try:
                pending.content = clean_note_content(text)
            except ValueError as err:
                return str(err)
            pending.stage = "new_security"
            current = self.notes.get(pending.selected_note_id or "")
            current_hint = (
                f" Mức hiện tại là {security_label(current.security_level)}; "
                "có thể trả lời **giữ nguyên**."
                if current
                else ""
            )
            return self._security_prompt("sửa") + current_hint

        if pending.stage == "new_security":
            current = self.notes.get(pending.selected_note_id or "")
            level = parse_security_level(
                text, current.security_level if current else None
            )
            if level is None:
                return "Tôi chưa nhận ra mức bảo mật. " + self._security_prompt("sửa")
            pending.security_level = level
            if level == NOTE_SECURITY_PRIVATE:
                pending.stage = "new_password"
                return (
                    "Hãy đặt pass mới cho phiên bản ghi chú bảo mật này, "
                    "tối thiểu 4 ký tự."
                )
            pending.encrypted_content = None
            pending.encryption_salt = None
            pending.encryption_nonce = None
            pending.stage = "confirm"
            return self._confirmation_prompt(pending)

        if pending.stage == "new_password":
            password = extract_password(text, allow_whole_text=True)
            if password is None:
                return "Hãy nhập pass cho ghi chú."
            try:
                encrypted, salt, nonce = encrypt_note_content(
                    pending.proposed_note_id
                    or pending.selected_note_id
                    or uuid.uuid4().hex,
                    pending.content or "",
                    password,
                )
            except ValueError as err:
                return str(err)
            pending.encrypted_content = encrypted
            pending.encryption_salt = salt
            pending.encryption_nonce = nonce
            # Do not keep protected plaintext in the pending object.
            pending.content = None
            pending.stage = "confirm"
            return self._confirmation_prompt(pending)

        if pending.stage == "confirm":
            if is_negative(text):
                action = pending.action
                self._remove_note_pending(pending)
                return {
                    "create": "Đã hủy lưu ghi chú.",
                    "edit": "Đã hủy sửa ghi chú.",
                    "delete": "Đã hủy xóa ghi chú.",
                }.get(action, "Đã hủy yêu cầu.")
            if not is_affirmative(text):
                return (
                    "Hãy trả lời **có** để xác nhận hoặc **không** "
                    "để **hủy**."
                )

            now = dt_util.now()
            if pending.action == "create":
                note_id = pending.proposed_note_id or uuid.uuid4().hex
                note = Note(
                    note_id=note_id,
                    security_level=pending.security_level
                    or NOTE_SECURITY_PUBLIC,
                    created_at=now,
                    updated_at=now,
                    owner_key=pending.owner_key,
                    content=(
                        pending.content
                        if pending.security_level == NOTE_SECURITY_PUBLIC
                        else None
                    ),
                    encrypted_content=pending.encrypted_content,
                    encryption_salt=pending.encryption_salt,
                    encryption_nonce=pending.encryption_nonce,
                )
                await self._async_add_note(note)
                self._remove_note_pending(pending)
                return (
                    f"Đã lưu ghi chú ở {security_label(note.security_level)}. "
                    f"Hiện có {self.note_count} ghi chú."
                )

            note = self.notes.get(pending.selected_note_id or "")
            if note is None:
                self._remove_note_pending(pending)
                return "Ghi chú đã thay đổi hoặc không còn tồn tại."

            if pending.action == "edit":
                note.security_level = pending.security_level or NOTE_SECURITY_PUBLIC
                note.updated_at = now
                note.failed_attempts = 0
                note.locked_until = None
                if note.security_level == NOTE_SECURITY_PRIVATE:
                    note.content = None
                    note.encrypted_content = pending.encrypted_content
                    note.encryption_salt = pending.encryption_salt
                    note.encryption_nonce = pending.encryption_nonce
                else:
                    note.content = pending.content
                    note.encrypted_content = None
                    note.encryption_salt = None
                    note.encryption_nonce = None
                self._save_later()
                self._notify_update()
                self._remove_note_pending(pending)
                return f"Đã cập nhật ghi chú ở {security_label(note.security_level)}."

            await self._async_delete_note_by_id(note.note_id)
            self._remove_note_pending(pending)
            return (
                "Đã xóa ghi chú. "
                f"Còn {self.note_count} ghi chú."
            )

        self._remove_note_pending(pending)
        return "Yêu cầu ghi chú đã hết hiệu lực. Hãy thực hiện lại."

    def _start_create_note(
        self,
        *,
        content: str,
        owner_key: str | None,
        source_keys: set[str] | None = None,
    ) -> tuple[PendingNoteAction, str]:
        try:
            cleaned = clean_note_content(content) if content else None
        except ValueError as err:
            pending = self._new_note_pending(
                action="create",
                stage="content",
                owner_key=owner_key,
                source_keys=source_keys,
            )
            return pending, str(err) + " Hãy nhập lại nội dung."
        pending = self._new_note_pending(
            action="create",
            stage="security" if cleaned else "content",
            owner_key=owner_key,
            source_keys=source_keys,
            content=cleaned,
        )
        prompt = (
            self._security_prompt()
            if cleaned
            else "Bạn muốn ghi nhớ nội dung gì?"
        )
        return pending, prompt

    def _start_note_list_action(
        self,
        *,
        action: str,
        owner_key: str | None,
        source_keys: set[str] | None = None,
    ) -> tuple[PendingNoteAction | None, str]:
        notes = self._ordered_notes()
        if not notes:
            return None, "Bạn chưa có ghi chú nào."
        pending = self._new_note_pending(
            action=action,
            stage="select",
            owner_key=owner_key,
            source_keys=source_keys,
            note_ids=[note.note_id for note in notes],
        )
        return pending, self._note_list_prompt(notes, action=action)

    async def _async_create_note_from_voice(
        self, user_input: ConversationInput, result: RecognizeResult
    ) -> str:
        request = self._request_slot(user_input, result)
        if not result.entities.get("request"):
            request = _extract_note_request(user_input.text)
        pending, prompt = self._start_create_note(
            content=request,
            owner_key=None,
            source_keys=self._source_keys(user_input),
        )
        self._set_voice_note_pending(user_input, pending)
        return await self._async_voice_response(user_input, prompt)

    async def _async_list_notes_from_voice(
        self, user_input: ConversationInput, _result: RecognizeResult
    ) -> str:
        pending, prompt = self._start_note_list_action(
            action="view",
            owner_key=None,
            source_keys=self._source_keys(user_input),
        )
        if pending:
            self._set_voice_note_pending(user_input, pending)
        return await self._async_voice_response(user_input, prompt)

    async def _async_edit_note_from_voice(
        self, user_input: ConversationInput, _result: RecognizeResult
    ) -> str:
        pending, prompt = self._start_note_list_action(
            action="edit",
            owner_key=None,
            source_keys=self._source_keys(user_input),
        )
        if pending:
            self._set_voice_note_pending(user_input, pending)
        return await self._async_voice_response(user_input, prompt)

    async def _async_delete_note_from_voice(
        self, user_input: ConversationInput, _result: RecognizeResult
    ) -> str:
        pending, prompt = self._start_note_list_action(
            action="delete",
            owner_key=None,
            source_keys=self._source_keys(user_input),
        )
        if pending:
            self._set_voice_note_pending(user_input, pending)
        return await self._async_voice_response(user_input, prompt)

    async def _async_view_note_from_voice(
        self, user_input: ConversationInput, result: RecognizeResult
    ) -> str:
        pending, prompt = self._start_note_list_action(
            action="view",
            owner_key=None,
            source_keys=self._source_keys(user_input),
        )
        if pending is None:
            return await self._async_voice_response(user_input, prompt)
        self._set_voice_note_pending(user_input, pending)
        request = self._request_slot(user_input, result)
        if request and re.search(r"\d", request):
            prompt = await self._async_process_note_pending_text(
                pending, request
            )
        return await self._async_voice_response(user_input, prompt)

    async def _async_pending_note_followup_from_voice(
        self,
        user_input: ConversationInput,
        _result: RecognizeResult,
        pending: PendingNoteAction | None = None,
    ) -> str:
        pending = pending or self._find_pending_note(user_input)
        if pending is None:
            return await self._async_voice_response(
                user_input, "Không có yêu cầu ghi chú nào đang chờ."
            )
        response = await self._async_process_note_pending_text(
            pending, user_input.text
        )
        return await self._async_voice_response(user_input, response)

    async def _async_process_note_zalo_command(
        self, context: Any, command: str
    ) -> str:
        owner_key = context.owner_key
        if command == "note_create":
            content = _extract_note_request(context.text)
            pending, prompt = self._start_create_note(
                content=content, owner_key=owner_key
            )
            self._set_zalo_note_pending(owner_key, pending)
            return prompt

        action = {
            "note_list": "view",
            "note_view": "view",
            "note_edit": "edit",
            "note_delete": "delete",
        }[command]
        pending, prompt = self._start_note_list_action(
            action=action, owner_key=owner_key
        )
        if pending is None:
            return prompt
        self._set_zalo_note_pending(owner_key, pending)

        if command == "note_view":
            request = context.text
            if re.search(r"\d", request):
                return await self._async_process_note_pending_text(
                    pending, request
                )
        return prompt

    async def _async_pending_note_reply_from_zalo(
        self, context: Any, pending: PendingNoteAction
    ) -> str:
        return await self._async_process_note_pending_text(
            pending, context.text
        )
