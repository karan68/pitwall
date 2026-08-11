"""Speech-to-text using a local Whisper pipeline (runs fully offline after first download).

Whisper degenerates into repetition loops on short or noisy audio — measured on
real broadcast radio, a five-word clip decoded as "I'm sorry" twenty-eight
times. Two guards: block repeated n-grams at decode time, and detect the
degenerate output that still gets through so it is reported as unusable rather
than shown as a transcript.
"""
import os
import re
from collections import Counter
from functools import lru_cache

import numpy as np
from transformers import pipeline

MODEL_NAME = os.environ.get("PITWALL_ASR_MODEL", "openai/whisper-small.en")

GENERATE_KWARGS = {
    "no_repeat_ngram_size": 4,
    "repetition_penalty": 1.15,
}


@lru_cache(maxsize=1)
def get_asr_pipeline():
    return pipeline("automatic-speech-recognition", model=MODEL_NAME)


def is_degenerate(text: str) -> bool:
    """Spot the repetition collapse Whisper falls into on low-information audio."""
    words = re.sub(r"[^a-z' ]", " ", (text or "").lower()).split()
    if len(words) < 8:
        return False

    if len(set(words)) / len(words) < 0.35:
        return True

    trigrams = [" ".join(words[i : i + 3]) for i in range(len(words) - 2)]
    return bool(trigrams) and Counter(trigrams).most_common(1)[0][1] > 3


def transcribe(audio: np.ndarray, sampling_rate: int) -> dict:
    result = get_asr_pipeline()(
        {"raw": audio, "sampling_rate": sampling_rate},
        generate_kwargs=GENERATE_KWARGS,
    )
    text = result["text"].strip()
    degenerate = is_degenerate(text)

    return {
        "text": "" if degenerate else text,
        "rawText": text,
        "degenerate": degenerate,
        "model": MODEL_NAME,
    }
