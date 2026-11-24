# SicMP4 – Video & Audio Downloader / Converter

Aplikacja webowa (FastAPI + `yt-dlp` + `FFmpeg`) w oprawie **Solar Eclipse Edition**, umożliwiająca pobieranie oraz konwersję wideo i audio z ponad 1700+ serwisów w przeglądarce – gotowa zarówno do hostingu w chmurze (Docker / Render / Railway / VPS), jak i do działania lokalnego.

---

## Najważniejsze możliwości

- **Obsługiwane Platformy (1700+ serwisów)** – YouTube, TikTok, Instagram (Reels & Stories), Facebook, X (Twitter), Reddit, Pinterest, Twitch (VOD & Klipy), CDA.pl, Vimeo, Dailymotion, Rumble, Bitchute, SoundCloud, Bandcamp, Mixcloud oraz odtwarzacze HTML5.
- **Formaty Wideo** – MP4 (H.264 / AAC z optymalizacją `+faststart` dla dużych plików) od 480p i 720p do 1080p, 2K i 4K Ultra HD oraz bezstratne MKV / WebM (VP9 / AV1).
- **Formaty Audio** – MP3 (do 320 kbps z automatyczną okładką i tagami ID3), M4A / AAC, WAV oraz FLAC.
- **Funkcje Dodatkowe** – wycinki czasowe (`Od` – `Do`), napisy (`.srt`, osadzone w kontenerze lub wtopione na stałe w obraz) oraz pobieranie całych playlist (pakowanych automatycznie do `.zip`).
- **Tryb chmurowy** – automatyczne pobieranie gotowego pliku na urządzenie użytkownika oraz cykliczne czyszczenie starych plików tymczasowych na serwerze (`AUTO_CLEANUP_HOURS=2`).

---

## Jak wrzucić ten folder na GitHub i zahostować

Cała zawartość tego folderu (`SicMP4-GIthub`) jest oczyszczona z lokalnych środowisk `venv` i plików tymczasowych – możesz wrzucić ją bezpośrednio do nowego repozytorium na GitHubie.

### Krok 1: Wrzucenie na GitHub
- **Przez stronę GitHub.com**: Utwórz nowe repozytorium -> kliknij *uploading an existing file* -> zaznacz **wszystkie pliki i foldery wewnątrz `SicMP4-GIthub`** i przeciągnij je do okna przeglądarki -> kliknij *Commit changes*.
- **Lub przez Git / GitHub Desktop**: Wskaż folder `SicMP4-GIthub` jako katalog repozytorium i opublikuj na swoim koncie GitHub.

### Krok 2: Uruchomienie hostingu (wybierz dowolną platformę)
- **Render.com**: Kliknij *New +* -> *Web Service* (lub *Blueprint*) -> wybierz swoje repozytorium z GitHuba. Render automatycznie wykryje `Dockerfile` oraz `render.yaml`, zainstaluje FFmpeg + Node.js + Pythona i uruchomi aplikację pod publicznym adresem `https://...`.
- **Railway.app**: Kliknij *New Project* -> *Deploy from GitHub repo* -> wybierz repozytorium. Plik `railway.json` oraz `Dockerfile` skonfigurują kontener automatycznie.
- **Własny VPS z Dockerem**:
  ```bash
  docker build -t sicmp4 .
  docker run -d -p 8000:8000 --restart unless-stopped --name sicmp4 sicmp4
  ```

---

## Uruchomienie lokalne (Windows)
Kliknij dwukrotnie `start.bat` (wymagany zainstalowany Python oraz `FFmpeg` w systemie).
