"""Throwaway: exercise the real OmniDimension path end to end through our own API.

Creates (or reuses) the PITWALL agent, mints a voice session preloaded with the
current driver reading, and prints what the browser would receive. Never prints
the API key or the full session token.

Run with the backend up:  .venv\\Scripts\\python.exe verify_voice.py
"""
import json

import httpx

API = "http://localhost:8000"

with httpx.Client(timeout=90) as client:
    status = client.get(f"{API}/api/voice/status").json()
    print(f"1. configured = {status['configured']}  agent = {status['agentName']}")
    if not status["configured"]:
        raise SystemExit("OMNIDIM_API_KEY not loaded by the backend")

    brief = client.get(f"{API}/api/voice/brief").json()
    print(f"\n2. spoken summary\n   {brief['summary']}")
    print("\n3. variables handed to the agent (server-side, tamper-proof)")
    for key, value in brief["variables"].items():
        printable = value if len(value) <= 96 else value[:93] + "..."
        print(f"   {key:20} {printable}")

    print("\n4. minting a voice session")
    response = client.post(f"{API}/api/voice/session")
    if response.status_code != 200:
        raise SystemExit(f"   FAILED {response.status_code}: {response.text[:400]}")

    session = response.json()
    ws = session["wsUrl"] or ""
    print(f"   agentId    {session['agentId']}")
    print(f"   sessionId  {session['sessionId']}")
    print(f"   expiresAt  {session['expiresAt']}")
    print(f"   wsUrl      {ws.split('=')[0]}=<token hidden, {len(ws)} chars total>")
    print(f"\n   scheme ok  {ws.startswith('wss://')}")
    print("\nPASS — the browser can now connect this ws_url with @omnidim-ai/client")
