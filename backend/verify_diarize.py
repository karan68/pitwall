"""Does within-clip diarisation actually separate two speakers, or is it guessing?

speaker.py already failed at cross-clip identity (separation 0.011), so nothing
here is assumed to work. Two measurements, both with ground truth:

  A. Exact boundary. Concatenate a clip from one driver's radio with a clip from
     another team's radio. Different teams are different channels, and the join
     sample is known exactly, so every window has a true source. Chance is 50%.

  B. Negative control. Concatenate a clip with more of *itself*. Same channel,
     same speakers, no boundary. Anything that reports two speakers here is
     splitting on noise, and a method that always says "two" would score well on
     A alone.

The gap between the separation scores of A and B is what sets
SEPARATION_THRESHOLD. The script prints the value that best splits them rather
than taking the constant on trust.

    .venv\\Scripts\\python.exe verify_diarize.py
"""
import io
import json
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf

from services.diarize import HOP_SECONDS, diarize

OPENF1 = "https://api.openf1.org/v1"
CACHE = Path(__file__).parent / "data" / "diarize_cache"
SR = 16000


def openf1(path: str, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    request = urllib.request.Request(f"{OPENF1}/{path}?{query}", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


def clip(url: str, name: str) -> np.ndarray | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{name}.wav"
    if path.exists():
        return sf.read(path)[0]

    from transformers.pipelines.audio_utils import ffmpeg_read

    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            audio = ffmpeg_read(response.read(), SR)
    except Exception:
        return None
    sf.write(path, audio, SR)
    return audio


def channel_features(chunks: list[np.ndarray], sr: int) -> np.ndarray:
    """Kept only so this file documents what is being compared; the real one lives
    in services.diarize and is what the measurement below exercises."""
    from services.diarize import _channel_features

    return _channel_features(chunks, sr)


def window_accuracy(result: dict, boundary: int) -> float:
    """Cluster ids are arbitrary, so score the better of the two mappings."""
    labels, spans = np.array(result["labels"]), result["spans"]
    if not len(labels):
        return float("nan")
    truth = np.array([1 if (s + e) / 2 >= boundary else 0 for s, e in spans])
    agree = float(np.mean(labels == truth))
    return max(agree, 1.0 - agree)


def run(representation: str, usable: dict[int, list[np.ndarray]]) -> dict:
    numbers = sorted(usable)

    print(f"\nA. two channels joined at a known boundary  [{representation}]")
    print(f"  {'pair':<16} {'speakers':>8} {'separation':>11} {'window acc':>11}")
    two_speaker, accuracies, detected = [], [], 0
    for i, a in enumerate(numbers):
        for b in numbers[i + 1:]:
            first, second = usable[a][0], usable[b][0]
            result = diarize(np.concatenate([first, second]), SR, representation)
            accuracy = window_accuracy(result, len(first))
            two_speaker.append(result["separation"])
            accuracies.append(accuracy)
            detected += result["speakers"] == 2
            print(f"  #{a} + #{b:<11} {result['speakers']:>8} {result['separation']:>11.3f} {accuracy:>10.0%}")

    # A clip joined to an exact copy of itself. Same channel, same speakers, no
    # boundary to find. The previous version of this control joined two different
    # transmissions from one driver, which is not one speaker at all: each of
    # those already contains both the driver and their engineer.
    print(f"\nB. negative control - a clip joined to a copy of itself  [{representation}]")
    print(f"  {'clip':<16} {'speakers':>8} {'separation':>11}")
    one_speaker, false_splits = [], 0
    for number in numbers:
        result = diarize(np.concatenate([usable[number][0], usable[number][0]]), SR, representation)
        one_speaker.append(result["separation"])
        false_splits += result["speakers"] == 2
        print(f"  #{number:<15} {result['speakers']:>8} {result['separation']:>11.3f}")

    return {
        "two": two_speaker,
        "one": one_speaker,
        "accuracy": float(np.nanmean(accuracies)),
        "detected": detected,
        "false": false_splits,
    }


def main() -> None:
    sessions = openf1("sessions", year=2024, session_name="Race")
    session = next(s for s in sessions if "Belgium" in s["country_name"])
    key = session["session_key"]
    print(f"Session {key}: {session['country_name']} 2024\n")

    radio = openf1("team_radio", session_key=key)
    by_driver: dict[int, list] = {}
    for message in radio:
        by_driver.setdefault(message["driver_number"], []).append(message)

    # Different teams, so genuinely different radio channels.
    drivers = [1, 63, 55, 44, 81, 16]
    pool: dict[int, list[np.ndarray]] = {}
    for number in drivers:
        for index, message in enumerate(sorted(by_driver.get(number, []), key=lambda m: m["date"])[:4]):
            audio = clip(message["recording_url"], f"{number}_{index}")
            if audio is not None and len(audio) >= int(3.5 * SR):
                pool.setdefault(number, []).append(audio)

    usable = {n: c for n, c in pool.items() if len(c) >= 2}
    print("clips available: " + ", ".join(f"#{n}={len(c)}" for n, c in usable.items()))

    if len(usable) < 2:
        raise SystemExit("not enough clips downloaded to measure")

    results = {name: run(name, usable) for name in ("speaker", "channel")}

    print(f"\n{'=' * 72}\nRESULT\n{'=' * 72}")
    print(f"  {'representation':<16} {'window acc':>11} {'2-spk sep':>10} {'1-spk sep':>10} {'gap':>8} {'false':>7}")
    for name, r in results.items():
        gap = float(np.mean(r["two"])) - float(np.mean(r["one"]))
        print(f"  {name:<16} {r['accuracy']:>10.0%} {np.mean(r['two']):>10.3f} "
              f"{np.mean(r['one']):>10.3f} {gap:>+8.3f} {r['false']}/{len(r['one'])}")
    print("  chance             50%")

    best = max(results, key=lambda n: results[n]["accuracy"])
    r = results[best]
    gap = float(np.mean(r["two"])) - float(np.mean(r["one"]))

    scores = [(s, 1) for s in r["two"]] + [(s, 0) for s in r["one"]]
    candidates = np.linspace(0.0, 1.0, 201)
    threshold = max(candidates, key=lambda t: sum((s >= t) == bool(y) for s, y in scores))
    correct = sum((s >= threshold) == bool(y) for s, y in scores)
    print(f"\n  best representation      {best}")
    print(f"  best threshold           {threshold:.2f} -> {correct}/{len(scores)} correct")

    print()
    if r["accuracy"] > 0.75 and gap > 0.05:
        print(f"  Separates real channels above chance using the {best} representation.")
        print(f"  Worth wiring in, with SEPARATION_THRESHOLD = {threshold:.2f}.")
    else:
        print("  Does NOT separate reliably under either representation. Do not wire")
        print("  this into the pipeline; record the negative result as speaker.py does.")


if __name__ == "__main__":
    main()
