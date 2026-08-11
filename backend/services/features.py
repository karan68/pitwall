"""Explainable vocal-load biomarkers extracted with plain signal processing.

Everything here is a *measured* property of the waveform, not a model output.
That is deliberate: an engineer can be shown why a driver reads as loaded
instead of being asked to trust an opaque label.

References for the specific measures (all standard in voice/speech science):
  F0 mean/variability, jitter, shimmer, harmonics-to-noise ratio, spectral
  tilt, articulation rate and pause ratio are the established correlates of
  vocal effort, arousal and vocal fatigue.
"""
import numpy as np

FRAME_MS = 40.0
HOP_MS = 10.0
F0_MIN_HZ = 70.0
F0_MAX_HZ = 350.0

# An autocorrelation peak below this is treated as unvoiced (engine noise, silence).
VOICING_THRESHOLD = 0.45
# Frames more than 20 dB below the clip's loudest frame are not carrying speech.
ENERGY_FLOOR_RATIO = 0.10
ABSOLUTE_SILENCE = 1e-4


def _frame(audio: np.ndarray, frame_len: int, hop_len: int) -> np.ndarray:
    if len(audio) < frame_len:
        audio = np.pad(audio, (0, frame_len - len(audio)))
    n_frames = 1 + (len(audio) - frame_len) // hop_len
    starts = hop_len * np.arange(n_frames)[:, None]
    return audio[starts + np.arange(frame_len)[None, :]]


def _analyze_frames(audio: np.ndarray, sr: int) -> dict:
    """Frame the signal once and derive voicing, pitch and periodicity together."""
    frame_len = int(sr * FRAME_MS / 1000)
    hop_len = int(sr * HOP_MS / 1000)
    frames = _frame(audio, frame_len, hop_len)

    rms = np.sqrt((frames**2).mean(axis=1))

    centred = frames - frames.mean(axis=1, keepdims=True)
    windowed = centred * np.hanning(frame_len)[None, :]
    n_fft = 1 << int(np.ceil(np.log2(2 * frame_len)))
    power = np.abs(np.fft.rfft(windowed, n=n_fft, axis=1)) ** 2
    corr = np.fft.irfft(power, n=n_fft, axis=1)[:, :frame_len]

    zero_lag = corr[:, 0:1]
    corr = np.divide(corr, zero_lag, out=np.zeros_like(corr), where=zero_lag > 1e-12)

    min_lag = max(1, int(sr / F0_MAX_HZ))
    max_lag = min(int(sr / F0_MIN_HZ), corr.shape[1] - 1)
    band = corr[:, min_lag:max_lag]
    peak_lag = np.argmax(band, axis=1) + min_lag
    peak_strength = band.max(axis=1)

    # Gate on the clip's own loudest frame. A percentile floor collapses on
    # continuously-loud speech and silently reports zero voiced frames.
    energy_floor = max(rms.max() * ENERGY_FLOOR_RATIO, ABSOLUTE_SILENCE)
    voiced = (peak_strength >= VOICING_THRESHOLD) & (rms > energy_floor)
    # Consonants carry energy without periodicity, so timing has to be measured
    # on speech activity; using the voiced mask alone triples the speech rate.
    active = rms > energy_floor

    return {
        "frames": frames,
        "rms": rms,
        "voiced": voiced,
        "active": active,
        "peakLag": peak_lag,
        "peakStrength": peak_strength,
    }


def _high_frequency_ratio(frames: np.ndarray, voiced: np.ndarray, sr: int) -> float:
    """Share of voiced-band energy above 1 kHz. Rises with vocal effort.

    Restricted to voiced frames and to 50 Hz-5 kHz so that broadband background
    noise between words cannot masquerade as vocal effort.
    """
    selected = frames[voiced] if voiced.any() else frames
    spec = np.abs(np.fft.rfft(selected * np.hanning(frames.shape[1])[None, :], axis=1)) ** 2
    freqs = np.fft.rfftfreq(frames.shape[1], d=1.0 / sr)

    band = (freqs >= 50) & (freqs <= 5000)
    total = spec[:, band].sum()
    if total <= 0:
        return 0.0
    return float(spec[:, band & (freqs >= 1000)].sum() / total)


def extract(audio: np.ndarray, sr: int, word_count: int = 0) -> dict:
    """Return the biomarker set for one radio call."""
    analysis = _analyze_frames(audio, sr)
    voiced, rms, active = analysis["voiced"], analysis["rms"], analysis["active"]

    duration = len(audio) / sr
    voiced_ratio = float(voiced.mean()) if len(voiced) else 0.0
    active_ratio = float(active.mean()) if len(active) else 0.0

    if voiced.sum() >= 3:
        periods = analysis["peakLag"][voiced] / sr
        f0 = 1.0 / periods
        amps = rms[voiced]
        strength = analysis["peakStrength"][voiced]

        f0_mean = float(np.median(f0))
        f0_std = float(np.std(f0))

        # Jitter / shimmer: cycle-to-cycle instability, normalised so they are
        # comparable across speakers and recording levels.
        jitter = float(np.mean(np.abs(np.diff(periods))) / np.mean(periods) * 100)
        shimmer = float(np.mean(np.abs(np.diff(amps))) / max(np.mean(amps), 1e-9) * 100)

        clipped = np.clip(strength, 1e-6, 1 - 1e-6)
        hnr_db = float(np.median(10 * np.log10(clipped / (1 - clipped))))
    else:
        f0_mean = f0_std = jitter = shimmer = hnr_db = 0.0

    speaking_seconds = float(active.sum() * HOP_MS / 1000) or duration
    energy_db = float(20 * np.log10(max(rms.max(), 1e-9)))

    return {
        "durationSeconds": round(duration, 2),
        "f0MeanHz": round(f0_mean, 1),
        "f0StdHz": round(f0_std, 1),
        "energyDb": round(energy_db, 1),
        "jitterPct": round(jitter, 2),
        "shimmerPct": round(shimmer, 2),
        "hnrDb": round(hnr_db, 1),
        "highFreqRatio": round(_high_frequency_ratio(analysis["frames"], voiced, sr), 3),
        "pauseRatio": round(1.0 - active_ratio, 3),
        "voicedRatio": round(voiced_ratio, 3),
        # Words the driver actually got out per second of speech, pauses excluded.
        "articulationRate": round(word_count / speaking_seconds, 2) if word_count else 0.0,
    }


def signal_quality(audio: np.ndarray, sr: int) -> dict:
    """Gate unreliable audio before it is ever scored.

    Real team radio is compressed, noisy and clipped. Reporting a confident
    driver state from audio that cannot support one is the main way a tool
    like this misleads a race engineer.
    """
    duration = len(audio) / sr
    peak = float(np.abs(audio).max()) if len(audio) else 0.0
    clipped_ratio = float((np.abs(audio) > 0.99).mean()) if len(audio) else 0.0

    analysis = _analyze_frames(audio, sr)
    rms, voiced = analysis["rms"], analysis["voiced"]

    # Noise is what is present when nobody is speaking. If the whole clip is
    # voiced there is no noise estimate to make, and that is a good clip.
    speech_level = float(np.median(rms[voiced])) if voiced.any() else float(rms.max())
    if (~voiced).any():
        noise_level = max(float(np.median(rms[~voiced])), 1e-9)
        snr_db = min(float(20 * np.log10(max(speech_level, 1e-9) / noise_level)), 60.0)
    else:
        snr_db = 40.0

    issues = []
    if duration < 1.0:
        issues.append("Clip shorter than 1s — not enough voiced speech to measure stability.")
    if peak < 0.02:
        issues.append("Signal level very low.")
    if clipped_ratio > 0.01:
        issues.append(f"{clipped_ratio * 100:.1f}% of samples are clipped.")
    if voiced.mean() < 0.08:
        issues.append("Almost no voiced speech detected.")
    if snr_db < 8:
        issues.append(f"Low speech-to-noise ratio ({snr_db:.1f} dB).")

    return {
        "snrDb": round(snr_db, 1),
        "peakLevel": round(peak, 3),
        "clippedRatio": round(clipped_ratio, 4),
        "voicedRatio": round(float(voiced.mean()), 3),
        "usable": len(issues) == 0,
        "issues": issues,
    }
