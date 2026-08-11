"""Build a stint from OpenF1: real team radio paired with real lap timing.

The Hugging Face dataset gives excellent audio but carries no lap times, so any
correlation drawn against it is illustrative. OpenF1 publishes team radio and
lap timing keyed to the same session, so a radio message can be placed on the
lap it was actually transmitted during, and the correlation becomes real.

Real timing is messy: red flags, safety cars and pit laps produce durations that
are not racing laps. Those are kept in the series because they happened, but
excluded from the reference pace so they cannot distort the baseline.

    .venv\\Scripts\\python.exe load_openf1_stint.py --year 2024 --driver 81
"""
import argparse
import io
import json
import urllib.request
from datetime import datetime
from pathlib import Path

import soundfile as sf

BASE = "https://api.openf1.org/v1"
OUT_ROOT = Path(__file__).parent / "sample_audio" / "openf1"

# A lap far off the median is a pit stop, safety car or red flag, not racing pace.
RACING_LAP_TOLERANCE = 1.25


def api(path: str, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    request = urllib.request.Request(f"{BASE}/{path}?{query}", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode())


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def pick_session(year: int, country: str | None) -> dict:
    sessions = api("sessions", year=year, session_name="Race")
    if country:
        sessions = [s for s in sessions if country.lower() in s["country_name"].lower()] or sessions
    return sessions[0]


def radio_to_lap(message_time: datetime, laps: list[dict]) -> dict | None:
    """The lap in progress when the message was transmitted."""
    current = None
    for lap in laps:
        if not lap.get("date_start"):
            continue
        if parse_time(lap["date_start"]) <= message_time:
            current = lap
        else:
            break
    return current


def reference_pace(laps: list[dict]) -> tuple[float, list[int]]:
    """Median racing pace, and which laps were excluded from it."""
    times = sorted(lap["lap_duration"] for lap in laps if lap.get("lap_duration"))
    if not times:
        return 0.0, []
    median = times[len(times) // 2]
    racing = [t for t in times if t <= median * RACING_LAP_TOLERANCE]
    excluded = [
        lap["lap_number"]
        for lap in laps
        if lap.get("lap_duration") and lap["lap_duration"] > median * RACING_LAP_TOLERANCE
    ]
    return (sum(racing) / len(racing) if racing else median), excluded


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--country", default=None, help="e.g. Belgium")
    parser.add_argument("--driver", type=int, default=None, help="racing number")
    parser.add_argument("--baseline", type=int, default=5)
    args = parser.parse_args()

    session = pick_session(args.year, args.country)
    key = session["session_key"]
    print(f"Session {key}: {session['country_name']} {session['session_name']} {session['date_start'][:10]}")

    radio = api("team_radio", session_key=key)
    by_driver: dict[int, list] = {}
    for message in radio:
        by_driver.setdefault(message["driver_number"], []).append(message)
    if not by_driver:
        raise SystemExit("no team radio in this session")

    driver = args.driver or max(by_driver, key=lambda d: len(by_driver[d]))
    messages = sorted(by_driver.get(driver, []), key=lambda m: m["date"])
    print(f"Driver #{driver}: {len(messages)} radio messages")

    laps = sorted(
        [lap for lap in api("laps", session_key=key, driver_number=driver) if lap.get("lap_duration")],
        key=lambda lap: lap["lap_number"],
    )
    pace, excluded = reference_pace(laps)
    print(f"{len(laps)} timed laps, reference racing pace {pace:.3f}s")
    print(f"  excluded from reference (pit/SC/red flag): {excluded or 'none'}")

    drivers = {d["driver_number"]: d for d in api("drivers", session_key=key)}
    info = drivers.get(driver, {})
    name = info.get("full_name") or info.get("broadcast_name") or f"#{driver}"

    out_dir = OUT_ROOT / f"{key}_{driver}"
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.wav"):
        stale.unlink()

    manifest = {
        "dataset": f"OpenF1 session {key} ({session['country_name']} {args.year})",
        "driverId": f"#{driver} {name}",
        "sessionKey": key,
        "referenceLapSeconds": round(pace, 3),
        "laps": [
            {
                "lap": lap["lap_number"],
                "timeSeconds": round(lap["lap_duration"], 3),
                "representative": lap["lap_duration"] <= pace * RACING_LAP_TOLERANCE,
            }
            for lap in laps
        ],
        "clips": [],
    }

    print(f"\nDownloading {len(messages)} clips")
    for index, message in enumerate(messages):
        lap = radio_to_lap(parse_time(message["date"]), laps)
        kind = "baseline" if index < args.baseline else "call"
        name_out = f"{kind}_{index + 1:02d}.wav"

        try:
            request = urllib.request.Request(message["recording_url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
            from transformers.pipelines.audio_utils import ffmpeg_read

            audio = ffmpeg_read(raw, 16000)
            sf.write(out_dir / name_out, audio, 16000)
        except Exception as exc:
            print(f"  {name_out}  FAILED {exc}")
            continue

        manifest["clips"].append(
            {
                "file": name_out,
                "kind": kind,
                "lap": lap["lap_number"] if lap else None,
                "lapTimeSeconds": round(lap["lap_duration"], 3) if lap else None,
                "transmittedAt": message["date"],
                "groundTruth": None,
                "durationSeconds": round(len(audio) / 16000, 2),
            }
        )
        lap_note = f"lap {lap['lap_number']} ({lap['lap_duration']:.3f}s)" if lap else "no lap match"
        print(f"  {name_out}  {len(audio) / 16000:5.1f}s  {lap_note}")

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nWrote {len(manifest['clips'])} clips + {len(manifest['laps'])} real laps to {out_dir}")


if __name__ == "__main__":
    main()
