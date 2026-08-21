# Conversational Assistant 2026.08.20.1600

## Critical startup recovery

- Register `conversational_assistant.process_zalo_webhook` before optional YouTube HTTP helpers.
- YouTube proxy registration is best-effort and can no longer make the whole config entry unavailable.
- Removed explicit HTTP `OPTIONS` handlers; Home Assistant owns CORS/preflight registration.
- YouTube proxy imports are lazy so an optional proxy/API incompatibility cannot break manager import.
- `media_extractor`, `ffmpeg`, and `cast` are soft `after_dependencies`, not hard startup dependencies.
- Cast MP3 proxy uses Home Assistant's configured FFmpeg binary when available, initialized lazily only on playback.
