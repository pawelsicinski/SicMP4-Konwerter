from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.downloader import (
    DOWNLOADS_DIR,
    clear_custom_cookies,
    extract_video_info,
    get_cookies_status,
    get_ffmpeg_status,
    list_downloaded_files,
    run_download_sync,
    save_custom_cookies,
    strip_ansi,
    task_manager,
)

if getattr(sys, "frozen", False):
    _BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)).resolve()
    APP_DIR = _BUNDLE_ROOT / "app"
else:
    APP_DIR = Path(__file__).resolve().parent

TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"
APP_VERSION = "1.5.0"

_LAN_IP_CACHE: dict[str, Any] = {"ip": "127.0.0.1", "expires": 0.0}
_INDEX_HTML_CACHE: dict[str, Any] = {"mtime_ns": None, "content": None}


class CachedStaticFiles(StaticFiles):
    """StaticFiles subclass applying public HTTP caching headers for static assets."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=86400"
        return response


class SelectiveGZipMiddleware:
    """Apply GZip compression to HTML/CSS/JS/JSON while bypassing SSE and binary downloads."""

    def __init__(self, app: ASGIApp, minimum_size: int = 1000) -> None:
        self.app = app
        self.gzip_app = GZipMiddleware(app, minimum_size=minimum_size)
        self.bypass_prefixes = ("/api/progress/", "/api/file/", "/api/downloads/file/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path.startswith(self.bypass_prefixes):
                await self.app(scope, receive, send)
                return
        await self.gzip_app(scope, receive, send)


app = FastAPI(
    title="SicMP4 – Video & Audio Downloader",
    description="Lokalny konwerter i downloader wideo/audio (yt-dlp + FFmpeg)",
    version=APP_VERSION,
)

app.add_middleware(SelectiveGZipMiddleware, minimum_size=1000)
app.mount("/static", CachedStaticFiles(directory=str(STATIC_DIR)), name="static")

_background_tasks: set[asyncio.Task] = set()


def get_lan_ip() -> str:
    now = time.monotonic()
    if now < _LAN_IP_CACHE["expires"]:
        return str(_LAN_IP_CACHE["ip"])
    ip = "127.0.0.1"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.4)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    _LAN_IP_CACHE["ip"] = ip
    _LAN_IP_CACHE["expires"] = now + 60.0
    return ip


def validate_http_url(raw_url: str) -> str:
    cleaned = raw_url.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Wklej prawidłowy adres URL filmu lub utworu.")
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail="Adres URL musi zaczynać się od http:// lub https://.",
        )
    return cleaned


class InfoRequest(BaseModel):
    url: str = Field(..., min_length=5, description="Adres URL wideo, audio lub playlisty")


class DownloadRequest(BaseModel):
    url: str = Field(..., min_length=5)
    format_type: Literal["mp4", "mp3", "m4a", "flac", "wav", "mkv", "webm"] = "mp4"
    quality: str = "1080"
    title: str = ""
    thumbnail: str = ""
    subtitle_mode: Literal["none", "embed", "srt", "burn"] = "none"
    clip_start: str = ""
    clip_end: str = ""
    allow_playlist: bool = False


class OpenFolderRequest(BaseModel):
    task_id: str | None = None
    filename: str | None = None


class CookiesRequest(BaseModel):
    cookies_text: str = Field(..., min_length=10)


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=500, detail="Brak pliku szablonu index.html.")
    mtime_ns = index_file.stat().st_mtime_ns
    if _INDEX_HTML_CACHE["mtime_ns"] != mtime_ns or _INDEX_HTML_CACHE["content"] is None:
        _INDEX_HTML_CACHE["content"] = index_file.read_text(encoding="utf-8")
        _INDEX_HTML_CACHE["mtime_ns"] = mtime_ns
    return HTMLResponse(
        content=_INDEX_HTML_CACHE["content"],
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    ico_file = STATIC_DIR / "img" / "favicon.ico"
    if not ico_file.is_file():
        raise HTTPException(status_code=404, detail="Brak ikony favicon.ico.")
    return FileResponse(
        path=str(ico_file),
        media_type="image/x-icon",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/api/health")
async def health_check() -> dict:
    ff_status = get_ffmpeg_status()
    lan_ip = get_lan_ip()
    port = os.environ.get("SICMP4_PORT") or os.environ.get("PORT") or "8000"
    is_desktop = os.environ.get("SICMP4_DESKTOP", "0") == "1"
    return {
        "status": "ok",
        "version": APP_VERSION,
        "desktop": is_desktop,
        "native_host_ui": os.name == "nt",
        "ffmpeg": ff_status,
        "cookies": get_cookies_status(),
        "lan_url": "" if is_desktop else f"http://{lan_ip}:{port}",
        "downloads_dir": str(DOWNLOADS_DIR),
    }


@app.post("/api/cookies")
async def api_save_cookies(payload: CookiesRequest) -> dict:
    try:
        return await asyncio.to_thread(save_custom_cookies, payload.cookies_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/cookies")
async def api_delete_cookies() -> dict:
    return await asyncio.to_thread(clear_custom_cookies)


@app.post("/api/info")
async def api_extract_info(payload: InfoRequest) -> dict:
    url = validate_http_url(payload.url)
    try:
        metadata = await asyncio.to_thread(extract_video_info, url)
        return metadata
    except Exception as exc:
        err_msg = strip_ansi(str(exc))
        raise HTTPException(
            status_code=400,
            detail=f"Nie udało się przeanalizować linku: {err_msg}",
        ) from exc


@app.post("/api/download")
async def api_start_download(payload: DownloadRequest) -> dict:
    url = validate_http_url(payload.url)

    state = task_manager.create_task(
        url=url,
        format_type=payload.format_type,
        quality=payload.quality,
        title=payload.title,
        thumbnail=payload.thumbnail,
        subtitle_mode=payload.subtitle_mode,
        clip_start=payload.clip_start,
        clip_end=payload.clip_end,
        allow_playlist=payload.allow_playlist,
    )
    task_id = state["task_id"]

    bg_task = asyncio.create_task(asyncio.to_thread(run_download_sync, task_id))
    _background_tasks.add(bg_task)
    bg_task.add_done_callback(_background_tasks.discard)

    return {"task_id": task_id, "state": state}


@app.get("/api/status/{task_id}")
async def api_task_status(task_id: str) -> dict:
    state = task_manager.get_task(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Nie znaleziono zadania o podanym ID.")
    return state


@app.get("/api/progress/{task_id}")
async def api_task_progress_sse(task_id: str, request: Request) -> StreamingResponse:
    initial = task_manager.get_task(task_id)
    if not initial:
        raise HTTPException(status_code=404, detail="Nie znaleziono zadania o podanym ID.")

    async def event_stream():
        last_sent_ts = -1.0
        idle_ticks = 0
        while True:
            if await request.is_disconnected():
                break

            state, changed = task_manager.get_task_if_updated(task_id, last_sent_ts)
            if changed:
                if not state:
                    err_payload = {"status": "error", "error": "Zadanie zostało usunięte."}
                    yield f"data: {json.dumps(err_payload, ensure_ascii=False)}\n\n"
                    break
                last_sent_ts = state.get("updated_at", 0.0)
                idle_ticks = 0
                public_state = {k: v for k, v in state.items() if k != "filepath"}
                yield f"data: {json.dumps(public_state, ensure_ascii=False)}\n\n"

                if state["status"] in ("completed", "error"):
                    break
            else:
                idle_ticks += 1
                if idle_ticks >= 20:
                    idle_ticks = 0
                    yield ": keepalive\n\n"

            await asyncio.sleep(0.18)

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=headers,
    )


def _media_type_for_suffix(suffix: str) -> str:
    return {
        ".mp4": "video/mp4",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".flac": "audio/flac",
        ".wav": "audio/wav",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
        ".srt": "application/x-subrip",
        ".zip": "application/zip",
    }.get(suffix.lower(), "application/octet-stream")


def _resolve_task_or_saved_file(task_id: str | None, filename: str | None) -> Path | None:
    downloads_resolved = DOWNLOADS_DIR.resolve()
    if task_id:
        state = task_manager.get_task(task_id)
        if state and state.get("filepath"):
            candidate = Path(state["filepath"]).resolve()
            if candidate.is_file() and downloads_resolved in candidate.parents:
                return candidate
    elif filename:
        candidate = (DOWNLOADS_DIR / filename).resolve()
        if candidate.parent == downloads_resolved and candidate.is_file():
            return candidate
    return None


@app.get("/api/file/{task_id}")
async def api_download_task_file(task_id: str) -> FileResponse:
    state = task_manager.get_task(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Nie znaleziono zadania.")
    if state.get("status") != "completed" or not state.get("filepath"):
        raise HTTPException(status_code=400, detail="Plik nie jest jeszcze gotowy do pobrania.")

    file_path = Path(state["filepath"]).resolve()
    if not file_path.is_file() or DOWNLOADS_DIR.resolve() not in file_path.parents:
        raise HTTPException(status_code=404, detail="Plik nie istnieje na dysku.")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=_media_type_for_suffix(file_path.suffix),
    )


@app.get("/api/downloads")
async def api_list_downloads() -> dict:
    files = await asyncio.to_thread(list_downloaded_files)
    return {"files": files}


@app.get("/api/downloads/file/{filename}")
async def api_download_saved_file(filename: str) -> FileResponse:
    safe_path = (DOWNLOADS_DIR / filename).resolve()
    if safe_path.parent != DOWNLOADS_DIR.resolve() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Plik nie został znaleziony.")
    return FileResponse(
        path=str(safe_path),
        filename=safe_path.name,
        media_type=_media_type_for_suffix(safe_path.suffix),
    )


@app.delete("/api/downloads/{filename}")
async def api_delete_saved_file(filename: str) -> dict:
    safe_path = (DOWNLOADS_DIR / filename).resolve()
    if safe_path.parent != DOWNLOADS_DIR.resolve() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Plik nie został znaleziony.")
    safe_path.unlink(missing_ok=True)
    return {"deleted": filename}


@app.post("/api/open-folder")
async def api_open_downloads_folder(payload: OpenFolderRequest, request: Request) -> dict:
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(
            status_code=403,
            detail="Otwieranie folderu Eksploratora działa wyłącznie bezpośrednio na komputerze-hoście.",
        )

    target_file = _resolve_task_or_saved_file(payload.task_id, payload.filename)
    if os.name == "nt":
        if target_file:
            subprocess.Popen(["explorer.exe", f"/select,{target_file}"])
        else:
            os.startfile(str(DOWNLOADS_DIR.resolve()))
    return {"status": "opened"}


def _read_windows_clipboard_text() -> str:
    if os.name != "nt":
        return ""
    import ctypes
    from ctypes import wintypes

    cf_unicodetext = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    for _ in range(3):
        if user32.OpenClipboard(None):
            try:
                handle = user32.GetClipboardData(cf_unicodetext)
                if not handle:
                    return ""
                ptr = kernel32.GlobalLock(handle)
                if not ptr:
                    return ""
                try:
                    return ctypes.wstring_at(ptr)
                finally:
                    kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
    return ""


@app.get("/api/clipboard")
async def api_read_clipboard(request: Request) -> dict:
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="Dostęp do schowka tylko lokalnie.")
    text = await asyncio.to_thread(_read_windows_clipboard_text)
    return {"text": text}


def _prompt_save_as_copy(source_file: Path) -> str | None:
    dest_str: str | None = None
    ext = source_file.suffix.lstrip(".").lower() or "mp4"
    file_types = (f"Plik {ext.upper()} (*.{ext})", "Wszystkie pliki (*.*)")

    try:
        import webview

        if webview.windows:
            dialog_mode = getattr(getattr(webview, "FileDialog", None), "SAVE", webview.SAVE_DIALOG)
            result = webview.windows[0].create_file_dialog(
                dialog_mode,
                save_filename=source_file.name,
                file_types=file_types,
            )
            if isinstance(result, (list, tuple)):
                dest_str = result[0] if result else None
            elif isinstance(result, str):
                dest_str = result
    except Exception:
        dest_str = None

    if dest_str is None:
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            picked = filedialog.asksaveasfilename(
                initialfile=source_file.name,
                defaultextension=source_file.suffix,
                filetypes=[(f"Plik {ext.upper()}", f"*.{ext}"), ("Wszystkie pliki", "*.*")],
                title="Zapisz plik jako...",
            )
            root.destroy()
            if picked:
                dest_str = picked
        except Exception:
            dest_str = None

    if not dest_str:
        return None

    dest_path = Path(dest_str).resolve()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path != source_file.resolve():
        shutil.copy2(source_file, dest_path)
    return str(dest_path)


@app.post("/api/save-as")
async def api_save_file_as(payload: OpenFolderRequest, request: Request) -> dict:
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="Zapisywanie działa wyłącznie lokalnie.")

    source_file = _resolve_task_or_saved_file(payload.task_id, payload.filename)
    if not source_file:
        raise HTTPException(status_code=404, detail="Plik źródłowy nie istnieje.")

    saved_path = await asyncio.to_thread(_prompt_save_as_copy, source_file)
    if not saved_path:
        return {"saved": False}
    return {"saved": True, "path": saved_path}
