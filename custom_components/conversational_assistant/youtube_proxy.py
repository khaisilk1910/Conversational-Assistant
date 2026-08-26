"""Short-lived HTTP helpers for YouTube audio playback.

Two deliberately separate paths are provided:

* generic speakers can consume a signed byte-range proxy of the yt-dlp
  selected audio stream;
* Google Cast / Google Home / Nest receives a *completed local audio file*.
  The integration downloads/remuxes the file before playback, then this module
  exposes it through a short random capability URL with normal file/range
  semantics.  The file is deleted after playback or by a TTL safety task.

No YouTube network request, download, file scan, or FFmpeg process runs while
Home Assistant starts.  These views only register lightweight HTTP routes.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
import logging
from pathlib import Path
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
_CAST_FILE_DATA_KEY = "youtube_cast_file_proxy"
_PROXY_TTL_SECONDS = 5 * 60 * 60
_CAST_FILE_TTL_SECONDS = 8 * 60 * 60
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
    "Access-Control-Expose-Headers": (
        "Content-Length, Content-Range, Accept-Ranges, Content-Type"
    ),
}


@dataclass(slots=True)
class YouTubeAudioProxyItem:
    """One short-lived upstream stream exposed through Home Assistant."""

    stream_url: str
    mime_type: str
    headers: dict[str, str]
    expires_at: float


@dataclass(slots=True)
class YouTubeCastFileItem:
    """One fully downloaded audio file exposed temporarily to Google Cast."""

    file_path: Path
    mime_type: str
    extension: str
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
def _cast_file_store(hass: HomeAssistant) -> dict[str, YouTubeCastFileItem]:
    domain_data = hass.data.setdefault(DOMAIN, {})
    store = domain_data.get(_CAST_FILE_DATA_KEY)
    if not isinstance(store, dict):
        store = {}
        domain_data[_CAST_FILE_DATA_KEY] = store
    return store


@callback
def _purge_expired_proxy_items(hass: HomeAssistant) -> None:
    now = monotonic()
    store = _proxy_store(hass)
    for token, item in list(store.items()):
        if item.expires_at <= now:
            store.pop(token, None)


@callback
def async_setup_youtube_audio_proxy(hass: HomeAssistant) -> None:
    """Register lightweight YouTube HTTP endpoints once."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(f"{_DATA_KEY}_view_registered"):
        return
    _proxy_store(hass)
    _cast_file_store(hass)
    hass.http.register_view(YouTubeAudioProxyView)
    hass.http.register_view(YouTubeCastFileView)
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
    _purge_expired_proxy_items(hass)
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


async def async_remove_youtube_cast_file(
    hass: HomeAssistant, token: str, *, delete_file: bool = True
) -> None:
    """Forget a temporary Cast file and optionally remove it from disk."""
    item = _cast_file_store(hass).pop(str(token), None)
    if not isinstance(item, YouTubeCastFileItem) or not delete_file:
        return

    def _unlink() -> None:
        with contextlib.suppress(FileNotFoundError, OSError):
            item.file_path.unlink()

    await hass.async_add_executor_job(_unlink)


@callback
def async_register_youtube_cast_file(
    hass: HomeAssistant,
    *,
    file_path: str | Path,
    mime_type: str,
    extension: str,
    ttl_seconds: int = _CAST_FILE_TTL_SECONDS,
) -> tuple[str, list[str]]:
    """Expose a completed local audio file using a random capability URL."""
    path_obj = Path(file_path)
    ext = str(extension or path_obj.suffix.lstrip(".") or "m4a").casefold().lstrip(".")
    if ext not in _ALLOWED_EXTENSIONS:
        ext = "m4a"
    ttl = max(300, int(ttl_seconds))
    token = token_urlsafe(24).replace(".", "_")
    _cast_file_store(hass)[token] = YouTubeCastFileItem(
        file_path=path_obj,
        mime_type=str(mime_type or "audio/mp4"),
        extension=ext,
        expires_at=monotonic() + ttl,
    )
    route = f"/api/{DOMAIN}/youtube_cast_file/{token}.{ext}"
    urls = [f"{base}{route}" for base in _candidate_base_urls(hass)]

    async def _expire_later() -> None:
        await asyncio.sleep(ttl)
        await async_remove_youtube_cast_file(hass, token)

    hass.async_create_background_task(
        _expire_later(), "conversational_assistant_youtube_proxy_expiry"
    )
    return token, urls


class YouTubeCastFileView(HomeAssistantView):
    """Serve a completed local audio file with byte-range support for Cast."""

    url = f"/api/{DOMAIN}/youtube_cast_file/{{token}}.{{ext}}"
    name = f"api:{DOMAIN}:youtube_cast_file"
    # The long random token is the short-lived capability.  No reusable HA
    # credential is embedded in the URL.
    requires_auth = False
    cors_allowed = True

    async def get(
        self, request: web.Request, token: str, ext: str
    ) -> web.StreamResponse:
        return await self._serve(request, token=token, ext=ext, head_only=False)

    async def head(
        self, request: web.Request, token: str, ext: str
    ) -> web.StreamResponse:
        return await self._serve(request, token=token, ext=ext, head_only=True)

    async def _serve(
        self,
        request: web.Request,
        *,
        token: str,
        ext: str,
        head_only: bool,
    ) -> web.StreamResponse:
        hass: HomeAssistant = request.app[KEY_HASS]
        item = _cast_file_store(hass).get(str(token))
        if not isinstance(item, YouTubeCastFileItem):
            raise web.HTTPNotFound()
        if item.expires_at <= monotonic():
            hass.async_create_background_task(
                async_remove_youtube_cast_file(hass, str(token)),
                "conversational_assistant_youtube_cast_expiry",
            )
            raise web.HTTPNotFound()

        def _stat_file() -> tuple[bool, int]:
            try:
                stat = item.file_path.stat()
                return item.file_path.is_file(), stat.st_size
            except OSError:
                return False, 0

        exists, file_size = await hass.async_add_executor_job(_stat_file)
        if not exists:
            _cast_file_store(hass).pop(str(token), None)
            raise web.HTTPNotFound()

        headers = {
            **_CORS_HEADERS,
            "Content-Type": item.mime_type,
            "Cache-Control": "no-store",
            "Content-Disposition": f'inline; filename="youtube_audio.{item.extension}"',
            "X-Content-Type-Options": "nosniff",
            "Accept-Ranges": "bytes",
        }
        if head_only:
            headers["Content-Length"] = str(file_size)
            return web.Response(status=200, headers=headers)

        # aiohttp FileResponse handles Range requests and partial responses for
        # seekable/buffered Cast playback.
        return web.FileResponse(path=item.file_path, headers=headers)


class YouTubeAudioProxyView(HomeAssistantView):
    """Proxy an audio stream through Home Assistant with signed-path auth."""

    url = f"/api/{DOMAIN}/youtube_audio/{{token}}.{{ext}}"
    name = f"api:{DOMAIN}:youtube_audio"
    requires_auth = True
    cors_allowed = True

    async def get(
        self, request: web.Request, token: str, ext: str
    ) -> web.StreamResponse:
        return await self._handle(request, token=token, head_only=False)

    async def head(
        self, request: web.Request, token: str, ext: str
    ) -> web.StreamResponse:
        return await self._handle(request, token=token, head_only=True)

    async def _handle(
        self, request: web.Request, *, token: str, head_only: bool
    ) -> web.StreamResponse:
        hass: HomeAssistant = request.app[KEY_HASS]
        _purge_expired_proxy_items(hass)
        item = _proxy_store(hass).get(str(token))
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
