"""Run the analysis engine over a folder of clips and score it against ground truth.

Works with either a plain folder (files named baseline* are calibration) or a
manifest.json written by load_real_radio.py, which also carries the human
transcription for every clip so word error rate can be measured rather than
claimed.

Run with the backend up:
    .venv\\Scripts\\python.exe run_stint.py sample_audio\\real\\LEWHAM01
"""
import json
import re
import sys
from pathlib import Path

import httpx

API = "http://localhost:8000"
CALL_LAPS = [4, 7, 9, 12, 14, 17, 19, 22, 25, 28, 31, 34]

# The dataset identifies drivers by code and racing number only. Names are filled
# in for the codes where the pairing is unambiguous; anything else stays as the
# raw code rather than being guessed at.
DRIVER_NAMES = {
    "LEWHAM01": "Lewis Hamilton",
    "MAXVER01": "Max Verstappen",
    "SEBVET01": "Sebastian Vettel",
    "DANRIC01": "Daniel Ricciardo",
    "VALBOT01": "Valtteri Bottas",
    "NICHUL01": "Nico Hulkenberg",
    "CARSAI01": "Carlos Sainz",
    "CHALEC01": "Charles Leclerc",
}


def session_context(manifest: dict, clips: list[dict]) -> dict:
    driver_id = manifest.get("driverId", "")
    first = clips[0] if clips else {}
    number = first.get("racingNumber")
    name = DRIVER_NAMES.get(driver_id, driver_id)

    return {
        "driver": f"{name}{f' #{number}' if number else ''}",
        "team": driver_id,
        "stint": first.get("grandPrix", "Session"),
        "provenance": {
            "audio": f"Real broadcast radio — Hugging Face {manifest.get('dataset')} (CC BY 4.0)",
            "transcripts": "Whisper small.en running locally, scored against the dataset's human transcriptions",
            "lapTimes": "Synthetic — illustrative only. This dataset carries no lap timing.",
        },
    }


def word_error_rate(reference: str, hypothesis: str) -> tuple[float, int]:
    """Standard WER: Levenshtein distance over words, normalised by reference length."""
    ref = _normalise_words(reference)
    hyp = _normalise_words(hypothesis)
    if not ref:
        return (0.0, 0) if not hyp else (1.0, len(hyp))

    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        current = [i]
        for j, h in enumerate(hyp, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (r != h)))
        previous = current
    return previous[-1] / len(ref), len(ref)


def _normalise_words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9' ]", " ", (text or "").lower()).split()


def load_clips(folder: Path) -> tuple[list[dict], dict]:
    manifest_path = folder / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return manifest["clips"], manifest

    clips = [
        {"file": p.name, "kind": "baseline" if p.stem.startswith("baseline") else "call", "groundTruth": None}
        for p in sorted(folder.glob("*.wav"))
    ]
    return clips, {"dataset": "local folder", "driverId": folder.name}


def main(folder: Path) -> None:
    clips, manifest = load_clips(folder)
    baselines = [c for c in clips if c["kind"] == "baseline"]
    calls = [c for c in clips if c["kind"] == "call"]

    print(f"Source: {manifest.get('dataset')}  driver: {manifest.get('driverId')}")
    print(f"{len(baselines)} baseline clips, {len(calls)} radio calls\n")

    with httpx.Client(timeout=300) as client:
        client.post(f"{API}/api/session/reset")
        client.post(f"{API}/api/baseline/reset")
        client.post(f"{API}/api/session/context", json=session_context(manifest, clips))

        print("Calibrating")
        for clip in baselines:
            response = client.post(
                f"{API}/api/baseline",
                files={"file": (clip["file"], (folder / clip["file"]).read_bytes(), "audio/wav")},
            )
            status = "ok" if response.status_code == 200 else f"REJECTED: {response.json().get('detail')}"
            print(f"  {clip['file']:<16} {status}")

        print(f"\nAnalysing {len(calls)} calls")
        header = f"  {'clip':<14} {'lap':>3} {'state':<10} {'load':>5} {'window':<8} {'qual':>5} intent"
        print(header)
        print("  " + "-" * (len(header) - 2))

        errors, ref_words, scored = 0.0, 0, 0
        rows = []
        for index, clip in enumerate(calls):
            lap = CALL_LAPS[index % len(CALL_LAPS)]
            response = client.post(
                f"{API}/api/analyze",
                files={"file": (clip["file"], (folder / clip["file"]).read_bytes(), "audio/wav")},
                data={"lap": lap},
            )
            if response.status_code != 200:
                print(f"  {clip['file']:<14} {lap:>3} FAILED {response.text[:80]}")
                continue

            event = response.json()["event"]
            quality = "ok" if event["quality"]["usable"] else "poor"
            print(
                f"  {clip['file']:<14} {lap:>3} {event['state']:<10} {event['driverLoad']:>5} "
                f"{event['recommendation']['radioWindow']:<8} {quality:>5} {event['content']['intent']}"
            )

            if clip.get("groundTruth"):
                rate, count = word_error_rate(clip["groundTruth"], event["transcript"])
                errors += rate * count
                ref_words += count
                scored += 1
                rows.append((clip["file"], clip["groundTruth"], event["transcript"], rate))

        if scored:
            print(f"\nASR accuracy on real broadcast audio ({scored} clips, {ref_words} reference words)")
            print(f"  word error rate: {errors / ref_words * 100:.1f}%")
            worst = max(rows, key=lambda r: r[3])
            best = min(rows, key=lambda r: r[3])
            for label, row in (("best", best), ("worst", worst)):
                print(f"\n  {label} ({row[3] * 100:.0f}% WER)")
                print(f"    truth: \"{row[1][:150]}\"")
                print(f"    ours : \"{row[2][:150]}\"")

        summary = client.get(f"{API}/api/session").json()
        print(f"\n{summary['analytics']['note']}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "sample_audio" / "real" / "LEWHAM01"
    if not target.is_absolute():
        target = Path(__file__).parent / target
    main(target)
