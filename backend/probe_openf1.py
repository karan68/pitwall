"""Throwaway probe: can OpenF1 give us REAL radio and REAL lap times from the same session?

Our lap times are currently synthetic and labelled as such. If OpenF1 pairs team
radio with lap timing by session, the correlation stops being illustrative and
becomes real. Verify before building anything on it.
"""
import json
import urllib.request
from datetime import datetime

BASE = "https://api.openf1.org/v1"


def get(path: str, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE}/{path}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return url, json.loads(response.read().decode())


print("=== 1. Recent race sessions ===")
url, sessions = get("sessions", year=2024, session_name="Race")
print(f"{url}\n  {len(sessions)} race sessions in 2024")
for s in sessions[:5]:
    print(f"  key={s['session_key']:<6} {s['country_name']:<16} {s['date_start'][:10]}")

if not sessions:
    raise SystemExit("no sessions")

session = sessions[3]
key = session["session_key"]
print(f"\nUsing session_key={key} ({session['country_name']} {session['date_start'][:10]})")

print("\n=== 2. Team radio for that session ===")
url, radio = get("team_radio", session_key=key)
print(f"{url}\n  {len(radio)} radio messages")
by_driver = {}
for r in radio:
    by_driver.setdefault(r["driver_number"], []).append(r)
print(f"  drivers with radio: {sorted(by_driver, key=lambda d: -len(by_driver[d]))[:10]}")
for r in radio[:3]:
    print(f"  #{r['driver_number']} {r['date']}  {r['recording_url'][:95]}")

busiest = max(by_driver, key=lambda d: len(by_driver[d]))
print(f"\n  busiest driver: #{busiest} with {len(by_driver[busiest])} messages")

print("\n=== 3. Lap timing for the same driver + session ===")
url, laps = get("laps", session_key=key, driver_number=busiest)
timed = [lap for lap in laps if lap.get("lap_duration")]
print(f"{url}\n  {len(laps)} laps, {len(timed)} with a duration")
for lap in timed[:3]:
    print(f"  lap {lap['lap_number']:<3} {lap['lap_duration']:.3f}s  start={lap.get('date_start')}")

print("\n=== 4. THE KEY QUESTION: can a radio message be mapped to the lap it happened on? ===")


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


starts = [(parse(lap["date_start"]), lap) for lap in timed if lap.get("date_start")]
starts.sort(key=lambda pair: pair[0])

matched = 0
for message in by_driver[busiest][:10]:
    when = parse(message["date"])
    lap = None
    for start, candidate in starts:
        if start <= when:
            lap = candidate
        else:
            break
    if lap:
        matched += 1
        print(f"  radio {message['date'][11:19]} -> lap {lap['lap_number']:<3} "
              f"({lap['lap_duration']:.3f}s)")

print(f"\n  mapped {matched}/{min(10, len(by_driver[busiest]))} messages to a real timed lap")
print(f"\n  VERDICT: {'REAL radio + REAL lap times, pairable by timestamp' if matched else 'NOT pairable'}")

print("\n=== 5. Is the audio actually downloadable? ===")
sample = by_driver[busiest][0]["recording_url"]
try:
    req = urllib.request.Request(sample, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read()
    print(f"  downloaded {len(data) / 1024:.0f} KB, content-type={response.headers.get('Content-Type')}")
    print(f"  first bytes: {data[:4]}")
except Exception as exc:
    print(f"  FAILED: {exc}")
