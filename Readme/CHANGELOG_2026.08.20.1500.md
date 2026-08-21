# Conversational Assistant 2026.08.20.1500

## YouTube audio / Google Cast fix

- Detect Google Cast speaker targets separately from generic media players.
- Keep yt-dlp audio-only validation (`acodec != none`, `vcodec == none`).
- Add an on-demand Home Assistant Cast audio endpoint that uses FFmpeg to transcode the selected YouTube audio-only stream to MP3 (`audio/mpeg`).
- The Cast endpoint uses a short random capability URL, CORS headers and `stream_type=LIVE`; it does not expose the Googlevideo URL to the Cast receiver.
- Try Home Assistant internal and external URLs when both are configured.
- Preserve the old byte-range proxy and direct audio path as compatibility fallbacks.
- For Cast targets, do not call `media_extractor.play_media` after the Cast-specific path fails, avoiding the yt-dlp JavaScript-runtime warning and a known-unhelpful fallback.
- FFmpeg work is lazy: no YouTube extraction or transcoding is performed during Home Assistant startup.
