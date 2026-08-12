# PITWALL — one image, one port. Suitable for Hugging Face Spaces (Docker SDK).
FROM node:20-slim AS frontend

WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim

# libsndfile for soundfile, ffmpeg for mp3/webm radio clips
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist

# /tmp is writable on a free Space; /data only exists with persistent storage.
ENV HF_HOME=/tmp/huggingface \
    PITWALL_ASR_MODEL=openai/whisper-small.en \
    PORT=7860

EXPOSE 7860
WORKDIR /app/backend
# Shell form so an injected PORT is honoured; Spaces uses 7860, Render sets its own.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
