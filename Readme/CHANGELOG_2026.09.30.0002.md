# Changelog 2026.09.30.0002

## Fix TTS settings persistence

- Fixed `tts_language` and `tts_voice` so an explicitly cleared value is stored as an empty string and remains empty after reopening the integration options.
- Migrated all user-editable settings from legacy `ConfigEntry.data` into `ConfigEntry.options`. Existing option values always win, including `""`, `false`, empty lists, and other intentional empty values, so stale setup data can no longer resurrect old settings.
- New installations now store mutable settings directly in `ConfigEntry.options`.
- Added config-entry minor schema migration `1.2`; the migration is backward-friendly and preserves existing configured values.

## Related configuration fixes

- Fixed the Weather entity selector so clearing it remains blank instead of silently selecting the first `weather.*` entity when the options page is reopened. This matches the documented behavior where blank means AI Search/fallback only.
- Fixed the Zalo invocation keyword form so an explicitly blank keyword remains blank while keyword enforcement is disabled. When enforcement is enabled, the existing required-field validation still applies.
- Kept explicit blank handling for YouTube API key and optional AI selectors; the canonical options migration now protects these fields from stale `ConfigEntry.data` values as well.

## Home Assistant compatibility and startup

- Switched the options handler to Home Assistant's `OptionsFlowWithReload`, removing the custom update listener and using the current native reload lifecycle.
- Moved the YouTube proxy import out of `async_setup()` so integration setup does not perform a late Python import on the event loop.
- Retained background Store restoration, lazy device discovery, bounded Home Assistant service calls, and config-entry-owned background tasks. No new dependency was added.

## Validation

- Verified the whole integration with Python `compileall`.
- Added regression checks during this build for TTS blank persistence, legacy-data migration precedence, and coverage of every runtime `_option()`/options-flow `_current()` setting by the canonical options-key list.
