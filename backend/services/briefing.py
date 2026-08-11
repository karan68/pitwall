"""Flatten the live session into plain sentences the voice agent can read out.

Numbers that make sense on a chart do not make sense spoken aloud, so this is
where "+1.52 sigma" becomes "speech rate well above his normal".
"""


def _spoken_z(z: float) -> str:
    magnitude = abs(z)
    if magnitude >= 2.5:
        band = "far"
    elif magnitude >= 1.2:
        band = "well"
    elif magnitude >= 0.5:
        band = "slightly"
    else:
        return "about normal"
    return f"{band} {'above' if z > 0 else 'below'} normal"


def build(payload: dict, event: dict | None) -> dict:
    session = payload["session"]
    analytics = payload["analytics"]
    baseline = payload["baseline"]

    if not event:
        return {
            "driver": session["driver"],
            "lap": "none yet",
            "transcript": "nothing yet",
            "driver_state": "unknown",
            "state_description": "No radio call has been analysed in this session yet.",
            "driver_load": "unknown",
            "arousal": "0",
            "strain": "0",
            "evidence": "no measurements yet",
            "intent": "none",
            "priority": "none",
            "radio_window": "Open",
            "window_reason": "Nothing measured yet, so there is no reason to hold the radio.",
            "action": "Analyse a radio call first.",
            "action_rationale": "There is no driver reading to act on.",
            "word_budget": "26",
            "flags": "none",
            "confidence": "None",
            "confidence_reason": "no radio calls analysed yet",
            "stint_summary": _stint_summary(analytics, baseline),
        }

    evidence = ", ".join(
        f"{d['feature']} {_spoken_z(d['z'])}" for d in event["drivers"]
    ) or "no single measurement stands out"

    flags = "; ".join(f"{f['title']}: {f['detail']}" for f in event["recommendation"]["flags"]) or "none"

    return {
        "driver": session["driver"],
        "lap": str(event["lap"]),
        "transcript": event["transcript"] or "no speech detected",
        "driver_state": event["state"],
        "state_description": event["description"],
        "driver_load": str(event["driverLoad"]),
        "arousal": str(event["arousal"]),
        "strain": str(event["strain"]),
        "evidence": evidence,
        "intent": event["content"]["intent"],
        "priority": event["content"]["priority"],
        "radio_window": event["recommendation"]["radioWindow"],
        "window_reason": event["recommendation"]["windowReason"],
        "action": event["recommendation"]["action"]["headline"],
        "action_rationale": event["recommendation"]["action"]["rationale"],
        "word_budget": str(event["recommendation"]["wordBudget"]),
        "flags": flags,
        "confidence": event["confidence"]["level"],
        "confidence_reason": event["confidence"]["reason"],
        "stint_summary": _stint_summary(analytics, baseline),
    }


def _stint_summary(analytics: dict, baseline: dict) -> str:
    calibration = (
        f"Calibrated on {baseline['sampleCount']} baseline clips."
        if baseline["calibrated"]
        else f"Not yet calibrated for this driver — {baseline['samplesNeeded']} more clips needed, "
        "so readings are against population averages."
    )

    if not analytics["sufficientData"]:
        return f"{calibration} {analytics['note']}"

    lag = analytics["lagLaps"]
    timing = "in the same lap" if lag == 0 else f"about {lag} lap{'s' if lag > 1 else ''} ahead"
    return (
        f"{calibration} Across {analytics['sampleSize']} radio calls, driver load tracks lap-time "
        f"loss {timing}, correlation {analytics['correlation']}, {analytics['strength'].lower()}. "
        f"Estimated {analytics['estimatedSecondsLost']} seconds lost over "
        f"{analytics['lapsAffected']} laps. This is indicative from one stint, not a validated model."
    )


def spoken_summary(variables: dict) -> str:
    """One-line fallback used when the voice agent is unavailable."""
    if variables["driver_state"] == "unknown":
        return "No radio call analysed yet."
    return (
        f"{variables['driver']} is {variables['driver_state'].lower()}, load {variables['driver_load']}. "
        f"Radio window {variables['radio_window'].lower()}. {variables['action']}"
    )
