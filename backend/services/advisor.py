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

    window, window_reason = _radio_window(state, load, priority)
    flags = _flags(driver_state, content, context)

    return {
        "radioWindow": window,
        "windowReason": window_reason,
        "wordBudget": WORD_BUDGET[window],
        "action": _action(state, intent),
        "flags": flags,
    }


def _radio_window(state: str, load: float, priority: str) -> tuple[str, str]:
    if priority == "Critical":
        return "Open", "Safety-critical traffic always goes through, whatever the driver load."

    if state == "Locked In":
        return "Closed", "Driver is performing at high effort. Interrupting costs more than the message gains."
    if state == "Stressed":
        return "Closed", "Driver is at capacity. A non-critical call now raises error risk."
    if state == "Tired":
        return "Caution", "Fatigue reading. Keep it short and concrete, avoid anything that needs interpretation."
    if load > 62:
        return "Caution", "Load is elevated even though the voice reads calm."
    return "Open", "Driver has spare capacity. Good window for a full strategy briefing."


def _action(state: str, intent: str) -> dict:
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

    # The signature finding of combining tone with content: the words say one
    # thing, the voice says another.
    if content["downplaying"] and driver_state["strain"] >= 0.6:
        flags.append(
            {
                "level": "warning",
                "title": "Possible under-reporting",
                "detail": "Driver is waving the team off, but vocal strain is well above their baseline. "
                "Check telemetry rather than taking the answer at face value.",
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

    if not driver_state["calibrated"]:
        flags.append(
            {
                "level": "info",
                "title": "Not yet calibrated",
                "detail": "Readings are against population averages, not this driver. Treat as indicative only.",
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
