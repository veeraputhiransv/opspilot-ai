"""SMTP email adapter. Recipients come from allowlisted groups, not the model."""

import asyncio
import smtplib
from email.message import EmailMessage

from app.tools.base import ToolResult


class EmailAdapter:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        mail_from: str,
        allowed_groups: dict[str, str],
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.mail_from = mail_from
        self.allowed_groups = allowed_groups

    def resolve_recipient(self, to_group: str) -> str:
        address = self.allowed_groups.get(to_group)
        if not address or "@" not in address:
            raise ValueError(f"Mail group is not allowlisted: {to_group}")
        return address

    async def verify(self) -> ToolResult:
        if not self.host or not self.mail_from:
            return ToolResult("FAILED", "SMTP is not configured.", {})
        return ToolResult("EXECUTED", "SMTP configuration is present.", {"from": self.mail_from})

    async def send(self, to_group: str, subject: str, body: str, idempotency_key: str) -> ToolResult:
        recipient = self.resolve_recipient(to_group)

        def _send() -> None:
            message = EmailMessage()
            message["Subject"] = subject[:200]
            message["From"] = self.mail_from
            message["To"] = recipient
            message["X-Idempotency-Key"] = idempotency_key
            message.set_content(body[:8000])
            with smtplib.SMTP(self.host, self.port, timeout=20) as client:
                client.starttls()
                if self.username:
                    client.login(self.username, self.password)
                client.send_message(message)

        await asyncio.to_thread(_send)
        return ToolResult(
            "EXECUTED",
            f"Sent email for group {to_group}.",
            {"delivered": True, "provider_message_id": idempotency_key, "to_group": to_group},
        )
