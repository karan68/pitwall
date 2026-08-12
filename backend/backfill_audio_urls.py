"""Give each seeded call the OpenF1 URL its audio came from.

The hosted demo ships readings without audio, because no Formula 1 broadcast
audio is redistributed in this repository. That left a player with nothing to
play. OpenF1 already serves the recordings publicly, so the fix is to remember
where each clip came from and point at it, rather than to copy it.

The manifest records `transmittedAt` for every clip, which is exactly the `date`
field OpenF1 keys its team_radio records on, so the match is deterministic.

    .venv\\Scripts\\python.exe backfill_audio_urls.py
"""
import json
import urllib.request
from pathlib import Path

OPENF1 = "https://api.openf1.org/v1"
STINT = Path(__file__).parent / "sample_audio" / "openf1" / "9574_81"
SEED = Path(__file__).parent / "data" / "seed_session.json"


def openf1(path: str, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    request = urllib.request.Request(f"{OPENF1}/{path}?{query}", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


def main() -> None:
    manifest = json.loads((STINT / "manifest.json").read_text(encoding="utf-8"))
    session_key = manifest["sessionKey"]
    driver = int(manifest["driverId"].split()[0].lstrip("#"))

    radio = openf1("team_radio", session_key=session_key, driver_number=driver)
    by_date = {message["date"]: message["recording_url"] for message in radio}
    print(f"OpenF1 returned {len(radio)} transmissions for #{driver} in session {session_key}")

    url_for_file = {}
    for clip in manifest["clips"]:
        stamp = clip.get("transmittedAt")
        if stamp and stamp in by_date:
            url_for_file[clip["file"]] = by_date[stamp]
    print(f"matched {len(url_for_file)}/{len(manifest['clips'])} clips by timestamp")

    seed = json.loads(SEED.read_text(encoding="utf-8"))
    attached = 0
    for event in seed["events"]:
        url = url_for_file.get(event.get("fileName"))
        if url:
            event["sourceUrl"] = url
            attached += 1
    print(f"attached a source URL to {attached}/{len(seed['events'])} seeded calls")

    if attached:
        SEED.write_text(json.dumps(seed, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {SEED.name}")

    missing = [e.get("fileName") for e in seed["events"] if not e.get("sourceUrl")]
    if missing:
        print(f"no URL for: {missing}")


if __name__ == "__main__":
    main()
