"""Calibrate the speaker-match threshold against real radio, not a guess.

Two questions decide whether isolating the driver is sound:
  1. Do windows from the SAME driver score higher than windows from a DIFFERENT
     driver, and by how much?
  2. Where does the boundary sit, so the threshold is chosen from data?

Uses OpenF1 clips for several drivers in one session.

    .venv\\Scripts\\python.exe verify_speaker.py
"""
import io
import json
import urllib.request

import numpy as np
import soundfile as sf

from services import speaker
from services.audio_utils import load_audio

OPENF1 = "https://api.openf1.org/v1"
SESSION = 9574  # Belgium 2024
DRIVERS = [81, 1, 63, 44]
PER_DRIVER = 5


def api(path: str, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    request = urllib.request.Request(f"{OPENF1}/{path}?{query}", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


def fetch(url: str) -> np.ndarray:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        audio, _ = load_audio(response.read())
    return audio


print(f"Session {SESSION}: collecting clips for drivers {DRIVERS}\n")
radio = api("team_radio", session_key=SESSION)
by_driver = {}
for message in radio:
    by_driver.setdefault(message["driver_number"], []).append(message)

clips: dict[int, list[np.ndarray]] = {}
for number in DRIVERS:
    messages = sorted(by_driver.get(number, []), key=lambda m: m["date"])[:PER_DRIVER]
    collected = []
    for message in messages:
        try:
            audio = fetch(message["recording_url"])
            if len(audio) / 16000 >= 2.0:
                collected.append(audio)
        except Exception:
            continue
    if collected:
        clips[number] = collected
    print(f"  #{number}: {len(collected)} usable clips")

if len(clips) < 2:
    raise SystemExit("need at least two drivers with clips")

print("\nBuilding a voice print per driver from their first 3 clips")
prints = {}
for number, audios in clips.items():
    embeddings = [speaker.embed(a, 16000).tolist() for a in audios[:3]]
    prints[number] = np.asarray(speaker.build_voice_print(embeddings), dtype=np.float32)
    print(f"  #{number}: from {len(embeddings)} clips")

print("\nScoring held-out clips against every driver print")
print(f"  {'clip from':<12} {'vs print':<10} {'similarity':>10}   {'same driver?':<12}")
print("  " + "-" * 52)

same, different = [], []
for source, audios in clips.items():
    for audio in audios[3:]:
        for target, reference in prints.items():
            score = speaker.similarity(speaker.embed(audio, 16000), reference)
            (same if source == target else different).append(score)
            print(f"  #{source:<11} #{target:<9} {score:>10.3f}   {'SAME' if source == target else 'different':<12}")

if not same or not different:
    raise SystemExit("not enough held-out clips to compare")

print(f"\n{'=' * 62}")
print(f"  same driver     n={len(same):<3} mean {np.mean(same):.3f}  min {min(same):.3f}  max {max(same):.3f}")
print(f"  different       n={len(different):<3} mean {np.mean(different):.3f}  min {min(different):.3f}  max {max(different):.3f}")

separation = np.mean(same) - np.mean(different)
print(f"  separation      {separation:.3f}")

# Threshold that best splits the two populations.
candidates = np.linspace(min(different), max(same), 200)
best, best_acc = None, -1.0
for threshold in candidates:
    correct = sum(s >= threshold for s in same) + sum(d < threshold for d in different)
    accuracy = correct / (len(same) + len(different))
    if accuracy > best_acc:
        best, best_acc = threshold, accuracy

print(f"  best threshold  {best:.3f}  ->  {best_acc:.0%} correct")
print(f"  currently using {speaker.MATCH_THRESHOLD}")

if separation < 0.05:
    print("\n  VERDICT: the model does not separate these speakers on this audio. "
          "Do not isolate on it.")
elif best_acc < 0.75:
    print(f"\n  VERDICT: separable but unreliable ({best_acc:.0%}). Use it to FLAG "
          "mixed clips, not to silently drop audio.")
else:
    print(f"\n  VERDICT: usable. Set MATCH_THRESHOLD near {best:.2f}.")
