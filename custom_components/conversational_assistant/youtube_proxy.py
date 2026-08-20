"""Short-lived Home Assistant proxy for YouTube audio streams.

The proxy gives legacy speakers a Home Assistant URL with a conventional audio
file suffix while preserving the HTTP headers and byte-range semantics selected
by yt-dlp for the upstream Googlevideo stream.
"""

from __future__ import annotations

from dataclasses import dataclass
import contextlib
import logging
from secrets import token_urlsafe
from time import monotonic
from typing import Mapping

from aiohttp import ClientError, web

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.components.media_player.browse_media import async_process_play_media_url
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_DATA_KEY = "youtube_audio_proxy"
_PROXY_TTL_SECONDS = 5 * 60 * 60
_ALLOWED_EXTENSIONS = {"m4a", "mp4", "mp3", "aac", "webm", "ogg", "opus"}
_FORWARD_RESPONSE_HEADERS = {
    "accept-ranges",
    "cache-control",
    "content-length",
    "content-range",
    "content-type",
    "etag",
    "last-modified",
}
_DROP_REQUEST_HEADERS = {
    "connection",
    "content-length",
    "host",
    "proxy-authorization",
    "proxy-connection",
    "transfer-encoding",
}


@dataclass(slots=True)
class YouTubeAudioProxyItem:
    """One short-lived upstream stream exposed through Home Assistant."""

    stream_url: str
    mime_type: str
    headers: dict[str, str]
    expires_at: float


@callback
def _proxy_store(hass: HomeAssistant) -> dict[str, YouTubeAudioProxyItem]:
    domain_data = hass.data.setdefault(DOMAIN, {})
    store = domain_data.get(_DATA_KEY)
    if not isinstance(store, dict):
        store = {}
        domain_data[_DATA_KEY] = store
    return store


@callback
def _purge_expired(hass: HomeAssistant) -> None:
    now = monotonic()
    store = _proxy_store(hass)
    for token, item in list(store.items()):
        if not isinstance(item, YouTubeAudioProxyItem) or item.expires_at <= now:
            store.pop(token, None)


@callback
def async_setup_youtube_audio_proxy(hass: HomeAssistant) -> None:
    """Register the proxy endpoint once without doing network I/O."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(f"{_DATA_KEY}_view_registered"):
        return
    _proxy_store(hass)
    hass.http.register_view(YouTubeAudioProxyView)
    domain_data[f"{_DATA_KEY}_view_registered"] = True


@callback
def async_register_youtube_audio_proxy(
    hass: HomeAssistant,
    *,
    stream_url: str,
    mime_type: str,
    headers: Mapping[str, str] | None = None,
    extension: str = "m4a",
) -> str:
    """Expose one upstream stream and return a signed absolute HA URL."""
    _purge_expired(hass)
    ext = str(extension or "m4a").strip().casefold().lstrip(".")
    if ext not in _ALLOWED_EXTENSIONS:
        ext = "m4a"
    token = token_urlsafe(24).replace(".", "_")
    cleaned_headers = {
        str(key): str(value)
        for key, value in dict(headers or {}).items()
        if key and value and str(key).casefold() not in _DROP_REQUEST_HEADERS
    }
    _proxy_store(hass)[token] = YouTubeAudioProxyItem(
        stream_url=str(stream_url),
        mime_type=str(mime_type or "audio/mp4"),
        headers=cleaned_headers,
        expires_at=monotonic() + _PROXY_TTL_SECONDS,
    )
    path = f"/api/{DOMAIN}/youtube_audio/{token}.{ext}"
    return async_process_play_media_url(hass, path)


class YouTubeAudioProxyView(HomeAssistantView):
    """Proxy an audio stream through Home Assistant with signed-path auth."""

    url = f"/api/{DOMAIN}/youtube_audio/{{token}}.{{ext}}"
    name = f"api:{DOMAIN}:youtube_audio"
    requires_auth = True

    async def get(self, request: web.Request) -> web.StreamResponse:
        """Proxy a GET request, including byte range requests."""
        return await self._handle(request, head_only=False)

    async def head(self, request: web.Request) -> web.StreamResponse:
        """Proxy a HEAD request for players that probe media first."""
        return await self._handle(request, head_only=True)

    async def _handle(
        self, request: web.Request, *, head_only: bool
    ) -> web.StreamResponse:
        hass: HomeAssistant = request.app[KEY_HASS]
        _purge_expired(hass)
        token = str(request.match_info.get("token", ""))
        item = _proxy_store(hass).get(token)
        if not isinstance(item, YouTubeAudioProxyItem):
            raise web.HTTPNotFound()

        upstream_headers = dict(item.headers)
        if request.headers.get("Range"):
            upstream_headers["Range"] = request.headers["Range"]
        if request.headers.get("If-Range"):
            upstream_headers["If-Range"] = request.headers["If-Range"]

        session = async_get_clientsession(hass)
        method = "HEAD" if head_only else "GET"
        try:
            upstream = await session.request(
                method,
                item.stream_url,
                headers=upstream_headers,
                allow_redirects=True,
            )
        except ClientError as err:
            _LOGGER.debug("YouTube audio proxy upstream request failed: %s", err)
            raise web.HTTPBadGateway() from err

        try:
            response_headers: dict[str, str] = {}
            for key, value in upstream.headers.items():
                if key.casefold() in _FORWARD_RESPONSE_HEADERS:
                    response_headers[key] = value
            response_headers.setdefault("Content-Type", item.mime_type)
            response_headers["Cache-Control"] = "no-store"
            response_headers.setdefault("Accept-Ranges", "bytes")

            response = web.StreamResponse(
                status=upstream.status,
                reason=upstream.reason,
                headers=response_headers,
            )
            await response.prepare(request)
            if head_only:
                await response.write_eof()
                return response

            try:
                async for chunk in upstream.content.iter_chunked(64 * 1024):
                    await response.write(chunk)
            except (ConnectionResetError, RuntimeError):
                # The speaker can close the connection while switching tracks.
                pass
            with contextlib.suppress(ConnectionResetError, RuntimeError):
                await response.write_eof()
            return response
        finally:
            upstream.release()
