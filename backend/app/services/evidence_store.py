"""Persist structured evidence from tool results. No chain-of-thought."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Incident, IncidentEvidence
from app.models.base import utcnow
from app.tools.base import ToolResult

_SOURCE = {
    "search_logs": ("log", "entries"),
    "get_recent_deployments": ("deployment", "deployments"),
    "get_recent_commits": ("commit", "commits"),
    "search_previous_incidents": ("previous_incident", "incidents"),
    "search_customer_reports": ("customer_signal", "reports"),
}


async def persist_tool_evidence(
    session: AsyncSession,
    incident: Incident,
    tool_name: str,
    result: ToolResult,
) -> list[UUID]:
    if result.status != "EXECUTED":
        return []
    mapping = _SOURCE.get(tool_name)
    if mapping is None:
        return []
    source_type, collection = mapping
    rows = result.data.get(collection) or []
    ids: list[UUID] = []
    if not isinstance(rows, list):
        return []
    for item in rows:
        if not isinstance(item, dict):
            continue
        title, summary, reference, observed = _describe(source_type, item)
        row = IncidentEvidence(
            workspace_id=incident.workspace_id,
            incident_id=incident.id,
            source_type=source_type,
            source_reference=reference,
            title=title[:200],
            summary=summary,
            observed_at=observed,
            meta={"tool": tool_name},
        )
        session.add(row)
        await session.flush()
        ids.append(row.id)
    return ids


def _describe(source_type: str, item: dict) -> tuple[str, str, str | None, datetime | None]:
    if source_type == "log":
        return (
            str(item.get("level") or "log"),
            str(item.get("message") or "")[:2000],
            None,
            _parse_time(item.get("timestamp")),
        )
    if source_type == "deployment":
        version = str(item.get("version") or "unknown")
        return (
            f"Deployment {version}",
            f"{item.get('status', '')} commit {item.get('commit_sha', '')}",
            version,
            _parse_time(item.get("deployed_at")),
        )
    if source_type == "commit":
        sha = str(item.get("sha") or "")
        return (
            f"Commit {sha}",
            str(item.get("message") or "")[:2000],
            sha,
            _parse_time(item.get("committed_at")),
        )
    if source_type == "previous_incident":
        ext = str(item.get("external_id") or item.get("title") or "prior")
        return (
            str(item.get("title") or ext),
            str(item.get("root_cause") or item.get("resolution") or "")[:2000],
            ext,
            None,
        )
    ext = str(item.get("external_ref") or item.get("title") or "signal")
    return (
        str(item.get("title") or ext),
        str(item.get("body") or "")[:2000],
        ext,
        None,
    )


def _parse_time(value: object) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return utcnow()
