"""Speech emotion recognition, collapsed into the Calm / Stressed / Tired reading."""
from functools import lru_cache

import numpy as np
from transformers import pipeline

MODEL_NAME = "superb/wav2vec2-base-superb-er"

# How much each raw emotion class contributes to the 0-100 stress index.
# Labels come from the IEMOCAP-based SUPERB ER task: neu, hap, ang, sad.
STRESS_WEIGHTS = {
    "ang": 95,
    "sad": 55,
    "neu": 25,
    "hap": 15,
}

# Collapse the model's 4 classes into the 3 labels the problem statement asks for.
LABEL_BUCKETS = {
    "ang": "Stressed",
    "sad": "Tired",
    "neu": "Calm",
    "hap": "Calm",
}


@lru_cache(maxsize=1)
def get_emotion_pipeline():
    return pipeline("audio-classification", model=MODEL_NAME)


def analyze_emotion(audio: np.ndarray, sampling_rate: int) -> dict:
    classifier = get_emotion_pipeline()
    scores = classifier({"raw": audio, "sampling_rate": sampling_rate}, top_k=None)

    top = max(scores, key=lambda s: s["score"])
    top_label = top["label"].lower()

    stress_index = sum(
        STRESS_WEIGHTS.get(s["label"].lower(), 50) * s["score"] for s in scores
    )

    return {
        "label": LABEL_BUCKETS.get(top_label, "Calm"),
        "rawEmotion": top_label,
        "confidence": round(top["score"] * 100, 1),
        "stressIndex": round(stress_index, 1),
        "breakdown": {s["label"]: round(s["score"] * 100, 1) for s in scores},
    }
