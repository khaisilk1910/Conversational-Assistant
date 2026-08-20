# YouTube search & playback setup

Conversational Assistant 2026.08.20.1000 can search YouTube and play to Home Assistant `media_player` entities.

## Recommended Home Assistant pieces

1. Add **Media extractor** in Home Assistant. The integration uses `media_extractor.extract_media_url` for speaker audio and `media_extractor.play_media` as a fallback.
2. For API search, install/configure **Pyscript** and copy `examples/youtube/youtube_data_tool.py` plus `examples/youtube/requirements.txt` to your Pyscript folder.
3. Configure the YouTube Data API key:

```yaml
pyscript:
  allow_all_imports: true
  hass_is_global: true
  youtube_api_key: !secret youtube_api_key
```

```yaml
# secrets.yaml
youtube_api_key: YOUR_KEY
```

4. In **Conversational Assistant > Configure > General settings**, add spoken names for speakers and optionally **TV/media players**. If the TV/media list has never been configured, compatible `media_player` entities are discovered lazily only when a YouTube request arrives.

## Natural requests

- `Tìm YouTube nhạc bolero phát loa Phòng Ngủ`
- `Tìm trên YouTube nhạc AI phát loa Phòng Khách`
- `Mở YouTube dạy tiếng Anh trên TV Phòng Ngủ`
- `Phát YouTube hoạt hình thiếu nhi ở Tivi Phòng Khách`

The integration returns up to 10 results. Reply with a number/name. If there is no selection after 20 seconds, result 1 is selected automatically. A busy speaker asks whether to override and otherwise waits up to 10 minutes; TV playback starts immediately.

The supplied blueprints remain useful as references, but the integration does not import or execute them at Home Assistant startup.
