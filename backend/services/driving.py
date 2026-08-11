"""Driver input telemetry as an independent channel.

The voice reading says how a driver sounds. This says how they were actually
driving on the same lap. It is deliberately kept as a *cross-check* rather than
folded into the driver-state score: rough inputs can come from traffic, tyre
state or track conditions just as easily as from the driver, so agreement
between the two channels is evidence and disagreement is a question, but
neither is proof on its own.

Metrics are scored against the driver's own median across the stint, the same
way the voice biomarkers are scored against their own baseline.
"""
import numpy as np

_MAD_TO_SIGMA = 0.6745
THROTTLE_ON = 50.0
# Below this the sample count cannot support a stable per-lap figure.
MIN_SAMPLES = 40


def lap_metrics(samples: list[dict], duration_seconds: float) -> dict | None:
    """Per-lap driver input activity, normalised so laps of different length compare."""
    throttle = [s["throttle"] for s in samples if s.get("throttle") is not None]
    brake = [s["brake"] for s in samples if s.get("brake") is not None]

    if len(throttle) < MIN_SAMPLES or duration_seconds <= 0:
        return None

    minutes = duration_seconds / 60.0
    lifts = sum(1 for a, b in zip(throttle, throttle[1:]) if a > THROTTLE_ON >= b)
    applications = sum(1 for a, b in zip(brake, brake[1:]) if a == 0 and b > 0)

    return {
        "throttleLiftsPerMin": round(lifts / minutes, 2),
        "brakeApplicationsPerMin": round(applications / minutes, 2),
        "throttleChatter": round(float(np.mean(np.abs(np.diff(throttle)))), 2),
        "meanThrottlePct": round(float(np.mean(throttle)), 1),
        "sampleCount": len(throttle),
    }


ROUGHNESS_FEATURES = {
    "throttleLiftsPerMin": 1.0,
    "brakeApplicationsPerMin": 0.8,
    "throttleChatter": 1.0,
}


def score_stint(laps: list[dict]) -> dict:
    """Turn per-lap metrics into a roughness z-score against this driver's own stint."""
    measured = [lap for lap in laps if lap.get("driving")]
    if len(measured) < 4:
        return {"available": False, "reason": f"only {len(measured)} laps carry input telemetry"}

    centres, spreads = {}, {}
    for feature in ROUGHNESS_FEATURES:
        values = [lap["driving"][feature] for lap in measured]
        centre = float(np.median(values))
        mad = float(np.median([abs(v - centre) for v in values]))
        centres[feature] = centre
        # A stint with near-identical laps must not turn noise into a large z.
        spreads[feature] = max(mad / _MAD_TO_SIGMA, abs(centre) * 0.15, 1e-6)

    scored = {}
    for lap in measured:
        total = sum(abs(w) for w in ROUGHNESS_FEATURES.values())
        roughness = sum(
            (lap["driving"][feature] - centres[feature]) / spreads[feature] * weight
            for feature, weight in ROUGHNESS_FEATURES.items()
        ) / total
        scored[lap["lap"]] = round(float(np.clip(roughness, -4, 4)), 2)

    return {"available": True, "roughnessByLap": scored, "lapsMeasured": len(measured)}


def cross_check(voice_load: float, roughness: float | None) -> dict:
    """Do the two channels agree about this lap?"""
    if roughness is None:
        return {
            "status": "unavailable",
            "detail": "No driver input telemetry for this lap.",
        }

    voice_elevated = voice_load > 58
    inputs_rough = roughness >= 0.6

    if voice_elevated and inputs_rough:
        return {
            "status": "agree",
            "detail": "Voice load is up and the driving inputs are rougher than this driver's own "
            "stint median. Two independent channels pointing the same way.",
        }
    if not voice_elevated and not inputs_rough:
        return {
            "status": "agree",
            "detail": "Voice reads normal and the driving inputs are within this driver's usual range.",
        }
    if voice_elevated and not inputs_rough:
        return {
            "status": "voice-only",
            "detail": "The voice reads loaded but the driving is still clean. Often the useful case: "
            "the driver is absorbing it without it reaching the car yet.",
        }
    return {
        "status": "inputs-only",
        "detail": "The driving is rougher than usual while the voice reads normal. Traffic, tyres or "
        "track can all do this, so treat it as a prompt to check telemetry, not a driver-state call.",
    }
