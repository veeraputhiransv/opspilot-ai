"""The public contract does not grow a generic execute endpoint."""

from app.main import create_app


def test_routes_match_the_design() -> None:
    app = create_app()
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/v1/events",
        "/api/v1/incidents",
        "/api/v1/incidents/{incident_id}",
        "/api/v1/incidents/{incident_id}/timeline",
        "/api/v1/incidents/{incident_id}/agent-runs",
        "/api/v1/agent-runs",
        "/api/v1/incidents/{incident_id}/resolve",
        "/api/v1/incidents/{incident_id}/rca",
        "/api/v1/approvals",
        "/api/v1/approvals/{approval_id}/approve",
        "/api/v1/approvals/{approval_id}/reject",
        "/api/v1/approvals/{approval_id}/modify",
        "/api/v1/events/stream",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/api-keys",
        "/api/v1/realtime/tickets",
        "/api/v1/audit",
    }
    assert expected <= paths
    assert not any("execute-tool" in path or path.endswith("/shell") for path in paths)
