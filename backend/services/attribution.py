"""Who is speaking - the driver or their engineer? BUILT, MEASURED, NOT USED.

Third and last attempt at the defect that matters most in this system, after two
acoustic ones failed: speaker.py could not tell drivers apart across clips
(separation 0.011) and diarize.py could not split a clip in two (66% against a
50% chance baseline, and it called a clip joined to an exact copy of itself two
speakers 6 times out of 6). Both failed because broadcast radio is already mixed
to one narrowband channel. The words are not mixed down, so language looked like
the way through.

verify_attribution.py measured it on 273 human transcriptions from
MikCil/f1-team-radio, labelled from unambiguous cues that were then stripped out
of the text so nothing was scored on the cue that defined it:

    approach            balanced accuracy    coverage
    markers                          12%          19% of clips answered
    zero-shot (mnli)                 46%         100%
    markers + model                  48%         100%
    chance                           50%

Below chance. The first run was worse still (25% overall) because both zero-shot
hypotheses contained the words "driver" and "team"; rewriting them to share no
content words moved the overall number but not the balanced one.

The likely reason it cannot work as posed: the labels assume one speaker per
clip, and a large share of transmissions contain both people - "Very good pace
out there. Good job. Yeah, I just don't know..." is engineer then driver inside
one file. Per-clip attribution is the wrong frame, and per-segment attribution
needs the diarisation that already failed.

So this module is NOT wired in. Three independent methods say the two-speaker
limitation is real and unsolved on this data, which is worth stating plainly
rather than papering over with a classifier that is no better than a coin.
"""
import re
from functools import lru_cache

ZERO_SHOT_MODEL = "valhalla/distilbart-mnli-12-1"

# Vocatives. An engineer says the driver's name; a driver does not say their own.
VOCATIVES = (
    r"\b(?:max|lewis|george|charles|carlos|lando|oscar|checo|sergio|fernando|lance|"
    r"esteban|pierre|yuki|daniel|valtteri|zhou|kevin|nico|alex|logan|franco|oliver|"
    r"mate|buddy|bud)\b"
)

# Phrases only the pitwall says.
ENGINEER_MARKERS = (
    r"\bbox,? box\b",
    r"\bbox this lap\b",
    r"\bwe need you to\b",
    r"\bstay out\b",
    r"\bwe are going to\b",
    r"\btarget (?:plus|minus)\b",
    r"\bmode\b.{0,12}\b(?:push|charge|recharge|deploy|scenario)\b",
    r"\bgap (?:to|behind|ahead) (?:him|the car|is)\b",
    r"\b(?:he|they) (?:has|have|is|are) (?:yet to|not) stop\b",
    r"\bwell done\b",
    r"\bgood job\b",
    r"\bkeep it up\b",
    r"\bhow are the tyres\b",
    r"\bcan you (?:go|give|do)\b",
    r"\blast lap (?:was )?a?\s?\d",
)

# Phrases only the person actually driving says.
DRIVER_MARKERS = (
    r"\bi (?:can't|cannot|can not)\b",
    r"\bi'm (?:struggling|losing|going|pushing|flat|done|okay|fine)\b",
    r"\bi am (?:struggling|losing|going|pushing|flat|done|okay|fine)\b",
    r"\bmy (?:tyres|tires|brakes|engine|neck|seat|drink|steering|front|rear)\b",
    r"\bthe car (?:is|feels|won't|keeps)\b",
    r"\bno grip\b",
    r"\bgive me\b",
    r"\bwhat(?:'s| is) the gap\b",
    r"\bthese (?:tyres|tires) are\b",
    r"\bi need\b",
    r"\bi think (?:we|i|the)\b",
)

# Zero-shot hypotheses have to be lexically distinct. The first version read
# "the race engineer talking to the driver" against "the driver talking to the
# team": both contain driver and team, the NLI model could not separate them and
# answered "driver" almost every time, scoring 25% where always-guessing scores
# 77%. These share no content words.
LABELS = [
    "someone on the pit wall giving instructions over the radio",
    "someone driving a race car describing how it feels",
]


def _hits(text: str, patterns) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text, re.IGNORECASE))


def _vocative(text: str) -> bool:
    """A name used to address someone, not merely mentioned."""
    return bool(
        re.search(rf"^\W*(?:and |so |okay,? )?{VOCATIVES}\s*,", text, re.IGNORECASE)
        or re.search(rf",\s*{VOCATIVES}\s*[.,!?]*$", text.strip(), re.IGNORECASE)
    )


@lru_cache(maxsize=1)
def _classifier():
    from transformers import pipeline

    return pipeline("zero-shot-classification", model=ZERO_SHOT_MODEL)


def _zero_shot(text: str) -> tuple[str, float]:
    result = _classifier()(text, LABELS, multi_label=False)
    top = result["labels"][0]
    margin = float(result["scores"][0] - result["scores"][1])
    return ("engineer" if top == LABELS[0] else "driver"), margin


def attribute(text: str, use_model: bool = True) -> dict:
    """Best guess at who is speaking, with how much of it rests on the model."""
    text = (text or "").strip()
    if len(text.split()) < 3:
        return {"speaker": "unknown", "confidence": 0.0, "basis": "Too few words to attribute.",
                "engineerMarkers": 0, "driverMarkers": 0}

    engineer = _hits(text, ENGINEER_MARKERS) + (2 if _vocative(text) else 0)
    driver = _hits(text, DRIVER_MARKERS)

    if engineer or driver:
        speaker = "engineer" if engineer > driver else "driver" if driver > engineer else "mixed"
        strength = abs(engineer - driver)
        return {
            "speaker": speaker,
            "confidence": round(min(0.5 + 0.25 * strength, 1.0), 2),
            "basis": f"Phrasing: {engineer} engineer marker(s), {driver} driver marker(s).",
            "engineerMarkers": engineer,
            "driverMarkers": driver,
        }

    if not use_model:
        return {"speaker": "unknown", "confidence": 0.0, "basis": "No decisive phrasing.",
                "engineerMarkers": 0, "driverMarkers": 0}

    speaker, margin = _zero_shot(text)
    return {
        "speaker": speaker,
        "confidence": round(min(margin * 2, 1.0), 2),
        "basis": f"No decisive phrasing; language model leans {speaker} by {margin:.2f}.",
        "engineerMarkers": 0,
        "driverMarkers": 0,
    }
