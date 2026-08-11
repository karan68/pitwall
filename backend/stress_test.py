"""Adversarial input testing: what does the system do with audio it should refuse?

A demo fails on the clip nobody tried. Each case below is something a judge or a
real pit wall could plausibly feed it, and the expectation is stated up front so
the result is pass/fail rather than interpretation.

Run with the backend up:  .venv\\Scripts\\python.exe stress_test.py
"""
import io
import shutil
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf

API = "http://localhost:8000"
SR = 16000
STORE = Path(__file__).parent / "data" / "session.json"


def wav_bytes(audio: np.ndarray, rate: int = SR) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, audio.astype(np.float32), rate, format="WAV")
    return buffer.getvalue()


def tone(freq: float, seconds: float, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    return amp * np.sin(2 * np.pi * freq * t)


def music(seconds: float = 6.0) -> np.ndarray:
    """A chord progression: harmonic, sustained, but not speech."""
    t = np.arange(int(SR * seconds)) / SR
    out = np.zeros_like(t)
    for start, chord in enumerate([(261, 329, 392), (293, 369, 440), (220, 277, 329)]):
        window = (t >= start * 2) & (t < (start + 1) * 2)
        for freq in chord:
            out[window] += np.sin(2 * np.pi * freq * t[window]) / 3
    return 0.35 * out


def engine_noise(seconds: float = 5.0) -> np.ndarray:
    """Broadband roar with a rising fundamental — no voice at all."""
    t = np.arange(int(SR * seconds)) / SR
    sweep = np.sin(2 * np.pi * np.cumsum(np.linspace(80, 200, len(t))) / SR)
    return (0.25 * sweep + 0.3 * np.random.default_rng(3).standard_normal(len(t))).astype(np.float32)


rng = np.random.default_rng(11)

CASES = [
    ("digital silence", np.zeros(int(SR * 4)), "reject"),
    ("0.3s fragment", tone(150, 0.3), "reject"),
    ("pure white noise", 0.3 * rng.standard_normal(int(SR * 5)), "reject"),
    ("engine roar, no voice", engine_noise(), "reject"),
    ("music, no speech", music(), "reject"),
    ("hard clipped", np.clip(tone(150, 4) * 8, -1, 1), "reject"),
    ("near-silent whisper", tone(150, 4, amp=0.004), "reject"),
    ("DC offset only", np.full(int(SR * 4), 0.5), "reject"),
    ("single click", np.concatenate([np.zeros(SR * 2), [1.0], np.zeros(SR * 2)]), "reject"),
    ("60s of tone", tone(150, 60), "either"),
]


def restore(backup: Path) -> None:
    if backup.exists():
        shutil.copy2(backup, STORE)
        backup.unlink()


backup = Path(str(STORE) + ".stress-backup")
if STORE.exists():
    shutil.copy2(STORE, backup)

passed, failed = 0, 0
print(f"{'case':<24} {'expect':<8} {'result':<10} detail")
print("-" * 100)

try:
    with httpx.Client(timeout=240) as client:
        for name, audio, expectation in CASES:
            response = client.post(
                f"{API}/api/analyze",
                files={"file": (f"{name}.wav", wav_bytes(np.asarray(audio)), "audio/wav")},
                data={"lap": 1},
            )

            if response.status_code != 200:
                outcome, detail = "rejected", response.json().get("detail", "")[:64]
            else:
                event = response.json()["event"]
                usable = event["quality"]["usable"]
                outcome = "accepted" if usable else "flagged"
                detail = (
                    f"{event['state']} load={event['driverLoad']} "
                    f"conf={event['confidence']['level']} "
                    f"txt={(event['transcript'] or '(empty)')[:34]!r}"
                )
                if not usable:
                    detail = "; ".join(event["quality"]["issues"])[:70]

            ok = expectation == "either" or (
                expectation == "reject" and outcome in ("rejected", "flagged")
            )
            passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
            print(f"{name:<24} {expectation:<8} {'PASS ' if ok else 'FAIL '}{outcome:<10} {detail}")
finally:
    restore(backup)

print(f"\n{passed}/{passed + failed} handled correctly")
if failed:
    print("A FAIL means the system produced a confident driver reading from audio "
          "that cannot support one.")
