"""Slack incoming-webhook adapter. Channel must already be allowlisted."""

from app.integrations.http import request_json
from app.tools.base import ToolResult


class SlackAdapter:
    def __init__(self, webhook_url: str, allowed_channels: set[str]) -> None:
        self.webhook_url = webhook_url
        self.allowed_channels = allowed_channels

    def _channel(self, channel: str) -> str:
        if channel not in self.allowed_channels:
            raise ValueError(f"Slack channel is not allowlisted: {channel}")
        return channel

    async def verify(self) -> ToolResult:
        return ToolResult("EXECUTED", "Slack webhook is configured.", {"connected": True})

    async def send(self, channel: str, text: str, idempotency_key: str) -> ToolResult:
        self._channel(channel)
        safe = {
            "channel": channel,
            "text": text[:2000],
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": text[:2000]},
                }
            ],
        }
        await request_json(
            "POST",
            self.webhook_url,
            json={**safe, "idempotency_key": idempotency_key},
            extra_hosts=set(),
        )
        return ToolResult("EXECUTED", "Posted the Slack message.", {"delivered": True, "channel": channel})
