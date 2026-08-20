# Changelog 2026.08.20.1100

## Added

- **Conversational Assistant options > YouTube Settings** with a masked `youtube_api_key` field.
- Direct asynchronous YouTube Data API v3 search through Home Assistant's shared HTTP session. Pyscript is no longer required for the normal search path.
- Actionable error messages for missing/rejected API keys, quota exhaustion, timeout, and network failures.

## Changed

- Search order is now: native `media_player.search_media` -> direct YouTube Data API v3 -> legacy `pyscript.youtube_search_tool`.
- Native media search no longer treats every arbitrary 11-character media ID as a YouTube ID; a YouTube hint is required for bare IDs.
- YouTube API calls remain lazy: no Google/Pyscript imports and no YouTube network requests are made during integration startup.
- Documentation now recommends configuring the key in the integration UI instead of `configuration.yaml`/Pyscript.
- Version bumped to `2026.08.20.1100`.

## Compatibility

- Existing `pyscript.youtube_search_tool` installations continue to work as a fallback, including installations that keep their own key in `pyscript.config`.
- Existing speaker/TV aliases and all previous YouTube selection/busy/wait behavior are preserved.
