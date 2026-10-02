import httpx
import pytest

from app.core.errors import PolicyViolation
from app.integrations.github import GitHubAdapter
from app.integrations.http import assert_public_https


@pytest.mark.asyncio
async def test_github_allowlist_and_issue_create(monkeypatch) -> None:
    adapter = GitHubAdapter("token", {"acme/payments"})

    async def fake_request(self, method, url, **kwargs):
        class Response:
            status_code = 201
            content = b"{}"

            def raise_for_status(self) -> None:
                return None

            def json(self):
                if method == "GET" and url.endswith("/user"):
                    return {"login": "octocat"}
                if method == "GET" and url.endswith("/commits"):
                    return [
                        {
                            "sha": "abcdef123",
                            "commit": {
                                "message": "fix pool",
                                "author": {"name": "A", "date": "2026-01-01T00:00:00Z"},
                            },
                        }
                    ]
                return {"number": 42, "html_url": "https://github.com/acme/payments/issues/42"}

        return Response()

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    verified = await adapter.verify()
    assert verified.status == "EXECUTED"
    commits = await adapter.recent_commits("acme/payments")
    assert commits.data["commits"][0]["sha"] == "abcdef1"
    with pytest.raises(ValueError):
        await adapter.recent_commits("evil/repo")
    issue = await adapter.create_issue("acme/payments", "Outage", "body", "idem-1")
    assert issue.data["external_issue_id"] == "42"


def test_ssrf_blocked() -> None:
    with pytest.raises(PolicyViolation):
        assert_public_https("http://127.0.0.1/secrets")
    with pytest.raises(PolicyViolation):
        assert_public_https("https://evil.example/x")
