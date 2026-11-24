from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.downloader import (
    DOWNLOADS_DIR,
    extract_video_info,
    get_ffmpeg_status,
    list_downloaded_files,
    run_download_sync,
    strip_ansi,
    task_manager,
)

APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

app = FastAPI(
    title="SicMP4 – Video & Audio Downloader",
    description="Lokalny konwerter i downloader wideo/audio (yt-dlp + FFmpeg)",
    version="1.3.0",
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_background_tasks: set[asyncio.Task] = set()


def get_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


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


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=500, detail="Brak pliku szablonu index.html.")
    return HTMLResponse(
        content=index_file.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    ico_file = STATIC_DIR / "img" / "favicon.ico"
    if not ico_file.is_file():
        raise HTTPException(status_code=404, detail="Brak ikony favicon.ico.")
    return FileResponse(path=str(ico_file), media_type="image/x-icon")


@app.get("/api/health")
async def health_check() -> dict:
    ff_status = get_ffmpeg_status()
    lan_ip = get_lan_ip()
    return {
        "status": "ok",
        "ffmpeg": ff_status,
        "lan_url": f"http://{lan_ip}:8000",
        "downloads_dir": str(DOWNLOADS_DIR),
    }


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
        last_sent_ts = 0.0
        idle_ticks = 0
        while True:
            if await request.is_disconnected():
                break

            state = task_manager.get_task(task_id)
            if not state:
                err_payload = {"status": "error", "error": "Zadanie zostało usunięte."}
                yield f"data: {json.dumps(err_payload, ensure_ascii=False)}\n\n"
                break

            updated_at = state.get("updated_at", 0.0)
            if updated_at != last_sent_ts:
                last_sent_ts = updated_at
                idle_ticks = 0
                public_state = {k: v for k, v in state.items() if k != "filepath"}
                yield f"data: {json.dumps(public_state, ensure_ascii=False)}\n\n"

                if state["status"] in ("completed", "error"):
                    break
            else:
                idle_ticks += 1
                if idle_ticks >= 15:
                    idle_ticks = 0
                    yield ": keepalive\n\n"

            await asyncio.sleep(0.25)

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

    target_file: Path | None = None
    if payload.task_id:
        state = task_manager.get_task(payload.task_id)
        if state and state.get("filepath"):
            candidate = Path(state["filepath"]).resolve()
            if candidate.is_file() and DOWNLOADS_DIR.resolve() in candidate.parents:
                target_file = candidate
    elif payload.filename:
        candidate = (DOWNLOADS_DIR / payload.filename).resolve()
        if candidate.parent == DOWNLOADS_DIR.resolve() and candidate.is_file():
            target_file = candidate

    if os.name == "nt":
        if target_file:
            subprocess.Popen(["explorer.exe", f"/select,{target_file}"])
        else:
            os.startfile(str(DOWNLOADS_DIR.resolve()))
    return {"status": "opened"}
