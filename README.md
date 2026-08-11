# PITWALL — The Silent Co-Driver

**Grand Prix hackathon · Problem Statement 1 · Powered by Hugging Face**

A race engineer's co-pilot. It reads a driver's state from their radio calls, measures what
that state is costing in lap time, and tells the engineer whether to press the talk button
at all — and in how many words.

---

## The problem behind the problem

The brief says engineers miss warning signs in a driver's voice because they are too busy
watching data. True — but that is only half of it. The other half is that when engineers
*do* notice, the instinctive response is to talk to the driver, and talking to a driver who
is already at capacity is how a bad lap becomes a lost race.

So the useful output is not a mood label. It is a decision: **talk, or don't.**

## Why the obvious build is not good enough

The direct reading of this problem is: run an audio-emotion model, print the label, plot it
against lap time. That build has three defects, and this project is built around fixing them.

**1. Emotion classifiers are trained on acted speech.** RAVDESS, IEMOCAP and similar corpora
are actors performing emotions. Race radio is task speech under g-load, heat and dehydration.
The domain gap is not small, and the model does not know it is out of domain — it returns a
confident label regardless.

*This is not a theoretical objection.* The reference classifier is still wired in and shown
on screen. On our stressed test call — "there is no grip at all out here, the rear is
completely gone, I cannot hold this pace" — it returns **neutral, 67% confidence**. The
biomarker engine disagrees, and shows the measurements that put it there.

**2. An absolute label ignores the driver.** Some drivers are naturally loud and fast-talking.
Scoring them against a population average marks them permanently stressed. What matters is
deviation from *their own* voice.

**3. One axis cannot separate the states that matter.** A driver on a qualifying lap and a
driver who is drowning both sound "high arousal". Collapsing them loses the only distinction
the pit wall cares about.

## What this does instead

### 1. Explainable biomarkers, not a black box

Eight measurements computed with plain signal processing (`backend/services/features.py`) —
no model, nothing to take on trust:

| Measure | What it indicates |
|---|---|
| F0 mean / variability | Pitch; rises with arousal |
| RMS energy | Vocal effort |
| Articulation rate | Words per second of speech, pauses excluded |
| High-frequency energy ratio | Vocal effort — measured on voiced frames only, so background noise cannot fake it |
| Jitter | Cycle-to-cycle pitch instability |
| Shimmer | Cycle-to-cycle amplitude instability |
| Harmonics-to-noise ratio | Voice clarity; falls under strain |
| Pause ratio | Rises with fatigue |

Pitch tracking is FFT-based autocorrelation over 40 ms frames, verified against synthetic
signals of known F0 from 95–300 Hz.

### 2. Scored against the driver's own baseline

Three calm clips calibrate the driver. Everything after is a robust z-score (median + MAD)
against that baseline, clamped to ±4σ so a tight baseline cannot manufacture absurd readings.
Uncalibrated sessions still work but are explicitly downgraded to low confidence and labelled
as scored against population averages.

### 3. Two axes, four states

```
                    high arousal
                         │
          LOCKED IN      │      STRESSED
      (effort, clean)    │   (effort + strain)
                         │
   low strain ───────────┼─────────── high strain
                         │
            CALM         │        TIRED
       (near baseline)   │   (strain, no effort)
                         │
                     low arousal
```

**Locked In** is the state a one-dimensional model cannot express: a driver working hard and
performing well. It still closes the radio window — but for the opposite reason to Stressed.

### 4. Tone × content, not tone alone

The transcript is classified into race-radio intents (zero-shot, `valhalla/distilbart-mnli-12-1`).
Hazard terms bypass the model entirely — safety detection is never left to a probabilistic
classifier. The engineer's recommended action comes from the *combination*:

| State | Intent | Call |
|---|---|---|
| Stressed | Car problem | Confirm you've seen it, give one number, nothing else |
| Stressed | Self-blame | Do not send data. One reassurance, then silence |
| Tired | Physical strain | Bring the pit window forward, simplify every call |
| Locked In | anything non-critical | Radio silence. The driver is delivering |
| Calm | Car problem | Good window to debrief properly |

**Tone/content mismatch:** a driver saying "I'm fine" with vocal strain well above baseline
raises an under-reporting flag. Drivers downplay problems; the voice does not.

### 5. The radio window

`OPEN` / `CAUTION` / `CLOSED`, with a word budget attached. The message composer rewrites what
the engineer typed to fit it — dropping filler first, then justifications, keeping imperatives
and numbers.

> **34 words:** *"Okay so we're looking at plan B which is the two stop, we need you to push for three laps and then we'll bring you in, and just watch the front left because it's degrading faster than we expected"*
>
> **6-word budget:** *"Just watch the front left."*

Safety-critical traffic always overrides a closed window.

### 6. Cost in seconds

Driver load is correlated against lap-time delta at lags of 0, 1 and 2 laps, and the best lag
is reported — that lag is the warning time the pit wall actually gets. Output is in seconds
lost, because that is the unit a race engineer thinks in.

### 7. It refuses to answer when it shouldn't

A signal-quality gate (SNR, clipping, duration, voiced content) blocks scoring on audio that
cannot support a conclusion. Correlations are suppressed below five radio calls. Every reading
carries a confidence level and the reason for it.

### 8. Hands-free, because that is the actual problem

The brief's premise is that engineers miss what is in a driver's voice *because their eyes are
on the data*. Another dashboard does not fix that — it adds another screen. So the reading is
also available by voice, through an **OmniDimension** agent:

- The engineer presses **Talk to pit wall** and asks out loud: *"How is the driver?"*,
  *"Can I talk to him?"*, *"What should I say?"*, *"Why do you think that?"*
- The agent is briefed **server-side** on the radio call currently selected, using OmniDimension's
  `custom_variables`. Those are set at session creation and cannot be tampered with from the
  browser, so the agent can only report what was actually measured.
- Its prompt instructs it to answer with radio discipline — numbers first, one or two sentences —
  and to say it does not have something rather than invent it. It is explicitly told never to
  claim emotion detection, only measured vocal load against a personal baseline.

Architecture: the API key never leaves the backend. `POST /api/voice/session` mints a
single-use `ws_url` that expires in 15 minutes; the browser receives only that, and
`@omnidim-ai/client` handles microphone capture, playback, barge-in and transcripts.

---

## Running it

**Voice agent (optional).** Copy `backend/.env.example` to `backend/.env` and add an
OmniDimension API key:

```
OMNIDIM_API_KEY=your_key_here
```

`backend/.env` is gitignored — never commit a key. Without it everything still works; the
voice panel simply reports "not configured". The PITWALL agent is created automatically on
first use and its id cached in `backend/data/omnidim_agent.json`.

**Backend** (http://localhost:8000)

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn main:app --port 8000 --reload
```

**Frontend** (http://localhost:5173)

```powershell
cd frontend
npm run dev
```

First run downloads three Hugging Face models (~1.6 GB total) into `~/.cache/huggingface`.
Everything runs locally on CPU after that — no audio ever leaves the machine, which matters
for a team that guards its data.

**Verify the engine** — 27 known-answer and ablation checks:

```powershell
cd backend
.venv\Scripts\python.exe verify_features.py
```

**Verify the voice path** — creates/reuses the agent, mints a real session, prints the briefing
the agent receives (never the key or the full token):

```powershell
.venv\Scripts\python.exe verify_voice.py
```

**Load a demo stint** from a folder of clips. Files named `baseline*` calibrate the driver,
the rest are analysed as radio calls:

```powershell
.venv\Scripts\python.exe seed_demo.py sample_audio\my_clips
```

---

## Demo audio — read this before the demo

`backend/sample_audio/placeholder/` holds synthetic clips from `make_placeholder_clips.ps1`.
They exist to prove the pipeline runs. **They are not good enough for the demo.**

Text-to-speech has near-zero jitter and shimmer no matter how fast or slow you set it. A
synthetic "stressed" clip therefore reads as *Locked In* — high effort, clean voice — because
that is genuinely what it is. The engine is right; the audio simply cannot express strain.
This is an expected limitation, not a bug, and the thresholds have deliberately **not** been
tuned to make fake audio pass.

Record real voices. For each driver:

- **3 calm reference clips** — normal delivery, ~5 s each. These set the baseline.
- **Urgent/overloaded** — fast, loud, pressured. Produces the Stressed quadrant.
- **Exhausted** — slow, quiet, breathy, with audible strain. Produces Tired.
- **Under-reporting** — "no, I'm fine, don't worry" said while clearly strained. Fires the
  mismatch flag, and is the most memorable moment in the demo.
- **Hazard** — "yellow flag, car in the wall". Proves safety overrides a closed window.

Self-recorded audio also avoids any question over broadcast rights.

---

## Hugging Face models

| Model | Role |
|---|---|
| `openai/whisper-base.en` | Speech to text |
| `valhalla/distilbart-mnli-12-1` | Zero-shot radio intent classification |
| `superb/wav2vec2-base-superb-er` | Reference emotion classifier, kept as an on-screen cross-check |

Model names are constants at the top of each service and swap without touching anything else.
`whisper-small.en` is a drop-in accuracy upgrade if CPU time allows — `base.en` currently
mis-hears "braking points" as "breaking points".

## Voice partner

| Service | Role |
|---|---|
| OmniDimension | Hands-free race-engineer agent, grounded in the live reading via server-set session variables |

---

## Honest limitations

- Biomarkers are validated against synthetic signals of known properties, not against labelled
  driver-stress data. No such public dataset exists for race radio.
- Lap-time correlations from a single stint are indicative, not evidence. The interface says so.
- The reference emotion classifier is shown for contrast, not treated as ground truth. Neither
  reading is claimed to be clinically validated stress detection.
- The system advises. The engineer decides.

---

## Layout

```
backend/
  main.py                    FastAPI routes
  services/
    features.py              biomarker extraction + signal-quality gate
    state.py                 baseline, z-scores, arousal/strain quadrant
    content.py               zero-shot radio intent + hazard override
    advisor.py               radio window, engineer action, message compression
    analytics.py             load-vs-lap-time correlation and cost
    transcribe.py            Whisper
    reference_model.py       the cross-check classifier
    audio_utils.py           decode + resample to 16 kHz mono
    omnidim.py               OmniDimension agent + voice session minting
    briefing.py              the live reading, flattened into speech
  verify_features.py         27-check verification harness
  verify_voice.py            end-to-end check of the voice path
  seed_demo.py               load a stint from a folder of clips
  make_placeholder_clips.ps1 synthetic smoke-test audio
frontend/src/
  App.tsx                    layout and session state
  components/                status strip, quadrant, charts, advisor, console, voice, log
```
