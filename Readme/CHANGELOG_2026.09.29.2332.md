# Changelog 2026.09.29.2332

## TTS

- Kept speaker announcements on Home Assistant's current `tts.speak` entity action (`target.entity_id` = TTS entity, `media_player_entity_id` in action data).
- Validate configured language/options against the selected TTS entity when Home Assistant exposes those capabilities.
- If a request with optional language/voice fails, retry once with the TTS engine defaults and keep the exact provider error in the integration result/log.
- This makes stale or unsupported language/voice settings non-fatal when the provider can synthesize with its defaults.
- Wyoming transport/protocol failures still surface unchanged; they must be fixed in the Wyoming TTS server itself rather than hidden in this integration.

## Options flow persistence

- TTS language and voice can now be cleared and remain blank after saving.
- A cleared TTS entity remains blank, which means automatic TTS entity selection, instead of resurrecting a legacy value from the config entry.
- The same legacy-value resurrection was fixed for optional AI task/search selectors and the YouTube API key.
- General behavior, Zalo webhook, YouTube, AI, and TTS forms now persist immediately when their Submit button is pressed instead of requiring a second Finish action.

## Natural follow-up context

- Added a short-lived, in-memory 120-second context for Weather and Search on Voice Assist and Zalo.
- Natural continuations such as `thế ngày mai thì sao`, `còn cuối tuần?`, or `còn độ ẩm?` can continue the previous weather topic without repeating the weather keyword.
- Explicit keywords and explicit Home Assistant/device commands always take priority and replace/clear the older topic context.
- Weather follow-ups remain local-first: deterministic parsing and the configured Home Assistant weather entity are attempted before AI fallback.
- Search follow-ups reuse the provider conversation ID when available; otherwise the previous question is supplied as compact context.
- Context is memory-only, per source/thread, timer-expiring, and adds no startup storage I/O.

## Compatibility and performance

- No new Python dependencies.
- No synchronous network work was added to Home Assistant startup.
- Existing per-speaker locking/background delivery remains in place for TTS announcements.
