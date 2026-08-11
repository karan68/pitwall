# The Silent Co-Driver

Grand Prix hackathon entry. Upload or record a driver radio call → Whisper transcribes it,
a speech-emotion model reads the tone of voice, and the result is plotted against lap times
so the team can see if stress is matching up with slower laps.

## Stack
- **Backend**: FastAPI + Hugging Face `transformers` (Whisper `whisper-base.en` for ASR,
  `wav2vec2` speech-emotion-recognition for tone), runs fully locally/offline after first model download.
- **Frontend**: Vite + React + TypeScript + Tailwind v4 + Recharts.

## Run it

### Backend (http://localhost:8000)
```powershell
cd backend
.venv\Scripts\Activate.ps1
uvicorn main:app --reload --port 8000
```
First run downloads the models (a few hundred MB, cached in `~/.cache/huggingface`).

### Frontend (http://localhost:5173)
```powershell
cd frontend
npm run dev
```

## Adding real demo clips
Drop short (5-15s) recordings of someone reading race-radio-style lines in `backend/sample_audio/`
(calm/neutral delivery, then stressed/urgent, then a tired/flat one) and upload them from the UI.
Recording your own avoids any copyright issues with real broadcast audio.

## Notes
- Every team member needs their own Hugging Face account (hackathon rule).
- Swap `MODEL_NAME` in `backend/services/transcribe.py` / `emotion.py` for bigger/smaller models
  if accuracy or speed needs tuning.
- Lap-time data is synthetic (`backend/data/laptimes.json`); analyzed radio calls get appended
  to it as "events" tied to a lap number so the chart updates live.
