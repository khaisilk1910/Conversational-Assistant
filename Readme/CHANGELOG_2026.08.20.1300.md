# Changelog 2026.08.20.1300

## YouTube speaker playback fix

- Changed speaker playback to resolve a real audio-only YouTube URL first instead of calling `media_extractor.play_media` first.
- The preferred audio selector is `140/bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio`, so YouTube itag 140 (M4A/AAC) is preferred for legacy/audio-only speakers.
- Direct audio URLs are sent with `media_content_type: music` first. A concrete MIME type such as `audio/mp4` is only a compatibility fallback.
- Added `media_extractor` as an integration dependency so Conversational Assistant can reuse Home Assistant Core's maintained `yt-dlp` Python package without requiring a separately installed binary.
- Kept yt-dlp import/extraction lazy: no YouTube extraction is performed during Home Assistant startup.
- Added optional compatibility with an existing `shell_command.youtube_stream` action. If present, Conversational Assistant can consume its `stdout` URL and play it using the same direct-audio path.
- `media_extractor.play_media` is now a late fallback for speakers because Home Assistant's YouTube-specific media extractor path selects streams containing both audio and video codecs.
- Playback success is still verified using the target media player's state before reporting success.

## Important HAOS note

Installing `yt-dlp` with `apk add yt-dlp` inside the Terminal & SSH add-on installs it in that add-on container, not in the Home Assistant Core container. `shell_command` actions run inside the Home Assistant Core container. The built-in Python path used by this release avoids that container mismatch.

## Version

- Version bumped to `2026.08.20.1300`.
