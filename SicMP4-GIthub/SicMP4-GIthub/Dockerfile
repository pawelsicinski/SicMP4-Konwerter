FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AUTO_CLEANUP_HOURS=1 \
    PORT=8000

WORKDIR /app

# Install FFmpeg (video/audio muxing & MP3 conversion) and Node.js (JS runtime for yt-dlp)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        nodejs \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Create writable directories (compatible with both root and non-root cloud containers)
RUN mkdir -p /app/downloads /app/downloads/.tmp /app/downloads/.cookies /app/bin \
    && chmod -R 777 /app/downloads /app/bin

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/api/health" || exit 1

# Single worker ensures in-memory task progress (SSE) stays consistent across requests
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*' --timeout-keep-alive 65"]
