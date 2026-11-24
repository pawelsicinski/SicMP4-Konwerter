from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any

import yt_dlp
from yt_dlp.utils import download_range_func

BASE_DIR = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
TEMP_ROOT_DIR = DOWNLOADS_DIR / ".tmp"
COOKIES_STORE_DIR = DOWNLOADS_DIR / ".cookies"
CUSTOM_COOKIES_FILE = COOKIES_STORE_DIR / "cookies.txt"
RENDER_SECRET_COOKIES = Path("/etc/secrets/cookies.txt")
LOCAL_ROOT_COOKIES = BASE_DIR / "cookies.txt"
LOCAL_BIN_DIR = BASE_DIR / "bin"

DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_ROOT_DIR.mkdir(parents=True, exist_ok=True)
COOKIES_STORE_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_BIN_DIR.mkdir(parents=True, exist_ok=True)

ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str | None) -> str:
    if not text:
        return ""
    return ANSI_ESCAPE_RE.sub("", str(text)).strip()


def format_bytes(num_bytes: float | int | None) -> str:
    if num_bytes is None or num_bytes <= 0:
        return "—"
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{value:.1f} TB"


def format_duration(seconds: float | int | None) -> str:
    if seconds is None or seconds < 0:
        return "Na żywo / Nieznany"
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def parse_timestamp_to_seconds(raw: str | None) -> float | None:
    """Parse MM:SS, HH:MM:SS, or raw seconds into float seconds."""
    if not raw:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    parts = cleaned.split(":")
    if len(parts) > 3:
        raise ValueError(f"Nieprawidłowy format czasu: {cleaned} (użyj MM:SS lub GG:MM:SS).")
    total = 0.0
    for part in parts:
        try:
            val = float(part.replace(",", "."))
        except ValueError as exc:
            raise ValueError(f"Nieprawidłowa wartość czasu: {cleaned}.") from exc
        if val < 0:
            raise ValueError("Czas wycinka nie może być ujemny.")
        total = total * 60.0 + val
    return total


def find_ffmpeg_dir() -> str | None:
    """Locate directory containing ffmpeg and ffprobe binaries on Windows/Linux."""
    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    probe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"

    if (LOCAL_BIN_DIR / exe_name).is_file():
        return str(LOCAL_BIN_DIR)

    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        parent = Path(which_ffmpeg).resolve().parent
        if (parent / probe_name).exists() or shutil.which("ffprobe"):
            return str(parent)

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        user_profile = os.environ.get("USERPROFILE", "")
        program_data = os.environ.get("ProgramData", r"C:\ProgramData")

        candidate_dirs: list[Path] = []
        if local_app_data:
            winget_links = Path(local_app_data) / "Microsoft" / "WinGet" / "Links"
            candidate_dirs.append(winget_links)
            winget_pkgs = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
            if winget_pkgs.is_dir():
                for found in winget_pkgs.rglob("ffmpeg.exe"):
                    candidate_dirs.insert(0, found.parent)

        candidate_dirs.extend([
            Path(r"C:\ffmpeg\bin"),
            Path(program_data) / "chocolatey" / "bin",
            Path(user_profile) / "scoop" / "shims" if user_profile else Path(),
        ])

        for folder in candidate_dirs:
            if folder and (folder / exe_name).is_file():
                return str(folder)

    return None


FFMPEG_DIR = find_ffmpeg_dir()
AUTO_CLEANUP_HOURS = float(os.environ.get("AUTO_CLEANUP_HOURS", "0") or "0")


def cleanup_old_downloads(max_age_hours: float) -> None:
    """Remove old files in downloads/ when running in cloud-hosted mode."""
    if max_age_hours <= 0 or not DOWNLOADS_DIR.is_dir():
        return
    cutoff = time.time() - (max_age_hours * 3600.0)
    for item in DOWNLOADS_DIR.iterdir():
        if item.name in (".gitkeep", ".tmp", ".cookies"):
            continue
        try:
            if item.is_file() and item.stat().st_mtime < cutoff:
                item.unlink(missing_ok=True)
        except OSError:
            pass


def _resolve_cookie_source_text() -> tuple[str | None, str]:
    """Return (cookies_text, source_label) if any user-provided cookies exist."""
    for candidate, label in (
        (CUSTOM_COOKIES_FILE, "panel"),
        (RENDER_SECRET_COOKIES, "render_secret"),
        (LOCAL_ROOT_COOKIES, "local_file"),
    ):
        if candidate.is_file():
            try:
                txt = candidate.read_text(encoding="utf-8", errors="ignore").strip()
                if txt:
                    return txt, label
            except OSError:
                pass

    env_cookies = os.environ.get("YOUTUBE_COOKIES", "").strip()
    if env_cookies:
        return env_cookies, "env"

    return None, "none"


def make_temp_cookiefile() -> Path | None:
    """Create an isolated writable copy of cookies.txt so read-only /etc/secrets never fails."""
    txt, _ = _resolve_cookie_source_text()
    if not txt:
        return None
    if "# Netscape HTTP Cookie File" not in txt and "# HTTP Cookie File" not in txt:
        txt = "# Netscape HTTP Cookie File\n" + txt
    tmp_cookie = TEMP_ROOT_DIR / f"cookies_{uuid.uuid4().hex[:10]}.txt"
    tmp_cookie.write_text(txt + "\n", encoding="utf-8")
    return tmp_cookie


def get_cookies_status() -> dict[str, Any]:
    txt, source = _resolve_cookie_source_text()
    return {
        "configured": txt is not None,
        "source": source,
    }


def save_custom_cookies(raw_text: str) -> dict[str, Any]:
    cleaned = raw_text.replace("\r\n", "\n").strip()
    if not cleaned:
        raise ValueError("Zawartość pliku cookies.txt jest pusta.")
    valid_lines = [
        ln for ln in cleaned.splitlines()
        if ln.strip() and not ln.strip().startswith("#") and "\t" in ln
    ]
    if not valid_lines:
        raise ValueError(
            "Nie wykryto wpisów w formacie Netscape cookies.txt (linie rozdzielane tabulatorami)."
        )
    if "# Netscape HTTP Cookie File" not in cleaned and "# HTTP Cookie File" not in cleaned:
        cleaned = "# Netscape HTTP Cookie File\n" + cleaned
    COOKIES_STORE_DIR.mkdir(parents=True, exist_ok=True)
    CUSTOM_COOKIES_FILE.write_text(cleaned + "\n", encoding="utf-8")
    return {"configured": True, "source": "panel", "entries": len(valid_lines)}


def clear_custom_cookies() -> dict[str, Any]:
    CUSTOM_COOKIES_FILE.unlink(missing_ok=True)
    return get_cookies_status()


def get_ffmpeg_status() -> dict[str, Any]:
    global FFMPEG_DIR
    if not FFMPEG_DIR or not Path(FFMPEG_DIR).exists():
        FFMPEG_DIR = find_ffmpeg_dir()
    return {
        "available": FFMPEG_DIR is not None,
        "path": FFMPEG_DIR,
        "yt_dlp_version": yt_dlp.version.__version__,
    }


def _pick_best_thumbnail(info: dict[str, Any]) -> str:
    thumb = info.get("thumbnail")
    if thumb and isinstance(thumb, str) and thumb.startswith("http"):
        return thumb
    thumbs = info.get("thumbnails") or []
    http_thumbs = [
        t for t in thumbs
        if isinstance(t, dict) and isinstance(t.get("url"), str) and t["url"].startswith("http")
    ]
    if http_thumbs:
        http_thumbs.sort(
            key=lambda t: (t.get("preference") or 0, t.get("height") or 0, t.get("width") or 0)
        )
        return http_thumbs[-1]["url"]
    return ""


def _build_js_runtimes() -> dict[str, dict[str, Any]]:
    runtimes: dict[str, dict[str, Any]] = {}
    if shutil.which("deno"):
        runtimes["deno"] = {}
    if shutil.which("node"):
        runtimes["node"] = {}
    return runtimes


def extract_video_info(url: str) -> dict[str, Any]:
    """Quickly extract video/audio/playlist metadata and available resolutions."""
    tmp_cookie = make_temp_cookiefile()
    try:
        return _extract_video_info_inner(url, tmp_cookie)
    finally:
        if tmp_cookie:
            tmp_cookie.unlink(missing_ok=True)


def _extract_video_info_inner(url: str, cookie_path: Path | None) -> dict[str, Any]:
    is_pure_playlist_url = ("/playlist?" in url.lower()) or ("list=" in url.lower() and "v=" not in url.lower())

    if is_pure_playlist_url:
        flat_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "socket_timeout": 15,
        }
        if cookie_path:
            flat_opts["cookiefile"] = str(cookie_path)
        js_rt = _build_js_runtimes()
        if js_rt:
            flat_opts["js_runtimes"] = js_rt
        with yt_dlp.YoutubeDL(flat_opts) as ydl:
            pl_info = ydl.extract_info(url, download=False)
            entries = [e for e in (pl_info.get("entries") or []) if e]
            count = pl_info.get("playlist_count") or len(entries)
            first = entries[0] if entries else {}
            return {
                "id": pl_info.get("id") or "",
                "url": pl_info.get("webpage_url") or url,
                "title": pl_info.get("title") or "Playlista",
                "author": pl_info.get("uploader") or pl_info.get("channel") or "Playlista",
                "duration": None,
                "duration_string": f"Playlista ({count} poz.)",
                "thumbnail": _pick_best_thumbnail(pl_info) or _pick_best_thumbnail(first),
                "extractor": pl_info.get("extractor_key") or pl_info.get("extractor") or "Playlist",
                "view_count": pl_info.get("view_count"),
                "available_heights": [2160, 1440, 1080, 720, 480],
                "resolutions": [],
                "has_subtitles": True,
                "subtitle_langs": ["pl", "en"],
                "is_playlist": True,
                "playlist_count": count,
                "best_audio_size_str": None,
            }

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extract_flat": False,
        "socket_timeout": 15,
    }
    if FFMPEG_DIR:
        ydl_opts["ffmpeg_location"] = FFMPEG_DIR
    if cookie_path:
        ydl_opts["cookiefile"] = str(cookie_path)
    js_rt = _build_js_runtimes()
    if js_rt:
        ydl_opts["js_runtimes"] = js_rt

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False, process=False)
        if not info:
            raise ValueError("Nie udało się pobrać informacji dla podanego adresu URL.")

        if info.get("_type") in ("url", "url_transparent", "playlist") or "formats" not in info:
            info = ydl.process_ie_result(info, download=False)

        if info.get("_type") == "playlist" and info.get("entries"):
            first_entry = next((e for e in info["entries"] if e), None)
            if not first_entry:
                raise ValueError("Playlista jest pusta lub niedostępna.")
            info = first_entry
            if "formats" not in info:
                info = ydl.process_ie_result(info, download=False)

    formats = info.get("formats") or []

    audio_sizes = [
        f.get("filesize") or f.get("filesize_approx") or 0
        for f in formats
        if f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none")
    ]
    best_audio_size = max(audio_sizes) if audio_sizes else 0

    height_map: dict[int, dict[str, Any]] = {}
    for fmt in formats:
        vcodec = fmt.get("vcodec")
        ext = fmt.get("ext")
        height = fmt.get("height")
        if not height or vcodec in (None, "none") or ext == "mhtml" or height < 144:
            continue

        fsize = fmt.get("filesize") or fmt.get("filesize_approx") or 0
        has_audio = fmt.get("acodec") not in (None, "none")
        est_total = fsize + (0 if has_audio or fsize == 0 else best_audio_size)
        fps = fmt.get("fps") or 0

        existing = height_map.get(height)
        is_mp4_https = ext == "mp4" and fmt.get("protocol") == "https"
        if not existing or (is_mp4_https and not existing["is_mp4_https"]) or (
            is_mp4_https == existing["is_mp4_https"] and est_total > existing["filesize_approx"]
        ):
            height_map[height] = {
                "height": height,
                "label": f"{height}p" + (f" {int(fps)}fps" if fps and fps > 30 else ""),
                "fps": int(fps) if fps else None,
                "filesize_approx": est_total,
                "filesize_str": format_bytes(est_total) if est_total else None,
                "is_mp4_https": is_mp4_https,
            }

    available_heights = sorted(height_map.keys(), reverse=True)
    resolutions = [
        {
            "height": h,
            "label": height_map[h]["label"],
            "filesize_str": height_map[h]["filesize_str"],
        }
        for h in available_heights
    ]

    subtitles_dict = info.get("subtitles") or {}
    auto_captions_dict = info.get("automatic_captions") or {}
    subtitle_langs = sorted(set(subtitles_dict.keys()) | {k for k in auto_captions_dict.keys() if k in ("pl", "en")})

    duration = info.get("duration")
    author = (
        info.get("uploader")
        or info.get("channel")
        or info.get("artist")
        or info.get("creator")
        or "Nieznany autor"
    )

    has_list_param = "list=" in url.lower()

    return {
        "id": info.get("id") or "",
        "url": url if has_list_param else (info.get("webpage_url") or url),
        "title": info.get("title") or "Bez tytułu",
        "author": author,
        "duration": duration,
        "duration_string": format_duration(duration),
        "thumbnail": _pick_best_thumbnail(info),
        "extractor": info.get("extractor_key") or info.get("extractor") or "Web",
        "view_count": info.get("view_count"),
        "available_heights": available_heights,
        "resolutions": resolutions,
        "has_subtitles": len(subtitle_langs) > 0,
        "subtitle_langs": subtitle_langs[:12],
        "is_playlist": False,
        "has_playlist_param": has_list_param,
        "best_audio_size_str": format_bytes(best_audio_size) if best_audio_size else None,
    }


class TaskManager:
    """Thread-safe manager for active and completed download/conversion tasks."""

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_task(
        self,
        url: str,
        format_type: str,
        quality: str,
        title: str = "",
        thumbnail: str = "",
        subtitle_mode: str = "none",
        clip_start: str = "",
        clip_end: str = "",
        allow_playlist: bool = False,
    ) -> dict[str, Any]:
        task_id = uuid.uuid4().hex[:12]
        now = time.time()
        state: dict[str, Any] = {
            "task_id": task_id,
            "url": url,
            "title": title or "Pobieranie multimediów...",
            "thumbnail": thumbnail or "",
            "format_type": format_type,
            "quality": quality,
            "subtitle_mode": subtitle_mode,
            "clip_start": clip_start,
            "clip_end": clip_end,
            "allow_playlist": allow_playlist,
            "status": "queued",
            "stage": "Oczekiwanie w kolejce...",
            "percent": 0.0,
            "speed": "—",
            "eta": "—",
            "downloaded_str": "0 B",
            "filename": None,
            "filepath": None,
            "filesize": None,
            "filesize_str": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            self._tasks[task_id] = state
        return dict(state)

    def update_task(self, task_id: str, **updates: Any) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task.update(updates)
            task["updated_at"] = time.time()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None


task_manager = TaskManager()


def _quality_tag(format_type: str, quality: str, clip_start: str, clip_end: str) -> str:
    if format_type == "mp3":
        base = f"{quality}kbps"
    elif format_type in ("m4a", "flac", "wav"):
        base = format_type.upper()
    elif quality == "best":
        base = "MAX"
    else:
        base = f"{quality}p"

    if clip_start or clip_end:
        s_clean = (clip_start or "0").replace(":", "-")
        e_clean = (clip_end or "end").replace(":", "-")
        return f"{base}_{s_clean}-{e_clean}"
    return base


def _burn_subtitles_ffmpeg(ffmpeg_dir: str, video_path: Path, srt_path: Path) -> Path:
    """Burn an .srt subtitle file permanently into the video stream using FFmpeg."""
    ffmpeg_exe = Path(ffmpeg_dir) / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    temp_out = video_path.with_name(f"{video_path.stem}_hardsub{video_path.suffix}")
    escaped_srt = str(srt_path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    cmd = [
        str(ffmpeg_exe),
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"subtitles='{escaped_srt}'",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "copy",
        str(temp_out),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    temp_out.replace(video_path)
    return video_path


def run_download_sync(task_id: str) -> None:
    """Blocking worker executed in a background thread via asyncio.to_thread."""
    task = task_manager.get_task(task_id)
    if not task:
        return

    global FFMPEG_DIR
    if not FFMPEG_DIR:
        FFMPEG_DIR = find_ffmpeg_dir()

    if not FFMPEG_DIR:
        task_manager.update_task(
            task_id,
            status="error",
            stage="Brak narzędzia FFmpeg",
            error=(
                "Nie znaleziono binarek ffmpeg / ffprobe. Zainstaluj Gyan.FFmpeg przez winget "
                "lub umieść ffmpeg.exe i ffprobe.exe w folderze bin/."
            ),
        )
        return

    url: str = task["url"]
    format_type: str = task["format_type"].lower()
    quality: str = str(task["quality"]).lower()
    subtitle_mode: str = str(task.get("subtitle_mode") or "none").lower()
    clip_start_raw: str = str(task.get("clip_start") or "").strip()
    clip_end_raw: str = str(task.get("clip_end") or "").strip()
    allow_playlist: bool = bool(task.get("allow_playlist", False))

    is_audio_only_target = format_type in ("mp3", "m4a", "flac", "wav")
    if is_audio_only_target:
        subtitle_mode = "none"

    try:
        start_sec = parse_timestamp_to_seconds(clip_start_raw)
        end_sec = parse_timestamp_to_seconds(clip_end_raw)
        if start_sec is not None and end_sec is not None and end_sec <= start_sec:
            raise ValueError("Czas końcowy wycinka musi być większy niż czas początkowy.")
    except ValueError as val_err:
        task_manager.update_task(
            task_id,
            status="error",
            stage="Nieprawidłowy wycinek czasowy",
            error=str(val_err),
        )
        return

    qtag = _quality_tag(format_type, quality, clip_start_raw, clip_end_raw)
    if allow_playlist:
        outtmpl_name = f"%(playlist_index&{{}} - |)s%(title).100B [{qtag}].%(ext)s"
    else:
        outtmpl_name = f"%(title).110B [{qtag}].%(ext)s"

    task_temp_dir = TEMP_ROOT_DIR / task_id
    task_temp_dir.mkdir(parents=True, exist_ok=True)
    if AUTO_CLEANUP_HOURS > 0:
        cleanup_old_downloads(AUTO_CLEANUP_HOURS)
    started_wall_time = time.time()

    def progress_hook(d: dict[str, Any]) -> None:
        st = d.get("status")
        info_dict = d.get("info_dict") or {}

        pl_idx = info_dict.get("playlist_index")
        pl_cnt = info_dict.get("n_entries") or info_dict.get("playlist_count")
        pl_prefix = f"[Pozycja {pl_idx}/{pl_cnt}] " if (allow_playlist and pl_idx and pl_cnt) else ""

        if st == "downloading":
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0

            raw_pct = 0.0
            if total > 0:
                raw_pct = min(100.0, (downloaded / total) * 100.0)
            else:
                frag_idx = d.get("fragment_index")
                frag_cnt = d.get("fragment_count")
                if frag_idx and frag_cnt and frag_cnt > 0:
                    raw_pct = min(100.0, (frag_idx / frag_cnt) * 100.0)

            vcodec = info_dict.get("vcodec")
            acodec = info_dict.get("acodec")
            is_video_stream = vcodec not in (None, "none") and acodec in (None, "none")
            is_audio_stream = vcodec in (None, "none") and acodec not in (None, "none")

            if not is_audio_only_target and is_video_stream:
                mapped_pct = raw_pct * 0.84
                stage_text = f"{pl_prefix}Pobieranie strumienia wideo (1/2)..."
            elif not is_audio_only_target and is_audio_stream:
                mapped_pct = 84.0 + (raw_pct * 0.11)
                stage_text = f"{pl_prefix}Pobieranie strumienia audio (2/2)..."
            elif is_audio_only_target:
                mapped_pct = raw_pct * 0.90
                stage_text = f"{pl_prefix}Pobieranie strumienia audio..."
            else:
                mapped_pct = raw_pct * 0.94
                stage_text = f"{pl_prefix}Pobieranie multimediów..."

            speed_bytes = d.get("speed")
            speed_str = f"{format_bytes(speed_bytes)}/s" if speed_bytes else strip_ansi(d.get("_speed_str")) or "—"

            eta_sec = d.get("eta")
            if isinstance(eta_sec, (int, float)) and eta_sec >= 0:
                eta_str = format_duration(eta_sec)
            else:
                eta_str = strip_ansi(d.get("_eta_str")) or "—"

            dl_str = (
                f"{format_bytes(downloaded)} / {format_bytes(total)}"
                if total > 0
                else format_bytes(downloaded)
            )

            current = task_manager.get_task(task_id)
            prev_pct = current["percent"] if (current and not allow_playlist) else 0.0
            updates: dict[str, Any] = {
                "status": "downloading",
                "stage": stage_text,
                "percent": round(max(prev_pct, mapped_pct), 1),
                "speed": speed_str,
                "eta": eta_str,
                "downloaded_str": dl_str,
            }
            if info_dict.get("title") and not allow_playlist and (
                not current or current["title"] == "Pobieranie multimediów..."
            ):
                updates["title"] = info_dict["title"]
            task_manager.update_task(task_id, **updates)

        elif st == "finished":
            current = task_manager.get_task(task_id)
            prev_pct = current["percent"] if (current and not allow_playlist) else 90.0
            task_manager.update_task(
                task_id,
                status="processing",
                stage=f"{pl_prefix}Przetwarzanie strumieni w FFmpeg...",
                percent=round(max(prev_pct, 94.0), 1),
                speed="FFmpeg",
                eta="chwilka...",
            )

    def postprocessor_hook(d: dict[str, Any]) -> None:
        pp_status = d.get("status")
        pp_name = d.get("postprocessor") or ""
        if pp_status == "started":
            if "ExtractAudio" in pp_name:
                stage_msg = f"Konwersja audio do {format_type.upper()}..."
                pct = 95.0
            elif "EmbedThumbnail" in pp_name or "Thumbnails" in pp_name:
                stage_msg = "Osadzanie okładki albumu..."
                pct = 98.0
            elif "Metadata" in pp_name:
                stage_msg = "Zapisywanie tagów i metadanych..."
                pct = 97.0
            elif "Subtitle" in pp_name:
                stage_msg = "Przetwarzanie i konwersja napisów..."
                pct = 96.5
            else:
                stage_msg = "Łączenie obrazu i dźwięku (FFmpeg muxing)..."
                pct = 96.0

            current = task_manager.get_task(task_id)
            prev_pct = current["percent"] if (current and not allow_playlist) else 95.0
            task_manager.update_task(
                task_id,
                status="processing",
                stage=stage_msg,
                percent=round(max(prev_pct, pct), 1),
                speed="FFmpeg",
                eta="chwilka...",
            )

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": not allow_playlist,
        "ignoreerrors": allow_playlist,
        "ffmpeg_location": FFMPEG_DIR,
        "paths": {
            "home": str(DOWNLOADS_DIR),
            "temp": str(task_temp_dir),
        },
        "outtmpl": {"default": outtmpl_name},
        "windowsfilenames": True,
        "overwrites": True,
        "hls_use_mpegts": False,
        "concurrent_fragment_downloads": 8,
        "retries": 10,
        "fragment_retries": 10,
        "file_access_retries": 5,
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [postprocessor_hook],
    }
    js_rt = _build_js_runtimes()
    if js_rt:
        ydl_opts["js_runtimes"] = js_rt
    tmp_cookie = make_temp_cookiefile()
    if tmp_cookie:
        ydl_opts["cookiefile"] = str(tmp_cookie)

    if start_sec is not None or end_sec is not None:
        r_start = start_sec if start_sec is not None else 0.0
        r_end = end_sec if end_sec is not None else float("inf")
        ydl_opts["download_ranges"] = download_range_func(None, [(r_start, r_end)])
        ydl_opts["force_keyframes_at_cuts"] = True

    postprocessors: list[dict[str, Any]] = []

    if format_type == "mp4":
        if quality == "best":
            fmt_selector = "bv*+ba[ext=m4a]/bv*+ba/b[ext=mp4]/b"
            ydl_opts["format_sort"] = ["res", "fps", "vcodec:h264", "acodec:m4a", "proto:https"]
        else:
            h = int(quality) if quality.isdigit() else 1080
            fmt_selector = f"bv*[height<={h}]+ba[ext=m4a]/bv*[height<={h}]+ba/b[height<={h}]/b"
            ydl_opts["format_sort"] = [f"res:{h}", "vcodec:h264", "acodec:m4a", "proto:https"]
        ydl_opts["format"] = fmt_selector
        ydl_opts["merge_output_format"] = "mp4"
        # Ensure single-stream HLS (.m3u8/.ts) or other containers are always remuxed to .mp4 BEFORE metadata!
        postprocessors.append({"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"})
        ydl_opts["postprocessor_args"] = {
            "Merger+ffmpeg_o": ["-movflags", "+faststart"],
            "VideoRemuxer+ffmpeg_o": ["-movflags", "+faststart"],
        }

    elif format_type in ("mkv", "webm"):
        if quality == "best":
            fmt_selector = "bv*+ba/b"
        else:
            h = int(quality) if quality.isdigit() else 1080
            fmt_selector = f"bv*[height<={h}]+ba/b[height<={h}]/b"
            ydl_opts["format_sort"] = [f"res:{h}", "proto:https"]
        ydl_opts["format"] = fmt_selector
        ydl_opts["merge_output_format"] = format_type
        postprocessors.append({"key": "FFmpegVideoRemuxer", "preferedformat": format_type})

    elif format_type == "mp3":
        bitrate = quality if quality in ("320", "256", "192", "128") else "320"
        ydl_opts["format"] = "ba[ext=m4a]/ba/b"
        ydl_opts["format_sort"] = ["abr", "proto:https"]
        ydl_opts["writethumbnail"] = True
        postprocessors.extend([
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": bitrate},
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg"},
            {"key": "FFmpegMetadata", "add_metadata": True},
            {"key": "EmbedThumbnail"},
        ])

    elif format_type in ("m4a", "flac", "wav"):
        ydl_opts["format"] = "ba/b"
        ydl_opts["format_sort"] = ["abr", "proto:https"]
        postprocessors.extend([
            {"key": "FFmpegExtractAudio", "preferredcodec": format_type},
            {"key": "FFmpegMetadata", "add_metadata": True},
        ])

    else:
        task_manager.update_task(
            task_id,
            status="error",
            stage="Nieobsługiwany format",
            error=f"Nieznany typ formatu: {format_type}",
        )
        return

    if not is_audio_only_target and subtitle_mode in ("embed", "srt", "burn"):
        ydl_opts["writesubtitles"] = True
        ydl_opts["writeautomaticsub"] = True
        ydl_opts["subtitleslangs"] = ["pl", "en"]
        if subtitle_mode in ("srt", "burn"):
            postprocessors.append({"key": "FFmpegSubtitlesConvertor", "format": "srt"})
        elif subtitle_mode == "embed":
            postprocessors.append({"key": "FFmpegEmbedSubtitle"})

    if not is_audio_only_target:
        postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True})

    ydl_opts["postprocessors"] = postprocessors

    task_manager.update_task(
        task_id,
        status="downloading",
        stage="Inicjalizacja pobierania z serwisu...",
        percent=1.0,
    )

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise RuntimeError("Nie otrzymano danych wyjściowych z yt-dlp.")

            if allow_playlist and info.get("_type") == "playlist":
                entries = [e for e in (info.get("entries") or []) if e]
                downloaded_paths: list[Path] = []
                for entry in entries:
                    reqs = entry.get("requested_downloads") or []
                    if reqs and reqs[0].get("filepath"):
                        p = Path(reqs[0]["filepath"])
                        if p.is_file():
                            downloaded_paths.append(p)

                if not downloaded_paths:
                    downloaded_paths = [
                        p for p in DOWNLOADS_DIR.glob(f"*.{format_type}")
                        if p.stat().st_mtime >= started_wall_time - 2
                    ]

                if not downloaded_paths:
                    raise FileNotFoundError("Nie udało się pobrać żadnej pozycji z playlisty.")

                if len(downloaded_paths) == 1:
                    final_path = downloaded_paths[0]
                else:
                    task_manager.update_task(
                        task_id,
                        status="processing",
                        stage=f"Pakowanie playlisty ({len(downloaded_paths)} plików) do archiwum ZIP...",
                        percent=98.5,
                    )
                    safe_pl_title = re.sub(r'[<>:"/\\|?*]+', "_", info.get("title") or "Playlista").strip()[:80]
                    zip_path = DOWNLOADS_DIR / f"{safe_pl_title} [{format_type.upper()}].zip"
                    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
                        for mp in downloaded_paths:
                            zf.write(mp, arcname=mp.name)
                    final_path = zip_path
            else:
                final_path = None
                req_downloads = info.get("requested_downloads") or []
                if req_downloads and req_downloads[0].get("filepath"):
                    candidate = Path(req_downloads[0]["filepath"])
                    if candidate.is_file():
                        final_path = candidate

                if not final_path:
                    prepared = Path(ydl.prepare_filename(info))
                    candidate_ext = prepared.with_suffix(f".{format_type}")
                    if candidate_ext.is_file():
                        final_path = candidate_ext
                    elif prepared.is_file():
                        final_path = prepared

                if not final_path or not final_path.is_file():
                    recent_files = sorted(
                        DOWNLOADS_DIR.glob(f"*.{format_type}"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    )
                    if recent_files and recent_files[0].stat().st_mtime >= started_wall_time - 5:
                        final_path = recent_files[0]

                if not final_path or not final_path.is_file():
                    raise FileNotFoundError("Plik wynikowy nie został odnaleziony po zakończeniu konwersji.")

                if subtitle_mode == "burn" and not is_audio_only_target:
                    srt_candidates = sorted(
                        final_path.parent.glob(f"{re.escape(final_path.stem)}*.srt"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    )
                    if srt_candidates:
                        task_manager.update_task(
                            task_id,
                            status="processing",
                            stage="Wtapianie napisów na stałe w obraz (FFmpeg)...",
                            percent=98.0,
                            speed="FFmpeg",
                        )
                        _burn_subtitles_ffmpeg(FFMPEG_DIR, final_path, srt_candidates[0])
                        srt_candidates[0].unlink(missing_ok=True)

            fsize = final_path.stat().st_size
            task_manager.update_task(
                task_id,
                title=info.get("title") or task.get("title") or final_path.stem,
                thumbnail=_pick_best_thumbnail(info) or task.get("thumbnail") or "",
                status="completed",
                stage="Gotowe! Plik został zapisany.",
                percent=100.0,
                speed="Zakończono",
                eta="00:00",
                filename=final_path.name,
                filepath=str(final_path.resolve()),
                filesize=fsize,
                filesize_str=format_bytes(fsize),
            )

    except Exception as exc:
        clean_err = strip_ansi(str(exc))
        task_manager.update_task(
            task_id,
            status="error",
            stage="Błąd pobierania lub konwersji",
            error=clean_err or "Wystąpił nieoczekiwany błąd podczas przetwarzania.",
        )
    finally:
        if tmp_cookie:
            tmp_cookie.unlink(missing_ok=True)
        shutil.rmtree(task_temp_dir, ignore_errors=True)


def list_downloaded_files() -> list[dict[str, Any]]:
    """Return downloaded media & subtitle files from downloads/ sorted newest first."""
    allowed_exts = {".mp4", ".mp3", ".mkv", ".webm", ".m4a", ".flac", ".wav", ".srt", ".zip"}
    items: list[dict[str, Any]] = []
    if not DOWNLOADS_DIR.is_dir():
        return items

    for path in DOWNLOADS_DIR.iterdir():
        if not path.is_file() or path.suffix.lower() not in allowed_exts:
            continue
        if re.search(r"\.f\d+\.[a-z0-9]+$", path.name, re.IGNORECASE):
            continue
        stat = path.stat()
        items.append({
            "filename": path.name,
            "ext": path.suffix.lstrip(".").upper(),
            "filesize": stat.st_size,
            "filesize_str": format_bytes(stat.st_size),
            "modified_at": stat.st_mtime,
        })

    items.sort(key=lambda x: x["modified_at"], reverse=True)
    return items
