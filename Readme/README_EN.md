# Conversational Assistant

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.7.0%2B-41BDF5.svg)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Languages](https://img.shields.io/badge/languages-Ti%E1%BA%BFng%20Vi%E1%BB%87t%20%7C%20English-red.svg)](#languages)

**Conversational Assistant** is a custom integration for Home Assistant focused on natural-language interaction through **Home Assistant Assist** and **Zalo**.

The integration combines reminder management, secure notes, multi-channel notifications, and smart-home control in a single configuration. Users can create reminders by voice, receive notifications on their phone, through Zalo, or over speakers, and ask about device status, weather, and calendar events directly from Zalo.

> [!IMPORTANT]
> Install the integration and add the automation below if you want to interact through Zalo.
>
> Replace `your_bot_uid_to_prevent_self_replies` with the bot's UID so the bot does not respond to its own messages.
>
> Set `webhook_id` to the webhook used by your existing Zalo Bot automation.
>
> Add `'@1080' in (trigger.json.data.content | default('') | string)` if every request must include `@1080` followed by the request content.
>
> Example: **`@1080` hẹn 10h30 hàng ngày uống thuốc**
>
> Remove `and '@1080' in (trigger.json.data.content | default('') | string)` if the mention is not required.
>
> In that case, users can simply send: **Hẹn 10h30 hàng ngày uống thuốc**

```yaml
alias: Zalo - Bot Answer Multi Group Voice Reminder
description: ""
triggers:
  - trigger: webhook
    allowed_methods:
      - POST
    local_only: false
    webhook_id: "your_existing_zalo_bot_webhook"
conditions:
  - condition: template
    value_template: |-
      {{
        (trigger.json.data.uidFrom | string) != 'your_bot_uid_to_prevent_self_replies'
        and
        '@1080' in (trigger.json.data.content | default('') | string)
      }}
    enabled: true
actions:
  - action: conversational_assistant.process_zalo_webhook
    data:
      payload: "{{ trigger.json | to_json }}"
mode: parallel
max: 50
```

---

## Table of Contents

- [Key Features](#key-features)
- [System Requirements](#system-requirements)
- [Installation](#installation)
- [Adding the Integration to Home Assistant](#adding-the-integration-to-home-assistant)
- [General Configuration](#general-configuration)
- [Zalo Integration](#zalo-integration)
- [Controlling Home Assistant from Zalo](#controlling-home-assistant-from-zalo)
- [Reminder Management](#reminder-management)
- [Note Management](#note-management)
- [Created Sensors](#created-sensors)
- [Storage and Security](#storage-and-security)
- [Upgrading from the Previous Integration](#upgrading-from-the-previous-integration)
- [Troubleshooting](#troubleshooting)
- [Repository Structure](#repository-structure)
- [Development and Contributions](#development-and-contributions)
- [Languages](#languages)
- [Version](#version)
- [License](#license)
- [Disclaimer](#disclaimer)

---

## Key Features

### Natural-Language Reminders

- Create reminders through Home Assistant Assist or Zalo.
- Understand many Vietnamese time formats:
  - relative times: `30 phút nữa`, `2 giờ nữa`, `ngày mai`;
  - numeric times: `18h30`, `18:30`, `1830`, `18 giờ 30 phút`;
  - written-out times: `mười tám giờ ba mươi`;
  - specific dates: `20/10`, `ngày 20 tháng 10`, with or without a year;
  - weekdays and groups of days.
- Support one-time and recurring reminders:
  - daily;
  - weekdays;
  - weekends;
  - one or more selected weekdays;
  - monthly;
  - yearly.
- List and delete reminders with natural-language commands.
- Select multiple reminders for deletion.
- Snooze a reminder for 10 minutes or dismiss it directly from a Mobile App notification.
- Optionally treat swiping away an Android notification as dismissing the reminder.

### Multi-Channel Notifications

Each reminder can be delivered simultaneously to one or more destinations:

- **Home Assistant Companion App** through a `notify` service;
- **Zalo** through `zalo_bot.send_message`;
- **speakers/media players** through `tts.speak`;
- a Home Assistant **Persistent Notification** when none of the selected channels is available.

The integration automatically discovers:

- Mobile App devices with an active notification service;
- compatible `media_player` entities for TTS playback;
- configured Zalo recipients;
- the current Zalo conversation that sent the command.

When destination confirmation is enabled, users can reply with exact Vietnamese selections such as:

```text
1
1 và 3
Điện thoại của Nam
Tất cả
Tất cả điện thoại
Tất cả loa
Tất cả Zalo
```

### Public and Secure Notes

- Add, list, read, edit, and delete notes.
- Share notes between Assist and Zalo conversations within the same config entry.
- Two security levels:
  - **Level 1 — Secure:** the content is encrypted and requires a passphrase to read, edit, or delete;
  - **Level 2 — Public:** the content may appear in note lists and sensor attributes.
- Each secure note uses its own salt and nonce.
- Passphrases are never stored in the Home Assistant Store.
- Access is temporarily locked for five minutes after five incorrect passphrase attempts.
- Conversation flows are isolated by device, user, or Zalo conversation to prevent confirmation replies from being mixed up.

### Smart-Home Control from Zalo

- Turn devices on or off, open or close them, lock them, and adjust their settings.
- Check status by:
  - device name;
  - room;
  - area;
  - floor.
- Ask about temperature, humidity, and weather.
- Read events from one or more `calendar` entities.
- Choose a dedicated Conversation agent for Zalo commands.
- Maintain a separate `conversation_id` for each conversation.
- In group chats, process only clear Home Assistant commands to reduce accidental replies to ordinary conversation.
- Only entities exposed to Assist can be queried or controlled.

### Data Monitoring Sensors

The integration creates three sensors:

- the number of active reminders;
- the time of the next reminder;
- the number of notes.

These sensors also expose attributes that can be used in dashboards, templates, and automations.

---

## System Requirements

| Component | Requirement |
|---|---|
| Home Assistant | `2026.7.0` or later |
| Configuration method | UI-based Config Flow |
| Number of config entries | One |
| Command language | Optimized for Vietnamese |
| Home Assistant Assist | Required for voice commands and Home Assistant control from Zalo |
| Mobile App | Optional; required for phone notifications |
| TTS and media player | Optional; required for spoken reminders |
| [Zalo Bot](https://github.com/smarthomeblack/zalo_bot) | Optional; required for Zalo notifications or commands |
| Calendar/Weather | Optional; corresponding entities are required for queries |

### Home Assistant Dependencies

The integration declares the following dependencies:

```text
conversation
mobile_app
media_player
tts
```

### Requirements for Zalo

Conversational Assistant **does not create its own Zalo webhook endpoint**. You need:

1. a webhook source that receives a payload compatible with `zca-js`;
2. an automation that forwards the payload to the integration action;
3. the `zalo_bot.send_message` service to send replies and notifications to Zalo.

---

## Installation

### Automatic Installation

- Select the button below to add the repository to HACS in Home Assistant.

  [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=khaisilk1910&repository=Conversational-Assistant&category=integration)

- After adding it in HACS, restart Home Assistant.
- Go to **Settings → Devices & services → Add integration**, then search for `Conversational Assistant`.

### Manual Installation through HACS

If the repository is not yet included in the default HACS repository list, add it as a **Custom repository**.

1. Open **HACS** in Home Assistant.
2. Select the three-dot menu in the upper-right corner.
3. Select **Custom repositories**.
4. Enter the Conversational Assistant GitHub repository URL: `https://github.com/khaisilk1910/Conversational-Assistant`
5. Select **Integration** as the category.
6. Select **Add**.
7. Find **Conversational Assistant** in HACS and select **Download**.
8. Restart Home Assistant.

HACS documentation: [Custom Repositories](https://hacs.xyz/docs/faq/custom_repositories/)

> [!NOTE]
> The repository must contain `hacs.json`, `README.md`, and the `custom_components/conversational_assistant` directory in the correct structure for HACS to recognize it.

### Manual File Installation

1. Download the latest release.
2. Extract the downloaded archive.
3. Copy the entire directory:

```text
custom_components/conversational_assistant
```

to the Home Assistant configuration directory:

```text
/config/custom_components/conversational_assistant
```

4. Verify the final structure:

```text
/config/
└── custom_components/
    └── conversational_assistant/
        ├── __init__.py
        ├── config_flow.py
        ├── const.py
        ├── manager.py
        ├── manifest.json
        ├── models.py
        ├── note_flow.py
        ├── notes.py
        ├── parser.py
        ├── sensor.py
        ├── services.yaml
        ├── strings.json
        ├── targeting.py
        ├── zalo_home_assistant.py
        └── translations/
            ├── en.json
            └── vi.json
```

5. Restart Home Assistant.
6. Clear the browser cache or perform a hard refresh if the integration name or translations have not updated.

---

## Adding the Integration to Home Assistant

After Home Assistant restarts:

1. Open **Settings**.
2. Select **Devices & services**.
3. Select **Add integration**.
4. Search for **Conversational Assistant**.
5. Complete the initial setup.

The integration allows only one config entry to prevent duplicate registration of conversation sentence patterns.

---

## General Configuration

Open:

```text
Settings → Devices & services → Conversational Assistant → Configure
```

### Options

| Option | Description |
|---|---|
| Treat swiping away a notification as Dismiss | Applies to Android notification-clear events |
| Ask for destinations before saving | Lists phones, Zalo recipients, and speakers, then waits for the user to choose |
| Include auto-discovered speakers | Makes compatible media players available as reminder destinations |
| TTS engine | TTS entity used with `tts.speak`; when left empty, the integration uses the first available TTS entity |
| Process Zalo webhook commands | Enables or disables Zalo payload processing |
| Bot Zalo account ID | Used to filter messages sent by the bot itself |
| Zalo account used for webhook replies | The `account_selection` value used when sending responses |
| Allow Zalo to control Home Assistant | Enables device, status, weather, and calendar requests from Zalo |
| Conversation agent for Zalo | Natural-language agent used for Zalo commands; defaults to Home Assistant |

### Adding a Zalo Destination

In the options menu, select **Add Zalo destination** and enter:

| Field | Example |
|---|---|
| Destination name | `Family`, `Nam` |
| Enabled | On |
| Recipient type | User or Group |
| Thread ID | Zalo user or group ID |
| Account selection | Phone number or bot account used by the Zalo service |

Use short, easy-to-pronounce, unique names to improve destination selection by voice.

---

## Zalo Integration

### Payload Processing Action

The integration registers the following action:

```text
conversational_assistant.process_zalo_webhook
```

The action accepts two fields:

| Field | Required | Description |
|---|---:|---|
| `payload` | Yes | A JSON object or JSON string containing the Zalo payload |
| `config_entry_id` | No | Config entry ID; only needed when multiple entries exist, although the integration currently permits only one entry |

### Webhook Automation

Keep your existing webhook trigger and call the new action:

```yaml
alias: Conversational Assistant - Zalo webhook
mode: queued
max: 20
triggers:
  - trigger: webhook
    webhook_id: YOUR_ZALO_WEBHOOK_ID
    allowed_methods:
      - POST
    local_only: false

actions:
  - action: conversational_assistant.process_zalo_webhook
    data:
      payload: "{{ trigger.json | to_json }}"
```

> [!WARNING]
> Do not use **Run actions** to test this automation. A manually triggered run does not contain the `trigger.json` variable.

### Example Payload

```json
{
  "type": 1,
  "data": {
    "msgId": "32321323231",
    "uidFrom": "32321321321321321321",
    "content": "Bật đèn phòng khách"
  },
  "threadId": "32132132132132131",
  "isSelf": false,
  "_accountId": "3213213213232313"
}
```

### Webhook Filters

A payload is ignored when:

- `isSelf` is `true`;
- `data.uidFrom` matches the configured bot ID;
- `_accountId` does not match the configured bot account;
- the `msgId` was processed recently;
- the content is not a valid text message;
- Zalo webhook processing is disabled in the integration options.

The duplicate-message cache retains up to 512 recent message IDs during the current runtime session.

### Help Commands

Send one of these exact commands to the bot:

```text
Help
Trợ giúp
Hướng dẫn
Các lệnh
```

The bot returns a condensed command reference.

See also: [ZALO_WEBHOOK.md](https://github.com/smarthomeblack/zalo_bot)

---

## Controlling Home Assistant from Zalo

### Enabling the Feature

1. Open the **Conversational Assistant** options.
2. Enable **Allow Zalo to check and control Home Assistant**.
3. Select a Conversation agent.
4. Expose the entities that users are allowed to control or query.

In Home Assistant, open:

```text
Settings → Voice assistants → Expose
```

Expose only the entities that are genuinely required. Home Assistant uses its exposure mechanism to reduce the risk of accidentally controlling sensitive devices such as locks or garage doors.

Home Assistant documentation: [Exposing entities to Assist](https://www.home-assistant.io/voice_control/voice_remote_expose_devices/)

### Device Control Examples

The parser and Zalo flow are optimized for Vietnamese. Example commands:

```text
Bật đèn phòng khách
Tắt toàn bộ đèn tầng 2
Mở rèm phòng ngủ
Khóa cửa chính
Đặt điều hòa phòng khách 25 độ
Tăng nhiệt độ phòng ngủ lên 26 độ
```

### Status Query Examples

```text
Cửa chính đã khóa chưa?
Đèn phòng khách có đang bật không?
Phòng ngủ đang thế nào?
Tầng 2 có thiết bị nào đang bật?
Kiểm tra trạng thái khu vực sân vườn
Nhiệt độ phòng khách là bao nhiêu?
Độ ẩm phòng ngủ hiện tại
```

### Weather Query Examples

```text
Thời tiết hôm nay thế nào?
Ngày mai có mưa không?
Nhiệt độ ngoài trời hiện tại
```

Results depend on the selected Conversation agent and the exposed weather entities.

### Calendar Query Examples

```text
Lịch hôm nay
Ngày mai có sự kiện gì?
Xem lịch 7 ngày tới
Lịch Gia đình tuần này
```

The integration reads events from exposed `calendar` entities, combines results from multiple calendars, and sorts them chronologically.

See also: [ZALO_HOME_ASSISTANT.md](ZALO_HOME_ASSISTANT.md)

---

## Reminder Management

### Creating a One-Time Reminder

Example Vietnamese commands:

```text
Nhắc tôi 30 phút nữa uống thuốc
Nhắc tôi 2 giờ nữa kiểm tra máy giặt
Tạo nhắc hẹn 18h30 ngày mai đi tập thể dục
Nhắc tôi 7 giờ sáng ngày 20 tháng 10 gọi cho mẹ
Nhắc tôi 20:15 thứ sáu gửi báo cáo
```

### Creating a Recurring Reminder

```text
Nhắc tôi 7 giờ mỗi ngày uống vitamin
Nhắc tôi 8 giờ từ thứ hai đến thứ sáu đi làm
Nhắc tôi 9 giờ cuối tuần tưới cây
Nhắc tôi 18h30 mỗi tuần thứ hai và thứ năm tập thể dục
Nhắc tôi 9 giờ ngày 15 hàng tháng thanh toán hóa đơn
Nhắc tôi 8 giờ ngày 20 tháng 10 hàng năm mua quà
```

For monthly reminders scheduled on the 29th, 30th, or 31st, the integration uses the final day of a month when that month does not contain the requested date.

### Selecting Destinations

When destination confirmation is enabled, the integration displays or reads a list similar to:

```text
1 - Điện thoại Pixel
2 - Zalo Gia đình
3 - Loa phòng khách
4 - Loa phòng ngủ
```

Users can reply with exact Vietnamese selections such as:

```text
1 và 3
Chọn Zalo Gia đình
Tất cả
Tất cả loa
Bỏ yêu cầu vừa rồi
```

A pending destination selection expires after five minutes.

### Listing Reminders

```text
Danh sách nhắc hẹn
Liệt kê nhắc nhở
Nhắc hẹn tiếp theo là gì?
```

Assist reads the first 10 reminders and reports how many remain. The sensor still contains the complete list of upcoming reminders.

### Deleting Reminders

```text
Xóa nhắc hẹn
Xóa nhắc hẹn uống thuốc
Xóa tất cả nhắc hẹn
```

When the user says only `Xóa nhắc hẹn`, the integration presents a numbered list and allows one or more items to be selected.

### Mobile App Notifications

Each notification provides two actions:

- **Snooze for 10 minutes**;
- **Dismiss**.

For a one-time reminder, **Dismiss** deletes the reminder. For a recurring reminder, it dismisses only the current occurrence and leaves the recurring schedule active.

---

## Note Management

### Adding a Note

Example Vietnamese commands:

```text
Ghi nhớ mua pin cho khóa cửa
Thêm ghi chú lịch bảo trì máy lọc nước
Nhớ rằng mã tủ đồ là 2468
```

The note-creation flow is:

1. enter the content;
2. select Level 1 or Level 2;
3. enter a passphrase when Level 1 is selected;
4. confirm that the note should be saved.

### Listing Notes

```text
Danh sách ghi chú
Xem ghi chú
Tôi có ghi chú gì?
```

A Level 1 note displays only its sequence number and the `Bảo mật` label. Its content never appears in lists or sensor attributes.

### Reading a Note

```text
Xem ghi chú số 2
Đọc ghi chú số 1
Số 1 pass 1234
```

A secure note requires the correct passphrase.

### Editing a Note

```text
Sửa ghi chú
Cập nhật ghi chú số 2
```

The integration allows users to change the note content, security level, and passphrase.

### Deleting a Note

```text
Xóa ghi chú
Xóa ghi chú số 3
```

Every delete operation requires confirmation. A Level 1 note also requires its passphrase before deletion.

### Limits

- Note content: up to 4,000 characters.
- Passphrase: 4 to 256 characters.
- After five incorrect attempts: access is locked for five minutes.
- There is no content-recovery mechanism for a forgotten passphrase.

See also: [GHI_CHU_BAO_MAT.md](GHI_CHU_BAO_MAT.md)

---

## Created Sensors

Actual entity IDs may vary depending on the selected language, entity registry history, or user-defined renaming. Check the entities on the integration's device page instead of relying entirely on the example entity IDs below.

### Reminder Count Sensor

**State:** total number of active reminders.

**Attributes:**

| Attribute | Content |
|---|---|
| `list_nhac_nho` | Human-readable reminder list |
| `nhac_nho_sap_toi` | List of objects containing the sequence number, time, content, recurrence type, and reminder ID |
| `zalo_webhook_enabled` | Whether Zalo webhook processing is enabled |
| `zalo_webhook_action` | Name of the webhook action currently in use |
| `zalo_webhook_mode` | Current webhook mode |
| `zalo_bot_account_id` | Configured Zalo bot ID |
| `zalo_home_assistant_enabled` | Whether Home Assistant control from Zalo is enabled |
| `zalo_conversation_agent_id` | Selected Conversation agent |

Example template for reading the reminder list:

```jinja2
{{ state_attr('sensor.conversational_assistant_so_nhac_nho', 'list_nhac_nho') }}
```

### Next Reminder Sensor

**Device class:** `timestamp`.

**State:** time of the nearest upcoming reminder.

**Attributes:**

- `reminder_id`;
- `message`;
- `recurrence`;
- `snoozed`.

### Note Count Sensor

**State:** total number of notes.

**Attributes:**

| Attribute | Content |
|---|---|
| `list_ghi_chu` | Human-readable note list; secure-note content is always masked |
| `ghi_chu` | Safe metadata for each note |
| `so_ghi_chu_bao_mat` | Number of Level 1 notes |
| `so_ghi_chu_cong_khai` | Number of Level 2 notes |
| `bao_mat` | Information about the content-masking policy |

> [!TIP]
> The entity IDs above are examples only. Use **Developer Tools → States** to find the exact entity IDs in your system.

---

## Storage and Security

### Stored Data

Data is stored through the Home Assistant Store under a key in this format:

```text
conversational_assistant.<config_entry_id>
```

The stored data includes:

- reminders;
- recurrence rules;
- destinations assigned to each reminder;
- public notes;
- ciphertext, salt, and nonce for secure notes;
- metadata required for scheduling and sensor display.

Back up the `.storage` directory before removing the integration or making major changes.

### Level 1 Note Encryption

Secure notes use:

- AES-GCM;
- a 256-bit key derived from the passphrase;
- PBKDF2-HMAC-SHA256;
- 260,000 iterations;
- a random 16-byte salt;
- a random 12-byte nonce;
- the note ID as associated data.

Passphrases are not stored in the Home Assistant Store. Plaintext Level 1 note content is never exposed through sensors.

### Recommendations

- Do not speak sensitive passphrases aloud when other people are nearby.
- Prefer entering passphrases through Zalo or another text interface.
- Do not reuse a single passphrase for every note.
- Expose only the entities that Assist genuinely needs.
- Carefully assess the risks before exposing locks, garage doors, alarms, or other safety-sensitive devices.
- Protect the Zalo webhook and never publish its webhook ID.
- Never commit `secrets.yaml`, `.storage` data, logs, or real payloads to Git.

---

## Upgrading from the Previous Integration

Conversational Assistant uses its own domain and data store, so Home Assistant treats it as a separate integration.

Before migrating to the new version:

1. back up Home Assistant;
2. record the configured Zalo destinations and options;
3. disable or remove the previous config entry;
4. install Conversational Assistant;
5. add the new config entry;
6. update the webhook automation to call:

```text
conversational_assistant.process_zalo_webhook
```

7. recreate or migrate reminders and notes as needed.

> [!WARNING]
> Do not run two integrations that register the same reminder and note sentence patterns at the same time. Both integrations may process the same Assist command and create duplicate data.

Config entries, entity registry entries, reminders, notes, and Store data from the previous integration are not imported automatically into Conversational Assistant.

See also: [CAI_DAT_CONVERSATIONAL_ASSISTANT.md](CAI_DAT_CONVERSATIONAL_ASSISTANT.md)

---

## Troubleshooting

### The Integration Does Not Appear after Installation

Check that:

- the directory is `/config/custom_components/conversational_assistant`;
- `manifest.json` is located directly inside that directory;
- Home Assistant has been fully restarted;
- the extracted archive did not create an extra nested directory;
- the installed Home Assistant version meets the minimum requirement.

Then review the logs for import or syntax errors.

### HACS Does Not Recognize the Repository

Verify that the repository contains:

```text
README.md
hacs.json
custom_components/conversational_assistant/manifest.json
```

The integration name and minimum Home Assistant version in `hacs.json` must be valid. Before official publication through HACS, the repository must also satisfy HACS metadata, documentation, and brand-asset requirements.

Documentation: [HACS publishing requirements](https://hacs.xyz/docs/publish/integration/)

### Zalo Receives the Webhook but the Bot Does Not Reply

Check that:

- the automation action is `conversational_assistant.process_zalo_webhook`;
- `payload` receives `trigger.json`;
- the `zalo_bot.send_message` service exists under **Developer Tools → Actions**;
- `account_selection` points to the correct bot account;
- the payload `_accountId` matches the configured bot ID;
- webhook processing is enabled;
- the payload does not contain `isSelf: true`.

### The Bot Replies Twice

- Check whether multiple automations use the same webhook.
- Confirm that the previous integration is fully disabled.
- Check whether the Zalo gateway sends two events for the same message.
- Ensure that the payload contains a stable `msgId` so duplicate filtering can work.

### Devices Cannot Be Controlled from Zalo

Check that:

- Home Assistant control from Zalo is enabled;
- a working Conversation agent is selected;
- the entity is exposed to Assist;
- device, room, area, and floor names in Home Assistant are clear and unique;
- the user or context that calls the action has sufficient permissions.

### No Calendar Events Are Returned

Check that:

- at least one entity belongs to the `calendar` domain;
- the calendar is exposed to Assist;
- `calendar.get_events` works;
- the calendar name in the request matches or closely resembles the entity's friendly name;
- the requested time range actually contains events.

### A Phone Does Not Appear in the Destination List

Check that:

- the device is registered through the Home Assistant Companion App;
- its `mobile_app` config entry is active;
- the device's `notify` service exists;
- the device has not been removed or disabled.

### A Speaker Does Not Appear or Does Not Play Audio

Check that:

- the option to include auto-discovered speakers is enabled;
- the media player is not in the `unavailable` or `unknown` state;
- the media player supports the required playback method;
- a TTS entity exists;
- `tts.speak` works when tested manually;
- the speaker and Home Assistant can access the media URL generated by TTS.

### The Name or Translation Has Not Updated

- Restart Home Assistant.
- Perform a hard refresh in the browser.
- Clear the frontend cache if necessary.
- Confirm that no previous integration directory or duplicate copy remains under `custom_components`.

### Enabling Debug Logging

Add the following to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.conversational_assistant: debug
```

Restart Home Assistant, reproduce the problem, and review **Settings → System → Logs**.

> [!CAUTION]
> Before sharing logs, remove webhook IDs, thread IDs, account IDs, phone numbers, note content, and any other private information.

---

## Repository Structure

```text
.
├── .gitignore
├── README.md
├── hacs.json
├── CAI_DAT_CONVERSATIONAL_ASSISTANT.md
├── GHI_CHU_BAO_MAT.md
├── ZALO_HOME_ASSISTANT.md
├── ZALO_WEBHOOK.md
└── custom_components/
    └── conversational_assistant/
        ├── __init__.py
        ├── config_flow.py
        ├── const.py
        ├── manager.py
        ├── manifest.json
        ├── models.py
        ├── note_flow.py
        ├── notes.py
        ├── parser.py
        ├── sensor.py
        ├── services.yaml
        ├── strings.json
        ├── targeting.py
        ├── zalo_home_assistant.py
        └── translations/
            ├── en.json
            └── vi.json
```

### Main File Responsibilities

| File | Responsibility |
|---|---|
| `__init__.py` | Sets up the integration and registers the webhook action |
| `config_flow.py` | Implements the Config Flow and Options Flow |
| `const.py` | Defines the domain, options, sentence patterns, and constants |
| `manager.py` | Handles reminder scheduling, Zalo, notifications, and main coordination |
| `parser.py` | Parses Vietnamese dates, times, and recurrence rules |
| `note_flow.py` | Implements multi-step note conversations |
| `notes.py` | Handles note encryption, decryption, and authentication |
| `zalo_home_assistant.py` | Classifies Home Assistant queries and formats calendar results |
| `targeting.py` | Parses destination selections by number, name, or group |
| `sensor.py` | Implements sensors and state attributes |
| `services.yaml` | Describes actions in the Home Assistant UI |
| `translations/` | Contains Vietnamese and English translations |

---

## Development and Contributions

When reporting an issue, include:

- the Conversational Assistant version;
- the Home Assistant version;
- whether the integration was installed through HACS or manually;
- the command category: Assist, Zalo, reminders, notes, TTS, or calendar;
- a sanitized input command with sensitive information removed;
- relevant debug logs;
- steps to reproduce the issue;
- the expected result and the actual result.

Before submitting a pull request, verify that:

- the Python code compiles successfully;
- JSON and YAML files are valid;
- Vietnamese and English translation keys remain synchronized;
- no secrets or private data are included in commits;
- the `conversational_assistant` domain is unchanged;
- unique IDs and storage keys are not changed without a migration strategy;
- Assist, Zalo, and multi-step conversation flows do not register duplicate triggers.

### Quick Validation

```bash
python -m compileall custom_components/conversational_assistant
python -m json.tool custom_components/conversational_assistant/manifest.json
python -m json.tool custom_components/conversational_assistant/strings.json
python -m json.tool custom_components/conversational_assistant/translations/vi.json
python -m json.tool custom_components/conversational_assistant/translations/en.json
```

---

## Languages

- User interface: Vietnamese and English.
- Reminder parser, note flows, and Zalo command classifier: optimized for Vietnamese.
- The Conversation agent used for device and weather requests may support additional languages depending on the selected agent, but the integration currently sends Zalo commands with the `vi` language code.

---

## Version

Current version: **2026.07.30**

Domain:

```text
conversational_assistant
```

Webhook action:

```text
conversational_assistant.process_zalo_webhook
```

Minimum Home Assistant version declared in `hacs.json`:

```text
2026.7.0
```

---

## License

This repository should include a dedicated `LICENSE` file before public distribution. Choose a license that matches the project's goals, then update this section with the license name and a link to the `LICENSE` file.

---

## Disclaimer

Conversational Assistant can control real devices in Home Assistant. Users are responsible for configuring entity exposure, securing webhooks, protecting Zalo accounts, and evaluating the risks before allowing control of locks, doors, alarms, heating equipment, or other safety-critical systems.


## YouTube audio speakers (2026.08.20.1900)

When Home Assistant exposes `yt_dlp.play`, Conversational Assistant uses it as the primary audio-only speaker path after both the YouTube result and speaker have been selected. It passes `url` and `media_player` exactly to that action. TV/video playback keeps its native platform flow. The action is discovered lazily and is not a hard startup dependency.
