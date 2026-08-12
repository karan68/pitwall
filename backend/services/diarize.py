"""Splitting one radio clip into its two speakers - BUILT, MEASURED, NOT USED.

Team radio is a two-way exchange. Most clips carry the race engineer as well as
the driver, and averaging voice biomarkers over two people measures neither.

speaker.py failed at cross-clip identity (separation 0.011) because the embedding
tracks the *channel* rather than the speaker. That looked like an opening: driver
and engineer are on genuinely different channels - a helmet in a car at 300km/h
against a pitwall headset - so telling two channels apart inside one clip should
be easier than recognising one person across clips.

verify_diarize.py measured it two ways, clustering on speaker x-vectors and on
channel features (noise floor, spectral shape, band balance) directly:

    representation    window acc   2-spk sep   1-spk sep      gap
    speaker                  66%       0.477       0.577    -0.100
    channel                  66%       0.501       0.547    -0.046
    chance                   50%

Ground truth was exact: two teams' clips concatenated at a known join. 66% is far
too low to cut audio on. The control settles it - a clip joined to an *exact copy
of itself*, where no boundary exists at all, still scored 0.45-0.61 separation and
was called two speakers 6 times out of 6. The silhouette is measuring within-clip
variation, loud speech against quiet speech, not how many people are talking. The
gap is negative under both representations: the score is slightly *higher* when
there is no second speaker.

So this module is deliberately NOT wired in, and the two-speaker limitation still
stands and is still documented rather than silently "fixed". A real fix needs
audio that is not already mixed down to one broadcast channel, or supervision
from something other than the acoustics.
"""
from functools import lru_cache

import numpy as np

WINDOW_SECONDS = 1.5
HOP_SECONDS = 0.5

# A cluster smaller than this is a clustering artefact, not a second speaker.
MIN_SPEAKER_SECONDS = 1.2

# Mean silhouette over cosine distance. Below this a clip is treated as one
# speaker. Set from the measured separation between true one- and two-speaker
# clips in verify_diarize.py.
SEPARATION_THRESHOLD = 0.12

# The noise-floor gap between the two channels has to be worth acting on before
# we claim to know which cluster is the driver.
MIN_FLOOR_GAP_DB = 1.5


@lru_cache(maxsize=1)
def _model():
    from transformers import AutoFeatureExtractor, AutoModelForAudioXVector

    from .speaker import MODEL_NAME

    extractor = AutoFeatureExtractor.from_pretrained(MODEL_NAME)
    model = AutoModelForAudioXVector.from_pretrained(MODEL_NAME)
    model.eval()
    return extractor, model


def _embed_batch(chunks: list[np.ndarray], sr: int) -> np.ndarray:
    """One forward pass for every window in the clip."""
    import torch

    extractor, model = _model()
    inputs = extractor(chunks, sampling_rate=sr, return_tensors="pt", padding=True)
    with torch.no_grad():
        vectors = model(**inputs).embeddings.numpy()
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1.0, norms)


def _channel_features(chunks: list[np.ndarray], sr: int) -> np.ndarray:
    """Per-window description of the line itself, not of who is on it.

    This is what the channel hypothesis actually implies: noise floor, spectral
    shape and band balance. Standardised within the clip, so it describes how
    the windows differ from each other rather than absolute broadcast level.
    """
    rows = []
    for chunk in chunks:
        spectrum = np.abs(np.fft.rfft(chunk * np.hanning(len(chunk))))
        freqs = np.fft.rfftfreq(len(chunk), 1 / sr)
        total = float(spectrum.sum()) or 1.0
        cumulative = np.cumsum(spectrum) / total

        frame = max(int(0.02 * sr), 1)
        frames = max(len(chunk) // frame, 1)
        rms = np.sqrt(np.mean(chunk[: frames * frame].reshape(frames, frame) ** 2, axis=1))

        rows.append([
            20 * np.log10(max(float(np.percentile(rms, 10)), 1e-8)),
            float((spectrum * freqs).sum() / total),
            float(freqs[int(np.searchsorted(cumulative, 0.85))]),
            float(spectrum[freqs < 500].sum() / total),
            float(spectrum[(freqs >= 500) & (freqs < 2000)].sum() / total),
            float(spectrum[freqs >= 2000].sum() / total),
            float(np.mean(np.abs(np.diff(np.sign(chunk))) > 0)),
        ])

    matrix = np.array(rows, dtype=float)
    spread = matrix.std(axis=0)
    matrix = (matrix - matrix.mean(axis=0)) / np.where(spread == 0, 1.0, spread)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0, 1.0, norms)


def _represent(chunks: list[np.ndarray], sr: int, representation: str) -> np.ndarray:
    if representation == "channel":
        return _channel_features(chunks, sr)
    return _embed_batch(chunks, sr)


def _speech_windows(audio: np.ndarray, sr: int) -> list[tuple[int, int]]:
    """Windows that actually contain speech, so silence is not clustered."""
    length = int(WINDOW_SECONDS * sr)
    hop = int(HOP_SECONDS * sr)
    if len(audio) < length:
        return []

    spans = [(s, s + length) for s in range(0, len(audio) - length + 1, hop)]
    energies = np.array([float(np.sqrt(np.mean(audio[s:e] ** 2))) for s, e in spans])
    if not len(energies) or energies.max() <= 0:
        return []

    keep = energies >= max(energies.max() * 0.15, 1e-5)
    return [span for span, ok in zip(spans, keep) if ok]


def _cluster(embeddings: np.ndarray) -> tuple[np.ndarray, float]:
    """Two-way split with the mean silhouette that says whether it was worth making."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    similarity = embeddings @ embeddings.T
    distance = np.clip(1.0 - similarity, 0.0, 2.0)
    np.fill_diagonal(distance, 0.0)

    labels = fcluster(linkage(squareform(distance, checks=False), method="average"), 2, "maxclust") - 1

    if len(set(labels)) < 2:
        return labels, 0.0

    scores = []
    for i, label in enumerate(labels):
        own = [distance[i][j] for j in range(len(labels)) if labels[j] == label and j != i]
        other = [distance[i][j] for j in range(len(labels)) if labels[j] != label]
        if not own or not other:
            continue
        a, b = float(np.mean(own)), float(np.mean(other))
        scores.append((b - a) / max(a, b, 1e-9))

    return labels, float(np.mean(scores)) if scores else 0.0


def _noise_floor_db(audio: np.ndarray, sr: int) -> float:
    """Level between words. A channel property, not a property of the voice.

    Deliberately independent of every biomarker that feeds the state score: if
    the driver were chosen as the rougher-sounding cluster, the pipeline would
    invent the strain it later reports.
    """
    frame = max(int(0.02 * sr), 1)
    frames = len(audio) // frame
    if frames < 3:
        return -np.inf
    rms = np.sqrt(np.mean(audio[: frames * frame].reshape(frames, frame) ** 2, axis=1))
    floor = float(np.percentile(rms, 10))
    return 20 * np.log10(max(floor, 1e-8))


def diarize(audio: np.ndarray, sr: int, representation: str = "channel") -> dict:
    """How many voices are in this clip, and which of them is in the car."""
    audio = np.asarray(audio, dtype=float)
    spans = _speech_windows(audio, sr)

    if len(spans) < 4:
        return {
            "speakers": 1,
            "separation": 0.0,
            "driverSeconds": round(len(audio) / sr, 1),
            "otherSeconds": 0.0,
            "driverCluster": 0,
            "assigned": False,
            "reason": "Clip too short to test for a second speaker; measured as one voice.",
            "labels": [],
            "spans": spans,
        }

    labels, separation = _cluster(_represent([audio[s:e] for s, e in spans], sr, representation))
    seconds = {c: float(np.sum(labels == c)) * HOP_SECONDS for c in (0, 1)}

    if separation < SEPARATION_THRESHOLD or min(seconds.values()) < MIN_SPEAKER_SECONDS:
        return {
            "speakers": 1,
            "separation": round(separation, 3),
            "driverSeconds": round(len(audio) / sr, 1),
            "otherSeconds": 0.0,
            "driverCluster": 0,
            "assigned": False,
            "reason": f"One voice in this transmission (separation {separation:.2f}).",
            "labels": labels.tolist(),
            "spans": spans,
        }

    floors = {
        c: _noise_floor_db(np.concatenate([audio[s:e] for (s, e), lab in zip(spans, labels) if lab == c]), sr)
        for c in (0, 1)
    }
    gap = abs(floors[0] - floors[1])
    # In-car is the noisier channel.
    driver = max(floors, key=lambda c: floors[c])
    assigned = gap >= MIN_FLOOR_GAP_DB

    return {
        "speakers": 2,
        "separation": round(separation, 3),
        "driverCluster": driver if assigned else None,
        "assigned": assigned,
        "driverSeconds": round(seconds[driver], 1),
        "otherSeconds": round(seconds[1 - driver], 1),
        "floorGapDb": round(gap, 1),
        "reason": (
            f"Two voices in this transmission. The in-car channel is {gap:.1f} dB noisier "
            f"between words, so {seconds[driver]:.1f}s is measured as the driver and "
            f"{seconds[1 - driver]:.1f}s is set aside as the engineer."
            if assigned
            else f"Two voices in this transmission, but their channels differ by only {gap:.1f} dB "
            "between words, which is not enough to say which one is in the car. The whole clip is "
            "measured, so treat the reading as contaminated."
        ),
        "labels": labels.tolist(),
        "spans": spans,
    }


def driver_audio(audio: np.ndarray, sr: int, result: dict) -> np.ndarray:
    """Just the driver's speech, or the original clip when it cannot be split."""
    if result["speakers"] < 2 or not result.get("assigned"):
        return audio
    keep = [audio[s:e] for (s, e), lab in zip(result["spans"], result["labels"])
            if lab == result["driverCluster"]]
    return np.concatenate(keep) if keep else audio
