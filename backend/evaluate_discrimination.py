"""Does the reading discriminate, or does everything come out the same?

A driver-state tool that returns the same answer for every clip is not measuring
anything. This pulls radio for several drivers from one session, calibrates each
driver separately, and reports the spread of states, loads and confidence.

The honest question it answers: across many real clips, does the output vary,
and does it vary for reasons we can point at?

    .venv\\Scripts\\python.exe evaluate_discrimination.py --drivers 1 63 55 44
"""
import argparse
import io
import json
import shutil
import statistics as stats
import urllib.request
from collections import Counter
from pathlib import Path

import httpx
import soundfile as sf

API = "http://localhost:8000"
OPENF1 = "https://api.openf1.org/v1"
STORE = Path(__file__).parent / "data" / "session.json"


def openf1(path: str, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    request = urllib.request.Request(f"{OPENF1}/{path}?{query}", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def to_wav(raw: bytes) -> bytes:
    from transformers.pipelines.audio_utils import ffmpeg_read

    audio = ffmpeg_read(raw, 16000)
    buffer = io.BytesIO()
    sf.write(buffer, audio, 16000, format="WAV")
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--country", default="Belgium")
    parser.add_argument("--drivers", type=int, nargs="+", default=[1, 63, 55, 44])
    parser.add_argument("--baseline", type=int, default=4)
    parser.add_argument("--calls", type=int, default=6)
    args = parser.parse_args()

    sessions = openf1("sessions", year=args.year, session_name="Race")
    session = next((s for s in sessions if args.country.lower() in s["country_name"].lower()), sessions[0])
    key = session["session_key"]
    print(f"Session {key}: {session['country_name']} {args.year}\n")

    radio = openf1("team_radio", session_key=key)
    by_driver = {}
    for message in radio:
        by_driver.setdefault(message["driver_number"], []).append(message)

    names = {d["driver_number"]: d.get("full_name", "") for d in openf1("drivers", session_key=key)}

    backup = Path(str(STORE) + ".eval-backup")
    if STORE.exists():
        shutil.copy2(STORE, backup)

    rows = []
    try:
        with httpx.Client(timeout=300) as client:
            for number in args.drivers:
                messages = sorted(by_driver.get(number, []), key=lambda m: m["date"])
                if len(messages) < args.baseline + 2:
                    print(f"#{number} {names.get(number, '')}: only {len(messages)} messages, skipping")
                    continue

                client.post(f"{API}/api/session/reset")
                client.post(f"{API}/api/baseline/reset")

                stride = max(1, len(messages) // (args.baseline + args.calls))
                sample = messages[::stride][: args.baseline + args.calls]
                calibrated = 0

                for index, message in enumerate(sample):
                    try:
                        clip = to_wav(download(message["recording_url"]))
                    except Exception:
                        continue

                    if index < args.baseline:
                        response = client.post(
                            f"{API}/api/baseline", files={"file": ("b.wav", clip, "audio/wav")}
                        )
                        calibrated += response.status_code == 200
                        continue

                    response = client.post(
                        f"{API}/api/analyze",
                        files={"file": ("c.wav", clip, "audio/wav")},
                        data={"lap": index},
                    )
                    if response.status_code != 200:
                        continue

                    event = response.json()["event"]
                    rows.append(
                        {
                            "driver": f"#{number} {names.get(number, '')[:16]}",
                            "state": event["state"],
                            "load": event["driverLoad"],
                            "arousal": event["arousal"],
                            "strain": event["strain"],
                            "confidence": event["confidence"]["level"],
                            "usable": event["quality"]["usable"],
                            "intent": event["content"]["intent"],
                            "words": len(event["transcript"].split()),
                            "text": event["transcript"][:58],
                        }
                    )

                print(f"#{number} {names.get(number, ''):<18} calibrated on {calibrated}/{args.baseline}, "
                      f"{len([r for r in rows if r['driver'].startswith(f'#{number} ')])} calls analysed")
    finally:
        if backup.exists():
            shutil.copy2(backup, STORE)
            backup.unlink()

    if not rows:
        raise SystemExit("no clips analysed")

    print(f"\n{'driver':<22} {'state':<10} {'load':>5} {'arous':>6} {'strain':>6} {'conf':<7} {'intent':<20} transcript")
    print("-" * 132)
    for row in rows:
        print(f"{row['driver']:<22} {row['state']:<10} {row['load']:>5} {row['arousal']:>6} "
              f"{row['strain']:>6} {row['confidence']:<7} {row['intent']:<20} {row['text']!r}")

    loads = [r["load"] for r in rows]
    print(f"\n{'=' * 60}\nDISCRIMINATION\n{'=' * 60}")
    print(f"  clips analysed      {len(rows)}")
    print(f"  states             {dict(Counter(r['state'] for r in rows))}")
    print(f"  intents            {dict(Counter(r['intent'] for r in rows))}")
    print(f"  confidence         {dict(Counter(r['confidence'] for r in rows))}")
    print(f"  usable audio       {sum(r['usable'] for r in rows)}/{len(rows)}")
    print(f"  load range         {min(loads):.1f} - {max(loads):.1f}")
    print(f"  load spread (sd)   {stats.pstdev(loads):.1f}")
    print(f"  distinct states    {len(set(r['state'] for r in rows))} of 4")

    verdict = []
    if stats.pstdev(loads) < 5:
        verdict.append("load barely varies - the score is not discriminating")
    if len(set(r["state"] for r in rows)) < 2:
        verdict.append("every clip lands in one state - no discrimination at all")
    if sum(r["confidence"] == "High" for r in rows) / len(rows) < 0.3:
        verdict.append("fewer than a third of readings are high confidence")
    print("\n  " + ("\n  ".join(verdict) if verdict else "output varies across clips and drivers"))


if __name__ == "__main__":
    main()
