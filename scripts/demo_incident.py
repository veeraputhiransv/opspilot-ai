#!/usr/bin/env python3
"""Open the payment-service pool incident and wait until the workflow pauses.

Logs in as the AcmeFlow demo operator. Does not approve anything — approve the
rollback in the console so the decision stays human.

Requires a seeded workspace (OPSPILOT_DEMO_SEED_ENABLED=true and scripts/seed_demo.py).

    python scripts/demo_incident.py
    python scripts/demo_incident.py http://localhost:8000
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
DEMO_EMAIL = os.environ.get("OPSPILOT_DEMO_EMAIL", "alex.morgan@acmeflow.example")
DEMO_PASSWORD = os.environ.get("OPSPILOT_DEMO_PASSWORD", "AcmeFlow-operator-12")


def request(method: str, path: str, body: dict | None = None, token: str | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    call = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    call.add_header("Content-Type", "application/json")
    if token:
        call.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(call, timeout=30) as response:
        return json.loads(response.read().decode())


def main() -> int:
    try:
        tokens = request(
            "POST",
            "/api/v1/auth/login",
            {"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        )
    except urllib.error.HTTPError as exc:
        print(f"Demo login failed ({exc.code}). Seed the workspace first: python scripts/seed_demo.py")
        return 1
    except urllib.error.URLError as exc:
        print(f"Cannot reach {BASE}: {exc}")
        return 1

    token = tokens["access_token"]
    try:
        created = request("POST", "/api/v1/demo/scenarios/db_pool/trigger", token=token)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode() if exc.fp else ""
        print(f"Cannot trigger demo scenario ({exc.code}): {detail}")
        return 1

    incident_id = created["id"]
    print(f"Opened {created['incident_number']}")
    print(f"Console: http://localhost:3000/incidents/{incident_id}")
    deadline = time.time() + 90
    while time.time() < deadline:
        incident = request("GET", f"/api/v1/incidents/{incident_id}", token=token)
        activity = incident.get("current_activity") or ""
        print(f"  {incident['status']} · {activity}")
        if incident["status"] == "awaiting_approval":
            print("Workflow paused. Approve the rollback in the console.")
            return 0
        if incident["status"] in {"resolved", "closed"}:
            print("Incident reached a terminal state before approval.")
            return 0
        time.sleep(1)
    print("Timed out waiting for the approval pause.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
