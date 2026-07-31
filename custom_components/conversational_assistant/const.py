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

# Calendar event sensor and scheduled notification settings.
CONF_CALENDAR_LOOKAHEAD_DAYS = "calendar_lookahead_days"
CONF_CALENDAR_NOTIFICATION_ENABLED = "calendar_notification_enabled"
CONF_CALENDAR_NOTIFICATION_TIME = "calendar_notification_time"
CONF_CALENDAR_NOTIFICATION_MOBILE_DEVICES = (
    "calendar_notification_mobile_devices"
)
CONF_CALENDAR_NOTIFICATION_ZALO_TARGETS = (
    "calendar_notification_zalo_targets"
)

# Incoming Zalo messages (zca-js compatible webhook payloads).
CONF_ZALO_WEBHOOK_ENABLED = "zalo_webhook_enabled"
CONF_ZALO_WEBHOOK_BOT_ACCOUNT_ID = "zalo_webhook_bot_account_id"
CONF_ZALO_WEBHOOK_ACCOUNT_SELECTION = "zalo_webhook_account_selection"
CONF_ZALO_HOME_ASSISTANT_ENABLED = "zalo_home_assistant_enabled"
CONF_ZALO_CONVERSATION_AGENT_ID = "zalo_conversation_agent_id"
CONF_AI_SEARCH_AGENT_ID = "ai_search_agent_id"
CONF_AI_IMAGE_TASK_ENTITY_ID = "ai_image_task_entity_id"
CONF_AI_CAMERA_TASK_ENTITY_ID = "ai_camera_task_entity_id"
CONF_AI_AGENT_FAILOVER_ENABLED = "ai_agent_failover_enabled"

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
DEFAULT_CALENDAR_LOOKAHEAD_DAYS = 30
DEFAULT_CALENDAR_NOTIFICATION_ENABLED = False
DEFAULT_CALENDAR_NOTIFICATION_TIME = "07:00:00"
MAX_CALENDAR_LOOKAHEAD_DAYS = 365
CALENDAR_REFRESH_INTERVAL_MINUTES = 15
DEFAULT_ZALO_WEBHOOK_ENABLED = True
# Deliberately blank. Each installation must provide its own Zalo bot
# account ID instead of inheriting a developer-specific value.
DEFAULT_ZALO_WEBHOOK_BOT_ACCOUNT_ID = ""
DEFAULT_ZALO_HOME_ASSISTANT_ENABLED = True
DEFAULT_ZALO_CONVERSATION_AGENT_ID = "conversation.home_assistant"
DEFAULT_AI_SEARCH_AGENT_ID = ""
DEFAULT_AI_IMAGE_TASK_ENTITY_ID = ""
DEFAULT_AI_CAMERA_TASK_ENTITY_ID = ""
DEFAULT_AI_AGENT_FAILOVER_ENABLED = True

AI_TASK_DOMAIN = "ai_task"
AI_TASK_SERVICE_GENERATE_IMAGE = "generate_image"
AI_TASK_SERVICE_GENERATE_DATA = "generate_data"

# Action used by an existing webhook/automation to pass Zalo payloads in.
SERVICE_PROCESS_ZALO_WEBHOOK = "process_zalo_webhook"
ATTR_ZALO_PAYLOAD = "payload"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"

ZALO_DOMAIN = "zalo_bot"
ZALO_SERVICE_SEND_MESSAGE = "send_message"
ZALO_SERVICE_SEND_IMAGE = "send_image"
ZALO_SERVICE_SEND_IMAGES_TO_GROUP = "send_images_to_group"
ZALO_SERVICE_SEND_TYPING_EVENT = "send_typing_event"
ZALO_TYPE_USER = "0"
ZALO_TYPE_GROUP = "1"

ZALO_WEBHOOK_SEEN_MESSAGE_LIMIT = 512

# Refresh the native Zalo typing indicator while a command is still being
# processed. The task is created only for an active webhook request and is
# stopped immediately after the final text/image response is delivered.
ZALO_TYPING_REFRESH_SECONDS = 4

# Long-running Zalo jobs are detached from the webhook action so the original
# automation can finish promptly. These limits guarantee a final error message
# instead of leaving the user waiting forever when an AI provider stalls.
ZALO_SEARCH_TIMEOUT_SECONDS = 180
ZALO_IMAGE_TIMEOUT_SECONDS = 360
CAMERA_ANALYSIS_TIMEOUT_SECONDS = 180

# Device/entity discovery is intentionally lazy.  A short cache keeps repeated
# reminder/camera requests fast without scanning Home Assistant registries while
# Home Assistant is starting.
DISCOVERY_CACHE_SECONDS = 60

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

# Every multi-turn confirmation/selection remains valid for exactly 120 seconds.
# The timeout is refreshed whenever the integration sends the next prompt.
PENDING_CONFIRMATION_TIMEOUT_SECONDS = 120

# Registered only while a reminder is waiting for destination confirmation.
PENDING_FOLLOWUP_SENTENCES = ["{selection}"]

# Users can teach persistent alternative phrases for existing workflows.
# These management commands are static; learned phrases themselves are
# registered dynamically after loading Home Assistant Store.
COMMAND_LEARN_SENTENCES = [
    "[please ](learn|teach|add) command",
    "[please ](learn|teach|add) command {request}",
    "[please ]add custom command {request}",
    "[please ]add phrase {request}",
    "[hãy ](học|dạy|thêm) câu lệnh",
    "[hãy ](học|dạy|thêm) câu lệnh {request}",
    "[hãy ]thêm câu lệnh tùy chỉnh",
    "[hãy ]thêm câu lệnh tùy chỉnh {request}",
    "[hãy ](thêm|dạy) cách nói",
    "[hãy ](thêm|dạy) cách nói {request}",
]

COMMAND_LIST_SENTENCES = [
    "[please ]list learned commands",
    "[please ]show learned commands",
    "[please ]show custom commands",
    "what commands have I taught you",
    "command memory",
    "[hãy ]danh sách câu lệnh đã học",
    "[hãy ]liệt kê câu lệnh đã học",
    "[hãy ]xem câu lệnh đã học",
    "[hãy ]các câu lệnh đã học",
    "[hãy ]tôi đã dạy những câu lệnh nào",
    "[hãy ]bộ nhớ câu lệnh",
]

COMMAND_DELETE_SENTENCES = [
    "[please ](delete|remove|forget) command",
    "[please ](delete|remove|forget) command {request}",
    "[please ](delete|remove|forget) all learned commands",
    "[please ]clear command memory",
    "[hãy ](xóa|xoá|quên) câu lệnh",
    "[hãy ](xóa|xoá|quên) câu lệnh {request}",
    "[hãy ](xóa|xoá) câu lệnh đã học {request}",
    "[hãy ](xóa|xoá) câu lệnh tùy chỉnh {request}",
    "[hãy ](xóa|xoá|quên) tất cả câu lệnh đã học",
    "[hãy ](xóa|xoá|quên) toàn bộ câu lệnh đã học",
]

# Dedicated search triggers keep Internet queries inside this integration,
# including while another workflow is waiting for a follow-up answer.
SEARCH_SENTENCES = [
    "[hãy ]tìm thông tin",
    "[hãy ]tìm thông tin {request}",
    "[hãy ]tìm kiếm",
    "[hãy ]tìm kiếm {request}",
    "[hãy ]tìm kiếm trên mạng",
    "[hãy ]tìm kiếm trên mạng {request}",
    "[hãy ]tìm trên mạng",
    "[hãy ]tìm trên mạng {request}",
    "[hãy ]tra cứu",
    "[hãy ]tra cứu {request}",
    "[please ]search for",
    "[please ]search for {request}",
    "[please ]search the internet for",
    "[please ]search the internet for {request}",
    "[please ]search the web for",
    "[please ]search the web for {request}",
    "[please ]look up",
    "[please ]look up {request}",
    "[please ]find information about",
    "[please ]find information about {request}",
]


# Camera analysis uses AI Task generate_data with the selected camera media
# source attached. Each selected camera is processed independently so one
# unavailable camera or provider failure does not discard other results.
CAMERA_ANALYSIS_INSTRUCTIONS = (
    "Phân tích camera nếu có người hãy đếm số người, mô tả giới tính, độ tuổi, "
    "đặc điểm nhận dạng mũ nón đầu tóc trang phục, xe đang ở bên cạnh hoặc điều "
    "khiển là xe gì. Nếu có động vật hãy mô tả loài gì, đặc điểm loài. Bỏ qua các "
    "chi tiết vật thể cố định. Nếu không có người hay động vật trả lời Không có "
    "người, động vật. Chỉ trả lại nội dung trên một dòng duy nhất ( không ngắt "
    "dòng). Mô tả ngắn gọn đủ ý không thưa gửi dài dòng."
)

CAMERA_ANALYSIS_SENTENCES = [
    "[hãy ]phân tích cam",
    "[hãy ]phân tích camera",
    "[hãy ]kiểm tra cam",
    "[hãy ]kiểm tra camera",
    "[hãy ]xem và phân tích cam",
    "[hãy ]xem và phân tích camera",
    "[please ]analyze camera",
    "[please ]analyse camera",
    "[please ]check camera",
    "[please ]inspect camera",
]

# AI image generation is currently delivered to the originating Zalo chat.
# The same action can be taught additional aliases through command memory.
IMAGE_GENERATION_PREFIXES = (
    "tạo một bức ảnh",
    "tạo bức ảnh",
    "tạo một ảnh",
    "tạo ảnh",
    "generate an image",
    "generate image",
    "create an image",
    "create image",
    "make an image",
    "make image",
    "draw an image",
    "draw image",
)


HELP_SENTENCES = [
    "help",
    "[please ]show help",
    "[please ]show commands",
    "[please ]show features",
    "[please ](help|guide) me [to ]use (the integration|conversational assistant)",
    "how [do I ]use (the integration|conversational assistant)",
    "how does (the integration|conversational assistant) work",
    "what can (the integration|conversational assistant) do",
    "what features does (the integration|conversational assistant) support",
    "[hãy ](trợ giúp|hướng dẫn|hướng dẫn sử dụng|lệnh|các lệnh|các tính năng)",
    "[hãy ](hướng dẫn|chỉ) [tôi ]sử dụng (tích hợp|conversational assistant)",
    "[hãy ](hướng dẫn|chỉ) [tôi ]cách sử dụng (tích hợp|conversational assistant)",
    "[hãy ](hướng dẫn|giới thiệu) [các ]tính năng [của ](tích hợp|conversational assistant)",
    "[hãy ](hướng dẫn|chỉ) [tôi ]sử dụng [các ]tính năng [của ](tích hợp|tích hợp này|conversational assistant)",
    "[hãy ](hướng dẫn|giới thiệu) (tích hợp|conversational assistant)",
    "[hãy ](sử dụng|dùng) tích hợp",
    "[hãy ]học cách sử dụng (tích hợp|tích hợp này|conversational assistant)",
    "[tôi muốn ]học cách sử dụng [các ]tính năng [của ](tích hợp|tích hợp này|conversational assistant)",
    "[hãy ]chỉ [cho ]tôi cách dùng [các ]tính năng [của ](tích hợp|tích hợp này|conversational assistant)",
    "[hãy ](tích hợp|conversational assistant) (có|hỗ trợ) [những ]tính năng gì",
    "[hãy ]cho tôi biết (tích hợp|conversational assistant) (có|làm được) gì",
    "[hãy ](tích hợp|conversational assistant) làm được gì",
    "[hãy ]tôi có thể (dùng|sử dụng) tích hợp như thế nào",
]

CREATE_SENTENCES = [
    "[please ]remind me {request}",
    "[please ]set [a ]reminder {request}",
    "[please ]create [a ]reminder {request}",
    "[please ]add [a ]reminder {request}",
    "[please ]schedule [a ]reminder {request}",
    # Explicit forms first so their wildcard contains only the actual request.
    "[hãy ]nhắc tôi {request}",
    "[hãy ]hẹn giờ nhắc tôi {request}",
    "[hãy ]tạo hẹn giờ nhắc tôi {request}",
    "(tạo|đặt|thêm) (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ) {request}",
    # Natural short commands.
    "[hãy ](nhắc|hẹn) {request}",
]



LIST_SENTENCES = [
    "[please ](list|show|read) [my ]reminders",
    "[please ]show [my ]reminder list",
    "what reminders do I have",
    "what is my next reminder",
    "what's my next reminder",
    "next reminder",
    "liệt kê (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ)",
    "đọc danh sách (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ)",
    "xem danh sách (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ)",
    "danh sách (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ)",
    "cho tôi danh sách (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ)",
    "tôi có những (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ) nào",
    "(nhắc hẹn|nhắc nhở) tiếp theo là gì",
]

CANCEL_SENTENCES = [
    "[please ](delete|cancel|remove) [a ]reminder",
    "[please ](delete|cancel|remove) [a ]reminder {request}",
    "[please ](delete|cancel|remove) all reminders",
    "[please ]clear all reminders",
    # Accept both common Vietnamese spellings: xóa/xoá and hủy/huỷ.
    "(hủy|huỷ|xóa|xoá) (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ)",
    "(hủy|huỷ|xóa|xoá) (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ) {request}",
    "(hủy|huỷ|xóa|xoá) tất cả (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ)",
    "(hủy|huỷ|xóa|xoá) toàn bộ (nhắc hẹn|nhắc nhở|lịch nhắc|hẹn giờ)",
]


CAMERA_SENTENCES = [
    "[please ](take|capture|get|send) (a photo|a picture|an image) [from ](camera|cameras)",
    "[please ](take|capture|get|send) (a photo|a picture|an image) [from ](camera|cameras) {request}",
    "[please ](take|capture) [a ]camera snapshot",
    "[please ](take|capture) [a ]camera snapshot {request}",
    "[hãy ](chụp|lấy) (ảnh|hình) [từ ](camera|máy quay)",
    "[hãy ](chụp|lấy) (ảnh|hình) [từ ](camera|máy quay) {request}",
    "[hãy ]chụp (camera|máy quay)",
    "[hãy ]chụp (camera|máy quay) {request}",
]


TARGET_SELECTION_SENTENCES = [
    "(select|choose|confirm|send to|notify) {selection}",
    "I (select|choose) {selection}",
    "[please ]send [it ]to {selection}",
    "all",
    "all (speakers|phones|zalo destinations)",
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
    "cancel the last request",
    "do not save this reminder",
    "stop creating the reminder",
    "cancel",
    "bỏ yêu cầu vừa rồi",
    "không lưu nhắc nhở này",
    "dừng tạo nhắc nhở",
]


# Natural-language note commands. Protected notes are encrypted per note and
# are never exposed through list responses or sensor attributes.
NOTE_CREATE_SENTENCES = [
    "[please ](add|create|save|write) [a ]note",
    "[please ](add|create|save|write) [a ]note {request}",
    "[please ]remember {request}",
    "[please ]make [a ]note {request}",
    "note {request}",
    "(thêm|tạo|lưu|viết) (ghi chú|ghi nhớ|note)",
    "(thêm|tạo|lưu|viết) (ghi chú|ghi nhớ|note) {request}",
    "(ghi chú|ghi nhớ|note|ghi lại)",
    "(ghi chú|ghi nhớ|note|ghi lại) {request}",
    "hãy (ghi chú|ghi nhớ|nhớ|ghi lại) {request}",
    "[hãy ]nhớ rằng {request}",
    "[hãy ]nhớ giúp tôi {request}",
]


NOTE_LIST_SENTENCES = [
    "[please ](list|show|read) [my ]notes",
    "[please ]show [my ]note list",
    "what notes do I have",
    "my notes",
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
    "[please ](edit|update|change) [a ]note",
    "[please ](edit|update|change) [a ]note {request}",
    "(sửa|chỉnh sửa|cập nhật|đổi) (ghi chú|ghi nhớ|note)",
    "(sửa|chỉnh sửa|cập nhật|đổi) (ghi chú|ghi nhớ|note) {request}",
]

NOTE_DELETE_SENTENCES = [
    "[please ](delete|remove|cancel) [a ]note",
    "[please ](delete|remove|cancel) [a ]note {request}",
    "(xóa|xoá|hủy|huỷ) (ghi chú|ghi nhớ|note)",
    "(xóa|xoá|hủy|huỷ) (ghi chú|ghi nhớ|note) {request}",
]

NOTE_VIEW_SENTENCES = [
    "[please ](open|read|view|show) note {request}",
    "[please ]show note number {request}",
    "(mở|đọc) ghi chú {request}",
    "xem nội dung ghi chú {request}",
    "xem ghi chú số {request}",
]
