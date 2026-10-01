# Changelog 2026.10.01.0830

## Weather settings / Zalo delivery reliability

- Centralized every Conversational Assistant text send through one bounded Zalo sender.
- Serialized text sends per configured Zalo account so Weather, Calendar, reminders, direct Zalo messages, and webhook replies from this integration cannot race the same `zalo_bot` account session.
- Removed the scheduled Weather/Calendar/reminder typing-event race before text delivery.
- Added up to 3 attempts for transient transport/server failures only (`HTTP 429`, `HTTP 500/502/503/504`, timeout/connection/temporary failures). Permanent configuration errors are not retried.
- Kept the existing 15-second bounded Home Assistant service-call timeout; no blocking I/O or new dependency was added to Home Assistant startup.
- Scheduled Weather now uses the same common sender and continues to the next configured destination when one destination ultimately fails.

The downstream `zalo_bot` server can still return an external HTTP 500. This build cannot guarantee that an external server never fails, but it prevents the integration's own concurrent text sends from colliding and automatically retries the transient error reported in the supplied log.

## Vietnamese / English pending confirmations and selections

- Fixed the root routing collision where Vietnamese `Tất cả` normalizes to `tat ca` and was incorrectly classified as the `tắt ...` Home Assistant device-control prefix. This was why English `All` worked while Vietnamese `Tất cả` could leave the pending camera/target flow and fall through to Home Assistant/AI.
- `Tất cả`, `TẤT CẢ`, `Tat Ca`, `All`, `ALL`, `Toàn bộ`, and category forms such as `Tất cả camera`, `Tất cả loa`, `all cameras`, and `all speakers` now stay in an active pending flow.
- Pending-flow control replies are normalized accent-insensitively and case-insensitively before routing.
- Corrected all affected user prompts so they advertise the actual bilingual accepted replies, including `Tất cả / All`, `Hủy / Cancel`, `Không chụp / No / Cancel / Hủy`, `Không quay / No / Cancel / Hủy`, `Đồng ý / Yes / Confirm`, `Xác nhận xóa / Confirm delete`, `Sửa / Edit`, `Xóa / Delete`, `Bỏ qua / Skip`, and rolling-door confirmation aliases.
- Calendar single-target creation now explicitly accepts both `Xác nhận` and `Confirm` (plus the existing equivalent confirmations).
- Fixed target-selection phrase matching to use whole tokens so a target named `Hall` no longer accidentally matches the English `all` command.

## Validation

- Verified the entire integration with Python `compileall`.
- Ran regression checks for Vietnamese/English/case-insensitive `Tất cả / All` selection, category selections, compact numeric selection, and the `Hall`/`all` boundary case.
- Ran isolated router tests proving `Tất cả` and `Tất cả camera` no longer become `tắt ...`, while real commands such as `Tắt đèn bếp` and `turn off kitchen light` still route to Home Assistant.
- Ran confirmation tests for camera, camera-schedule deletion, rolling-door confirmation, cancellation, and pending-flow routing in Vietnamese and English.
- Static AST check confirms there is now only one direct `zalo_bot.send_message` service-call implementation in the manager; all integration text-send call sites use the common serialized/retrying sender.
