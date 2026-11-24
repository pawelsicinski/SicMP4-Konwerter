# SicMP4 – Docker Edition (Video & Audio Downloader)

Aplikacja webowa (FastAPI + `yt-dlp` + `FFmpeg` + `Node.js`) przygotowana do bezpośredniego uruchomienia w środowisku **Docker** (zarówno na **Render.com**, **Railway**, **Koyeb**, **Fly.io**, jak i na własnym serwerze VPS lub Docker Desktop).

---

## Uruchomienie na Render.com (Runtime: Docker)

1. Wrzuć **zawartość folderu `SicMP4-GIthub`** bezpośrednio do głównego katalogu swojego repozytorium na GitHubie (tak, aby plik `Dockerfile` leżał na najwyższym poziomie repozytorium).
2. W panelu **Render.com** utwórz nowy **Web Service** połączony z repozytorium:
   - **Language / Runtime**: `Docker`
   - **Root Directory**: zostaw puste *(jeśli wrzuciłeś samą zawartość folderu)* albo wpisz `SicMP4-GIthub` *(jeśli wrzuciłeś cały folder jako podkatalog)*
   - **Dockerfile Path**: `./Dockerfile` (domyślne)
3. Kliknij **Deploy Web Service**. Obraz automatycznie zainstaluje Pythona 3.12, FFmpeg, Node.js oraz `yt-dlp[default]` i wystartuje na porcie przydzielonym przez zmienną środowiskową `PORT`.

---

## Uruchomienie lokalne lub na VPS przez Docker

### Opcja A: Docker Compose
```bash
docker compose up -d --build
```
Aplikacja będzie dostępna pod adresem `http://localhost:8000`.

### Opcja B: Czysty Docker CLI
```bash
docker build -t sicmp4 .
docker run -d -p 8000:8000 --name sicmp4 sicmp4
```

---

## Zmienne środowiskowe (opcjonalne)

| Zmienna | Domyślnie | Opis |
| :--- | :--- | :--- |
| `PORT` | `8000` | Port nasłuchiwania serwera HTTP (ustawiany automatycznie przez Render / Railway). |
| `AUTO_CLEANUP_HOURS` | `1` | Czas (w godzinach), po którym stare pobrane pliki są automatycznie usuwane z dysku kontenera. |
