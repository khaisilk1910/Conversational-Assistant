"""Short-lived Home Assistant proxies for YouTube audio streams.

Two proxy modes are intentionally provided:

* the generic byte-range proxy preserves the yt-dlp selected audio stream and
  headers for media players that can consume M4A/WebM directly;
* the Cast proxy is a token-protected, unauthenticated HTTP endpoint which
  transcodes the selected audio-only stream to MP3 on demand.  Google Cast's
  Default Media Receiver then sees a conventional ``audio/mpeg`` stream and
  never has to fetch an expiring Googlevideo URL or reproduce yt-dlp headers.

Nothing is downloaded or transcoded at Home Assistant startup.  FFmpeg is only
spawned after a Cast device actually requests a generated stream URL.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
import logging
from secrets import token_urlsafe
from time import monotonic
from typing import Mapping

from aiohttp import ClientError, web

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.components.media_player.browse_media import async_process_play_media_url
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_DATA_KEY = "youtube_audio_proxy"
_CAST_DATA_KEY = "youtube_cast_audio_proxy"
_PROXY_TTL_SECONDS = 5 * 60 * 60
_CAST_PROXY_TTL_SECONDS = 60 * 60
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
_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Allow-Headers": "Range, Content-Type",
    "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges, Content-Type",
}


@dataclass(slots=True)
class YouTubeAudioProxyItem:
    """One short-lived upstream stream exposed through Home Assistant."""

    stream_url: str
    mime_type: str
    headers: dict[str, str]
    expires_at: float


@dataclass(slots=True)
class YouTubeCastAudioProxyItem:
    """An audio-only upstream which will be transcoded for Google Cast."""

    stream_url: str
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
def _cast_proxy_store(hass: HomeAssistant) -> dict[str, YouTubeCastAudioProxyItem]:
    domain_data = hass.data.setdefault(DOMAIN, {})
    store = domain_data.get(_CAST_DATA_KEY)
    if not isinstance(store, dict):
        store = {}
        domain_data[_CAST_DATA_KEY] = store
    return store


@callback
def _purge_expired(hass: HomeAssistant) -> None:
    now = monotonic()
    for store in (_proxy_store(hass), _cast_proxy_store(hass)):
        for token, item in list(store.items()):
            if item.expires_at <= now:
                store.pop(token, None)


@callback
def async_setup_youtube_audio_proxy(hass: HomeAssistant) -> None:
    """Register both proxy endpoints once without doing network I/O."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(f"{_DATA_KEY}_view_registered"):
        return
    _proxy_store(hass)
    _cast_proxy_store(hass)
    hass.http.register_view(YouTubeAudioProxyView)
    hass.http.register_view(YouTubeCastAudioProxyView)
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


def _candidate_base_urls(hass: HomeAssistant) -> list[str]:
    """Return LAN first, then external HA URLs suitable for a Cast receiver."""
    bases: list[str] = []
    attempts = (
        dict(allow_internal=True, allow_external=False, allow_cloud=False),
        dict(
            allow_internal=False,
            allow_external=True,
            allow_cloud=True,
            prefer_external=True,
        ),
    )
    for kwargs in attempts:
        try:
            base = get_url(hass, **kwargs).rstrip("/")
        except NoURLAvailableError:
            continue
        if base and base not in bases:
            bases.append(base)
    return bases


@callback
def async_register_youtube_cast_audio_proxy(
    hass: HomeAssistant,
    *,
    stream_url: str,
    headers: Mapping[str, str] | None = None,
) -> list[str]:
    """Return short capability URLs that transcode one source to MP3 for Cast.

    This view deliberately uses a long random token instead of Home Assistant's
    ``authSig`` query string.  Some Cast receivers are sensitive to long URLs,
    and the endpoint contains no reusable credential beyond the short-lived
    random capability itself.
    """
    _purge_expired(hass)
    token = token_urlsafe(24).replace(".", "_")
    cleaned_headers = {
        str(key): str(value)
        for key, value in dict(headers or {}).items()
        if key and value and str(key).casefold() not in _DROP_REQUEST_HEADERS
    }
    _cast_proxy_store(hass)[token] = YouTubeCastAudioProxyItem(
        stream_url=str(stream_url),
        headers=cleaned_headers,
        expires_at=monotonic() + _CAST_PROXY_TTL_SECONDS,
    )
    path = f"/api/{DOMAIN}/youtube_cast_audio/{token}.mp3"
    return [f"{base}{path}" for base in _candidate_base_urls(hass)]


class YouTubeAudioProxyView(HomeAssistantView):
    """Proxy an audio stream through Home Assistant with signed-path auth."""

    url = f"/api/{DOMAIN}/youtube_audio/{{token}}.{{ext}}"
    name = f"api:{DOMAIN}:youtube_audio"
    requires_auth = True

    async def get(self, request: web.Request) -> web.StreamResponse:
        return await self._handle(request, head_only=False)

    async def head(self, request: web.Request) -> web.StreamResponse:
        return await self._handle(request, head_only=True)

    async def options(self, request: web.Request) -> web.StreamResponse:
        return web.Response(status=204, headers=_CORS_HEADERS)

    async def _handle(self, request: web.Request, *, head_only: bool) -> web.StreamResponse:
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
            response_headers: dict[str, str] = dict(_CORS_HEADERS)
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
                pass
            with contextlib.suppress(ConnectionResetError, RuntimeError):
                await response.write_eof()
            return response
        finally:
            upstream.release()


class YouTubeCastAudioProxyView(HomeAssistantView):
    """Transcode yt-dlp audio-only input to a simple MP3 stream for Cast."""

    url = f"/api/{DOMAIN}/youtube_cast_audio/{{token}}.mp3"
    name = f"api:{DOMAIN}:youtube_cast_audio"
    # The random path token is the short-lived capability.  Avoid authSig so the
    # Cast receiver sees a short URL and does not need HA authentication logic.
    requires_auth = False

    async def options(self, request: web.Request) -> web.StreamResponse:
        return web.Response(status=204, headers=_CORS_HEADERS)

    async def head(self, request: web.Request) -> web.StreamResponse:
        hass: HomeAssistant = request.app[KEY_HASS]
        _purge_expired(hass)
        token = str(request.match_info.get("token", ""))
        if not isinstance(_cast_proxy_store(hass).get(token), YouTubeCastAudioProxyItem):
            raise web.HTTPNotFound()
        return web.Response(
            status=200,
            headers={
                **_CORS_HEADERS,
                "Content-Type": "audio/mpeg",
                "Cache-Control": "no-store",
            },
        )

    async def get(self, request: web.Request) -> web.StreamResponse:
        hass: HomeAssistant = request.app[KEY_HASS]
        _purge_expired(hass)
        token = str(request.match_info.get("token", ""))
        item = _cast_proxy_store(hass).get(token)
        if not isinstance(item, YouTubeCastAudioProxyItem):
            raise web.HTTPNotFound()

        header_lines: list[str] = []
        for key, value in item.headers.items():
            safe_key = str(key).replace("\r", "").replace("\n", "").strip()
            safe_value = str(value).replace("\r", " ").replace("\n", " ").strip()
            if safe_key and safe_value:
                header_lines.append(f"{safe_key}: {safe_value}")
        header_blob = "\r\n".join(header_lines)
        if header_blob:
            header_blob += "\r\n"

        args = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-reconnect",
            "1",
            "-reconnect_streamed",
            "1",
            "-reconnect_delay_max",
            "5",
        ]
        if header_blob:
            args.extend(["-headers", header_blob])
        args.extend(
            [
                "-i",
                item.stream_url,
                "-map",
                "0:a:0",
                "-vn",
                "-sn",
                "-dn",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "128k",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-f",
                "mp3",
                "pipe:1",
            ]
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except (FileNotFoundError, OSError) as err:
            _LOGGER.warning("FFmpeg is unavailable for YouTube Cast audio: %s", err)
            raise web.HTTPServiceUnavailable(text="FFmpeg unavailable") from err

        response = web.StreamResponse(
            status=200,
            headers={
                **_CORS_HEADERS,
                "Content-Type": "audio/mpeg",
                "Cache-Control": "no-store",
                "Content-Disposition": 'inline; filename="youtube_audio.mp3"',
            },
        )
        await response.prepare(request)

        try:
            assert proc.stdout is not None
            while chunk := await proc.stdout.read(64 * 1024):
                await response.write(chunk)
        except (ConnectionResetError, RuntimeError):
            if proc.returncode is None:
                proc.terminate()
        except asyncio.CancelledError:
            if proc.returncode is None:
                proc.terminate()
            raise
        finally:
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.terminate()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=3)
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                with contextlib.suppress(Exception):
                    await proc.wait()
            if proc.returncode not in (0, None):
                _LOGGER.debug("YouTube Cast FFmpeg exited with code %s", proc.returncode)

        with contextlib.suppress(ConnectionResetError, RuntimeError):
            await response.write_eof()
        return response
