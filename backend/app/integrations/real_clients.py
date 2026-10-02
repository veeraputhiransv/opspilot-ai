"""Real adapters.

Destructive actions POST a JSON body to an operator-configured webhook.
They never open a shell. Missing configuration is a failed tool call.
"""

import asyncio
import smtplib
from email.message import EmailMessage

import httpx

from app.core.config import Settings
from app.tools.base import ToolResult


async def _post_json(url: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        if not response.content:
            return {"status_code": response.status_code}
        return response.json()


async def search_logs_real(settings: Settings, service: str, environment: str) -> ToolResult:
    if not settings.log_query_url:
        return ToolResult("FAILED", "Log query URL is not configured.", {"entries": []})
    data = await _post_json(
        settings.log_query_url,
        {"service": service, "environment": environment},
    )
    entries = data.get("entries", [])
    return ToolResult("EXECUTED", f"Fetched {len(entries)} log lines.", {"entries": entries})


async def commits_real(settings: Settings, repo: str) -> ToolResult:
    if not settings.github_token:
        return ToolResult("FAILED", "GitHub token is not configured.", {"commits": []})
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"https://api.github.com/repos/{repo}/commits",
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
            },
            params={"per_page": 5},
        )
        response.raise_for_status()
        commits = [
            {
                "sha": item["sha"][:7],
                "message": item["commit"]["message"].split("\n", 1)[0],
                "author": item["commit"]["author"]["name"],
                "committed_at": item["commit"]["author"]["date"],
                "files": [],
            }
            for item in response.json()
        ]
    return ToolResult("EXECUTED", f"Fetched {len(commits)} commits from {repo}.", {"commits": commits})


async def create_issue_real(settings: Settings, repo: str, title: str, body: str) -> ToolResult:
    if not settings.github_token:
        return ToolResult("FAILED", "GitHub token is not configured.", {})
    data = await _post_json(
        f"https://api.github.com/repos/{repo}/issues",
        {"title": title, "body": body},
        headers={
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
        },
    )
    return ToolResult(
        "EXECUTED",
        f"Opened GitHub issue {data.get('html_url', '')}.",
        {"url": data.get("html_url"), "number": data.get("number")},
    )


async def slack_real(settings: Settings, text: str) -> ToolResult:
    if not settings.slack_webhook_url:
        return ToolResult("FAILED", "Slack webhook is not configured.", {})
    await _post_json(settings.slack_webhook_url, {"text": text})
    return ToolResult("EXECUTED", "Posted the Slack message.", {"delivered": True})


async def rollback_real(settings: Settings, payload: dict) -> ToolResult:
    if not settings.rollback_webhook:
        return ToolResult("FAILED", "Rollback webhook is not configured.", {})
    data = await _post_json(settings.rollback_webhook, payload)
    return ToolResult("EXECUTED", "Rollback webhook accepted the request.", data)


async def restart_real(settings: Settings, payload: dict) -> ToolResult:
    if not settings.restart_webhook:
        return ToolResult("FAILED", "Restart webhook is not configured.", {})
    data = await _post_json(settings.restart_webhook, payload)
    return ToolResult("EXECUTED", "Restart webhook accepted the request.", data)


async def email_real(settings: Settings, subject: str, body: str, to_group: str) -> ToolResult:
    if not settings.smtp_host or not settings.smtp_from:
        return ToolResult("FAILED", "SMTP is not configured.", {})

    def _send() -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.smtp_from
        message["To"] = settings.smtp_from
        message.set_content(f"Group: {to_group}\n\n{body}")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as client:
            client.starttls()
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)

    await asyncio.to_thread(_send)
    return ToolResult("EXECUTED", f"Sent email for group {to_group}.", {"delivered": True})
