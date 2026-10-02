"""Tool call result shared by demo and real adapters."""

from dataclasses import dataclass


@dataclass
class ToolResult:
    status: str
    summary: str
    data: dict
