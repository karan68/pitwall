"""Driver state as a deviation from that driver's own voice, not an absolute label.

Two design choices carry the whole system:

1. Everything is scored against the driver's personal baseline. A driver with a
   naturally high, fast voice is not permanently "stressed"; what matters is
   the change from how *they* normally sound.

2. State is two-dimensional. Arousal alone cannot separate a driver who is
   overloaded from one who is simply attacking, and it cannot see fatigue at
   all. Splitting arousal from vocal strain gives four states, one of which
   (Locked In) is a *good* state that still warrants radio silence.
"""
import numpy as np

# Robust z-scores: median + MAD, because a stint gives us a handful of samples
# and one shouted call would wreck a mean/std baseline.
_MAD_TO_SIGMA = 0.6745

# Fallback spread used before a driver is calibrated, so an uncalibrated
# reading degrades to "roughly typical adult speech" instead of dividing by zero.
POPULATION_PRIORS = {
    "f0MeanHz": (145.0, 35.0),
    "energyDb": (-14.0, 6.0),
    "articulationRate": (3.4, 1.0),
    "highFreqRatio": (0.22, 0.10),
    "jitterPct": (1.6, 0.9),
    "shimmerPct": (9.0, 4.0),
    "hnrDb": (8.0, 4.0),
    "pauseRatio": (0.45, 0.15),
}

AROUSAL_FEATURES = {
    "f0MeanHz": 1.0,
    "articulationRate": 1.0,
    # Spectral tilt is the level-invariant vocal-effort correlate. Absolute
    # loudness is deliberately absent: on broadcast radio dBFS is set by the TV
    # mix, not the driver. Measured on real F1 audio it differed by 8.5 dB
    # between clips of the same driver and swamped every other signal.
    "highFreqRatio": 0.6,
}

# Negative weight means "lower is worse": harmonics-to-noise falls as the voice strains.
STRAIN_FEATURES = {
    "jitterPct": 1.0,
    "shimmerPct": 0.9,
    "hnrDb": -1.0,
    "pauseRatio": 0.6,
}

MIN_BASELINE_SAMPLES = 3
QUADRANT_THRESHOLD = 0.6
# A handful of calibration clips cannot resolve spread better than this, and
# without the clamp a tight baseline turns ordinary speech into a z of 20.
MIN_SPREAD_FRACTION = 0.5
Z_CLAMP = 4.0

# Cycle-to-cycle measures scale with recording noise, so their usable resolution
# is proportional to the level measured rather than a fixed constant. Without
# this, ordinary variation in broadcast quality pinned them at the clamp.
RELATIVE_SPREAD_FLOOR = {"jitterPct": 0.5, "shimmerPct": 0.4, "hnrDb": 0.5}

# Beyond this gap between a call's SNR and the baseline's, the strain axis is
# comparing recording conditions rather than the voice.
COMPARABLE_SNR_DB = 6.0

STATE_DESCRIPTIONS = {
    "Locked In": "High effort, clean voice. Driver is on it — this is performance, not distress.",
    "Stressed": "High effort with vocal strain. Capacity is being consumed; error risk rises.",
    "Tired": "Effort dropping while strain stays high. Physical or mental fatigue.",
    "Calm": "Close to this driver's normal voice. Spare capacity available.",
}


def _robust_stats(values: list[float]) -> tuple[float, float]:
    arr = np.asarray(values, dtype=float)
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median)))
    sigma = mad / _MAD_TO_SIGMA
    return median, sigma


def build_baseline(samples: list[dict]) -> dict:
    """Turn stored calibration clips into per-feature centre and spread."""
    calibrated = len(samples) >= MIN_BASELINE_SAMPLES
    stats = {}

    for feature, (prior_centre, prior_spread) in POPULATION_PRIORS.items():
        values = [s[feature] for s in samples if s.get(feature)]
        if calibrated and len(values) >= MIN_BASELINE_SAMPLES:
            centre, spread = _robust_stats(values)
            spread = max(
                spread,
                prior_spread * MIN_SPREAD_FRACTION,
                abs(centre) * RELATIVE_SPREAD_FLOOR.get(feature, 0.0),
            )
        else:
            centre, spread = prior_centre, prior_spread
        stats[feature] = {"centre": round(centre, 3), "spread": round(spread, 3)}

    snrs = [s["snrDb"] for s in samples if s.get("snrDb") is not None]

    return {
        "calibrated": calibrated,
        "sampleCount": len(samples),
        "samplesNeeded": max(0, MIN_BASELINE_SAMPLES - len(samples)),
        "snrDb": round(float(np.median(snrs)), 1) if snrs else None,
        "stats": stats,
    }


def _z_scores(features: dict, baseline: dict) -> dict:
    scores = {}
    for feature, stat in baseline["stats"].items():
        value = features.get(feature, 0.0)
        if not value:
            continue
        z = (value - stat["centre"]) / max(stat["spread"], 1e-6)
        scores[feature] = round(float(np.clip(z, -Z_CLAMP, Z_CLAMP)), 2)
    return scores


def _weighted_axis(z_scores: dict, weights: dict) -> float:
    used = {f: w for f, w in weights.items() if f in z_scores}
    if not used:
        return 0.0
    total = sum(abs(w) for w in used.values())
    return sum(z_scores[f] * w for f, w in used.items()) / total


def classify(features: dict, baseline: dict, snr_db: float | None = None) -> dict:
    z_scores = _z_scores(features, baseline)
    arousal = _weighted_axis(z_scores, AROUSAL_FEATURES)
    strain = _weighted_axis(z_scores, STRAIN_FEATURES)

    high_arousal = arousal >= QUADRANT_THRESHOLD
    high_strain = strain >= QUADRANT_THRESHOLD

    if high_arousal and high_strain:
        state = "Stressed"
    elif high_arousal:
        state = "Locked In"
    elif high_strain:
        state = "Tired"
    else:
        state = "Calm"

    # Load is capacity consumed, so a Locked In driver still reads high: they are
    # working hard, they just are not in trouble.
    load = 50 + 16 * (0.45 * arousal + 0.55 * strain)

    return {
        "state": state,
        "description": STATE_DESCRIPTIONS[state],
        "arousal": round(arousal, 2),
        "strain": round(strain, 2),
        "driverLoad": round(float(np.clip(load, 0, 100)), 1),
        "zScores": z_scores,
        "calibrated": baseline["calibrated"],
        "confidence": _confidence(baseline, z_scores, arousal, strain, snr_db),
        "drivers": _top_drivers(z_scores),
    }


def _snr_gap(baseline: dict, snr_db: float | None) -> float | None:
    if snr_db is None or baseline.get("snrDb") is None:
        return None
    return abs(snr_db - baseline["snrDb"])


def _confidence(baseline: dict, z_scores: dict, arousal: float, strain: float,
                snr_db: float | None = None) -> dict:
    """State how much to trust this reading, and say so in words."""
    if not baseline["calibrated"]:
        return {
            "level": "Low",
            "reason": f"Uncalibrated — {baseline['samplesNeeded']} more baseline clip(s) needed. "
            "Scored against population averages.",
        }
    if len(z_scores) < 5:
        return {"level": "Low", "reason": "Too few usable voice measurements in this clip."}

    gap = _snr_gap(baseline, snr_db)
    if gap is not None and gap > COMPARABLE_SNR_DB:
        return {
            "level": "Low",
            "reason": f"This clip's signal-to-noise ratio differs from the baseline by {gap:.0f} dB. "
            "Voice-instability measures move with recording quality, so the strain reading is "
            "comparing conditions as much as the driver.",
        }

    if max(abs(arousal), abs(strain)) < 0.35:
        return {"level": "Medium", "reason": "Reading sits close to this driver's normal voice."}
    return {"level": "High", "reason": f"Calibrated on {baseline['sampleCount']} clips."}


def _top_drivers(z_scores: dict, limit: int = 3) -> list[dict]:
    """The measurements actually pushing this reading, so the label is auditable."""
    labels = {
        "f0MeanHz": "pitch",
        "energyDb": "loudness",
        "articulationRate": "speech rate",
        "highFreqRatio": "vocal effort",
        "jitterPct": "pitch instability",
        "shimmerPct": "volume instability",
        "hnrDb": "voice clarity",
        "pauseRatio": "pausing",
    }
    ranked = sorted(z_scores.items(), key=lambda kv: abs(kv[1]), reverse=True)[:limit]
    return [
        {
            "feature": labels.get(name, name),
            "z": z,
            "direction": "above" if z > 0 else "below",
        }
        for name, z in ranked
        if abs(z) >= 0.4
    ]
