"""Speech-to-text using a local Whisper pipeline (runs fully offline after first download)."""
from functools import lru_cache

import numpy as np
from transformers import pipeline

MODEL_NAME = "openai/whisper-base.en"


@lru_cache(maxsize=1)
def get_asr_pipeline():
    return pipeline("automatic-speech-recognition", model=MODEL_NAME)


def transcribe(audio: np.ndarray, sampling_rate: int) -> str:
    asr = get_asr_pipeline()
    result = asr({"raw": audio, "sampling_rate": sampling_rate})
    return result["text"].strip()
