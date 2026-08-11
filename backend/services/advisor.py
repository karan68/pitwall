"""Turns a driver-state reading into the two decisions a race engineer makes:
whether to press the button at all, and what to say if they do.

The rules below encode ordinary race-engineering practice: you do not load a
driver who is already at capacity, you never sit on a safety call, and the
more loaded the driver the shorter the message has to be.
"""
import re

WORD_BUDGET = {"Open": 26, "Caution": 12, "Closed": 6}

FILLER_PATTERNS = [
    r"\b(okay|ok|so|right|now then|alright)\b[, ]*",
    r"\bjust (to let you know|so you know|wanted to say)\b[, ]*",
    r"\bwe(?:'re| are) (?:looking at|thinking about|going to see)\b",
    r"\bif you (?:can|could|would)\b",
    r"\bi (?:think|mean|guess)\b",
    r"\bat this (?:point|stage)\b",
    r"\bas (?:you know|we discussed)\b",
    r"\bkind of\b|\bsort of\b|\ba little bit\b",
    r"\bplease\b",
]

IMPERATIVES = (
    "box", "push", "hold", "stay", "watch", "target", "lift", "save", "attack",
    "defend", "pit", "confirm", "copy", "manage", "charge", "deploy",
)

KEY_TERMS = (
    "lap", "laps", "tyre", "tyres", "tire", "tires", "gap", "delta", "position",
    "fuel", "brake", "brakes", "engine", "front", "rear", "left", "right",
    "sector", "flag", "safety", "car", "plan", "mode", "temperature", "wing",
)

# Radio brevity: when a message will not fit, the justification goes and the
# instruction stays. These introduce the part that can be dropped.
SUBORDINATE_MARKERS = r"\b(because|since|which|that's why|as it|while|when|although|though)\b"


def advise(driver_state: dict, content: dict, context: dict) -> dict:
    load = driver_state["driverLoad"]
    state = driver_state["state"]
    intent = content["intent"]
    priority = content["priority"]
    calibrated = driver_state["calibrated"]

    window, window_reason = _radio_window(
        state, load, priority, content.get("selfReportedLimit", False), calibrated
    )
    flags = _flags(driver_state, content, context)

    return {
        "radioWindow": window,
        "windowReason": window_reason,
        "wordBudget": WORD_BUDGET[window],
        "action": _action(state, intent, content.get("selfReportedLimit", False), calibrated),
        "flags": flags,
    }


def _radio_window(state: str, load: float, priority: str, self_reported_limit: bool,
                  calibrated: bool = True) -> tuple[str, str]:
    if priority == "Critical":
        return "Open", "Safety-critical traffic always goes through, whatever the driver load."

    # Without a personal baseline there is no deviation to report, and an
    # uncalibrated reading is scored against population averages instead.
    # Measured on real radio (ablate_baseline.py, Hamilton, Spa 2024): the same
    # six clips read Tired at load 60-73 uncalibrated and Calm at load 50-54
    # once the baseline was valid. The only power this tool has over an engineer
    # is to *restrict* comms, so restricting on that reading is the failure that
    # does harm. Uncalibrated therefore degrades to how the team already works.
    if not calibrated:
        if self_reported_limit:
            return "Caution", (
                "Driver has reported being at a limit. A first-hand report needs no baseline to be "
                "credible, so this window is set on the driver's own words. Keep transmissions short."
            )
        return "Open", (
            "No baseline for this driver yet, so no state has been established. Comms are left open "
            "deliberately: the reading is against population averages and is not a basis for holding "
            "a call back."
        )

    if state == "Locked In":
        return "Closed", "Driver is performing at high effort. Interrupting costs more than the message gains."
    if state == "Stressed":
        return "Closed", "Driver is at capacity. A non-critical call now raises error risk."
    if state == "Tired":
        return "Caution", "Fatigue reading. Keep it short and concrete, avoid anything that needs interpretation."

    # The driver has said out loud that they are at a limit. Take that at face
    # value: a composed voice does not make the report untrue.
    if self_reported_limit:
        return "Caution", (
            "Driver has reported being at a limit. The voice reads composed, but a first-hand "
            "report outranks the tone. Keep transmissions short."
        )

    if load > 62:
        return "Caution", "Load is elevated even though the voice reads calm."
    return "Open", "Driver has spare capacity. Good window for a full strategy briefing."


def _action(state: str, intent: str, self_reported_limit: bool = False,
            calibrated: bool = True) -> dict:
    if not calibrated:
        # The words are still measured directly, so intent-driven advice survives;
        # anything that depends on the voice deviating from normal does not.
        if self_reported_limit:
            return {
                "headline": "Act on the report itself: acknowledge, then check hydration, temps and stint length.",
                "rationale": "The driver stated a limit. That stands on its own without a voice baseline.",
            }
        return {
            "headline": "No state call yet — collect baseline clips before using the readout.",
            "rationale": "Until this driver has a baseline, the state label describes an average adult "
            "voice rather than theirs, and the same audio can read Tired or Calm depending only on "
            "how many calibration clips were accepted.",
        }

    # A first-person report of hitting a limit is acted on whatever the voice did.
    if self_reported_limit and state in ("Calm", "Locked In"):
        return {
            "headline": "Treat the report as real. Acknowledge, then check hydration, temps and stint length.",
            "rationale": "The driver said they are at a limit while sounding composed. Drivers who stay "
            "articulate under load are the ones whose problems get missed.",
        }

    table = {
        ("Stressed", "Car problem"): (
            "Confirm you have seen it, give one number, nothing else.",
            "Acknowledgement removes the driver's need to keep reporting it, which is itself load.",
        ),
        ("Stressed", "Self-blame"): (
            "Do not send data. One short reassurance, then go quiet.",
            "A driver blaming themselves is already self-correcting. Adding information compounds the error.",
        ),
        ("Stressed", "Team friction"): (
            "Acknowledge once. Do not argue, do not explain now.",
            "Defending a call over the radio mid-stint spends the driver's attention on the argument.",
        ),
        ("Stressed", "Hazard"): (
            "Send the safety call immediately, in the fewest words possible.",
            "Safety overrides load management, but the message still has to fit the driver's capacity.",
        ),
        ("Tired", "Physical strain"): (
            "Bring the pit window forward and simplify every remaining call.",
            "Fatigue degrades lap time and decision quality faster than tyre wear does.",
        ),
        ("Tired", "Car problem"): (
            "Take the report at face value and act. Do not ask for more detail.",
            "A tired driver's diagnosis gets worse; asking them to elaborate costs more than it returns.",
        ),
        ("Locked In", "Information request"): (
            "Answer with the number only. No context.",
            "The driver asked, so answer, but they are at high effort — give data, not conversation.",
        ),
        ("Calm", "Car problem"): (
            "Good window to debrief the issue properly and agree a plan.",
            "Spare capacity is when you get the driver's best technical feedback.",
        ),
        ("Calm", "Physical strain"): (
            "Take the report seriously and plan around it, even though the voice reads calm.",
            "Physical complaints do not need a strained voice to be true.",
        ),
    }

    default_by_state = {
        "Stressed": (
            "Hold non-essential traffic until load drops.",
            "Nothing being sent right now is worth the capacity it costs.",
        ),
        "Locked In": (
            "Radio silence unless it is safety or strategy-critical.",
            "The driver is delivering. Protect that.",
        ),
        "Tired": (
            "Shorten everything. Consider an earlier stop.",
            "Fatigue is the constraint, not the tyres.",
        ),
        "Calm": (
            "Normal comms. Use this window for anything complex.",
            "This is the cheapest moment in the stint to talk.",
        ),
    }

    headline, rationale = table.get((state, intent), default_by_state[state])
    return {"headline": headline, "rationale": rationale}


def _flags(driver_state: dict, content: dict, context: dict) -> list[dict]:
    flags = []
    calibrated = driver_state["calibrated"]

    if not calibrated:
        # Every flag below this point compares the voice to the driver's normal
        # voice. With no baseline that comparison is against population averages,
        # which measured out as a false "Tired" plus a false sustained-load
        # warning on six consecutive real Hamilton calls. Say what is missing
        # instead of raising warnings that the audio does not support.
        flags.append(
            {
                "level": "warning",
                "title": "Not calibrated — state readout is not usable",
                "detail": "This driver has no baseline yet, so the reading is scored against population "
                "averages rather than their own voice. On real radio the same clips moved from Tired to "
                "Calm once a valid baseline existed. Comms advice is deliberately left open and "
                "voice-based flags are suppressed until calibration completes.",
            }
        )
        if content.get("selfReportedLimit"):
            flags.append(
                {
                    "level": "warning",
                    "title": "Driver reported a limit",
                    "detail": "Taken from the words, not the voice, so it stands without a baseline. "
                    "Act on the report.",
                }
            )
        return flags

    # The signature finding of combining tone with content: the words say one
    # thing, the voice says another. It matters in both directions.
    if content["downplaying"] and driver_state["strain"] >= 0.6:
        flags.append(
            {
                "level": "warning",
                "title": "Possible under-reporting",
                "detail": "Driver is waving the team off, but vocal strain is well above their baseline. "
                "Check telemetry rather than taking the answer at face value.",
            }
        )

    if content.get("selfReportedLimit") and driver_state["strain"] < 0.6:
        flags.append(
            {
                "level": "warning",
                "title": "Reported limit, composed voice",
                "detail": "Driver has said they are at a limit, but the voice does not show it. Either they "
                "are stating it calmly — which makes it more credible, not less — or the radio audio is "
                "not carrying the strain. Act on the words.",
            }
        )

    recent = context.get("recentLoads", [])
    if len(recent) >= 3 and all(v > 62 for v in recent[-3:]):
        flags.append(
            {
                "level": "warning",
                "title": "Sustained load",
                "detail": f"Driver load has stayed above 62 for {len(recent[-3:])} consecutive calls. "
                "Single spikes are normal; a plateau is not.",
            }
        )

    if driver_state["state"] == "Tired" and context.get("stintLaps", 0) >= 12:
        flags.append(
            {
                "level": "warning",
                "title": "Fatigue in a long stint",
                "detail": f"Fatigue markers at lap {context.get('stintLaps')} of the stint. "
                "Weigh an earlier stop against track position.",
            }
        )

    return flags

def compress(message: str, word_budget: int) -> dict:
    """Cut a message down to a radio brevity budget, keeping what is actionable."""
    original = message.strip()
    if not original:
        return {"original": "", "adapted": "", "removedWords": 0, "changed": False}

    stripped = original
    for pattern in FILLER_PATTERNS:
        stripped = re.sub(pattern, "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\s+", " ", stripped).strip(" ,.")

    if len(stripped.split()) <= word_budget:
        adapted = stripped
    else:
        clauses = [c.strip() for c in re.split(r"[,.;]|\band\b|\bthen\b|\bbut\b|\bso\b", stripped) if c.strip()]
        ranked = sorted(enumerate(clauses), key=lambda pair: -_clause_score(pair[1]))

        kept, used = [], 0
        for index, clause in ranked:
            trimmed = _drop_justification(clause, word_budget)
            length = len(trimmed.split())
            if used + length <= word_budget or not kept:
                kept.append((index, trimmed))
                used += length
            if used >= word_budget:
                break

        adapted = ". ".join(clause for _, clause in sorted(kept))
        adapted = " ".join(adapted.split()[:word_budget])

    adapted = adapted.strip(" ,.")
    if adapted and not adapted.endswith("."):
        adapted += "."

    return {
        "original": original,
        "adapted": adapted,
        "removedWords": max(0, len(original.split()) - len(adapted.split())),
        "changed": adapted.lower().strip(".") != original.lower().strip("."),
    }


def _drop_justification(clause: str, word_budget: int) -> str:
    """Keep the instruction, drop the reason for it, when there is no room for both."""
    if len(clause.split()) <= word_budget:
        return clause
    head = re.split(SUBORDINATE_MARKERS, clause, maxsplit=1, flags=re.IGNORECASE)[0].strip(" ,.")
    return head or clause


def _clause_score(clause: str) -> float:
    words = clause.lower().split()
    if not words:
        return 0.0

    score = 0.0
    if words[0].strip(",.") in IMPERATIVES:
        score += 4
    score += 2 * sum(1 for w in words if any(ch.isdigit() for ch in w))
    score += 1.5 * sum(1 for w in words if w.strip(",.") in KEY_TERMS)
    score += 1.0 * sum(1 for w in words if w.strip(",.") in IMPERATIVES)
    score -= 0.15 * len(words)
    return score
