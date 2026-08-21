# Conversational Assistant 2026.08.20.1800

## Fixed

- Fixed Home Assistant view route signatures for `{token}` / `{ext}`. Version 1700 could raise `TypeError: ...get() got an unexpected keyword argument 'token'`, returning HTTP 500 to Cast before any media bytes were served.
- Applied the same signature correction to the generic YouTube audio proxy.

## Google Cast download-first playback

- Cast/Google Home/Nest now downloads audio-only to a complete local file before playback instead of relying on the realtime proxy as the primary path.
- AAC/itag 140 is stream-copied/remuxed to a normal M4A with `+faststart`; no audio re-encode is needed on the common path.
- Static files are served with a short random capability URL, `HEAD`, GET and HTTP Range support.
- Cast uses Default Media Receiver `BUFFERED` playback with `audio/mp4; codecs="mp4a.40.2"`.
- If M4A is rejected, the completed local file is converted to MP3 and retried without re-downloading YouTube.
- The file is deleted after playback ends. Eight-hour TTL and stale-cache cleanup provide crash/restart safety.

## Startup and concurrency

- No YouTube download, FFmpeg process or cache scan runs at integration startup.
- Download/remux starts only after a user has selected a YouTube video and a Cast speaker.
- Existing owner/source pending isolation and per-media-player playback locks are retained.
