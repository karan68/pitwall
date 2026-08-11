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

# Whisper transcribes expanded forms ("it is fine", "do not worry"), so phrase
# matching has to be done on a normalised string or it silently never fires.
CONTRACTIONS = {
    "i am": "i'm", "it is": "it's", "that is": "that's", "there is": "there's",
    "do not": "don't", "does not": "doesn't", "did not": "didn't",
    "cannot": "can't", "can not": "can't", "is not": "isn't", "was not": "wasn't",
    "will not": "won't", "i have": "i've", "i will": "i'll", "have not": "haven't",
}

# Phrases drivers use to wave the team off. Paired with high vocal strain these
# are the tell that a problem is being under-reported.
DOWNPLAY_TERMS = (
    "i'm fine", "it's fine", "all good", "no problem", "don't worry",
    "it's okay", "i'm ok", "i'm okay", "forget it", "leave it", "never mind",
)

# First-person reports of hitting a limit. These are the driver telling you
# directly that they are saturated, and they must be able to raise concern even
# when the voice sounds composed.
SELF_LIMIT_TERMS = (
    "i can't", "i'm struggling", "struggling", "my neck", "i'm done",
    "can't see", "can't hold", "can't keep", "losing it", "no energy",
    "cramping", "cramp", "dizzy", "can't breathe", "i'm cooked", "too hot",
    "exhausted", "can't take",
)


def _normalise(text: str) -> str:
    lowered = " ".join(text.lower().split())
    for expanded, contracted in CONTRACTIONS.items():
        lowered = lowered.replace(expanded, contracted)
    return lowered


def text_signals(transcript: str) -> dict:
    """Deterministic phrase signals. Kept free of the model so safety and
    self-reports never depend on a probabilistic classifier."""
    normalised = _normalise(transcript or "")
    return {
        "hazardTerms": [t for t in HAZARD_TERMS if t in normalised],
        "downplaying": any(t in normalised for t in DOWNPLAY_TERMS),
        "selfReportedLimit": any(t in normalised for t in SELF_LIMIT_TERMS),
    }


@lru_cache(maxsize=1)
def _classifier():
    from transformers import pipeline

    return pipeline("zero-shot-classification", model=MODEL_NAME)


def analyze(transcript: str) -> dict:
    text = (transcript or "").strip()
    signals = text_signals(text)
    hazard_hits = signals["hazardTerms"]

    if not text:
        return {
            "intent": "Unclear",
            "intentConfidence": 0.0,
            "hazardTerms": [],
            "downplaying": False,
            "selfReportedLimit": False,
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
        **signals,
        "priority": "Critical" if hazard_hits else _priority(intent),
    }


def _priority(intent: str) -> str:
    if intent in ("Car problem", "Physical strain"):
        return "Strategic"
    return "Informational"
