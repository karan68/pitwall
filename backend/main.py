"""PITWALL API — driver-state readings and the radio decisions that follow."""
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv(Path(__file__).parent / ".env")

from services import advisor, analytics, briefing, content, driving, features, omnidim, reference_model, state  # noqa: E402
from services.audio_utils import load_audio  # noqa: E402
from services.transcribe import transcribe  # noqa: E402

STORE_PATH = Path(__file__).parent / "data" / "session.json"
SEED_PATH = Path(__file__).parent / "data" / "seed_session.json"

app = FastAPI(title="PITWALL API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _read_store() -> dict:
    if not STORE_PATH.exists():
        STORE_PATH.write_text(SEED_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return json.loads(STORE_PATH.read_text(encoding="utf-8"))


def _write_store(store: dict) -> None:
    STORE_PATH.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")


def _session_payload(store: dict) -> dict:
    baseline = state.build_baseline(store["baselineSamples"])
    inputs = driving.score_stint(store["laps"])

    events = store["events"]
    if inputs["available"]:
        roughness = inputs["roughnessByLap"]
        events = [
            {
                **event,
                "drivingRoughness": roughness.get(event["lap"]),
                "drivingCrossCheck": driving.cross_check(
                    event["driverLoad"], roughness.get(event["lap"])
                ),
            }
            for event in events
        ]

    return {
        "session": store["session"],
        "laps": store["laps"],
        "events": events,
        "baseline": baseline,
        "driverInputs": inputs,
        "analytics": analytics.analyze(
            store["laps"], store["events"], store["session"]["referenceLapSeconds"]
        ),
    }


def _decode(raw_bytes: bytes):
    if not raw_bytes:
        raise HTTPException(400, "Empty audio upload.")
    try:
        return load_audio(raw_bytes)
    except Exception as exc:
        raise HTTPException(400, f"Could not decode audio: {exc}") from exc


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/session")
def get_session():
    return _session_payload(_read_store())


@app.post("/api/session/reset")
def reset_session():
    store = _read_store()
    store["events"] = []
    _write_store(store)
    return _session_payload(store)


@app.post("/api/baseline/reset")
def reset_baseline():
    store = _read_store()
    store["baselineSamples"] = []
    _write_store(store)
    return _session_payload(store)


@app.post("/api/baseline")
async def add_baseline(file: UploadFile = File(...)):
    """Register a calm reference clip so later calls are scored against this driver."""
    audio, sr = _decode(await file.read())

    quality = features.signal_quality(audio, sr)
    if not quality["usable"]:
        raise HTTPException(400, "; ".join(quality["issues"]))

    asr = transcribe(audio, sr)
    sample = features.extract(audio, sr, word_count=len(asr["text"].split()))
    sample["snrDb"] = quality["snrDb"]

    store = _read_store()
    store["baselineSamples"].append(sample)
    _write_store(store)

    payload = _session_payload(store)
    payload["addedSample"] = sample
    return payload


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), lap: int | None = Form(None)):
    audio, sr = _decode(await file.read())

    quality = features.signal_quality(audio, sr)
    store = _read_store()

    asr = transcribe(audio, sr)
    transcript = asr["text"]
    if asr["degenerate"]:
        quality = {
            **quality,
            "usable": False,
            "issues": quality["issues"] + [
                "Speech recognition collapsed into repetition on this clip; transcript discarded."
            ],
        }

    biomarkers = features.extract(audio, sr, word_count=len(transcript.split()))
    baseline = state.build_baseline(store["baselineSamples"])

    driver_state = state.classify(biomarkers, baseline, snr_db=quality["snrDb"])
    said = content.analyze(transcript)

    context = {
        "recentLoads": [e["driverLoad"] for e in store["events"][-4:]],
        "stintLaps": lap or len(store["events"]) + 1,
    }
    recommendation = advisor.advise(driver_state, said, context)

    event = {
        "id": int(time.time() * 1000),
        "lap": lap if lap is not None else len(store["events"]) + 1,
        "fileName": file.filename,
        "transcript": transcript,
        "asr": {"model": asr["model"], "degenerate": asr["degenerate"]},
        "quality": quality,
        "biomarkers": biomarkers,
        "content": said,
        "reference": reference_model.reference_reading(audio, sr),
        **driver_state,
        "recommendation": recommendation,
    }
    event["referenceDisagrees"] = event["reference"]["state"] != event["state"]

    store["events"].append(event)
    _write_store(store)

    payload = _session_payload(store)
    payload["event"] = event
    return payload


class SessionContext(BaseModel):
    driver: str
    team: str = ""
    stint: str = ""
    provenance: dict[str, str] | None = None


@app.post("/api/session/context")
def set_session_context(context: SessionContext):
    """Label whose radio this is and where each part of the data came from."""
    store = _read_store()
    store["session"].update(
        {k: v for k, v in context.model_dump().items() if v not in (None, "")}
    )
    _write_store(store)
    return _session_payload(store)


class LapSeries(BaseModel):
    laps: list[dict]
    referenceLapSeconds: float


@app.post("/api/session/laps")
def set_laps(series: LapSeries):
    """Replace the lap series, e.g. with real timing pulled from OpenF1."""
    store = _read_store()
    store["laps"] = [
        {
            "lap": lap["lap"],
            "timeSeconds": lap["timeSeconds"],
            **({"driving": lap["driving"]} if lap.get("driving") else {}),
        }
        for lap in series.laps
    ]
    store["session"]["referenceLapSeconds"] = series.referenceLapSeconds
    _write_store(store)
    return _session_payload(store)


class ComposeRequest(BaseModel):
    message: str
    wordBudget: int = 26


@app.post("/api/compose")
def compose(request: ComposeRequest):
    return advisor.compress(request.message, max(3, request.wordBudget))


def _current_briefing(event_id: int | None = None) -> dict:
    store = _read_store()
    payload = _session_payload(store)
    events = store["events"]
    selected = next((e for e in events if e["id"] == event_id), None) if event_id else None
    return briefing.build(payload, selected or (events[-1] if events else None))


@app.get("/api/voice/status")
def voice_status():
    """Whether the hands-free agent is available, without ever exposing the key."""
    return {"configured": omnidim.is_configured(), "agentName": omnidim.AGENT_NAME}


@app.get("/api/voice/brief")
def voice_brief(eventId: int | None = None):
    """The live reading in speech-ready form. Also the shape an external agent tool would call."""
    variables = _current_briefing(eventId)
    return {"variables": variables, "summary": briefing.spoken_summary(variables)}


class VoiceSessionRequest(BaseModel):
    eventId: int | None = None


@app.post("/api/voice/session")
def voice_session(request: VoiceSessionRequest | None = None):
    """Mint a single-use browser voice session preloaded with the current reading."""
    if not omnidim.is_configured():
        raise HTTPException(503, "Voice agent not configured. Set OMNIDIM_API_KEY in backend/.env.")

    variables = _current_briefing(request.eventId if request else None)
    try:
        session = omnidim.create_voice_session(variables)
    except omnidim.OmniDimError as exc:
        raise HTTPException(502, str(exc)) from exc

    return {**session, "briefedOn": variables["lap"], "summary": briefing.spoken_summary(variables)}


# A Mount at "/" matches every path registered after it, so this must stay the
# last statement in the file. Building the frontend once silently 404'd every
# route declared below it; verify_api.py now guards against that returning.
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
