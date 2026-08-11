"""FastAPI backend for The Silent Co-Driver: race radio -> transcript + stress reading."""
import json
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from services.audio_utils import load_audio
from services.emotion import analyze_emotion
from services.transcribe import transcribe

DATA_PATH = Path(__file__).parent / "data" / "laptimes.json"

app = FastAPI(title="Silent Co-Driver API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _read_state() -> dict:
    return json.loads(DATA_PATH.read_text())


def _write_state(state: dict) -> None:
    DATA_PATH.write_text(json.dumps(state, indent=2))


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/laptimes")
def get_laptimes():
    return _read_state()


@app.post("/api/reset")
def reset_events():
    state = _read_state()
    state["events"] = []
    _write_state(state)
    return state


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), lap: int | None = Form(None)):
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(400, "Empty audio upload")

    try:
        audio, sr = load_audio(raw_bytes)
    except Exception as exc:
        raise HTTPException(400, f"Could not decode audio: {exc}") from exc

    if len(audio) < sr * 0.3:
        raise HTTPException(400, "Clip is too short to analyze")

    transcript = transcribe(audio, sr)
    emotion = analyze_emotion(audio, sr)

    state = _read_state()
    lap_number = lap if lap is not None else (len(state["events"]) + 1)
    event = {
        "id": int(time.time() * 1000),
        "lap": lap_number,
        "fileName": file.filename,
        "transcript": transcript,
        **emotion,
    }
    state["events"].append(event)
    _write_state(state)

    return {"event": event, "laps": state["laps"], "events": state["events"]}
