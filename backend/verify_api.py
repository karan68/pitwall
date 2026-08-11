"""Every declared /api route must actually be reachable on the running server.

Mounting the built frontend at "/" once shadowed every route declared after it,
so the voice endpoints returned 404 with no error anywhere. The app knows its
own routing table, so compare that against what the server really answers.

Some probes write to the session store, so it is snapshotted and restored —
running a health check must never destroy a loaded stint.

Run with the backend up:  .venv\\Scripts\\python.exe verify_api.py
"""
import shutil
from pathlib import Path

import httpx

from main import STORE_PATH, app

API = "http://localhost:8000"

# Routes that change state or need a real upload are checked for reachability
# only: anything other than 404 proves the route was not swallowed by a mount.
PROBE_BODY = {
    "/api/compose": {"message": "box this lap", "wordBudget": 12},
    "/api/session/context": {"driver": "probe"},
    "/api/session/laps": {"laps": [], "referenceLapSeconds": 90.0},
    "/api/voice/session": {"eventId": None},
}
SKIP = {"/api/session/reset", "/api/baseline/reset", "/api/analyze", "/api/baseline"}

declared = sorted(
    {
        (method, route.path)
        for route in app.routes
        if getattr(route, "path", "").startswith("/api")
        for method in getattr(route, "methods", set()) & {"GET", "POST"}
    },
    key=lambda pair: pair[1],
)

print(f"{len(declared)} /api routes declared\n")
failures = []

backup = Path(str(STORE_PATH) + ".probe-backup")
if STORE_PATH.exists():
    shutil.copy2(STORE_PATH, backup)

try:
    with httpx.Client(timeout=60) as client:
        for method, path in declared:
            if path in SKIP:
                print(f"  [skip] {method:<4} {path}")
                continue

            response = (
                client.get(f"{API}{path}")
                if method == "GET"
                else client.post(f"{API}{path}", json=PROBE_BODY.get(path, {}))
            )
            shadowed = response.status_code == 404
            if shadowed:
                failures.append(path)
            print(f"  [{'FAIL' if shadowed else 'ok':<4}] {method:<4} {path:<26} -> {response.status_code}")
finally:
    if backup.exists():
        shutil.copy2(backup, STORE_PATH)
        backup.unlink()
        print("\n  session store restored")

print()
if failures:
    print(f"{len(failures)} route(s) returned 404 and are unreachable: {failures}")
    print("Most likely the StaticFiles mount is no longer the last statement in main.py.")
    raise SystemExit(1)

print(f"All {len(declared) - len(SKIP & {p for _, p in declared})} probed routes reachable.")
