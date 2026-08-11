"""The off-the-shelf speech-emotion model, kept deliberately as a *reference*.

This is the model most solutions to this problem reach for as their answer. We
keep it on screen so its disagreements with the biomarker reading are visible
rather than hidden: it is trained on acted emotional speech (IEMOCAP), while
race radio is task speech under physical load, and that domain gap shows.
"""
from functools import lru_cache

import numpy as np

MODEL_NAME = "superb/wav2vec2-base-superb-er"

LABEL_BUCKETS = {"ang": "Stressed", "sad": "Tired", "neu": "Calm", "hap": "Calm"}
LABEL_NAMES = {"ang": "angry", "sad": "sad", "neu": "neutral", "hap": "happy"}


@lru_cache(maxsize=1)
def _classifier():
    from transformers import pipeline

    return pipeline("audio-classification", model=MODEL_NAME)


def reference_reading(audio: np.ndarray, sampling_rate: int) -> dict:
    scores = _classifier()({"raw": audio, "sampling_rate": sampling_rate}, top_k=None)
    top = max(scores, key=lambda s: s["score"])
    label = top["label"].lower()

    return {
        "model": MODEL_NAME,
        "state": LABEL_BUCKETS.get(label, "Calm"),
        "rawLabel": LABEL_NAMES.get(label, label),
        "confidence": round(top["score"] * 100, 1),
        "breakdown": {
            LABEL_NAMES.get(s["label"].lower(), s["label"]): round(s["score"] * 100, 1)
            for s in scores
        },
    }
