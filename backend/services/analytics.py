"""Relating driver load to lap time, in seconds, with the statistics stated plainly.

A correlation drawn from five radio calls is not evidence, so every result here
carries its sample size and is suppressed outright when there is too little
data to say anything. Overstating this is the fastest way to lose a race
engineer's trust.
"""
import numpy as np

MIN_PAIRS_FOR_CORRELATION = 5
NEUTRAL_LOAD = 50.0
# Below this the driver is working, not struggling; no time is attributed to load.
COST_THRESHOLD = 58.0
DECAY_PER_LAP = 0.45


def load_series(laps: list[dict], events: list[dict]) -> list[dict]:
    """Per-lap driver load, decaying back toward neutral between radio calls."""
    by_lap: dict[int, list[float]] = {}
    for event in events:
        by_lap.setdefault(event["lap"], []).append(event["driverLoad"])

    series, current = [], None
    for lap in laps:
        number = lap["lap"]
        if number in by_lap:
            current = float(np.mean(by_lap[number]))
            measured = True
        elif current is not None:
            current = NEUTRAL_LOAD + (current - NEUTRAL_LOAD) * (1 - DECAY_PER_LAP)
            measured = False
        else:
            measured = False

        series.append(
            {
                "lap": number,
                "timeSeconds": lap["timeSeconds"],
                "load": round(current, 1) if current is not None else None,
                "measured": measured,
            }
        )
    return series


def analyze(laps: list[dict], events: list[dict], reference_lap: float) -> dict:
    series = load_series(laps, events)
    paired = [p for p in series if p["load"] is not None]
    # Only laps with an actual radio call are evidence. The decayed values in
    # between are interpolation and must not inflate the sample size.
    measured = sum(1 for p in series if p["measured"])

    if measured < MIN_PAIRS_FOR_CORRELATION:
        return {
            "series": series,
            "sufficientData": False,
            "note": f"{measured} of {MIN_PAIRS_FOR_CORRELATION} radio calls needed before "
            "any load-to-lap-time relationship is worth reporting.",
            "sampleSize": measured,
        }

    loads = np.array([p["load"] for p in paired])
    deltas = np.array([p["timeSeconds"] - reference_lap for p in paired])

    best = {"lagLaps": 0, "r": 0.0}
    for lag in (0, 1, 2):
        if len(loads) - lag < MIN_PAIRS_FOR_CORRELATION:
            continue
        x, y = (loads[: len(loads) - lag], deltas[lag:]) if lag else (loads, deltas)
        r = _pearson(x, y)
        if abs(r) > abs(best["r"]):
            best = {"lagLaps": lag, "r": round(r, 2)}

    lag = best["lagLaps"]
    x, y = (loads[: len(loads) - lag], deltas[lag:]) if lag else (loads, deltas)
    slope = float(np.polyfit(x, y, 1)[0]) if np.std(x) > 1e-9 else 0.0

    elevated = np.maximum(loads - COST_THRESHOLD, 0)
    seconds_lost = float(np.sum(elevated * max(slope, 0.0)))

    return {
        "series": series,
        "sufficientData": True,
        "sampleSize": measured,
        "lapsCovered": len(paired),
        "correlation": best["r"],
        "lagLaps": lag,
        "strength": _strength(best["r"]),
        "secondsPerLoadPoint": round(slope, 3),
        "estimatedSecondsLost": round(seconds_lost, 2),
        "lapsAffected": int((loads > COST_THRESHOLD).sum()),
        "note": _note(best["r"], lag, measured),
    }


def _pearson(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3 or np.std(x) < 1e-9 or np.std(y) < 1e-9:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def _strength(r: float) -> str:
    magnitude = abs(r)
    if magnitude >= 0.7:
        return "Strong"
    if magnitude >= 0.4:
        return "Moderate"
    if magnitude >= 0.2:
        return "Weak"
    return "None detected"


def _note(r: float, lag: int, n: int) -> str:
    if abs(r) < 0.2:
        return f"No usable relationship in this stint (n={n} calls). Driver load is not explaining lap time here."
    timing = (
        "Load and lap-time loss move together in the same lap."
        if lag == 0
        else f"Load leads lap-time loss by {lag} lap{'s' if lag > 1 else ''}, "
        "which is the margin the pit wall gets to act in."
    )
    return f"{timing} Based on n={n} radio calls — indicative, not a validated model."
