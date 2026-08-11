"""Throwaway probe: what does this OmniDimension key actually let us do?

Prints endpoint shapes from the live API so the integration is written against
observed behaviour instead of assumptions. Never prints the key.
"""
import json
import os
import sys
from pathlib import Path

import httpx
import yaml

BASE = "https://omnidim.io/api/v1"


def load_key() -> str:
    env = Path(__file__).parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("OMNIDIM_API_KEY="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("OMNIDIM_API_KEY", "")


KEY = load_key()
if not KEY:
    sys.exit("No OMNIDIM_API_KEY found")
print(f"Key loaded ({len(KEY)} chars, ends ...{KEY[-4:]})\n")

HEADERS = {"Authorization": f"Bearer {KEY}"}


def show(label: str, response: httpx.Response, limit: int = 900) -> None:
    body = response.text
    try:
        body = json.dumps(response.json(), indent=1)[:limit]
    except Exception:
        body = body[:limit]
    print(f"--- {label}  [{response.status_code}]\n{body}\n")


with httpx.Client(timeout=45, headers=HEADERS) as client:
    show("GET /agents", client.get(f"{BASE}/agents"))

    print("--- OpenAPI: endpoints that matter")
    spec = yaml.safe_load(httpx.get("https://docs.omnidim.io/openapi.yaml", timeout=60).text)
    for path, methods in spec.get("paths", {}).items():
        if any(k in path for k in ("session", "agent", "dispatch", "voice")):
            for method, op in methods.items():
                if method in ("get", "post", "patch", "put", "delete"):
                    print(f"  {method.upper():6} {path}   {op.get('summary', '')}")

    print()
    session_paths = [p for p in spec.get("paths", {}) if "session" in p.lower()]
    for path in session_paths:
        op = spec["paths"][path].get("post")
        if not op:
            continue
        schema = (
            op.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        print(f"--- POST {path} request schema\n{json.dumps(schema, indent=1)[:1200]}\n")

    create = spec.get("paths", {}).get("/agents/create", {}).get("post")
    if create:
        schema = (
            create.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        print(f"--- POST /agents/create request schema\n{json.dumps(schema, indent=1)[:2600]}\n")

    agent_config = spec.get("components", {}).get("schemas", {}).get("AgentConfigInput", {})
    props = agent_config.get("properties", {})
    print("--- AgentConfigInput properties")
    for name, prop in props.items():
        print(f"  {name:24} {prop.get('type', prop.get('$ref', '?')):10} {str(prop.get('description', ''))[:80]}")
    print(f"\n--- context_breakdown\n{json.dumps(props.get('context_breakdown', {}), indent=1)[:900]}")
    print(f"\n--- web_search / post_call / voice hints\n{json.dumps({k: v for k, v in props.items() if k in ('voice', 'model', 'transcriber')}, indent=1)[:900]}")
