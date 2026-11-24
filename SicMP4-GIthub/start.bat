@echo off
chcp 65001 >nul
setlocal
title SicMP4 - Video ^& Audio Downloader (localhost:8000)

cd /d "%~dp0"

echo ============================================================
echo   SicMP4 ^| Lokalny Video ^& Audio Downloader
echo   Katalog: %~dp0
echo ============================================================
echo.

REM Zwolnij port 8000, jesli w tle dziala inna instancja serwera
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /F /T /PID %%a >nul 2>&1
)

if not exist "venv\Scripts\python.exe" (
    echo [1/3] Tworzenie wirtualnego srodowiska Pythona ^(venv^)...
    python -m venv venv
    if errorlevel 1 (
        echo [BLAD] Nie udalo sie utworzyc venv. Upewnij sie, ze Python jest zainstalowany.
        pause
        exit /b 1
    )
)

"venv\Scripts\python.exe" -c "import fastapi, uvicorn, yt_dlp, multipart" >nul 2>&1
if errorlevel 1 (
    echo [2/3] Instalacja brakujacych pakietow z requirements.txt...
    "venv\Scripts\python.exe" -m pip install --upgrade pip
    "venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [BLAD] Instalacja zaleznosci nie powiodla sie.
        pause
        exit /b 1
    )
) else (
    echo [OK] Zaleznosci Pythona sa gotowe.
)

if not exist "downloads" mkdir "downloads"

echo.
echo [START] Uruchamianie serwera SicMP4 na http://localhost:8000 ^(oraz LAN 0.0.0.0:8000^)...
echo         Aby zatrzymac aplikacje, nacisnij Ctrl+C lub zamknij to okno.
echo.

start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000"

"venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause
