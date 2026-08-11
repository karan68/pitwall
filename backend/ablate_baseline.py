"""Is a state reading a property of the driver, or of the baseline behind it?

In the four-driver discrimination run, Lewis Hamilton came out "Tired" on 6 of 6
calls at strain 1.1-2.5, while every other driver produced a mix. He was also the
only driver whose calibration failed: 2 of 4 clips passed the quality gate, and
MIN_BASELINE_SAMPLES is 3. Below that line build_baseline() silently falls back to
POPULATION_PRIORS, so those six calls were scored against a generic adult speaker
rather than against Hamilton.

That is a hypothesis, and it is testable. This holds the call clips fixed and
varies only the baseline behind them:

    uncalibrated  - baseline reset, no clips accepted -> population priors
    calibrated    - enough clips fed to clear MIN_BASELINE_SAMPLES

If "Tired" is a fact about Hamilton's voice it survives both. If it is an artefact
of the prior fallback, it moves.

    .venv\\Scripts\\python.exe ablate_baseline.py --driver 44
"""
import argparse
import io
import json
import shutil
import urllib.request
from collections import Counter
from pathlib import Path

import httpx
import soundfile as sf

API = "http://localhost:8000"
OPENF1 = "https://api.openf1.org/v1"
STORE = Path(__file__).parent / "data" / "session.json"
CACHE = Path(__file__).parent / "data" / "ablation_cache"


def openf1(path: str, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    request = urllib.request.Request(f"{OPENF1}/{path}?{query}", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


def fetch_clip(message: dict, index: int) -> bytes | None:
    """Download and transcode once, then reuse, so every condition sees identical audio."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{index:03d}.wav"
    if cached.exists():
        return cached.read_bytes()

    from transformers.pipelines.audio_utils import ffmpeg_read

    try:
        request = urllib.request.Request(message["recording_url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
        buffer = io.BytesIO()
        sf.write(buffer, ffmpeg_read(raw, 16000), 16000, format="WAV")
    except Exception:
        return None

    cached.write_bytes(buffer.getvalue())
    return buffer.getvalue()


def score(client: httpx.Client, clips: list[bytes], baseline_clips: list[bytes]) -> list[dict]:
    """Reset state, install a baseline, then score every call clip against it."""
    client.post(f"{API}/api/session/reset")
    client.post(f"{API}/api/baseline/reset")

    accepted = 0
    for clip in baseline_clips:
        response = client.post(f"{API}/api/baseline", files={"file": ("b.wav", clip, "audio/wav")})
        accepted += response.status_code == 200

    baseline = client.get(f"{API}/api/session").json()["baseline"]

    rows = []
    for clip in clips:
        response = client.post(
            f"{API}/api/analyze", files={"file": ("c.wav", clip, "audio/wav")}, data={"lap": len(rows) + 1}
        )
        if response.status_code != 200:
            continue
        event = response.json()["event"]
        rows.append(
            {
                "state": event["state"],
                "load": event["driverLoad"],
                "arousal": event["arousal"],
                "strain": event["strain"],
                "confidence": event["confidence"]["level"],
                "text": event["transcript"][:44],
            }
        )
    return [{"accepted": accepted, "calibrated": baseline["calibrated"], "rows": rows}]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--country", default="Belgium")
    parser.add_argument("--driver", type=int, default=44)
    parser.add_argument("--calls", type=int, default=6)
    parser.add_argument("--baseline", type=int, default=14)
    args = parser.parse_args()

    sessions = openf1("sessions", year=args.year, session_name="Race")
    session = next((s for s in sessions if args.country.lower() in s["country_name"].lower()), sessions[0])
    key = session["session_key"]

    radio = sorted(
        [m for m in openf1("team_radio", session_key=key) if m["driver_number"] == args.driver],
        key=lambda m: m["date"],
    )
    name = next(
        (d.get("full_name", "") for d in openf1("drivers", session_key=key) if d["driver_number"] == args.driver),
        str(args.driver),
    )
    print(f"Session {key}: {session['country_name']} {args.year} - #{args.driver} {name}")
    print(f"{len(radio)} radio messages available\n")

    # Reproduce the discrimination run's sampling exactly: same stride, same split,
    # so the call clips under test are the same six clips that read "Tired".
    stride = max(1, len(radio) // (4 + args.calls))
    sample = radio[::stride][: 4 + args.calls]

    original_baseline = [c for c in (fetch_clip(m, i) for i, m in enumerate(sample[:4])) if c]
    call_clips = [c for c in (fetch_clip(m, i + 4) for i, m in enumerate(sample[4:])) if c]

    # A wider pool of calibration clips, drawn from radio the call clips do not use,
    # so the calibrated condition has enough material to clear the gate.
    used = {m["recording_url"] for m in sample}
    extra = [m for m in radio if m["recording_url"] not in used][: args.baseline]
    wide_baseline = [c for c in (fetch_clip(m, 100 + i) for i, m in enumerate(extra)) if c]

    print(f"call clips under test   {len(call_clips)}")
    print(f"narrow baseline pool    {len(original_baseline)}")
    print(f"wide baseline pool      {len(wide_baseline)}\n")

    backup = Path(str(STORE) + ".ablate-backup")
    if STORE.exists():
        shutil.copy2(STORE, backup)

    conditions = {}
    try:
        with httpx.Client(timeout=300) as client:
            conditions["A no baseline (priors)"] = score(client, call_clips, [])[0]
            conditions["B narrow baseline (as run)"] = score(client, call_clips, original_baseline)[0]
            conditions["C wide baseline"] = score(client, call_clips, wide_baseline)[0]
    finally:
        if backup.exists():
            shutil.copy2(backup, STORE)
            backup.unlink()

    for label, result in conditions.items():
        rows = result["rows"]
        if not rows:
            print(f"{label}: no clips scored")
            continue
        tag = "CALIBRATED" if result["calibrated"] else "UNCALIBRATED -> population priors"
        print(f"\n{'=' * 96}")
        print(f"{label}   baseline accepted {result['accepted']}   {tag}")
        print(f"{'=' * 96}")
        print(f"{'state':<10} {'load':>6} {'arous':>7} {'strain':>7} {'conf':<8} transcript")
        for row in rows:
            print(f"{row['state']:<10} {row['load']:>6} {row['arousal']:>7} {row['strain']:>7} "
                  f"{row['confidence']:<8} {row['text']!r}")
        print(f"-> states {dict(Counter(r['state'] for r in rows))}")

    print(f"\n{'=' * 96}\nVERDICT\n{'=' * 96}")
    baseline_states = [r["state"] for r in conditions["B narrow baseline (as run)"]["rows"]]
    wide_states = [r["state"] for r in conditions["C wide baseline"]["rows"]]
    if not baseline_states or not wide_states:
        print("  inconclusive - a condition scored no clips")
    elif baseline_states == wide_states:
        print("  states are IDENTICAL across baselines - the reading is a property of the audio,")
        print("  not of the prior fallback. The original interpretation stands.")
    else:
        moved = sum(a != b for a, b in zip(baseline_states, wide_states))
        print(f"  {moved} of {len(baseline_states)} states MOVED when the baseline was made valid.")
        print("  The original reading was substantially an artefact of falling back to")
        print("  population priors, not a measurement of this driver.")


if __name__ == "__main__":
    main()
