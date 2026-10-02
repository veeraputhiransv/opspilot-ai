"""Replaceable integration adapters. Agent code depends on these protocols, not SDKs."""

from typing import Protocol

from app.tools.base import ToolResult


class LogSearch(Protocol):
    async def search(self, service: str, environment: str) -> ToolResult: ...


class SourceControl(Protocol):
    async def recent_commits(self, repo: str) -> ToolResult: ...

    async def create_issue(self, repo: str, title: str, body: str) -> ToolResult: ...


class DeploymentPlatform(Protocol):
    async def history(self, service: str) -> ToolResult: ...

    async def rollback(self, service: str, from_version: str, to_version: str) -> ToolResult: ...

    async def restart(self, service: str, environment: str) -> ToolResult: ...


class ChatNotifier(Protocol):
    async def send(self, channel: str, text: str) -> ToolResult: ...


class MailSender(Protocol):
    async def send(self, to_group: str, subject: str, body: str) -> ToolResult: ...


class KnowledgeStore(Protocol):
    async def search(self, query: str, limit: int) -> list[dict]: ...


class LlmProvider(Protocol):
    async def complete(self, prompt: str) -> str: ...
