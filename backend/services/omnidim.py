"""OmniDimension voice agent — the hands-free side of the pit wall.

The premise of the problem statement is that engineers miss what is in a
driver's voice because their eyes are on the data. A dashboard does not fix
that; it adds another screen. So the engineer can also just ask out loud, and
the agent answers from the live reading rather than from anything it invented.

The API key stays on this server. The browser only ever receives a single-use
`ws_url` that expires, which is what the platform is designed for.
"""
import json
import os
from pathlib import Path

import httpx

BASE_URL = os.environ.get("OMNIDIM_BASE_URL", "https://backend.omnidim.io/api/v1")
AGENT_FILE = Path(__file__).parent.parent / "data" / "omnidim_agent.json"
AGENT_NAME = "PITWALL Race Engineer"

# Placeholders are filled per session from the live reading, server-side, so a
# visitor cannot talk the agent into reporting a driver state that never happened.
CONTEXT_SECTIONS = [
    {
        "title": "Role",
        "body": (
            "You are PITWALL, the race engineer's assistant on the pit wall during a live "
            "session. The engineer's hands and eyes are busy, so they ask you out loud "
            "instead of reading the screen. You answer about one driver's current state, "
            "what it is costing in lap time, and whether it is a good moment to talk to "
            "the driver over the radio."
        ),
    },
    {
        "title": "Radio discipline",
        "body": (
            "Answer the way a race engineer talks: short, concrete, numbers first. One or "
            "two sentences. No preamble, no 'certainly', no restating the question. If the "
            "engineer asks something you were not given data for, say you do not have it. "
            "Never invent a lap time, a driver state or a number."
        ),
    },
    {
        "title": "Current reading",
        "body": (
            "This is the live state of the session. Treat it as the only source of truth.\n"
            "Driver: {{driver}}\n"
            "Latest radio call was lap {{lap}}, and the driver said: \"{{transcript}}\"\n"
            "Driver state: {{driver_state}} ({{state_description}})\n"
            "Driver load: {{driver_load}} out of 100. Arousal {{arousal}} sigma, vocal "
            "strain {{strain}} sigma against this driver's own baseline.\n"
            "What is pushing that reading: {{evidence}}\n"
            "Message intent: {{intent}}, priority {{priority}}\n"
            "Radio window: {{radio_window}}. {{window_reason}}\n"
            "Recommended call: {{action}}\n"
            "Reason: {{action_rationale}}\n"
            "Word budget if you do transmit: {{word_budget}} words\n"
            "Warnings: {{flags}}\n"
            "Confidence in this reading: {{confidence}} because {{confidence_reason}}\n"
            "Stint so far: {{stint_summary}}"
        ),
    },
    {
        "title": "How to answer common questions",
        "body": (
            "'How is the driver?' -> the state, the load number, and one measurement that "
            "explains it.\n"
            "'Can I talk to him?' -> the radio window, and if it is closed, why, and what "
            "would reopen it.\n"
            "'What should I say?' -> the recommended call, inside the word budget.\n"
            "'What is it costing?' -> the stint summary figures. If the data is marked "
            "insufficient, say so plainly instead of guessing.\n"
            "'Why do you think that?' -> name the measurements and how far they sit from "
            "this driver's baseline. Never claim to detect emotion; you report measured "
            "vocal load against a personal baseline."
        ),
    },
]


class OmniDimError(RuntimeError):
    pass


def api_key() -> str:
    return os.environ.get("OMNIDIM_API_KEY", "").strip()


def is_configured() -> bool:
    return bool(api_key())


def _client() -> httpx.Client:
    if not is_configured():
        raise OmniDimError("OMNIDIM_API_KEY is not set. Add it to backend/.env.")
    return httpx.Client(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
        timeout=45,
    )


def _request(method: str, path: str, **kwargs) -> dict:
    with _client() as client:
        response = client.request(method, path, **kwargs)
    if response.status_code >= 400:
        raise OmniDimError(f"OmniDimension {method} {path} -> {response.status_code}: {response.text[:300]}")
    return response.json() if response.content else {}


def _cached_agent_id() -> int | None:
    if AGENT_FILE.exists():
        return json.loads(AGENT_FILE.read_text(encoding="utf-8")).get("agentId")
    return None


def _cache_agent_id(agent_id: int) -> None:
    AGENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    AGENT_FILE.write_text(json.dumps({"agentId": agent_id}, indent=2), encoding="utf-8")


def ensure_agent() -> int:
    """Return the PITWALL agent id, reusing or creating it as needed."""
    cached = _cached_agent_id()
    if cached:
        return cached

    existing = _request("GET", "/agents").get("bots", [])
    for bot in existing:
        if bot.get("name") == AGENT_NAME:
            _cache_agent_id(bot["id"])
            return bot["id"]

    created = _request(
        "POST",
        "/agents/create",
        json={
            "name": AGENT_NAME,
            "welcome_message": "Pit wall. Go ahead.",
            "is_welcome_message_interruption": True,
            "is_interruption_allowed": True,
            "context_breakdown": CONTEXT_SECTIONS,
        },
    )
    agent_id = created.get("id") or created.get("bot", {}).get("id") or created.get("agent_id")
    if not agent_id:
        raise OmniDimError(f"Agent created but no id in response: {json.dumps(created)[:300]}")

    _cache_agent_id(agent_id)
    return agent_id


def create_voice_session(variables: dict) -> dict:
    """Mint a single-use browser voice session preloaded with the live reading."""
    agent_id = ensure_agent()
    session = _request(
        "POST",
        "/sessions/create",
        json={
            "agent_id": agent_id,
            "type": "voice",
            "custom_variables": {k: str(v) for k, v in variables.items()},
        },
    )
    return {
        "sessionId": session.get("session_id"),
        "wsUrl": session.get("ws_url"),
        "expiresAt": session.get("expires_at"),
        "agentId": agent_id,
    }
