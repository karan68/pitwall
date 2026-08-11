"""Throwaway probe: does OpenF1 expose driver INPUT telemetry for the same session?

renumics/f1_dataset showed that per-lap throttle/brake/gear traces exist as a
data type. If OpenF1 carries the same for the session our radio came from, the
voice reading can be cross-checked against how the car was actually being
driven on that lap — a second, independent modality rather than a different
view of the same signal.
"""
import json
import urllib.request
from datetime import datetime

BASE = "https://api.openf1.org/v1"
SESSION = 9574  # Belgium 2024, the stint already loaded
DRIVER = 81


def api(path: str, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    url = f"{BASE}/{path}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return url, json.loads(response.read().decode())


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


print("=== Does /car_data exist for this session and driver? ===")
laps = sorted(
    [lap for lap in api("laps", session_key=SESSION, driver_number=DRIVER)[1] if lap.get("lap_duration")],
    key=lambda lap: lap["lap_number"],
)
target = next(lap for lap in laps if lap["lap_number"] == 28)
start = parse(target["date_start"])
print(f"  lap {target['lap_number']} starts {target['date_start']} duration {target['lap_duration']}s")

end = start.timestamp() + target["lap_duration"]
url, samples = api(
    "car_data",
    session_key=SESSION,
    driver_number=DRIVER,
    **{"date>": target["date_start"]},
)
print(f"  {url}")
print(f"  {len(samples)} samples returned")

if samples:
    print(f"  fields: {sorted(samples[0].keys())}")
    within = [s for s in samples if parse(s["date"]).timestamp() <= end]
    print(f"  {len(within)} samples fall inside lap {target['lap_number']} "
          f"({len(within) / max(target['lap_duration'], 1):.1f} Hz)")
    for s in within[:3]:
        print(f"    {s['date'][11:23]} throttle={s.get('throttle')} brake={s.get('brake')} "
              f"rpm={s.get('rpm')} speed={s.get('speed')} gear={s.get('n_gear')}")

    if within:
        throttle = [s["throttle"] for s in within if s.get("throttle") is not None]
        brake = [s["brake"] for s in within if s.get("brake") is not None]
        applications = sum(
            1 for a, b in zip(brake, brake[1:]) if a == 0 and b > 0
        )
        lifts = sum(1 for a, b in zip(throttle, throttle[1:]) if a > 50 and b <= 50)
        print(f"\n  derived for this lap: {applications} brake applications, "
              f"{lifts} throttle lifts, mean throttle {sum(throttle) / len(throttle):.0f}%")
        print("\n  VERDICT: driver input telemetry IS available and lap-sliceable")
else:
    print("  VERDICT: no car_data for this session")
