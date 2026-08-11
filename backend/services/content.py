"""What the driver actually said, classified into race-radio intents.

Tone alone is ambiguous. "The tyres are gone" and "I threw it away, sorry" can
sound identical and demand opposite responses from the pit wall, so the intent
of the message is a first-class input to the advisor, not decoration.
"""
from functools import lru_cache

MODEL_NAME = "valhalla/distilbart-mnli-12-1"

INTENTS = {
    "the car has a technical problem": "Car problem",
    "the driver made a driving mistake": "Self-blame",
    "the driver is frustrated with the team": "Team friction",
    "asking the team for information": "Information request",
    "there is a hazard or danger on track": "Hazard",
    "acknowledging an instruction": "Acknowledgement",
    "the driver is physically struggling": "Physical strain",
}

# Safety detection must never depend on a probabilistic model, so these
# override the classifier outright.
HAZARD_TERMS = (
    "yellow", "red flag", "safety car", "crash", "crashed", "puncture", "debris",
    "fire", "smoke", "off", "in the wall", "spun", "accident", "oil",
)

# Phrases drivers use to wave the team off. Paired with high vocal strain these
# are the tell that a problem is being under-reported.
DOWNPLAY_TERMS = (
    "i'm fine", "im fine", "it's fine", "its fine", "all good", "no problem",
    "don't worry", "dont worry", "it's okay", "its okay", "i'm ok", "im ok",
    "nothing", "forget it", "leave it",
)


@lru_cache(maxsize=1)
def _classifier():
    from transformers import pipeline

    return pipeline("zero-shot-classification", model=MODEL_NAME)


def analyze(transcript: str) -> dict:
    text = (transcript or "").strip()
    lowered = text.lower()

    hazard_hits = [t for t in HAZARD_TERMS if t in lowered]
    downplaying = any(t in lowered for t in DOWNPLAY_TERMS)

    if not text:
        return {
            "intent": "Unclear",
            "intentConfidence": 0.0,
            "hazardTerms": [],
            "downplaying": False,
            "priority": "Informational",
        }

    if hazard_hits:
        intent, confidence = "Hazard", 100.0
    else:
        result = _classifier()(text, list(INTENTS.keys()), multi_label=False)
        intent = INTENTS[result["labels"][0]]
        confidence = round(result["scores"][0] * 100, 1)

    return {
        "intent": intent,
        "intentConfidence": confidence,
        "hazardTerms": hazard_hits,
        "downplaying": downplaying,
        "priority": "Critical" if hazard_hits else _priority(intent),
    }


def _priority(intent: str) -> str:
    if intent in ("Car problem", "Physical strain"):
        return "Strategic"
    return "Informational"
