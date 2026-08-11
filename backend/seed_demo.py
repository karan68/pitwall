"""Load a full stint into the running backend from a folder of clips.

Files named `baseline*` are registered as the driver's calm reference; every
other clip is analysed as a radio call. Lap numbers come from the order of the
`CALL_LAPS` list so a demo is reproducible run to run.

Run (backend must be up):
    .venv\\Scripts\\python.exe seed_demo.py [folder]
"""
import sys
from pathlib import Path

import httpx

API = "http://localhost:8000"
CALL_LAPS = [4, 8, 9, 10, 13, 17]


def main(folder: Path) -> None:
    clips = sorted(folder.glob("*.wav"))
    if not clips:
        sys.exit(f"No .wav files in {folder}")

    baselines = [c for c in clips if c.stem.startswith("baseline")]
    calls = [c for c in clips if not c.stem.startswith("baseline")]

    with httpx.Client(timeout=180) as client:
        client.post(f"{API}/api/session/reset")
        client.post(f"{API}/api/baseline/reset")

        print(f"Calibrating on {len(baselines)} clips")
        for clip in baselines:
            response = client.post(
                f"{API}/api/baseline", files={"file": (clip.name, clip.read_bytes(), "audio/wav")}
            )
            response.raise_for_status()
            print(f"  {clip.stem:<12} baseline sample added")

        print(f"\nAnalysing {len(calls)} radio calls")
        print(f"  {'clip':<12} {'lap':>3}  {'state':<10} {'load':>5}  {'window':<8} intent")
        print(f"  {'-' * 68}")

        for index, clip in enumerate(calls):
            lap = CALL_LAPS[index % len(CALL_LAPS)]
            response = client.post(
                f"{API}/api/analyze",
                files={"file": (clip.name, clip.read_bytes(), "audio/wav")},
                data={"lap": lap},
            )
            response.raise_for_status()
            event = response.json()["event"]
            print(
                f"  {clip.stem:<12} {lap:>3}  {event['state']:<10} {event['driverLoad']:>5}  "
                f"{event['recommendation']['radioWindow']:<8} {event['content']['intent']}"
            )

        summary = client.get(f"{API}/api/session").json()["analytics"]
        print(f"\n{summary['note']}")
        if summary["sufficientData"]:
            print(
                f"r={summary['correlation']} lag={summary['lagLaps']} lap(s) "
                f"estimated cost={summary['estimatedSecondsLost']}s over {summary['lapsAffected']} laps"
            )


if __name__ == "__main__":
    default = Path(__file__).parent / "sample_audio" / "placeholder"
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else default)
