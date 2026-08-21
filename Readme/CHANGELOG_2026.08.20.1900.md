# Conversational Assistant 2026.08.20.1900

## YouTube audio-only

- Added first-class support for the installed Home Assistant action `yt_dlp.play`.
- For a selected speaker, the action receives exactly:
  - `url`: selected YouTube result URL;
  - `media_player`: selected speaker entity ID.
- The action is called only after the multi-turn flow has a resolved speaker and an explicitly selected video.
- Speaker result lists no longer auto-start result 1 after 20 seconds; TV/video retains the previous auto-first behavior.
- Busy speaker logic remains unchanged: ask for override or wait up to 10 minutes.
- Playback is verified for up to 25 seconds after `yt_dlp.play`.
- If `yt_dlp.play` is registered but fails, the integration reports that failure and stops instead of firing duplicate Cast/Media Extractor fallback chains.
- Legacy native/proxy/Media Extractor paths remain only when `yt_dlp.play` is unavailable.
- `yt_dlp` is not a manifest hard dependency; service discovery is lazy so startup remains isolated.

## Natural language / guide

- Expanded YouTube examples for Vietnamese natural requests.
- Updated `huongdanlenh.md`, `YOUTUBE_SETUP.md`, root README and English README.
- Clarified the rule: clear request runs immediately; ambiguous feature-related request asks only for missing information and keeps the correct pending flow.
