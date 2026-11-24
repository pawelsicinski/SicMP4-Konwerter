from __future__ import annotations

import json
import multiprocessing
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

MAX_LOG_BYTES = 2 * 1024 * 1024


class _SafeLogStream:
    """Fallback stream when PyInstaller runs in GUI (--noconsole) mode where stdout/stderr are None."""

    def __init__(self, log_file: Path | None = None) -> None:
        self._fh = None
        if log_file is not None:
            try:
                log_file.parent.mkdir(parents=True, exist_ok=True)
                mode = "w" if (log_file.is_file() and log_file.stat().st_size > MAX_LOG_BYTES) else "a"
                self._fh = open(log_file, mode, encoding="utf-8", buffering=1)
            except Exception:
                self._fh = None

    def write(self, data: str) -> int:
        if self._fh is not None and data:
            try:
                return self._fh.write(str(data))
            except Exception:
                pass
        return len(data) if data else 0

    def flush(self) -> None:
        if self._fh is not None:
            try:
                self._fh.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        return False


def _setup_windows_environment(app_root: Path) -> None:
    log_path = app_root / "downloads" / ".tmp" / "sicmp4.log"
    if sys.stdout is None or sys.stderr is None:
        shared_stream = _SafeLogStream(log_path)
        if sys.stdout is None:
            sys.stdout = shared_stream
        if sys.stderr is None:
            sys.stderr = shared_stream

    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SicMP4.Desktop.Stable.1")
        except Exception:
            pass

        orig_popen = subprocess.Popen

        class _NoFlashPopen(orig_popen):
            def __init__(self, args, *pargs, **kwargs):
                cmd_head = ""
                if isinstance(args, (list, tuple)) and args:
                    cmd_head = str(args[0]).lower()
                elif isinstance(args, str):
                    cmd_head = args.lower()

                if "explorer" not in cmd_head and "creationflags" not in kwargs:
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                super().__init__(args, *pargs, **kwargs)

        subprocess.Popen = _NoFlashPopen  # type: ignore[assignment]


def _pick_available_port(preferred: int = 18420) -> int:
    for candidate in (preferred, 18421, 18422, 8765):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", candidate))
                return candidate
            except OSError:
                continue

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(health_url: str, timeout_sec: float = 15.0) -> dict | None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=1.0) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            time.sleep(0.05)
    return None


def _run_browser_fallback_controller(app_url: str, downloads_dir: Path) -> None:
    webbrowser.open(app_url)
    try:
        import tkinter as tk

        root = tk.Tk()
        root.title("SicMP4 - Kontroler Lokalny")
        root.geometry("420x190")
        root.resizable(False, False)
        root.configure(bg="#09090b")

        tk.Label(
            root,
            text="SicMP4 dziala lokalnie",
            font=("Segoe UI", 13, "bold"),
            fg="#fbbf24",
            bg="#09090b",
        ).pack(pady=(18, 4))

        tk.Label(
            root,
            text=f"Adres lokalny: {app_url}\nZamkniecie tego okna wylaczy program.",
            font=("Segoe UI", 9),
            fg="#d4d4d8",
            bg="#09090b",
        ).pack(pady=(0, 14))

        btn_frame = tk.Frame(root, bg="#09090b")
        btn_frame.pack(pady=4)

        tk.Button(
            btn_frame,
            text="Otworz w przegladarce",
            command=lambda: webbrowser.open(app_url),
            bg="#fbbf24",
            fg="#000000",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=6,
            relief="flat",
        ).pack(side="left", padx=6)

        tk.Button(
            btn_frame,
            text="Folder pobranych",
            command=lambda: os.startfile(str(downloads_dir)) if os.name == "nt" else None,
            bg="#27272a",
            fg="#ffffff",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=6,
            relief="flat",
        ).pack(side="left", padx=6)

        root.mainloop()
    except Exception:
        while True:
            time.sleep(1.0)


def main() -> int:
    if getattr(sys, "frozen", False):
        app_root = Path(sys.executable).resolve().parent
        bundle_root = Path(getattr(sys, "_MEIPASS", app_root)).resolve()
    else:
        app_root = Path(__file__).resolve().parent.parent
        bundle_root = app_root
        if str(app_root) not in sys.path:
            sys.path.insert(0, str(app_root))

    is_self_test = "--self-test" in sys.argv
    use_lan = "--lan" in sys.argv
    force_browser = "--browser" in sys.argv

    _setup_windows_environment(app_root)

    port = _pick_available_port(18420)
    bind_host = "0.0.0.0" if use_lan else "127.0.0.1"
    os.environ["SICMP4_PORT"] = str(port)
    os.environ["SICMP4_DESKTOP"] = "0" if use_lan else "1"

    import uvicorn
    from app.downloader import DOWNLOADS_DIR, TEMP_ROOT_DIR, extract_video_info
    from app.main import app as fastapi_app

    config = uvicorn.Config(
        fastapi_app,
        host=bind_host,
        port=port,
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, name="sicmp4-uvicorn", daemon=True)
    server_thread.start()

    app_url = f"http://127.0.0.1:{port}"
    health = _wait_for_server(f"{app_url}/api/health", timeout_sec=20.0)
    if not health:
        return 1

    if is_self_test:
        with urllib.request.urlopen(app_url, timeout=5.0) as html_resp:
            html_body = html_resp.read().decode("utf-8")

        result: dict = {
            "health": health,
            "html_len": len(html_body),
            "ffmpeg_available": bool((health.get("ffmpeg") or {}).get("available")),
            "desktop_mode": bool(health.get("desktop")),
            "has_cookies_modal": "cookiesModal" in html_body,
        }
        try:
            probe = extract_video_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            result["youtube_probe_title"] = probe.get("title")
            result["youtube_probe_heights"] = probe.get("available_heights")
        except Exception as exc:
            result["youtube_probe_error"] = str(exc)

        out_file = app_root / "downloads" / ".tmp" / "self_test_result.json"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        server.should_exit = True
        server_thread.join(timeout=2.0)
        os._exit(0)

    icon_path = bundle_root / "app" / "static" / "img" / "favicon.ico"
    webview_cache = DOWNLOADS_DIR / ".webview_cache"

    if not force_browser:
        try:
            import webview

            webview.settings["ALLOW_DOWNLOADS"] = True
            webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True

            webview.create_window(
                title="SicMP4",
                url=app_url,
                width=1440,
                height=900,
                min_size=(1024, 680),
                background_color="#000000",
                text_select=True,
                zoomable=True,
            )
            webview.start(
                private_mode=False,
                storage_path=str(webview_cache),
                icon=str(icon_path) if icon_path.is_file() else None,
            )
        except Exception:
            _run_browser_fallback_controller(app_url, DOWNLOADS_DIR)
    else:
        _run_browser_fallback_controller(app_url, DOWNLOADS_DIR)

    server.should_exit = True
    server_thread.join(timeout=1.5)

    try:
        if TEMP_ROOT_DIR.is_dir():
            for child in TEMP_ROOT_DIR.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
    except Exception:
        pass

    os._exit(0)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
