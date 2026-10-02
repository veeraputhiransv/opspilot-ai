"""Normalized log search. Log text is evidence, never instructions."""

from datetime import datetime

from app.core.redaction import looks_like_injection, redact
from app.integrations.http import request_json
from app.tools.base import ToolResult


class LogsAdapter:
    def __init__(self, query_url: str) -> None:
        self.query_url = query_url

    async def verify(self) -> ToolResult:
        if not self.query_url:
            return ToolResult("FAILED", "Log query URL is not configured.", {})
        return ToolResult("EXECUTED", "Log query URL is configured.", {"connected": True})

    async def search(
        self,
        *,
        service: str,
        environment: str,
        start_time: datetime | None,
        end_time: datetime | None,
        severity: str | None,
        search_terms: str,
        limit: int,
    ) -> ToolResult:
        if not self.query_url:
            return ToolResult(
                "FAILED",
                "Log search is not configured. Production fails closed when no provider is connected.",
                {"entries": []},
            )
        data = await request_json(
            "POST",
            self.query_url,
            json={
                "service": service,
                "environment": environment,
                "start_time": start_time.isoformat() if start_time else None,
                "end_time": end_time.isoformat() if end_time else None,
                "severity": severity,
                "search_terms": search_terms,
                "limit": limit,
            },
            extra_hosts=_host(self.query_url),
        )
        entries = []
        rows = data.get("entries", []) if isinstance(data, dict) else []
        for item in rows[:limit]:
            if not isinstance(item, dict):
                continue
            message = redact(str(item.get("message", "")))
            entries.append(
                {
                    "timestamp": item.get("timestamp"),
                    "severity": item.get("severity") or item.get("level"),
                    "service": item.get("service") or service,
                    "message": message,
                    "source_reference": item.get("source_reference"),
                    "metadata": item.get("metadata") or {},
                    "injection_flagged": looks_like_injection(message),
                }
            )
        return ToolResult("EXECUTED", f"Fetched {len(entries)} log lines.", {"entries": entries})


def _host(url: str) -> set[str]:
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    return {host} if host else set()
