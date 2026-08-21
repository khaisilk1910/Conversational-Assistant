# Conversational Assistant 2026.08.20.1700

## Fixed

- Google Cast YouTube audio no longer uses the normal `media_player.play_media` URL branch for the custom MP3 endpoint. It uses the official Cast quick-play payload (`media_content_type: cast`, `app_name: default_media_receiver`) so Home Assistant does not rewrite the random capability URL with `authSig`.
- Cast FFmpeg proxy pre-buffers the first MP3 bytes before sending HTTP 200. Timeout/early-exit returns 502/503 and logs a URL-redacted FFmpeg diagnostic.
- Cast no longer repeats known-incompatible raw M4A/Googlevideo/Media Extractor fallbacks after the MP3 path fails.
- Home Assistant Conversation `no_intent_match` is treated as an expected unmatched intent and falls back to deterministic feature clarification instead of a warning/error path.

## Natural language and guidance

- Expanded related-feature detection for device, weather, reminder, calendar, speaker, Zalo, camera, YouTube, Internet search, image generation, lunar/solar calendar, note and chat wording.
- Clear requests continue directly. Ambiguous but related requests receive feature-specific examples and a 120-second follow-up window on Zalo.
- Updated `huongdanlenh.md`, built-in help, README and YouTube setup guidance.

## Startup/concurrency

- YouTube proxy/transcoding remains lazy and optional. No yt-dlp extraction or FFmpeg process is started during Home Assistant startup.
- Existing owner/source-scoped pending flows and per-player locks are retained for concurrent Zalo/Voice requests.
