from datetime import datetime

import pytest

from app.integrations.email import EmailAdapter
from app.integrations.logs import LogsAdapter
from app.integrations.slack import SlackAdapter


@pytest.mark.asyncio
async def test_slack_channel_allowlist() -> None:
    adapter = SlackAdapter("https://hooks.slack.com/services/TEST/TEST/TEST", {"#incidents"})
    with pytest.raises(ValueError):
        await adapter.send("#random", "hello", "idem-1")


@pytest.mark.asyncio
async def test_email_group_allowlist() -> None:
    adapter = EmailAdapter(
        host="smtp.example",
        port=587,
        username="",
        password="",
        mail_from="ops@example.com",
        allowed_groups={"impacted_customers": "customers@example.com"},
    )
    with pytest.raises(ValueError):
        adapter.resolve_recipient("attackers")
    assert adapter.resolve_recipient("impacted_customers") == "customers@example.com"


@pytest.mark.asyncio
async def test_logs_fail_closed_without_url() -> None:
    adapter = LogsAdapter("")
    result = await adapter.search(
        service="payment-service",
        environment="production",
        start_time=datetime.fromisoformat("2026-10-02T00:00:00+00:00"),
        end_time=None,
        severity=None,
        search_terms="pool",
        limit=10,
    )
    assert result.status == "FAILED"
    assert result.data["entries"] == []
