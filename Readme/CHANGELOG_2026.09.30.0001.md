# Changelog 2026.09.30.0001

## General natural conversation context

- Expanded the 120-second RAM-only follow-up context from Weather/Search to every feature routed by Conversational Assistant, including reminders, notes, cameras, YouTube/media, lunar date, Zalo send, speaker announcements, learned commands, Home Assistant/device control, calendar, weather, search, and AI chat.
- Explicit commands and explicit new Home Assistant intents still take priority. A clearly different intent clears the previous topic before normal routing continues.
- Natural elliptical turns such as `thế ngày kia?`, `còn cái đó?`, `đặt 25 độ`, `bài khác đi`, `tại sao?`, and `còn thứ sáu?` can continue the active topic without repeating its keyword.
- Context remains short-lived and in memory only. No persistent context database, startup read, or synchronous startup work was added.

## Local-first continuation routing

- Weather follow-ups continue through the local weather parser/entity path before AI fallback and preserve an earlier explicit location across multiple turns.
- Calendar time-reference follow-ups on Zalo remain on the local Calendar path.
- Home Assistant/device follow-ups are sent through Home Assistant Conversation first. For an elliptical device value/action, only an exact device name resolved from the previous local command is appended; the integration does not ask AI to guess a target.
- Search keeps the configured provider conversation ID when available. Other completed feature flows use a compact previous-turn prompt only after no local/pending state machine can resolve the follow-up.

## Thread isolation and concurrency

- Voice context is isolated by a stable source key: satellite first, then device, conversation ID, user, and finally request context. This avoids merging different speakers owned by the same HA user while surviving Assist conversation-ID changes on satellite pipelines.
- Zalo context stays isolated by `owner_key`/thread.
- Existing feature-specific pending state machines still run before the generic context fallback, so confirmations and selections are not displaced by AI chat.
- Zalo generic contextual AI work uses the existing background action path so webhook handling is not blocked unnecessarily.

## Routing correctness

- Removed over-broad reminder command detection for bare Vietnamese `đặt`, `tạo`, and `thêm`, which could otherwise steal device follow-ups such as `đặt 25 độ`.
- Avoided treating common new-topic phrases such as `thế giới ...` as the Vietnamese continuation prefix `thế ...`.
- Preserved feature-enriched context after a response instead of overwriting it with the raw utterance; this keeps carried weather locations and locally resolved device references available for later follow-ups.
- Canceling an active flow now describes this state as `ngữ cảnh hội thoại`.

## Compatibility

- No new Python dependencies.
- No persistent context storage and no added blocking startup I/O.
- The TTS and options-flow fixes from 2026.09.29.2332 are retained unchanged.
