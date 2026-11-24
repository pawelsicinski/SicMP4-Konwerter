from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

APP_VERSION = "1.5.0"

PACKAGING_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGING_DIR.parent
ICON_PATH = PACKAGING_DIR / "sicmp4.ico"

STABLE_DIR = ROOT_DIR / "SicMP4-stable"
INSTALLER_DIR = ROOT_DIR / "SicMP4-Installer"

INSTALLER_EXCLUDES = [
    "yt_dlp",
    "fastapi",
    "uvicorn",
    "starlette",
    "pydantic",
    "webview",
    "pythonnet",
    "clr_loader",
    "websockets",
    "anyio",
    "sqlite3",
    "unittest",
    "pydoc_data",
]

APP_EXCLUDES = [
    "sqlite3",
    "unittest",
    "pydoc_data",
    "doctest",
]

STABLE_INSTRUKCJA = f"""======================================================================
SicMP4 v{APP_VERSION} - Wersja Desktopowa (Standalone Windows .exe)
======================================================================

JAK URUCHOMIC PROGRAM:
1. Uruchom plik "SicMP4.exe" dwukrotnym kliknieciem.
2. Otworzy sie natywne okno aplikacji SicMP4.
3. Wklej dowolny link (YouTube, TikTok, Instagram, CDA, Twitch,
   SoundCloud, Vimeo i ponad 1700 innych serwisow) i kliknij
   "Sprawdz link", a nastepnie wybierz format (np. MP4 4K lub MP3 320)
   i rozpocznij pobieranie.

NAJWAZNIEJSZE INFORMACJE:
- Program dziala w 100% lokalnie na komputerze uzytkownika (korzysta
  z domowego polaczenia internetowego, wiec NIE WYMAGA plikow cookies
  ani zadnego logowania).
- Nie wymaga instalacji Pythona ani FFmpeg - wszystkie biblioteki oraz
  silnik FFmpeg + ffprobe znajduja sie juz wewnatrz tego folderu
  (katalogi "_internal" oraz "bin").
- Pobrane filmy i utwory zapisywane sa automatycznie w folderze
  "downloads" obok pliku SicMP4.exe. Mozesz takze kliknac przycisk
  "Pokaz w folderze" lub "Zapisz jako...", aby zapisac plik w dowolnym
  innym miejscu na dysku.
- Opcjonalnie: plik "SicMP4-Przegladarka.bat" uruchamia program
  w domyslnej przegladarce internetowej zamiast w osobnym oknie.

ODINSTALOWANIE PROGRAMU:
- Jesli zainstalowales program przez SicMP4-Installer.exe, mozesz go
  odinstalowac w dowolnym momencie w Ustawieniach Windows
  (Aplikacje -> Zainstalowane aplikacje -> SicMP4), skrotem
  "Odinstaluj SicMP4" w Menu Start lub uruchamiajac plik
  "Uninstall-SicMP4.exe" w tym folderze (z opcja zachowania
  pobranych plikow w folderze downloads).

UDOSTEPNIANIE INNYM OSOBOM:
- Wyslij znajomym lekki plik "SicMP4-Installer.exe" lub spakuj caly
  folder "SicMP4-stable" (bez osobistych plikow w downloads/).
======================================================================
"""

RELEASES_INSTRUKCJA = f"""======================================================================
JAK URUCHOMIC INSTALATOR ONLINE (SicMP4-Installer.exe) NA GITHUBIE
======================================================================

W tym folderze znajduja sie 2 gotowe pliki (wersja v{APP_VERSION}):
1. SicMP4-Windows-x64.zip  -> Czysta paczka programu (wrzucasz ja na GitHub)
2. SicMP4-Installer.exe    -> Lekka instalka + dezinstalator (wysylasz znajomym!)

----------------------------------------------------------------------
KROK PO KROKU (ZAJMUJE 1 MINUTE):
----------------------------------------------------------------------

1. Upewnij sie, ze Twoje repozytorium:
   https://github.com/pawelsicinski/SicMP4-Konwerter
   jest ustawione jako PUBLIC (Settings -> przewin na sam dol do
   Danger Zone -> Change repository visibility -> Change to public).
   (Jesli jest juz Public, pomin ten punkt).

2. Otworz bezposredni link do tworzenia nowego wydania:
   https://github.com/pawelsicinski/SicMP4-Konwerter/releases/new

3. Kliknij przycisk "Choose a tag", wpisz np.:
   v{APP_VERSION}
   i kliknij "Create new tag: v{APP_VERSION} on publish".

4. W polu "Release title" wpisz np.:
   SicMP4 v{APP_VERSION} (Windows 64-bit)

5. Przeciagnij myszka plik "SicMP4-Windows-x64.zip" z tego folderu
   w pole "Attach binaries by dropping them here or selecting them"
   i zaczekaj, az pasek wgrywania dojdzie do konca.

6. Kliknij zielony przycisk "Publish release" na samym dole.

----------------------------------------------------------------------
GOTOWE!
----------------------------------------------------------------------
Od tej chwili wysylasz znajomym WYLACZNIE maly plik:
   SicMP4-Installer.exe

Po jego uruchomieniu kazda osoba zobaczy ciemny instalator SicMP4
w stylu Solar Eclipse z paskiem pobierania na zywo (%, MB/s, ETA),
ktory automatycznie pobierze paczke z Twojego GitHuba, rozpakuje
program wraz z silnikiem FFmpeg i graficznym dezinstalatorem
(Uninstall-SicMP4.exe), utworzy skroty na Pulpicie oraz w Menu Start
(SicMP4 + Odinstaluj SicMP4), zarejestruje program w Ustawieniach
Windows (Zainstalowane aplikacje) i uruchomi SicMP4.
======================================================================
"""


def _run_pyinstaller(args: list[str]) -> None:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", *args]
    print(">>", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=str(ROOT_DIR))


def _ensure_ffmpeg_binaries() -> tuple[Path, Path]:
    stable_bin = STABLE_DIR / "bin"
    root_bin = ROOT_DIR / "bin"
    for candidate_dir in (stable_bin, root_bin):
        ffmpeg_exe = candidate_dir / "ffmpeg.exe"
        ffprobe_exe = candidate_dir / "ffprobe.exe"
        if ffmpeg_exe.is_file() and ffprobe_exe.is_file():
            return ffmpeg_exe, ffprobe_exe
    raise FileNotFoundError(
        "Brak ffmpeg.exe lub ffprobe.exe w SicMP4-stable/bin/ oraz bin/."
    )


def main() -> int:
    if not ICON_PATH.is_file():
        raise FileNotFoundError(f"Brak pliku ikony: {ICON_PATH}")

    ffmpeg_exe, ffprobe_exe = _ensure_ffmpeg_binaries()

    build_root = Path(tempfile.gettempdir()) / "sicmp4_build"
    if build_root.exists():
        shutil.rmtree(build_root, ignore_errors=True)
    work_installer = build_root / "work_installer"
    work_app = build_root / "work_app"
    dist_dir = build_root / "dist"
    spec_dir = build_root / "spec"
    for d in (work_installer, work_app, dist_dir, spec_dir):
        d.mkdir(parents=True, exist_ok=True)

    print("[1/5] Kompilacja SicMP4-Installer.exe (Instalator + Dezinstalator)...", flush=True)
    installer_args = [
        "--noconsole",
        "--onefile",
        "--name", "SicMP4-Installer",
        "--icon", str(ICON_PATH),
        "--add-data", f"{ICON_PATH};.",
        "--workpath", str(work_installer),
        "--distpath", str(dist_dir),
        "--specpath", str(spec_dir),
    ]
    for mod in INSTALLER_EXCLUDES:
        installer_args.extend(["--exclude-module", mod])
    installer_args.append(str(PACKAGING_DIR / "installer_app.py"))
    _run_pyinstaller(installer_args)

    built_installer_exe = dist_dir / "SicMP4-Installer.exe"
    if not built_installer_exe.is_file():
        raise FileNotFoundError(f"Nie zbudowano {built_installer_exe}")

    print("[2/5] Kompilacja SicMP4.exe (Aplikacja Desktopowa)...", flush=True)
    app_args = [
        "--noconsole",
        "--onedir",
        "--name", "SicMP4",
        "--icon", str(ICON_PATH),
        "--paths", str(ROOT_DIR),
        "--add-data", f"{ROOT_DIR / 'app' / 'templates'};app/templates",
        "--add-data", f"{ROOT_DIR / 'app' / 'static'};app/static",
        "--collect-submodules", "yt_dlp",
        "--collect-submodules", "uvicorn",
        "--collect-all", "webview",
        "--collect-all", "pythonnet",
        "--collect-all", "clr_loader",
        "--workpath", str(work_app),
        "--distpath", str(dist_dir),
        "--specpath", str(spec_dir),
    ]
    for mod in APP_EXCLUDES:
        app_args.extend(["--exclude-module", mod])
    app_args.append(str(PACKAGING_DIR / "desktop_launcher.py"))
    _run_pyinstaller(app_args)

    built_app_dir = dist_dir / "SicMP4"
    built_app_exe = built_app_dir / "SicMP4.exe"
    built_internal_dir = built_app_dir / "_internal"
    if not built_app_exe.is_file() or not built_internal_dir.is_dir():
        raise FileNotFoundError(f"Niekompletny wynik buildu w {built_app_dir}")

    print("[3/5] Aktualizacja folderu SicMP4-stable/ (zachowujac bin/ i downloads/)...", flush=True)
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/IM", "SicMP4.exe"],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    STABLE_DIR.mkdir(parents=True, exist_ok=True)
    (STABLE_DIR / "bin").mkdir(parents=True, exist_ok=True)
    (STABLE_DIR / "downloads").mkdir(parents=True, exist_ok=True)

    if ffmpeg_exe.resolve() != (STABLE_DIR / "bin" / "ffmpeg.exe").resolve():
        shutil.copy2(ffmpeg_exe, STABLE_DIR / "bin" / "ffmpeg.exe")
    if ffprobe_exe.resolve() != (STABLE_DIR / "bin" / "ffprobe.exe").resolve():
        shutil.copy2(ffprobe_exe, STABLE_DIR / "bin" / "ffprobe.exe")

    shutil.copy2(built_app_exe, STABLE_DIR / "SicMP4.exe")
    shutil.copy2(built_installer_exe, STABLE_DIR / "Uninstall-SicMP4.exe")
    (STABLE_DIR / "Uninstall-SicMP4.bat").unlink(missing_ok=True)

    stable_internal = STABLE_DIR / "_internal"
    if stable_internal.exists():
        shutil.rmtree(stable_internal)
    shutil.copytree(built_internal_dir, stable_internal)

    # Clean only temporary/cookies folders inside SicMP4-stable/downloads, never user media
    for temp_sub in (".tmp", ".cookies"):
        sub_path = STABLE_DIR / "downloads" / temp_sub
        if sub_path.exists():
            shutil.rmtree(sub_path, ignore_errors=True)

    (STABLE_DIR / "SicMP4-Przegladarka.bat").write_text(
        '@echo off\r\nstart "" "%~dp0SicMP4.exe" --browser\r\n',
        encoding="utf-8",
    )
    (STABLE_DIR / "INSTRUKCJA.txt").write_text(STABLE_INSTRUKCJA.replace("\n", "\r\n"), encoding="utf-8")

    print("[4/5] Budowanie czystego archiwum SicMP4-Installer/SicMP4-Windows-x64.zip...", flush=True)
    INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
    zip_out_path = INSTALLER_DIR / "SicMP4-Windows-x64.zip"
    tmp_zip_path = INSTALLER_DIR / "SicMP4-Windows-x64.zip.tmp"

    with zipfile.ZipFile(tmp_zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.write(STABLE_DIR / "SicMP4.exe", arcname="SicMP4.exe")
        zf.write(STABLE_DIR / "Uninstall-SicMP4.exe", arcname="Uninstall-SicMP4.exe")
        zf.write(STABLE_DIR / "SicMP4-Przegladarka.bat", arcname="SicMP4-Przegladarka.bat")
        zf.write(STABLE_DIR / "INSTRUKCJA.txt", arcname="INSTRUKCJA.txt")
        zf.write(STABLE_DIR / "bin" / "ffmpeg.exe", arcname="bin/ffmpeg.exe")
        zf.write(STABLE_DIR / "bin" / "ffprobe.exe", arcname="bin/ffprobe.exe")
        zf.writestr("downloads/.gitkeep", b"")

        for item in sorted(stable_internal.rglob("*")):
            if item.is_file():
                rel = item.relative_to(STABLE_DIR).as_posix()
                zf.write(item, arcname=rel)

    tmp_zip_path.replace(zip_out_path)

    print("[5/5] Aktualizacja SicMP4-Installer/SicMP4-Installer.exe i instrukcji...", flush=True)
    shutil.copy2(built_installer_exe, INSTALLER_DIR / "SicMP4-Installer.exe")
    (INSTALLER_DIR / "INSTRUKCJA-GITHUB-RELEASES.txt").write_text(
        RELEASES_INSTRUKCJA.replace("\n", "\r\n"),
        encoding="utf-8",
    )

    shutil.rmtree(build_root, ignore_errors=True)

    zip_mb = zip_out_path.stat().st_size / (1024 * 1024)
    inst_mb = (INSTALLER_DIR / "SicMP4-Installer.exe").stat().st_size / (1024 * 1024)
    print(
        f"[GOTOWE] SicMP4 v{APP_VERSION} zbudowany pomyslnie!\n"
        f"  - {INSTALLER_DIR / 'SicMP4-Installer.exe'} ({inst_mb:.1f} MB)\n"
        f"  - {zip_out_path} ({zip_mb:.1f} MB)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
