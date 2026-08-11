"""Shared audio decoding so transcription and emotion models see the same waveform."""
import io

import numpy as np
import soundfile as sf

TARGET_SR = 16000


def load_audio(raw_bytes: bytes) -> tuple[np.ndarray, int]:
    """Decode uploaded audio bytes into a mono float32 array at 16kHz.

    Tries soundfile first (wav/flac, no external binary needed) and falls
    back to ffmpeg (via transformers) for formats like webm/mp3/m4a.
    """
    try:
        data, sr = sf.read(io.BytesIO(raw_bytes), dtype="float32", always_2d=False)
    except Exception:
        from transformers.pipelines.audio_utils import ffmpeg_read

        data = ffmpeg_read(raw_bytes, TARGET_SR)
        sr = TARGET_SR

    if data.ndim > 1:
        data = data.mean(axis=1)

    if sr != TARGET_SR:
        data = _resample(data, sr, TARGET_SR)

    return data.astype(np.float32), TARGET_SR


def _resample(data: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Linear-interpolation resample (avoids adding a librosa/resampy dependency)."""
    duration = len(data) / orig_sr
    target_len = max(1, int(round(duration * target_sr)))
    orig_idx = np.linspace(0, len(data) - 1, num=len(data))
    target_idx = np.linspace(0, len(data) - 1, num=target_len)
    return np.interp(target_idx, orig_idx, data)
