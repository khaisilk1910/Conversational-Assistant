# YouTube search & playback setup

Conversational Assistant 2026.08.20.1100 can search YouTube and play to Home Assistant `media_player` entities.

## Recommended setup

1. Add **Media extractor** in Home Assistant. The integration uses `media_extractor.extract_media_url` for speaker audio and `media_extractor.play_media` as a fallback.
2. Open **Settings > Devices & services > Conversational Assistant > Configure > YouTube Settings**.
3. Enter `youtube_api_key` from a Google Cloud project with **YouTube Data API v3** enabled, then choose **Save and Finish**. The field is masked in the Home Assistant UI and the integration never writes the key to its logs.
4. In **Conversational Assistant > Configure > General settings**, add spoken names for speakers and optionally **TV/media players**. If the TV/media list has never been configured, compatible `media_player` entities are discovered lazily only when a YouTube request arrives.

You no longer need to put the API key in `configuration.yaml`, `secrets.yaml`, or Pyscript for the normal Conversational Assistant YouTube flow. The supplied Pyscript helper remains an optional backward-compatible fallback.

## What happens without an API key?

The integration first tries `media_player.search_media` only when the selected media player advertises native search support. A native result is accepted as YouTube only when it contains a real YouTube URL/identifier hint. If that does not return YouTube results, the integration uses the API key from **YouTube Settings**. If no key is configured, an already configured `pyscript.youtube_search_tool` may still be used. When none of those sources can search YouTube, the user gets a clear prompt to configure `youtube_api_key`.

## Natural requests

- `Tìm YouTube nhạc bolero phát loa Phòng Ngủ`
- `Tìm trên YouTube nhạc AI phát loa Phòng Khách`
- `Mở YouTube dạy tiếng Anh trên TV Phòng Ngủ`
- `Phát YouTube hoạt hình thiếu nhi ở Tivi Phòng Khách`

The integration returns up to 10 results. Reply with a number/name. If there is no selection after 20 seconds, result 1 is selected automatically. A busy speaker asks whether to override and otherwise waits up to 10 minutes; TV playback starts immediately.

## Search order

1. Native `media_player.search_media` when supported and when the response can be positively identified as YouTube.
2. Direct asynchronous YouTube Data API v3 search using the API key stored in Conversational Assistant options.
3. Legacy `pyscript.youtube_search_tool` fallback when that service exists.

The direct API path uses Home Assistant's shared asynchronous HTTP session and performs no network access during integration startup.
