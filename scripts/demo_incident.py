#!/usr/bin/env python3
"""Open the payment-service pool incident and wait until the workflow pauses.

The script does not approve anything. Approve the rollback in the console so the
recording shows a real human decision.

    python scripts/demo_incident.py
    python scripts/demo_incident.py http://localhost:8000
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
EVENT = {
    "service": "payment-service",
    "environment": "production",
    "event_type": "error_rate_spike",
    "error_rate": 72,
    "message": "Database connection timeout",
}


def request(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    call = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    call.add_header("Content-Type", "application/json")
    call.add_header("X-Operator", "demo.operator")
    with urllib.request.urlopen(call, timeout=30) as response:
        return json.loads(response.read().decode())


def main() -> int:
    try:
        created = request("POST", "/api/v1/events", EVENT)
    except urllib.error.URLError as exc:
        print(f"Cannot reach {BASE}: {exc}")
        return 1
    incident_id = created["id"]
    print(f"Opened {created['incident_number']}")
    print(f"Console: http://localhost:3000/incidents/{incident_id}")
    deadline = time.time() + 90
    while time.time() < deadline:
        incident = request("GET", f"/api/v1/incidents/{incident_id}")
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
