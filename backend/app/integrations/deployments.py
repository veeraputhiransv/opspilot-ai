"""Normalized deployment operations. Targets must match the incident allowlist."""

from app.integrations.http import request_json
from app.tools.base import ToolResult


class DeploymentAdapter:
    def __init__(self, rollback_url: str, restart_url: str, allowed_services: set[str]) -> None:
        self.rollback_url = rollback_url
        self.restart_url = restart_url
        self.allowed_services = allowed_services

    async def verify(self) -> ToolResult:
        if not self.rollback_url and not self.restart_url:
            return ToolResult("FAILED", "Deployment webhooks are not configured.", {})
        return ToolResult("EXECUTED", "Deployment webhooks are configured.", {"connected": True})

    def _service(self, service: str) -> str:
        if self.allowed_services and service not in self.allowed_services:
            raise ValueError(f"Service is not allowlisted: {service}")
        return service

    async def history(self, service: str) -> ToolResult:
        self._service(service)
        return ToolResult("FAILED", "Deployment history webhook is not configured.", {"deployments": []})

    async def rollback(
        self, service: str, from_version: str, to_version: str, *, dry_run: bool, idempotency_key: str
    ) -> ToolResult:
        name = self._service(service)
        if not self.rollback_url:
            return ToolResult("FAILED", "Rollback webhook is not configured.", {})
        payload = {
            "service": name,
            "from_version": from_version,
            "to_version": to_version,
            "dry_run": dry_run,
            "idempotency_key": idempotency_key,
        }
        extra = _host(self.rollback_url)
        data = await request_json("POST", self.rollback_url, json=payload, extra_hosts=extra)
        body = data if isinstance(data, dict) else {"response": data}
        return ToolResult("EXECUTED", "Rollback webhook accepted the request.", body)

    async def restart(self, service: str, environment: str, *, dry_run: bool, idempotency_key: str) -> ToolResult:
        name = self._service(service)
        if not self.restart_url:
            return ToolResult("FAILED", "Restart webhook is not configured.", {})
        payload = {
            "service": name,
            "environment": environment,
            "dry_run": dry_run,
            "idempotency_key": idempotency_key,
        }
        extra = _host(self.restart_url)
        data = await request_json("POST", self.restart_url, json=payload, extra_hosts=extra)
        body = data if isinstance(data, dict) else {"response": data}
        return ToolResult("EXECUTED", "Restart webhook accepted the request.", body)


def _host(url: str) -> set[str]:
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    return {host} if host else set()
