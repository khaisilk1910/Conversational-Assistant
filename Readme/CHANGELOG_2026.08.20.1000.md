# Conversational Assistant 2026.08.20.1000

## Added

- Natural YouTube request routing for Zalo and Voice Assist.
- Isolated multi-turn YouTube flow per Zalo owner / Voice source.
- Up to 10 YouTube search results, numbered selection, cancellation, and automatic result 1 selection after 20 seconds.
- Speaker busy handling: ask for override, otherwise poll every 10 seconds for up to 10 minutes.
- TV/media playback path that does not wait for busy state.
- Native Home Assistant media search attempt through `media_player.search_media` when the target advertises support.
- YouTube Data API fallback through `pyscript.youtube_search_tool`.
- Speaker audio extraction through `media_extractor.extract_media_url`, with `media_extractor.play_media` / `media_player.play_media` fallbacks.
- Native YouTube app playback strategies for Cast, Android TV / Google TV, and Apple TV based on the supplied blueprint.
- General settings list for named TV/media-player targets.
- `examples/youtube/` with the supplied search/play blueprints, a startup-safe Pyscript YouTube helper, and requirements file.
- `Readme/YOUTUBE_SETUP.md`.

## Changed

- Command classification, related-feature clarification, command catalog, help text, Zalo long-running routing, learned-command routing, and Voice pending-follow-up routing now understand YouTube.
- Media target aliases now recognize TV/projector/media-player wording.
- Discovery of unconfigured media players is lazy and only happens when a YouTube request is received.
- Optional YouTube Pyscript helper no longer raises on missing API key at module load and imports the Google API client lazily on first search.
- Version bumped to `2026.08.20.1000`.

## Removed

- No existing feature was intentionally removed.

## Verification performed

- Python byte-code compilation for the complete custom component and YouTube examples.
- JSON validation for manifest, strings, and English/Vietnamese translations.
- YAML syntax parsing for both supplied Home Assistant blueprints with Home Assistant `!input` tags accepted.
- Natural-language parser tests for Vietnamese YouTube commands, including YouTube before and after the requested content.
- Static diff review against the original `2026.08.19.2330` package.

A live Home Assistant instance was not available in this build environment, so device-specific runtime behavior still depends on each media player's capabilities and installed integrations.
