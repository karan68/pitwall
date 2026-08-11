"""Isolating the driver from the engineer — BUILT, MEASURED, AND NOT USED.

Team radio is a two-way exchange, so most clips contain the race engineer as
well as the driver and averaging biomarkers across two people measures neither.
The intended fix was a speaker-embedding model: build a voice print from the
calibration clips, then drop the windows that do not match it.

verify_speaker.py measured whether that works on real broadcast radio, using
four drivers from Belgium 2024:

    same driver      n=8   mean similarity 0.841
    different driver n=24  mean similarity 0.830
    separation                              0.011

That is no separation at all — several different-driver pairs scored higher than
same-driver pairs. On compressed, noisy radio where every clip already contains
two people, the embedding tracks the channel rather than the speaker.

So this module is deliberately NOT wired into the pipeline, and the two-speaker
limitation stands and is documented instead of being silently "fixed". Re-run
verify_speaker.py before reconsidering; a cleaner separation would need proper
diarisation on audio that is not already mixed.
"""
from functools import lru_cache

import numpy as np

MODEL_NAME = "microsoft/wavlm-base-plus-sv"

WINDOW_SECONDS = 1.5
HOP_SECONDS = 0.75
# Measured, not assumed: the best achievable split was 0.965 for 78% accuracy,
# which is not good enough to drop audio on.
MATCH_THRESHOLD = 0.86
MIN_DRIVER_SECONDS = 1.0


@lru_cache(maxsize=1)
def _model():
    from transformers import AutoFeatureExtractor, AutoModelForAudioXVector

    extractor = AutoFeatureExtractor.from_pretrained(MODEL_NAME)
    model = AutoModelForAudioXVector.from_pretrained(MODEL_NAME)
    model.eval()
    return extractor, model


def embed(audio: np.ndarray, sr: int) -> np.ndarray:
    """A unit-length voice print for a stretch of speech."""
    import torch

    extractor, model = _model()
    inputs = extractor(audio, sampling_rate=sr, return_tensors="pt", padding=True)
    with torch.no_grad():
        vector = model(**inputs).embeddings[0].numpy()
    norm = np.linalg.norm(vector)
    return vector / norm if norm else vector


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def _windows(audio: np.ndarray, sr: int) -> list[tuple[int, int]]:
    length = int(WINDOW_SECONDS * sr)
    hop = int(HOP_SECONDS * sr)
    if len(audio) <= length:
        return [(0, len(audio))]
    return [(start, start + length) for start in range(0, len(audio) - length + 1, hop)]


def isolate(audio: np.ndarray, sr: int, voice_print: list[float] | None) -> dict:
    """Keep only the parts of the clip that sound like the calibrated driver."""
    duration = len(audio) / sr
    if voice_print is None or duration < WINDOW_SECONDS:
        return {
            "applied": False,
            "reason": "No calibrated voice print yet — the whole clip is being measured, "
            "including anyone else on the transmission.",
            "audio": audio,
            "driverShare": None,
            "driverSeconds": None,
        }

    reference = np.asarray(voice_print, dtype=np.float32)
    windows = _windows(audio, sr)
    scores = [(start, end, similarity(embed(audio[start:end], sr), reference)) for start, end in windows]
    matched = [(start, end) for start, end, score in scores if score >= MATCH_THRESHOLD]

    share = len(matched) / len(scores) if scores else 0.0
    kept = _merge(matched)
    driver_audio = np.concatenate([audio[start:end] for start, end in kept]) if kept else audio
    driver_seconds = len(driver_audio) / sr

    if not kept or driver_seconds < MIN_DRIVER_SECONDS:
        return {
            "applied": False,
            "reason": f"Only {driver_seconds:.1f}s of this clip matches the calibrated driver, "
            "so it is measured whole and the reading may describe the engineer as much as the driver.",
            "audio": audio,
            "driverShare": round(share, 2),
            "driverSeconds": round(driver_seconds, 2),
            "meanSimilarity": round(float(np.mean([s for _, _, s in scores])), 3),
        }

    return {
        "applied": True,
        "reason": f"Measured on the {driver_seconds:.1f}s of this clip that matches the driver's "
        f"calibrated voice ({share:.0%} of the transmission).",
        "audio": driver_audio,
        "driverShare": round(share, 2),
        "driverSeconds": round(driver_seconds, 2),
        "meanSimilarity": round(float(np.mean([s for _, _, s in scores])), 3),
    }


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    merged = [list(spans[0])]
    for start, end in spans[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def build_voice_print(embeddings: list[list[float]]) -> list[float] | None:
    """Average the calibration clips into one reference voice."""
    if not embeddings:
        return None
    stacked = np.asarray(embeddings, dtype=np.float32)
    mean = stacked.mean(axis=0)
    norm = np.linalg.norm(mean)
    return (mean / norm).tolist() if norm else mean.tolist()
