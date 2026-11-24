from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

GITHUB_OWNER = "pawelsicinski"
GITHUB_REPO = "SicMP4-Konwerter"
ASSET_FILENAME = "SicMP4-Windows-x64.zip"
APP_NAME = "SicMP4"
APP_VERSION = "1.5.0"
APP_PUBLISHER = "SicMP4 Studio"
UNINSTALL_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\SicMP4"

DIRECT_LATEST_URL = (
    f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest/download/{ASSET_FILENAME}"
)
API_LATEST_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
API_ALL_RELEASES_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"

CSIDL_PROGRAMS = 0x0002
CSIDL_DESKTOPDIRECTORY = 0x0010


def _enable_windows_dpi_and_appid(app_id: str) -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _apply_dark_titlebar(hwnd: int) -> None:
    if os.name != "nt" or not hwnd:
        return
    try:
        import ctypes
        import ctypes.wintypes

        dwmapi = ctypes.windll.dwmapi
        val = ctypes.c_int(1)
        for attr in (20, 19):
            dwmapi.DwmSetWindowAttribute(
                ctypes.wintypes.HWND(hwnd),
                ctypes.c_int(attr),
                ctypes.byref(val),
                ctypes.sizeof(val),
            )
    except Exception:
        pass


def _get_windows_shell_folder(csidl: int) -> Path:
    if os.name == "nt":
        try:
            import ctypes

            buf = ctypes.create_unicode_buffer(260)
            res = ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf)
            if res == 0 and buf.value:
                return Path(buf.value)
        except Exception:
            pass
    if csidl == CSIDL_DESKTOPDIRECTORY:
        return Path.home() / "Desktop"
    app_data = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    return app_data / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def _get_default_install_dir() -> Path:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    return local_app_data / "Programs" / "SicMP4"


def _detect_existing_install_dir() -> Path | None:
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_PATH) as key:
                loc, _ = winreg.QueryValueEx(key, "InstallLocation")
                if loc:
                    p = Path(str(loc))
                    if (p / "SicMP4.exe").is_file() or (p / "_internal").is_dir():
                        return p
        except Exception:
            pass

    default_dir = _get_default_install_dir()
    if (default_dir / "SicMP4.exe").is_file() or (default_dir / "_internal").is_dir():
        return default_dir
    return None


def _format_mb(num_bytes: float) -> str:
    return f"{num_bytes / (1024.0 * 1024.0):.1f} MB"


def _format_eta(seconds: float) -> str:
    if seconds <= 0 or seconds > 86400:
        return "--:--"
    s = int(round(seconds))
    m, sec = divmod(s, 60)
    return f"{m}:{sec:02d}"


def _resolve_github_download_url() -> tuple[str, int]:
    """Return (download_url, expected_size_bytes) from GitHub Releases."""
    headers = {
        "User-Agent": f"SicMP4-Installer/{APP_VERSION}",
        "Accept": "application/vnd.github+json",
    }

    for api_url in (API_LATEST_URL, API_ALL_RELEASES_URL):
        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                releases = data if isinstance(data, list) else [data]
                for rel in releases:
                    assets = rel.get("assets") or []
                    for asset in assets:
                        name = str(asset.get("name") or "")
                        if name.lower() == ASSET_FILENAME.lower():
                            return str(asset["browser_download_url"]), int(asset.get("size") or 0)
                    for asset in assets:
                        name = str(asset.get("name") or "")
                        if name.lower().endswith(".zip"):
                            return str(asset["browser_download_url"]), int(asset.get("size") or 0)
        except Exception:
            continue

    return DIRECT_LATEST_URL, 0


def _stop_running_sicmp4() -> None:
    if os.name != "nt":
        return
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "SicMP4.exe"],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=5,
        )
        time.sleep(0.45)
    except Exception:
        pass


def _remove_path_with_retries(target: Path, attempts: int = 6, delay: float = 0.25) -> bool:
    for i in range(attempts):
        if not target.exists():
            return True
        try:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)
            return True
        except OSError:
            if i < attempts - 1:
                time.sleep(delay)
    return not target.exists()


def _scan_user_downloads(downloads_dir: Path) -> tuple[int, int]:
    """Count user media files in downloads/ ignoring internal hidden cache folders and .gitkeep."""
    if not downloads_dir.is_dir():
        return 0, 0
    ignored_names = {".gitkeep", ".tmp", ".cookies", ".webview_cache"}
    count = 0
    total_bytes = 0
    for item in downloads_dir.iterdir():
        if item.name in ignored_names:
            continue
        try:
            if item.is_file():
                count += 1
                total_bytes += item.stat().st_size
            elif item.is_dir():
                for sub in item.rglob("*"):
                    if sub.is_file():
                        count += 1
                        total_bytes += sub.stat().st_size
        except OSError:
            pass
    return count, total_bytes


def _ps_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _create_windows_shortcuts_and_uninstaller(
    install_dir: Path,
    make_desktop: bool,
    make_start_menu: bool,
    unpacked_bytes: int,
    skip_system_integration: bool = False,
) -> None:
    if os.name != "nt":
        return

    exe_path = install_dir / "SicMP4.exe"
    uninstaller_exe = install_dir / "Uninstall-SicMP4.exe"
    legacy_bat = install_dir / "Uninstall-SicMP4.bat"
    legacy_bat.unlink(missing_ok=True)

    if getattr(sys, "frozen", False):
        src_exe = Path(sys.executable).resolve()
        try:
            if src_exe != uninstaller_exe.resolve():
                shutil.copy2(src_exe, uninstaller_exe)
        except Exception:
            pass

    if skip_system_integration:
        return

    desktop_dir = _get_windows_shell_folder(CSIDL_DESKTOPDIRECTORY)
    programs_dir = _get_windows_shell_folder(CSIDL_PROGRAMS)
    sm_folder = programs_dir / "SicMP4"

    ps_lines = ["$ws = New-Object -ComObject WScript.Shell"]
    if make_desktop:
        desktop_lnk = desktop_dir / "SicMP4.lnk"
        ps_lines.extend([
            f"$s1 = $ws.CreateShortcut({_ps_quote(desktop_lnk)})",
            f"$s1.TargetPath = {_ps_quote(exe_path)}",
            f"$s1.WorkingDirectory = {_ps_quote(install_dir)}",
            f"$s1.IconLocation = {_ps_quote(f'{exe_path},0')}",
            "$s1.Description = 'SicMP4 - Video & Audio Downloader'",
            "$s1.Save()",
        ])

    if make_start_menu:
        sm_folder.mkdir(parents=True, exist_ok=True)
        sm_app_lnk = sm_folder / "SicMP4.lnk"
        ps_lines.extend([
            f"$s2 = $ws.CreateShortcut({_ps_quote(sm_app_lnk)})",
            f"$s2.TargetPath = {_ps_quote(exe_path)}",
            f"$s2.WorkingDirectory = {_ps_quote(install_dir)}",
            f"$s2.IconLocation = {_ps_quote(f'{exe_path},0')}",
            "$s2.Description = 'SicMP4 - Video & Audio Downloader'",
            "$s2.Save()",
        ])
        if uninstaller_exe.is_file():
            sm_uninst_lnk = sm_folder / "Odinstaluj SicMP4.lnk"
            ps_lines.extend([
                f"$s3 = $ws.CreateShortcut({_ps_quote(sm_uninst_lnk)})",
                f"$s3.TargetPath = {_ps_quote(uninstaller_exe)}",
                "$s3.Arguments = '--uninstall'",
                f"$s3.WorkingDirectory = {_ps_quote(install_dir)}",
                f"$s3.IconLocation = {_ps_quote(f'{uninstaller_exe},0')}",
                "$s3.Description = 'Odinstaluj program SicMP4'",
                "$s3.Save()",
            ])
        (programs_dir / "SicMP4.lnk").unlink(missing_ok=True)

    if len(ps_lines) > 1:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "; ".join(ps_lines)],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=15,
        )

    uninstall_target = uninstaller_exe if uninstaller_exe.is_file() else exe_path
    try:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_PATH) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, APP_PUBLISHER)
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, f"{exe_path},0")
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(install_dir))
            winreg.SetValueEx(
                key,
                "UninstallString",
                0,
                winreg.REG_SZ,
                f'"{uninstall_target}" --uninstall',
            )
            winreg.SetValueEx(
                key,
                "QuietUninstallString",
                0,
                winreg.REG_SZ,
                f'"{uninstall_target}" --uninstall --silent',
            )
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
            size_kb = max(1024, int(unpacked_bytes // 1024))
            winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
    except Exception:
        pass


def _remove_windows_shortcuts_and_registry() -> None:
    if os.name != "nt":
        return

    desktop_dir = _get_windows_shell_folder(CSIDL_DESKTOPDIRECTORY)
    programs_dir = _get_windows_shell_folder(CSIDL_PROGRAMS)

    (desktop_dir / "SicMP4.lnk").unlink(missing_ok=True)
    (programs_dir / "SicMP4.lnk").unlink(missing_ok=True)

    sm_folder = programs_dir / "SicMP4"
    if sm_folder.is_dir():
        (sm_folder / "SicMP4.lnk").unlink(missing_ok=True)
        (sm_folder / "Odinstaluj SicMP4.lnk").unlink(missing_ok=True)
        try:
            if not any(sm_folder.iterdir()):
                sm_folder.rmdir()
        except OSError:
            pass

    try:
        import winreg

        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_PATH)
    except FileNotFoundError:
        pass
    except Exception:
        pass


def _draw_eclipse_header(
    root: tk.Tk,
    bg_main: str,
    orange: str,
    amber: str,
    subtitle_tag: str,
    description: str,
) -> None:
    header = tk.Frame(root, bg=bg_main)
    header.pack(fill="x", padx=32, pady=(24, 14))

    logo_cv = tk.Canvas(header, width=68, height=68, bg=bg_main, highlightthickness=0)
    logo_cv.pack(side="left")
    logo_cv.create_oval(3, 3, 65, 65, outline="#7c2d12", width=2)
    logo_cv.create_oval(6, 6, 62, 62, outline=orange, width=2, fill="#000000")
    logo_cv.create_oval(16, 14, 54, 54, fill=amber, outline="")
    logo_cv.create_oval(11, 12, 47, 52, fill="#000000", outline="")

    title_box = tk.Frame(header, bg=bg_main)
    title_box.pack(side="left", padx=(16, 0))

    tk.Label(
        title_box,
        text="SicMP4",
        font=("Segoe UI", 20, "bold"),
        fg="#ffffff",
        bg=bg_main,
        anchor="w",
    ).pack(anchor="w")

    tk.Label(
        title_box,
        text=subtitle_tag,
        font=("Consolas", 8, "bold"),
        fg=amber,
        bg=bg_main,
        anchor="w",
    ).pack(anchor="w", pady=(1, 0))

    tk.Label(
        title_box,
        text=description,
        font=("Segoe UI", 9),
        fg="#a1a1aa",
        bg=bg_main,
        anchor="w",
    ).pack(anchor="w", pady=(3, 0))


def _configure_tk_window(root: tk.Tk, title: str, width: int, height: int, bg_main: str) -> None:
    root.title(title)
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = max(0, (sw - width) // 2)
    y = max(0, (sh - height) // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")
    root.resizable(False, False)
    root.configure(bg=bg_main)

    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    ico_candidate = bundle_dir / "sicmp4.ico"
    if ico_candidate.is_file():
        try:
            root.iconbitmap(default=str(ico_candidate))
        except Exception:
            pass

    root.update_idletasks()
    try:
        import ctypes

        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
        _apply_dark_titlebar(hwnd)
    except Exception:
        pass


class SolarEclipseUninstallerApp:
    BG_MAIN = "#060608"
    BG_CARD = "#101014"
    BORDER = "#242429"
    TEXT_WHITE = "#ffffff"
    TEXT_MUTED = "#a1a1aa"
    TEXT_DIM = "#71717a"
    AMBER = "#fbbf24"
    ORANGE = "#f97316"
    DANGER = "#ef4444"

    def __init__(
        self,
        root: tk.Tk,
        target_dir: Path,
        silent: bool = False,
        delete_downloads_default: bool = False,
        skip_system_integration: bool = False,
    ) -> None:
        self.root = root
        self.target_dir = target_dir
        self.silent = silent
        self.skip_system_integration = skip_system_integration
        self.uninstalling = False
        self.finished = False
        self.delete_downloads_var = tk.BooleanVar(value=delete_downloads_default)

        self.user_file_count, self.user_file_bytes = _scan_user_downloads(self.target_dir / "downloads")

        _configure_tk_window(self.root, "Dezinstalator SicMP4", 600, 440, self.BG_MAIN)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()

        if self.silent:
            self.root.after(150, self.start_uninstall)

    def _build_ui(self) -> None:
        _draw_eclipse_header(
            self.root,
            self.BG_MAIN,
            self.ORANGE,
            self.AMBER,
            f"SOLAR ECLIPSE EDITION v{APP_VERSION}  //  USUWANIE PROGRAMU Z SYSTEMU WINDOWS",
            "Bezpieczne usuwanie aplikacji SicMP4, skrótów oraz wpisu w systemie Windows.",
        )

        self.card = tk.Frame(
            self.root,
            bg=self.BG_CARD,
            highlightbackground=self.BORDER,
            highlightthickness=1,
            padx=24,
            pady=20,
        )
        self.card.pack(fill="both", expand=True, padx=32, pady=(0, 18))

        self.confirm_frame = tk.Frame(self.card, bg=self.BG_CARD)
        self.confirm_frame.pack(fill="both", expand=True)

        tk.Label(
            self.confirm_frame,
            text="FOLDER DOCELOWY DO ODINSTALOWANIA",
            font=("Consolas", 8, "bold"),
            fg=self.TEXT_MUTED,
            bg=self.BG_CARD,
        ).pack(anchor="w")

        path_box = tk.Frame(
            self.confirm_frame,
            bg="#08080b",
            highlightbackground="#2e2e36",
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        path_box.pack(fill="x", pady=(6, 14))

        tk.Label(
            path_box,
            text=str(self.target_dir),
            font=("Consolas", 9),
            fg=self.TEXT_WHITE,
            bg="#08080b",
            anchor="w",
        ).pack(fill="x")

        if self.user_file_count > 0:
            dl_info = (
                f"Wykryto zapisane multimedia użytkownika w downloads/: "
                f"{self.user_file_count} szt. ({_format_mb(self.user_file_bytes)})"
            )
            dl_fg = self.AMBER
        else:
            dl_info = "Folder downloads/ nie zawiera pobranych plików użytkownika."
            dl_fg = self.TEXT_MUTED

        tk.Label(
            self.confirm_frame,
            text=dl_info,
            font=("Segoe UI", 9),
            fg=dl_fg,
            bg=self.BG_CARD,
            anchor="w",
        ).pack(anchor="w", pady=(0, 10))

        cb_text = (
            f"Usuń również pobrane filmy i muzykę z folderu downloads ({self.user_file_count} szt., {_format_mb(self.user_file_bytes)})"
            if self.user_file_count > 0
            else "Usuń również pusty folder downloads/"
        )
        tk.Checkbutton(
            self.confirm_frame,
            text=cb_text,
            variable=self.delete_downloads_var,
            font=("Segoe UI", 9),
            bg=self.BG_CARD,
            fg=self.TEXT_WHITE,
            selectcolor="#070709",
            activebackground=self.BG_CARD,
            activeforeground=self.AMBER,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        ).pack(anchor="w", pady=(0, 12))

        tk.Label(
            self.confirm_frame,
            text="Usunięte zostaną: SicMP4.exe, silnik FFmpeg, biblioteki _internal, skróty Pulpit / Menu Start\noraz wpis SicMP4 w ustawieniach Zainstalowane aplikacje.",
            font=("Segoe UI", 8),
            fg=self.TEXT_DIM,
            bg=self.BG_CARD,
            justify="left",
            anchor="w",
        ).pack(anchor="w")

        self.progress_frame = tk.Frame(self.card, bg=self.BG_CARD)

        top_row = tk.Frame(self.progress_frame, bg=self.BG_CARD)
        top_row.pack(fill="x", pady=(6, 8))

        self.stage_label = tk.Label(
            top_row,
            text="Przygotowywanie dezinstalacji...",
            font=("Segoe UI", 10, "bold"),
            fg=self.TEXT_WHITE,
            bg=self.BG_CARD,
            anchor="w",
        )
        self.stage_label.pack(side="left")

        self.percent_label = tk.Label(
            top_row,
            text="0.0%",
            font=("Consolas", 11, "bold"),
            fg=self.AMBER,
            bg=self.BG_CARD,
            anchor="e",
        )
        self.percent_label.pack(side="right")

        self.bar_canvas = tk.Canvas(
            self.progress_frame,
            height=14,
            bg="#050507",
            highlightbackground="#2c2c34",
            highlightthickness=1,
        )
        self.bar_canvas.pack(fill="x", pady=(0, 10))
        self.bar_fill_rect = self.bar_canvas.create_rectangle(0, 0, 0, 16, fill=self.AMBER, width=0)

        self.telemetry_label = tk.Label(
            self.progress_frame,
            text=str(self.target_dir),
            font=("Consolas", 9),
            fg=self.TEXT_MUTED,
            bg=self.BG_CARD,
            anchor="w",
        )
        self.telemetry_label.pack(fill="x", pady=(2, 10))

        self.sub_note_label = tk.Label(
            self.progress_frame,
            text="Trwa usuwanie plików aplikacji SicMP4...",
            font=("Segoe UI", 8),
            fg=self.TEXT_DIM,
            bg=self.BG_CARD,
            justify="left",
            anchor="w",
        )
        self.sub_note_label.pack(fill="x", pady=(6, 0))

        footer = tk.Frame(self.root, bg=self.BG_MAIN)
        footer.pack(fill="x", padx=32, pady=(0, 22))

        self.cancel_btn = tk.Button(
            footer,
            text="Anuluj",
            command=self._on_close,
            font=("Segoe UI", 9, "bold"),
            bg="#18181d",
            fg=self.TEXT_MUTED,
            activebackground="#27272f",
            activeforeground=self.TEXT_WHITE,
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
        )
        self.cancel_btn.pack(side="left")

        self.uninstall_btn = tk.Button(
            footer,
            text="Odinstaluj SicMP4",
            command=self.start_uninstall,
            font=("Segoe UI", 10, "bold"),
            bg=self.DANGER,
            fg="#ffffff",
            activebackground="#fca5a5",
            activeforeground="#000000",
            relief="flat",
            padx=24,
            pady=8,
            cursor="hand2",
        )
        self.uninstall_btn.pack(side="right")

    def _update_progress_ui(self, stage: str, percent: float, telemetry: str) -> None:
        pct = max(0.0, min(100.0, percent))

        def _apply() -> None:
            self.stage_label.config(text=stage)
            self.percent_label.config(text=f"{pct:.1f}%")
            self.telemetry_label.config(text=telemetry)
            total_w = max(1, self.bar_canvas.winfo_width())
            fill_w = int(round((pct / 100.0) * total_w))
            self.bar_canvas.coords(self.bar_fill_rect, 0, 0, fill_w, 16)

        self.root.after(0, _apply)

    def start_uninstall(self) -> None:
        if self.uninstalling:
            return
        if self.finished:
            self.root.destroy()
            return

        self.uninstalling = True
        self.confirm_frame.pack_forget()
        self.progress_frame.pack(fill="both", expand=True)
        self.cancel_btn.config(state="disabled")
        self.uninstall_btn.config(state="disabled", text="Usuwanie...", bg="#3f3f46", fg="#a1a1aa")

        threading.Thread(target=self._uninstall_worker, daemon=True).start()

    def _uninstall_worker(self) -> None:
        try:
            self._update_progress_ui("Zatrzymywanie procesów SicMP4...", 10.0, "Zamykanie aktywnych instancji")
            _stop_running_sicmp4()

            target = self.target_dir
            delete_downloads = bool(self.delete_downloads_var.get())
            downloads_dir = target / "downloads"
            preserved_user_files = False

            if target.is_dir():
                app_items = [
                    target / "SicMP4.exe",
                    target / "Uninstall-SicMP4.exe",
                    target / "Uninstall-SicMP4.bat",
                    target / "SicMP4-Przegladarka.bat",
                    target / "INSTRUKCJA.txt",
                    target / "_internal",
                    target / "bin",
                ]
                total_steps = len(app_items) + 3
                for idx, item in enumerate(app_items, start=1):
                    pct = 15.0 + (idx / total_steps) * 55.0
                    self._update_progress_ui("Usuwanie plików aplikacji...", pct, item.name)
                    _remove_path_with_retries(item)

                if downloads_dir.is_dir():
                    self._update_progress_ui("Czyszczenie katalogu roboczego...", 75.0, "downloads/.tmp, cache")
                    for hidden_name in (".tmp", ".cookies", ".webview_cache", ".gitkeep"):
                        _remove_path_with_retries(downloads_dir / hidden_name)

                    rem_count, _ = _scan_user_downloads(downloads_dir)
                    if delete_downloads or rem_count == 0:
                        _remove_path_with_retries(downloads_dir)
                    else:
                        preserved_user_files = True

                if not preserved_user_files:
                    try:
                        if target.is_dir():
                            remaining = list(target.iterdir())
                            if not remaining or delete_downloads:
                                _remove_path_with_retries(target)
                    except OSError:
                        pass

            if not self.skip_system_integration:
                self._update_progress_ui(
                    "Usuwanie skrótów i wpisu w systemie Windows...",
                    90.0,
                    "Pulpit, Menu Start, Rejestr Zainstalowanych Aplikacji",
                )
                _remove_windows_shortcuts_and_registry()

            self._update_progress_ui(
                "Program SicMP4 został pomyślnie odinstalowany!",
                100.0,
                f"Zachowano pobrane pliki w: {downloads_dir}" if preserved_user_files else "Wszystkie pliki programu zostały usunięte",
            )
            self.root.after(0, lambda: self._on_success(preserved_user_files, downloads_dir))
        except Exception as exc:
            err_msg = str(exc)
            self.root.after(0, lambda: self._on_error(err_msg))

    def _on_success(self, preserved_user_files: bool, downloads_dir: Path) -> None:
        self.uninstalling = False
        self.finished = True
        if preserved_user_files:
            self.sub_note_label.config(
                text=f"SicMP4 został usunięty. Twoje pobrane multimedia zachowano bezpiecznie w:\n{downloads_dir}",
                fg="#34d399",
            )
        else:
            self.sub_note_label.config(
                text="Program SicMP4 oraz wszystkie powiązane skróty zostały całkowicie usunięte z komputera.",
                fg="#34d399",
            )
        self.uninstall_btn.config(
            state="normal",
            text="Zakończ",
            bg=self.AMBER,
            fg="#000000",
        )
        if self.silent:
            self.root.after(250, self.root.destroy)

    def _on_error(self, message: str) -> None:
        self.uninstalling = False
        self.progress_frame.pack_forget()
        self.confirm_frame.pack(fill="both", expand=True)
        self.cancel_btn.config(state="normal")
        self.uninstall_btn.config(
            state="normal",
            text="Ponów odinstalowanie",
            bg=self.DANGER,
            fg="#ffffff",
        )
        if not self.silent:
            messagebox.showerror("Błąd dezinstalacji SicMP4", message)
        else:
            if sys.stderr is not None:
                sys.stderr.write(f"UNINSTALL_ERROR: {message}\n")
            self.root.destroy()

    def _on_close(self) -> None:
        if self.uninstalling:
            return
        self.root.destroy()


class SolarEclipseInstallerApp:
    BG_MAIN = "#060608"
    BG_CARD = "#101014"
    BORDER = "#242429"
    TEXT_WHITE = "#ffffff"
    TEXT_MUTED = "#a1a1aa"
    TEXT_DIM = "#71717a"
    AMBER = "#fbbf24"
    ORANGE = "#f97316"

    def __init__(
        self,
        root: tk.Tk,
        auto_local_zip: Path | None = None,
        silent_test: bool = False,
        custom_install_dir: str = "",
        skip_system_integration: bool = False,
    ) -> None:
        self.root = root
        self.auto_local_zip = auto_local_zip
        self.silent_test = silent_test
        self.skip_system_integration = skip_system_integration
        self.cancelled = False
        self.installing = False
        self.finished = False

        self.existing_dir = None if custom_install_dir else _detect_existing_install_dir()
        initial_dir = custom_install_dir or (str(self.existing_dir) if self.existing_dir else str(_get_default_install_dir()))

        self.install_dir_var = tk.StringVar(value=initial_dir)
        self.desktop_shortcut_var = tk.BooleanVar(value=True)
        self.startmenu_shortcut_var = tk.BooleanVar(value=True)
        self.launch_after_var = tk.BooleanVar(value=not silent_test)

        _configure_tk_window(self.root, f"Instalator SicMP4 v{APP_VERSION}", 600, 485, self.BG_MAIN)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()

        if self.silent_test:
            self.root.after(200, self.start_installation)

    def _build_ui(self) -> None:
        _draw_eclipse_header(
            self.root,
            self.BG_MAIN,
            self.ORANGE,
            self.AMBER,
            f"SOLAR ECLIPSE EDITION v{APP_VERSION}  //  INSTALATOR WINDOWS X64",
            "Lokalny downloader 4K Ultra HD oraz audio Hi-Fi (FFmpeg + yt-dlp) bez cookies.",
        )

        self.card = tk.Frame(
            self.root,
            bg=self.BG_CARD,
            highlightbackground=self.BORDER,
            highlightthickness=1,
            padx=24,
            pady=20,
        )
        self.card.pack(fill="both", expand=True, padx=32, pady=(0, 18))

        self.config_frame = tk.Frame(self.card, bg=self.BG_CARD)
        self.config_frame.pack(fill="both", expand=True)

        if self.existing_dir:
            tk.Label(
                self.config_frame,
                text="Wykryto zainstalowaną wersję SicMP4 (możesz zaktualizować lub odinstalować)",
                font=("Segoe UI", 8, "bold"),
                fg="#34d399",
                bg=self.BG_CARD,
                anchor="w",
            ).pack(anchor="w", pady=(0, 8))

        tk.Label(
            self.config_frame,
            text="FOLDER DOCELOWY INSTALACJI",
            font=("Consolas", 8, "bold"),
            fg=self.TEXT_MUTED,
            bg=self.BG_CARD,
        ).pack(anchor="w")

        dir_row = tk.Frame(self.config_frame, bg=self.BG_CARD)
        dir_row.pack(fill="x", pady=(6, 14))

        self.dir_entry = tk.Entry(
            dir_row,
            textvariable=self.install_dir_var,
            font=("Consolas", 9),
            bg="#08080b",
            fg=self.TEXT_WHITE,
            insertbackground=self.AMBER,
            relief="flat",
            highlightbackground="#2e2e36",
            highlightcolor=self.AMBER,
            highlightthickness=1,
        )
        self.dir_entry.pack(side="left", fill="x", expand=True, ipady=7, ipadx=8)

        tk.Button(
            dir_row,
            text="Zmień...",
            command=self._choose_directory,
            font=("Segoe UI", 9, "bold"),
            bg="#1f1f26",
            fg=self.TEXT_WHITE,
            activebackground="#32323d",
            activeforeground=self.TEXT_WHITE,
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        self._make_checkbox(
            self.config_frame,
            "Utwórz skrót SicMP4 na Pulpicie",
            self.desktop_shortcut_var,
        )
        self._make_checkbox(
            self.config_frame,
            "Dodaj skróty SicMP4 i Odinstaluj do Menu Start Windows",
            self.startmenu_shortcut_var,
        )
        self._make_checkbox(
            self.config_frame,
            "Uruchom program SicMP4 od razu po instalacji",
            self.launch_after_var,
        )

        self.progress_frame = tk.Frame(self.card, bg=self.BG_CARD)

        top_status_row = tk.Frame(self.progress_frame, bg=self.BG_CARD)
        top_status_row.pack(fill="x", pady=(6, 8))

        self.stage_label = tk.Label(
            top_status_row,
            text="Inicjalizacja instalatora...",
            font=("Segoe UI", 10, "bold"),
            fg=self.TEXT_WHITE,
            bg=self.BG_CARD,
            anchor="w",
        )
        self.stage_label.pack(side="left")

        self.percent_label = tk.Label(
            top_status_row,
            text="0.0%",
            font=("Consolas", 11, "bold"),
            fg=self.AMBER,
            bg=self.BG_CARD,
            anchor="e",
        )
        self.percent_label.pack(side="right")

        self.bar_canvas = tk.Canvas(
            self.progress_frame,
            height=14,
            bg="#050507",
            highlightbackground="#2c2c34",
            highlightthickness=1,
        )
        self.bar_canvas.pack(fill="x", pady=(0, 10))
        self.bar_fill_rect = self.bar_canvas.create_rectangle(0, 0, 0, 16, fill=self.AMBER, width=0)

        self.telemetry_label = tk.Label(
            self.progress_frame,
            text="Przygotowywanie połączenia z serwerem wydań...",
            font=("Consolas", 9),
            fg=self.TEXT_MUTED,
            bg=self.BG_CARD,
            anchor="w",
        )
        self.telemetry_label.pack(fill="x", pady=(2, 12))

        self.sub_note_label = tk.Label(
            self.progress_frame,
            text="Pakiet zawiera silnik FFmpeg, ffprobe, dezinstalator oraz wszystkie moduły lokalne.\nNie zamykaj okna do zakończenia procesu.",
            font=("Segoe UI", 8),
            fg=self.TEXT_DIM,
            bg=self.BG_CARD,
            justify="left",
            anchor="w",
        )
        self.sub_note_label.pack(fill="x", pady=(6, 0))

        footer = tk.Frame(self.root, bg=self.BG_MAIN)
        footer.pack(fill="x", padx=32, pady=(0, 24))

        self.cancel_btn = tk.Button(
            footer,
            text="Anuluj",
            command=self._on_close,
            font=("Segoe UI", 9, "bold"),
            bg="#18181d",
            fg=self.TEXT_MUTED,
            activebackground="#27272f",
            activeforeground=self.TEXT_WHITE,
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
        )
        self.cancel_btn.pack(side="left")

        if self.existing_dir:
            self.switch_uninstall_btn = tk.Button(
                footer,
                text="Odinstaluj...",
                command=self._switch_to_uninstaller,
                font=("Segoe UI", 9, "bold"),
                bg="#271417",
                fg="#fca5a5",
                activebackground="#ef4444",
                activeforeground="#ffffff",
                relief="flat",
                padx=16,
                pady=8,
                cursor="hand2",
            )
            self.switch_uninstall_btn.pack(side="left", padx=(10, 0))
        else:
            self.switch_uninstall_btn = None

        self.install_btn = tk.Button(
            footer,
            text="Zaktualizuj SicMP4" if self.existing_dir else "Zainstaluj SicMP4",
            command=self.start_installation,
            font=("Segoe UI", 10, "bold"),
            bg=self.AMBER,
            fg="#000000",
            activebackground=self.TEXT_WHITE,
            activeforeground="#000000",
            relief="flat",
            padx=26,
            pady=8,
            cursor="hand2",
        )
        self.install_btn.pack(side="right")

    def _switch_to_uninstaller(self) -> None:
        if self.installing or not self.existing_dir:
            return
        target = self.existing_dir
        for child in self.root.winfo_children():
            child.destroy()
        SolarEclipseUninstallerApp(
            self.root,
            target_dir=target,
            silent=False,
            skip_system_integration=self.skip_system_integration,
        )

    def _make_checkbox(self, parent: tk.Widget, text: str, var: tk.BooleanVar) -> None:
        cb = tk.Checkbutton(
            parent,
            text=text,
            variable=var,
            font=("Segoe UI", 9),
            bg=self.BG_CARD,
            fg=self.TEXT_WHITE,
            selectcolor="#070709",
            activebackground=self.BG_CARD,
            activeforeground=self.AMBER,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        cb.pack(anchor="w", pady=3)

    def _choose_directory(self) -> None:
        chosen = filedialog.askdirectory(
            initialdir=self.install_dir_var.get(),
            title="Wybierz folder instalacji SicMP4",
        )
        if chosen:
            chosen_path = Path(chosen)
            if chosen_path.name.lower() != "sicmp4":
                chosen_path = chosen_path / "SicMP4"
            self.install_dir_var.set(str(chosen_path))

    def _update_progress_ui(self, stage: str, percent: float, telemetry: str) -> None:
        pct = max(0.0, min(100.0, percent))

        def _apply() -> None:
            self.stage_label.config(text=stage)
            self.percent_label.config(text=f"{pct:.1f}%")
            self.telemetry_label.config(text=telemetry)
            total_w = max(1, self.bar_canvas.winfo_width())
            fill_w = int(round((pct / 100.0) * total_w))
            self.bar_canvas.coords(self.bar_fill_rect, 0, 0, fill_w, 16)

        self.root.after(0, _apply)

    def start_installation(self) -> None:
        if self.installing:
            return
        if self.finished:
            self._finish_and_exit()
            return

        install_dir = Path(self.install_dir_var.get().strip())
        if not str(install_dir):
            messagebox.showerror("Błąd ścieżki", "Wybierz prawidłowy folder instalacji.")
            return

        self.installing = True
        self.config_frame.pack_forget()
        self.progress_frame.pack(fill="both", expand=True)
        if self.switch_uninstall_btn:
            self.switch_uninstall_btn.config(state="disabled")
        self.install_btn.config(state="disabled", text="Instalowanie...", bg="#3f3f46", fg="#a1a1aa")

        threading.Thread(
            target=self._installation_worker,
            args=(install_dir,),
            daemon=True,
        ).start()

    def _installation_worker(self, install_dir: Path) -> None:
        tmp_zip_path: Path | None = None
        delete_tmp_zip = False

        try:
            if self.auto_local_zip and self.auto_local_zip.is_file():
                tmp_zip_path = self.auto_local_zip
                self._update_progress_ui(
                    "Weryfikacja lokalnego pakietu instalacyjnego...",
                    15.0,
                    f"Pakiet: {tmp_zip_path.name} ({_format_mb(tmp_zip_path.stat().st_size)})",
                )
                time.sleep(0.2)
            else:
                self._update_progress_ui(
                    "Łączenie z GitHub Releases...",
                    1.0,
                    f"Repozytorium: {GITHUB_OWNER}/{GITHUB_REPO}",
                )
                download_url, api_size = _resolve_github_download_url()

                fd, raw_tmp = tempfile.mkstemp(prefix="sicmp4_pkg_", suffix=".zip")
                os.close(fd)
                tmp_zip_path = Path(raw_tmp)
                delete_tmp_zip = True

                req = urllib.request.Request(
                    download_url,
                    headers={"User-Agent": f"SicMP4-Installer/{APP_VERSION}"},
                )
                try:
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        total_bytes = int(resp.headers.get("Content-Length") or api_size or 0)
                        downloaded = 0
                        start_t = time.monotonic()
                        last_ui_t = 0.0
                        chunk_size = 256 * 1024

                        with open(tmp_zip_path, "wb") as out_f:
                            while True:
                                if self.cancelled:
                                    return
                                chunk = resp.read(chunk_size)
                                if not chunk:
                                    break
                                out_f.write(chunk)
                                downloaded += len(chunk)

                                now = time.monotonic()
                                if now - last_ui_t >= 0.06:
                                    last_ui_t = now
                                    elapsed = max(0.001, now - start_t)
                                    speed_bps = downloaded / elapsed
                                    speed_str = f"{speed_bps / (1024 * 1024):.1f} MB/s"
                                    if total_bytes > 0:
                                        dl_pct = min(72.0, (downloaded / total_bytes) * 72.0)
                                        rem_sec = (total_bytes - downloaded) / max(1.0, speed_bps)
                                        telem = (
                                            f"Pobrano: {_format_mb(downloaded)} / {_format_mb(total_bytes)}"
                                            f"  |  {speed_str}  |  ETA: {_format_eta(rem_sec)}"
                                        )
                                    else:
                                        dl_pct = 35.0
                                        telem = f"Pobrano: {_format_mb(downloaded)}  |  {speed_str}"
                                    self._update_progress_ui("Pobieranie programu SicMP4...", dl_pct, telem)
                except (urllib.error.HTTPError, urllib.error.URLError) as net_err:
                    exe_dir = (
                        Path(sys.executable).resolve().parent
                        if getattr(sys, "frozen", False)
                        else Path(__file__).resolve().parent
                    )
                    sibling_zip = exe_dir / ASSET_FILENAME
                    if sibling_zip.is_file():
                        if tmp_zip_path and delete_tmp_zip:
                            tmp_zip_path.unlink(missing_ok=True)
                        tmp_zip_path = sibling_zip
                        delete_tmp_zip = False
                        self._update_progress_ui(
                            "Wykryto lokalny pakiet obok instalatora...",
                            70.0,
                            f"Użycie pliku: {sibling_zip.name}",
                        )
                    elif isinstance(net_err, urllib.error.HTTPError) and net_err.code == 404:
                        raise RuntimeError(
                            f"Nie znaleziono paczki {ASSET_FILENAME} w zakładce Releases repozytorium "
                            f"github.com/{GITHUB_OWNER}/{GITHUB_REPO}.\n\n"
                            "Upewnij się, że repozytorium jest ustawione jako Public (publiczne) "
                            f"oraz że opublikowano Release z plikiem {ASSET_FILENAME}."
                        ) from net_err
                    else:
                        raise RuntimeError(f"Błąd połączenia z serwerem pobierania: {net_err}") from net_err

            if self.cancelled or not tmp_zip_path:
                return

            self._update_progress_ui(
                "Przygotowywanie katalogu docelowego...",
                73.0,
                str(install_dir),
            )
            _stop_running_sicmp4()
            install_dir.mkdir(parents=True, exist_ok=True)
            (install_dir / "downloads").mkdir(parents=True, exist_ok=True)

            unpacked_bytes = 0
            with zipfile.ZipFile(tmp_zip_path, "r") as zf:
                members = [m for m in zf.infolist() if not m.is_dir()]
                total_unpacked = sum(max(1, m.file_size) for m in members)
                last_ui_t = 0.0

                for m in members:
                    if self.cancelled:
                        return
                    rel_parts = Path(m.filename).parts
                    if not rel_parts or ".." in rel_parts:
                        continue
                    if rel_parts[-1] == ".keep":
                        continue

                    target_file = install_dir.joinpath(*rel_parts)
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(m, "r") as src_s, open(target_file, "wb") as dst_s:
                        while True:
                            buf = src_s.read(512 * 1024)
                            if not buf:
                                break
                            dst_s.write(buf)
                            unpacked_bytes += len(buf)
                            now = time.monotonic()
                            if now - last_ui_t >= 0.06:
                                last_ui_t = now
                                ext_ratio = min(1.0, unpacked_bytes / max(1, total_unpacked))
                                pct = 74.0 + ext_ratio * 22.0
                                self._update_progress_ui(
                                    "Rozpakowywanie plików oraz silnika FFmpeg...",
                                    pct,
                                    f"Wypakowano: {_format_mb(unpacked_bytes)} / {_format_mb(total_unpacked)}",
                                )

            self._update_progress_ui(
                "Konfigurowanie skrótów i dezinstalatora...",
                97.5,
                "Tworzenie skrótów oraz wpisu w Zainstalowane aplikacje",
            )
            _create_windows_shortcuts_and_uninstaller(
                install_dir=install_dir,
                make_desktop=bool(self.desktop_shortcut_var.get()),
                make_start_menu=bool(self.startmenu_shortcut_var.get()),
                unpacked_bytes=unpacked_bytes,
                skip_system_integration=self.skip_system_integration,
            )

            self._update_progress_ui(
                "Instalacja zakończona pomyślnie!",
                100.0,
                f"Zainstalowano w: {install_dir}",
            )
            self.root.after(0, lambda: self._on_install_success(install_dir))

        except Exception as exc:
            err_text = str(exc)
            self.root.after(0, lambda: self._on_install_error(err_text))
        finally:
            if delete_tmp_zip and tmp_zip_path:
                try:
                    tmp_zip_path.unlink(missing_ok=True)
                except Exception:
                    pass

    def _on_install_success(self, install_dir: Path) -> None:
        self.installing = False
        self.finished = True
        self.installed_exe = install_dir / "SicMP4.exe"
        self.sub_note_label.config(
            text="SicMP4 jest gotowy do pracy. Pobieranie 4K oraz MP3 działa lokalnie bez plików cookies.",
            fg="#34d399",
        )
        self.cancel_btn.config(state="disabled")
        self.install_btn.config(
            state="normal",
            text="Uruchom i zamknij" if self.launch_after_var.get() else "Zakończ",
            bg=self.AMBER,
            fg="#000000",
        )

        if self.silent_test:
            self.root.after(250, self.root.destroy)
        elif self.launch_after_var.get():
            self.root.after(650, self._finish_and_exit)

    def _on_install_error(self, message: str) -> None:
        self.installing = False
        self.progress_frame.pack_forget()
        self.config_frame.pack(fill="both", expand=True)
        if self.switch_uninstall_btn:
            self.switch_uninstall_btn.config(state="normal")
        self.install_btn.config(
            state="normal",
            text="Ponów instalację",
            bg=self.AMBER,
            fg="#000000",
        )
        if not self.silent_test:
            messagebox.showerror("Błąd instalacji SicMP4", message)
        else:
            if sys.stderr is not None:
                sys.stderr.write(f"INSTALL_ERROR: {message}\n")
            self.root.destroy()

    def _finish_and_exit(self) -> None:
        if getattr(self, "installed_exe", None) and self.installed_exe.is_file() and self.launch_after_var.get():
            try:
                subprocess.Popen(
                    [str(self.installed_exe)],
                    cwd=str(self.installed_exe.parent),
                )
            except Exception:
                pass
        self.root.destroy()

    def _on_close(self) -> None:
        if self.installing:
            if not messagebox.askyesno(
                "Przerwać instalację?",
                "Czy na pewno chcesz przerwać pobieranie i instalację SicMP4?",
            ):
                return
            self.cancelled = True
        self.root.destroy()


def _get_cli_arg_value(flag: str) -> str:
    if flag in sys.argv:
        idx = sys.argv.index(flag)
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return ""


def _resolve_uninstall_target_dir(explicit_target: str) -> Path:
    if explicit_target:
        return Path(explicit_target).resolve()

    exe_dir = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    if (exe_dir / "SicMP4.exe").is_file() or (exe_dir / "_internal").is_dir():
        return exe_dir

    detected = _detect_existing_install_dir()
    if detected:
        return detected
    return _get_default_install_dir()


def main() -> int:
    is_frozen = getattr(sys, "frozen", False)
    exe_stem = (
        Path(sys.executable).stem.lower()
        if is_frozen
        else Path(__file__).stem.lower()
    )
    is_uninstall_mode = ("--uninstall" in sys.argv) or exe_stem.startswith(("uninstall", "odinstaluj"))
    from_temp = "--from-temp" in sys.argv
    silent_mode = ("--silent" in sys.argv) or ("--silent-test" in sys.argv)
    delete_downloads_flag = "--delete-downloads" in sys.argv
    skip_sys_integration = "--skip-system-integration" in sys.argv

    if is_uninstall_mode:
        target_dir = _resolve_uninstall_target_dir(_get_cli_arg_value("--target-dir"))

        if is_frozen and not from_temp:
            exe_resolved = Path(sys.executable).resolve()
            target_resolved = target_dir.resolve()
            if exe_resolved == (target_resolved / "Uninstall-SicMP4.exe") or target_resolved in exe_resolved.parents:
                temp_dir = Path(tempfile.gettempdir())
                temp_exe = temp_dir / f"SicMP4_Uninstall_{os.getpid()}.exe"
                shutil.copy2(exe_resolved, temp_exe)
                cmd = [str(temp_exe), "--uninstall", "--from-temp", "--target-dir", str(target_resolved)]
                for flag in ("--silent", "--silent-test", "--delete-downloads", "--skip-system-integration"):
                    if flag in sys.argv:
                        cmd.append(flag)
                subprocess.Popen(cmd, cwd=str(temp_dir))
                return 0

        _enable_windows_dpi_and_appid("SicMP4.Uninstaller.1")
        root = tk.Tk()
        SolarEclipseUninstallerApp(
            root,
            target_dir=target_dir,
            silent=silent_mode,
            delete_downloads_default=delete_downloads_flag,
            skip_system_integration=skip_sys_integration,
        )
        root.mainloop()

        if is_frozen and from_temp and os.name == "nt":
            try:
                ps_cleanup = (
                    f"$p = {_ps_quote(sys.executable)}; "
                    "for ($i = 0; $i -lt 20; $i++) { "
                    "Start-Sleep -Milliseconds 400; "
                    "Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue; "
                    "if (-not (Test-Path -LiteralPath $p)) { break } "
                    "}"
                )
                subprocess.Popen(
                    ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cleanup],
                    cwd=tempfile.gettempdir(),
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except Exception:
                pass
        return 0

    _enable_windows_dpi_and_appid("SicMP4.Installer.1")
    local_zip_arg = _get_cli_arg_value("--local-zip")
    local_zip = Path(local_zip_arg).resolve() if local_zip_arg else None
    custom_dir = _get_cli_arg_value("--install-dir")

    root = tk.Tk()
    app = SolarEclipseInstallerApp(
        root,
        auto_local_zip=local_zip,
        silent_test=silent_mode,
        custom_install_dir=custom_dir,
        skip_system_integration=skip_sys_integration,
    )
    if silent_mode:
        app.desktop_shortcut_var.set(False)
        app.startmenu_shortcut_var.set(False)
        app.launch_after_var.set(False)

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
