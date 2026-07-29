"""Constants for Conversational Assistant."""

from __future__ import annotations

DOMAIN = "conversational_assistant"
INTEGRATION_NAME = "Conversational Assistant"
PLATFORMS = ["sensor"]

CONF_NOTIFICATION_DEVICES = "notification_devices"
CONF_DISMISS_ON_CLEAR = "dismiss_on_clear"
CONF_CONFIRM_TARGETS = "confirm_targets"
CONF_ZALO_TARGETS = "zalo_targets"
CONF_SPEAKER_ENABLED = "speaker_enabled"
CONF_TTS_ENTITY_ID = "tts_entity_id"

# Incoming Zalo messages (zca-js compatible webhook payloads).
CONF_ZALO_WEBHOOK_ENABLED = "zalo_webhook_enabled"
CONF_ZALO_WEBHOOK_BOT_ACCOUNT_ID = "zalo_webhook_bot_account_id"
CONF_ZALO_WEBHOOK_ACCOUNT_SELECTION = "zalo_webhook_account_selection"
CONF_ZALO_HOME_ASSISTANT_ENABLED = "zalo_home_assistant_enabled"
CONF_ZALO_CONVERSATION_AGENT_ID = "zalo_conversation_agent_id"

# Legacy single-Zalo options, retained for automatic migration.
CONF_ZALO_ENABLED = "zalo_enabled"
CONF_ZALO_TYPE = "zalo_type"
CONF_ZALO_THREAD_ID = "zalo_thread_id"
CONF_ZALO_ACCOUNT_SELECTION = "zalo_account_selection"

CONF_ZALO_TARGET_ID = "target_id"
CONF_ZALO_TARGET_NAME = "name"
CONF_ZALO_TARGET_ENABLED = "enabled"

DEFAULT_DISMISS_ON_CLEAR = False
DEFAULT_CONFIRM_TARGETS = True
DEFAULT_SNOOZE_MINUTES = 10
DEFAULT_ZALO_ENABLED = False
DEFAULT_ZALO_TYPE = "1"
DEFAULT_SPEAKER_ENABLED = True
DEFAULT_ZALO_WEBHOOK_ENABLED = True
DEFAULT_ZALO_WEBHOOK_BOT_ACCOUNT_ID = "781454039143291053"
DEFAULT_ZALO_HOME_ASSISTANT_ENABLED = True
DEFAULT_ZALO_CONVERSATION_AGENT_ID = "conversation.home_assistant"

# Action used by an existing webhook/automation to pass Zalo payloads in.
SERVICE_PROCESS_ZALO_WEBHOOK = "process_zalo_webhook"
ATTR_ZALO_PAYLOAD = "payload"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"

ZALO_DOMAIN = "zalo_bot"
ZALO_SERVICE_SEND_MESSAGE = "send_message"
ZALO_TYPE_USER = "0"
ZALO_TYPE_GROUP = "1"

ZALO_WEBHOOK_SEEN_MESSAGE_LIMIT = 512

TTS_DOMAIN = "tts"
TTS_SERVICE_SPEAK = "speak"
MEDIA_PLAYER_DOMAIN = "media_player"

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = DOMAIN

EVENT_NOTIFICATION_ACTION = "mobile_app_notification_action"
EVENT_NOTIFICATION_CLEARED = "mobile_app_notification_cleared"

SIGNAL_UPDATE = f"{DOMAIN}_update"

ACTION_SNOOZE = "CONVERSATIONAL_ASSISTANT_SNOOZE"
ACTION_DISMISS = "CONVERSATIONAL_ASSISTANT_DISMISS"

PENDING_SELECTION_TIMEOUT_MINUTES = 5

ASSIST_SATELLITE_DOMAIN = "assist_satellite"
ASSIST_SATELLITE_SERVICE_ANNOUNCE = "announce"

# Registered only while a reminder is waiting for destination confirmation.
PENDING_FOLLOWUP_SENTENCES = ["{selection}"]

CREATE_SENTENCES = [
    # Explicit forms first so their wildcard contains only the actual request.
    "[hãy ]nhắc tôi {request}",
    "[hãy ]hẹn giờ nhắc tôi {request}",
    "[hãy ]tạo hẹn giờ nhắc tôi {request}",
    "(tạo|đặt|thêm) (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ) {request}",
    # Natural short commands.
    "[hãy ](nhắc|hẹn) {request}",
]



LIST_SENTENCES = [
    "liệt kê (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ)",
    "đọc danh sách (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ)",
    "xem danh sách (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ)",
    "danh sách (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ)",
    "cho tôi danh sách (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ)",
    "tôi có những (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ) nào",
    "(nhắc hẹn|nhắc nhở) tiếp theo là gì",
]

CANCEL_SENTENCES = [
    # Accept both common Vietnamese spellings: xóa/xoá and hủy/huỷ.
    "(hủy|huỷ|xóa|xoá) (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ)",
    "(hủy|huỷ|xóa|xoá) (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ) {request}",
    "(hủy|huỷ|xóa|xoá) tất cả (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ)",
    "(hủy|huỷ|xóa|xoá) toàn bộ (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ)",
]


TARGET_SELECTION_SENTENCES = [
    "(chọn|xác nhận|gửi đến|thông báo đến) {selection}",
    "tôi chọn {selection}",
    "hãy gửi đến {selection}",
    # Natural numeric-only follow-up answers. Home Assistant strips common
    # punctuation before matching, so these also cover inputs such as
    # "1,3" and "1-3" in addition to "1 3" and "1 và 3".
    "{1..99:selection_1}",
    "{1..99:selection_1} [và] {1..99:selection_2}",
    "{1..99:selection_1} [và] {1..99:selection_2} [và] {1..99:selection_3}",
    "{1..99:selection_1} [và] {1..99:selection_2} [và] {1..99:selection_3} [và] {1..99:selection_4}",
    "{1..99:selection_1} [và] {1..99:selection_2} [và] {1..99:selection_3} [và] {1..99:selection_4} [và] {1..99:selection_5}",
    "tất cả",
    "tất cả (loa|điện thoại|zalo)",
]

CANCEL_PENDING_SENTENCES = [
    "bỏ yêu cầu vừa rồi",
    "không lưu nhắc nhở này",
    "dừng tạo nhắc nhở",
]


# Natural-language note commands. Protected notes are encrypted per note and
# are never exposed through list responses or sensor attributes.
NOTE_CREATE_SENTENCES = [
    "(thêm|tạo|lưu|viết) (ghi chú|ghi nhớ|note)",
    "(thêm|tạo|lưu|viết) (ghi chú|ghi nhớ|note) {request}",
    "(ghi chú|ghi nhớ|note|ghi lại)",
    "(ghi chú|ghi nhớ|note|ghi lại) {request}",
    "hãy (ghi chú|ghi nhớ|nhớ|ghi lại) {request}",
    "[hãy ]nhớ rằng {request}",
    "[hãy ]nhớ giúp tôi {request}",
]


NOTE_LIST_SENTENCES = [
    "liệt kê (ghi chú|ghi nhớ)",
    "danh sách (ghi chú|ghi nhớ)",
    "xem danh sách (ghi chú|ghi nhớ)",
    "đọc danh sách (ghi chú|ghi nhớ)",
    "(ghi chú|ghi nhớ) của tôi",
    "tôi có những ghi chú nào",
    "tôi có ghi chú gì",
    "xem ghi chú",
    "các ghi chú",
    "cho tôi xem (ghi chú|ghi nhớ)",
    "đọc (ghi chú|ghi nhớ) của tôi",
]

NOTE_EDIT_SENTENCES = [
    "(sửa|chỉnh sửa|cập nhật|đổi) (ghi chú|ghi nhớ|note)",
    "(sửa|chỉnh sửa|cập nhật|đổi) (ghi chú|ghi nhớ|note) {request}",
]

NOTE_DELETE_SENTENCES = [
    "(xóa|xoá|hủy|huỷ) (ghi chú|ghi nhớ|note)",
    "(xóa|xoá|hủy|huỷ) (ghi chú|ghi nhớ|note) {request}",
]

NOTE_VIEW_SENTENCES = [
    "(mở|đọc) ghi chú {request}",
    "xem nội dung ghi chú {request}",
    "xem ghi chú số {request}",
]
