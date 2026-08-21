# Conversational Assistant 2026.08.20.1500

## YouTube speaker playback fixes

- Preserve yt-dlp selected-format metadata instead of keeping only the stream URL: HTTP headers, extension, format ID, container, audio codec and video codec.
- Reject a yt-dlp format unless it is explicitly audio-only (`acodec` present and `vcodec=none`).
- Add a short-lived signed Home Assistant audio proxy that forwards Range requests and yt-dlp headers and exposes a normal audio file suffix.
- Prefer the proxy URL for generic speakers, then fall back to the direct Googlevideo audio URL.
- Detect Phicomm R1 media-player entities and prefer `phicomm_r1.play_youtube` with the selected YouTube video ID.
- Verify Phicomm playback through `last_music_play`/`aibox_playback` before reporting success.
- Keep `shell_command.youtube_stream`, Media Extractor and direct YouTube URL paths only as compatibility fallbacks.
- No proxy item or yt-dlp extraction is created at Home Assistant startup; all playback work remains lazy.
