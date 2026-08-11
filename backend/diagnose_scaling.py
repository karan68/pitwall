"""Throwaway diagnostic: why does real broadcast audio read the way it does?

Extracts biomarkers directly (no server, no models beyond nothing) for the
baseline and call clips side by side, so the z-score scaling can be checked
against the actual spread of the recordings rather than guessed at.
"""
import json
import statistics as stats
import sys
from pathlib import Path

from services.features import extract, signal_quality
from services.audio_utils import load_audio
from services import state

FEATURES = ["f0MeanHz", "energyDb", "highFreqRatio", "jitterPct", "shimmerPct", "hnrDb", "pauseRatio"]


def measure(folder: Path) -> dict:
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    groups = {"baseline": [], "call": []}

    for clip in manifest["clips"]:
        audio, sr = load_audio((folder / clip["file"]).read_bytes())
        quality = signal_quality(audio, sr)
        features = extract(audio, sr, word_count=len(clip["groundTruth"].split()))
        features["_file"] = clip["file"]
        features["_usable"] = quality["usable"]
        features["_snr"] = quality["snrDb"]
        groups[clip["kind"]].append(features)
    return groups


def main(folder: Path) -> None:
    groups = measure(folder)
    usable_baseline = [f for f in groups["baseline"] if f["_usable"]]

    print(f"{'feature':<16} {'baseline median':>15} {'baseline MAD':>13} {'call median':>12} "
          f"{'call spread':>12} {'CoV%':>6}")
    print("-" * 82)

    for feature in FEATURES:
        base = [f[feature] for f in usable_baseline if f[feature]]
        call = [f[feature] for f in groups["call"] if f[feature]]
        if not base or not call:
            continue
        b_med = stats.median(base)
        b_mad = stats.median([abs(v - b_med) for v in base])
        c_med = stats.median(call)
        c_spread = stats.median([abs(v - c_med) for v in call])
        cov = abs(b_mad / b_med * 100) if b_med else 0
        print(f"{feature:<16} {b_med:>15.2f} {b_mad:>13.2f} {c_med:>12.2f} {c_spread:>12.2f} {cov:>6.1f}")

    print("\nWhat the current baseline turns those into:")
    baseline = state.build_baseline([{k: v for k, v in f.items() if not k.startswith('_')} for f in usable_baseline])
    for feature in FEATURES:
        stat = baseline["stats"].get(feature)
        prior = state.POPULATION_PRIORS.get(feature)
        if not stat or not prior:
            continue
        floored = abs(stat["spread"] - prior[1] * state.MIN_SPREAD_FRACTION) < 1e-6
        print(f"  {feature:<16} centre={stat['centre']:>8.2f}  spread={stat['spread']:>7.2f}"
              f"   {'<- FLOORED by clean-speech prior' if floored else ''}")

    print("\nResulting z-scores per call (clamped at +-4):")
    print(f"  {'clip':<14} {'arousal':>8} {'strain':>7}  {'state':<10} " +
          " ".join(f"{f[:9]:>9}" for f in FEATURES))
    for features in groups["call"]:
        clean = {k: v for k, v in features.items() if not k.startswith("_")}
        reading = state.classify(clean, baseline)
        z = reading["zScores"]
        print(f"  {features['_file']:<14} {reading['arousal']:>8.2f} {reading['strain']:>7.2f}  "
              f"{reading['state']:<10} " + " ".join(f"{z.get(f, 0):>9.2f}" for f in FEATURES))

    saturated = sum(1 for f in groups["call"]
                    for k, v in state.classify({k2: v2 for k2, v2 in f.items() if not k2.startswith('_')},
                                               baseline)["zScores"].items() if abs(v) >= 4.0)
    print(f"\n  z-scores pinned at the +-4 clamp: {saturated}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "sample_audio" / "real" / "LEWHAM01"
    main(target if target.is_absolute() else Path(__file__).parent / target)
