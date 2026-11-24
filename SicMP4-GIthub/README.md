# SicMP4 v1.5.0 – Solar Eclipse Edition (Video & Audio Downloader / Converter)

Uniwersalna aplikacja desktopowa (Windows `.exe`) oraz webowa (FastAPI + `yt-dlp` + `FFmpeg` + `Node.js`) w oprawie **Solar Eclipse Edition**, umożliwiająca pobieranie i konwersję wideo oraz audio z ponad **1700+ serwisów** bezpośrednio na dysk lub w kontenerze Docker.

---

## Główne możliwości

- **Obsługiwane Platformy (1700+ serwisów)** – YouTube, TikTok, Instagram (Reels & Stories), Facebook, X (Twitter), Reddit, Pinterest, Twitch (VOD & Klipy), CDA.pl, Vimeo, Dailymotion, Rumble, Bitchute, SoundCloud, Bandcamp, Mixcloud oraz odtwarzacze HTML5.
- **Formaty Wideo** – MP4 (H.264 / AAC) od 480p i 720p do 1080p, 2K i 4K Ultra HD oraz bezstratne MKV / WebM (VP9 / AV1).
- **Formaty Audio** – MP3 (do 320 kbps z automatyczną okładką i tagami ID3), M4A / AAC, WAV oraz FLAC.
- **Funkcje Dodatkowe** – wycinki czasowe (`Od` – `Do`), napisy (osobny plik `.srt`, osadzone w kontenerze lub wtopione na stałe w obraz) oraz pobieranie całych playlist (automatycznie pakowanych do `.zip`).
- **Zoptymalizowany silnik v1.5.0**:
  - Wspólny, adaptacyjny kod dla wersji Desktop Windows (`pywebview` + natywne dialogi „Zapisz jako...” i schowek) oraz wersji Web/Cloud (Docker, Render, Railway, VPS).
  - Pamięciowy cache metadanych (`/api/info` z TTL 5 min), cache plików `cookies.txt` oraz `index.html`, kompresja GZip z pominięciem SSE i plików binarnych, ogranicznik jednoczesnych pobierań (`MAX_CONCURRENT_DOWNLOADS`) i automatyczne czyszczenie nieaktywnych zadań.
  - Zoptymalizowane grafiki kart (mniejszy rozmiar o ~90%), anulowanie nieaktualnych zapytań `AbortController` oraz delegowane eventy DOM w interfejsie.
- **Instalator & Dezinstalator Windows (`SicMP4-Installer.exe` / `Uninstall-SicMP4.exe`)**:
  - Graficzny instalator online pobierający paczkę `SicMP4-Windows-x64.zip` z GitHub Releases.
  - Pełny graficzny dezinstalator (zintegrowany z **Ustawieniami Windows -> Zainstalowane aplikacje** oraz skrótem **Odinstaluj SicMP4** w Menu Start) z bezpiecznym przenoszeniem do `%TEMP%` oraz opcją zachowania lub usunięcia pobranych plików w `downloads/`.

---

## Struktura projektu

```text
SicMP4/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI, SSE, selektywny GZip, cache statyczny i API
│   ├── downloader.py        # Silnik yt-dlp + FFmpeg, TTL cache, limity współbieżności
│   ├── templates/
│   │   └── index.html       # Interfejs Solar Eclipse (jednostronicowy 100vh)
│   └── static/
│       ├── css/styles.css
│       ├── img/             # Zoptymalizowane grafiki Eclipse i favicony
│       └── js/app.js        # Adaptacyjny klient Desktop / Cloud / LAN
├── packaging/
│   ├── desktop_launcher.py  # Launcher okna desktopowego Windows (pywebview)
│   ├── installer_app.py     # Graficzny Instalator Online + Dezinstalator Windows
│   ├── build_release.py     # Skrypt budujący SicMP4.exe, Instalator oraz .zip
│   └── sicmp4.ico
├── downloads/               # Katalog roboczy na pobrane pliki
├── bin/                     # Opcjonalny katalog na lokalne binarki ffmpeg.exe / ffprobe.exe
├── Dockerfile               # Obraz produkcyjny z preinstalowanym FFmpeg i Node.js
├── docker-compose.yml       # Konfiguracja Docker Compose
├── render.yaml              # Automatyczne wdrożenie (Render.com)
├── railway.json             # Automatyczne wdrożenie (Railway)
├── requirements.txt
└── start.bat                # Szybkie uruchomienie lokalne z venv na Windows
```

---

## Uruchomienie lokalne (Windows)

1. Upewnij się, że w systemie zainstalowany jest Python oraz `FFmpeg` (`winget install Gyan.FFmpeg`) lub wrzuć `ffmpeg.exe` i `ffprobe.exe` do folderu `bin/`.
2. Kliknij dwukrotnie plik **`start.bat`**. Skrypt utworzy środowisko `venv`, zainstaluje zależności i otworzy `http://localhost:8000`.

### Budowanie paczki Windows (`.exe` + Instalator + Dezinstalator)

Mając zainstalowane zależności (w tym `pyinstaller`, `pywebview`) w `venv`:

```bash
venv\Scripts\python.exe packaging\build_release.py
```

Skrypt przebuduje `SicMP4-stable/` (zachowując lokalne binarki `bin/` i pobrane multimedia w `downloads/`), wygeneruje czyste archiwum `SicMP4-Installer/SicMP4-Windows-x64.zip` oraz zaktualizuje `SicMP4-Installer/SicMP4-Installer.exe` z wbudowanym dezinstalatorem.

---

## Publikacja na GitHub oraz Hosting (Docker / Render / Railway / VPS)

Projekt zawiera gotowy plik `Dockerfile` instalujący **Python 3.12**, **FFmpeg** oraz **Node.js** bezpośrednio w kontenerze Linuxowym.

### Wysłanie kodu na GitHub (z folderu `SicMP4-GIthub` lub głównego repozytorium)
```bash
git init
git add .
git commit -m "SicMP4 v1.5.0 - Optimized engine, unified UI & Windows Uninstaller"
git branch -M main
git remote add origin https://github.com/TWOJ_LOGIN/SicMP4-Konwerter.git
git push -u origin main
```

### Wdrożenie w chmurze (Render / Railway / VPS)
- **Render.com**: Połącz repozytorium GitHub jako **Web Service** (`Runtime: Docker` – wykryje automatycznie `Dockerfile` oraz `render.yaml`).
- **Railway / Coolify / Koyeb**: Wskaż repozytorium GitHub – platforma automatycznie zbuduje obraz z `Dockerfile` i przekaże zmienną środowiskową `PORT`.
- **Docker Compose**:
  ```bash
  docker compose up -d --build
  ```
- **Czysty Docker CLI**:
  ```bash
  docker build -t sicmp4 .
  docker run -d -p 8000:8000 --name sicmp4 sicmp4
  ```

### Zmienne środowiskowe (opcjonalne)

| Zmienna | Domyślnie | Opis |
| :--- | :--- | :--- |
| `PORT` | `8000` | Port nasłuchiwania serwera HTTP (ustawiany automatycznie przez Render / Railway). |
| `AUTO_CLEANUP_HOURS` | `0` (`1` w Docker/Render) | Czas (w godzinach), po którym stare pobrane pliki są automatycznie usuwane z dysku kontenera. |
| `MAX_CONCURRENT_DOWNLOADS` | `3` | Maksymalna liczba równoległych zadań pobierania i konwersji FFmpeg. |
