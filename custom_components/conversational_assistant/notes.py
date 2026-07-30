"""Secure note helpers for Conversational Assistant."""

from __future__ import annotations

import base64
from datetime import timedelta
import hashlib
import os
import re
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from homeassistant.util import dt as dt_util

from .models import Note
from .targeting import normalize_text

NOTE_SECURITY_PRIVATE: Final = 1
NOTE_SECURITY_PUBLIC: Final = 2
NOTE_KDF_ITERATIONS: Final = 260_000
NOTE_MAX_CONTENT_LENGTH: Final = 4_000
NOTE_MIN_PASSWORD_LENGTH: Final = 4
NOTE_MAX_FAILED_ATTEMPTS: Final = 5
NOTE_LOCKOUT_MINUTES: Final = 5


class NotePasswordError(ValueError):
    """Raised when a protected note password is invalid."""


class NoteLockedError(ValueError):
    """Raised when a protected note is temporarily locked."""


def clean_note_content(value: str) -> str:
    """Normalize and validate note content."""
    content = re.sub(r"\s+", " ", str(value or "").strip())
    if not content:
        raise ValueError("Nội dung ghi chú đang trống.")
    if len(content) > NOTE_MAX_CONTENT_LENGTH:
        raise ValueError(
            f"Ghi chú dài tối đa {NOTE_MAX_CONTENT_LENGTH} ký tự."
        )
    return content


def validate_note_password(value: str) -> str:
    """Validate one per-note password without changing its characters."""
    password = str(value or "").strip()
    if len(password) < NOTE_MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Pass cần ít nhất {NOTE_MIN_PASSWORD_LENGTH} ký tự."
        )
    if len(password) > 256:
        raise ValueError("Pass quá dài.")
    return password


def _derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        NOTE_KDF_ITERATIONS,
        dklen=32,
    )


def encrypt_note_content(
    note_id: str, content: str, password: str
) -> tuple[str, str, str]:
    """Encrypt content and return base64 ciphertext, salt, and nonce."""
    content = clean_note_content(content)
    password = validate_note_password(password)
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_key(password, salt)
    encrypted = AESGCM(key).encrypt(
        nonce,
        content.encode("utf-8"),
        note_id.encode("utf-8"),
    )
    return (
        base64.b64encode(encrypted).decode("ascii"),
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(nonce).decode("ascii"),
    )


def decrypt_note_content(note: Note, password: str) -> str:
    """Decrypt a protected note or raise a safe authentication error."""
    now = dt_util.now()
    if note.locked_until is not None and note.locked_until > now:
        remaining = max(
            1, int((note.locked_until - now).total_seconds() // 60) + 1
        )
        raise NoteLockedError(
            f"Ghi chú đang khóa tạm thời. Thử lại sau khoảng {remaining} phút."
        )

    password = validate_note_password(password)
    try:
        encrypted = base64.b64decode(note.encrypted_content or "", validate=True)
        salt = base64.b64decode(note.encryption_salt or "", validate=True)
        nonce = base64.b64decode(note.encryption_nonce or "", validate=True)
        key = _derive_key(password, salt)
        plaintext = AESGCM(key).decrypt(
            nonce,
            encrypted,
            note.note_id.encode("utf-8"),
        )
    except (InvalidTag, ValueError, TypeError):
        note.failed_attempts += 1
        if note.failed_attempts >= NOTE_MAX_FAILED_ATTEMPTS:
            note.failed_attempts = 0
            note.locked_until = now + timedelta(minutes=NOTE_LOCKOUT_MINUTES)
            raise NoteLockedError(
                "Sai pass quá nhiều lần. Ghi chú đã khóa tạm thời 5 phút."
            ) from None
        remaining = NOTE_MAX_FAILED_ATTEMPTS - note.failed_attempts
        raise NotePasswordError(
            f"Pass không đúng. Còn {remaining} lần thử trước khi khóa tạm thời."
        ) from None

    note.failed_attempts = 0
    note.locked_until = None
    return plaintext.decode("utf-8")


def parse_security_level(text: str, current_level: int | None = None) -> int | None:
    """Parse natural Vietnamese security-level choices."""
    normalized = normalize_text(text)
    if current_level is not None and any(
        phrase in normalized
        for phrase in (
            "keep current",
            "keep the same",
            "same level",
            "current level",
            "giu nguyen",
            "muc cu",
            "bao mat cu",
        )
    ):
        return current_level
    if re.search(r"\b(?:muc|level)\s*1\b", normalized):
        return NOTE_SECURITY_PRIVATE
    if re.search(r"\b(?:muc|level)\s*2\b", normalized):
        return NOTE_SECURITY_PUBLIC
    if any(
        phrase in normalized
        for phrase in (
            "bao mat",
            "rieng tu",
            "co pass",
            "can pass",
            "private",
            "protected",
            "password protected",
            "with password",
            "secure",
        )
    ):
        return NOTE_SECURITY_PRIVATE
    if any(
        phrase in normalized
        for phrase in (
            "cong khai",
            "khong pass",
            "public",
            "without password",
            "no password",
            "unprotected",
        )
    ):
        return NOTE_SECURITY_PUBLIC
    if normalized in {"1", "mot", "one"}:
        return NOTE_SECURITY_PRIVATE
    if normalized in {"2", "hai", "two"}:
        return NOTE_SECURITY_PUBLIC
    return None


def extract_password(text: str, *, allow_whole_text: bool = False) -> str | None:
    """Extract a password from natural text without normalizing its value."""
    value = str(text or "").strip()
    match = re.search(
        r"(?:pass(?:word)?|mật\s*khẩu|mat\s*khau)"
        r"\s*(?:(?:là|la|is)\s*)?[:=\-]?\s*(.+)$",
        value,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return value if allow_whole_text and value else None


def is_affirmative(text: str) -> bool:
    """Return whether text confirms an operation."""
    return normalize_text(text) in {
        "co",
        "dong y",
        "xac nhan",
        "luu",
        "luu di",
        "duoc",
        "ok",
        "okay",
        "yes",
        "confirm",
        "confirmed",
        "save",
        "save it",
        "proceed",
        "continue",
        "go ahead",
        "do it",
        "tiep tuc",
    }


def is_negative(text: str) -> bool:
    """Return whether text cancels an operation."""
    return normalize_text(text) in {
        "khong",
        "khong luu",
        "khong xoa",
        "huy",
        "huy bo",
        "bo qua",
        "thoi",
        "no",
        "cancel",
        "cancel it",
        "stop",
        "do not save",
        "don't save",
        "don t save",
        "do not delete",
        "don't delete",
        "don t delete",
        "never mind",
    }


def security_label(level: int) -> str:
    """Return a Vietnamese label for one note level."""
    return "Mức 1 - Bảo mật" if level == NOTE_SECURITY_PRIVATE else "Mức 2 - Công khai"
