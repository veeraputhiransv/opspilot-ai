"""Fixed tool catalog.

Handlers receive validated arguments. `mode=demo` never calls the network.
`mode=real` fails closed when credentials are missing.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import UnknownTool
from app.integrations import demo_data
from app.tools.base import ToolResult
from app.tools.schemas import (
    CommitsArgs,
    CustomerReportsArgs,
    DeploymentsArgs,
    EmailArgs,
    GitHubIssueArgs,
    PreviousIncidentsArgs,
    RestartArgs,
    RollbackArgs,
    SearchLogsArgs,
    SlackArgs,
)

ToolHandler = Callable[[BaseModel, "ToolContext"], Awaitable[ToolResult]]
logger = logging.getLogger("opspilot.tools")


@dataclass
class ToolContext:
    mode: str
    incident_id: UUID
    workspace_id: UUID
    scenario_key: str
    service: str
    environment: str
    started_at: datetime
    settings: Settings
    session: Any = None
    integrations: Any = None
    idempotency_key: str = ""


@dataclass
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: ToolHandler
    capability: str
    timeout_seconds: float = 15
    retry: int = 0
    idempotent: bool = True
    risk_category: str = "LOW"
    requires_approval: bool = False


class ToolRegistry:
    def __init__(self, specs: dict[str, ToolSpec]) -> None:
        self._specs = specs

    def get(self, name: str) -> ToolSpec:
        try:
            return self._specs[name]
        except KeyError as exc:
            raise UnknownTool(f"Tool is not registered: {name}") from exc

    def names(self) -> list[str]:
        return sorted(self._specs)


def build_registry() -> ToolRegistry:
    specs = {
        "search_logs": ToolSpec(
            "search_logs",
            "Search application logs for the affected service.",
            SearchLogsArgs,
            _search_logs,
            "logs.search",
            idempotent=True,
        ),
        "get_recent_deployments": ToolSpec(
            "get_recent_deployments",
            "List recent deployments for the service.",
            DeploymentsArgs,
            _deployments,
            "deployment.list",
        ),
        "get_recent_commits": ToolSpec(
            "get_recent_commits",
            "List recent source-control commits.",
            CommitsArgs,
            _commits,
            "source.recent_commits",
        ),
        "search_previous_incidents": ToolSpec(
            "search_previous_incidents",
            "Retrieve similar historical incidents in this workspace.",
            PreviousIncidentsArgs,
            _previous,
            "knowledge",
        ),
        "search_customer_reports": ToolSpec(
            "search_customer_reports",
            "Search customer or support signals for the service.",
            CustomerReportsArgs,
            _reports,
            "signals",
        ),
        "create_github_issue": ToolSpec(
            "create_github_issue",
            "Open a tracking issue in an allowlisted repository.",
            GitHubIssueArgs,
            _issue,
            "action.create_issue",
            idempotent=False,
        ),
        "draft_slack_message": ToolSpec(
            "draft_slack_message",
            "Draft an incident Slack message without sending it.",
            SlackArgs,
            _draft_slack,
            "communication.draft",
        ),
        "send_slack_message": ToolSpec(
            "send_slack_message",
            "Send a Slack message to an allowlisted channel.",
            SlackArgs,
            _send_slack,
            "communication.send",
            idempotent=False,
        ),
        "draft_customer_email": ToolSpec(
            "draft_customer_email",
            "Draft a customer email without sending it.",
            EmailArgs,
            _draft_email,
            "email.draft",
        ),
        "send_customer_email": ToolSpec(
            "send_customer_email",
            "Send email to an allowlisted recipient group.",
            EmailArgs,
            _send_email,
            "email.send",
            idempotent=False,
        ),
        "rollback_deployment": ToolSpec(
            "rollback_deployment",
            "Roll back to a version already present in deployment evidence.",
            RollbackArgs,
            _rollback,
            "deployment.rollback",
            timeout_seconds=30,
            idempotent=True,
        ),
        "restart_service": ToolSpec(
            "restart_service",
            "Restart the affected service via webhook.",
            RestartArgs,
            _restart,
            "service.restart",
            timeout_seconds=30,
            idempotent=False,
        ),
    }
    from app.policies.risk_policy import RiskPolicyService

    policy = RiskPolicyService()
    for name, spec in specs.items():
        decision = policy.evaluate(name)
        spec.risk_category = decision.risk
        spec.requires_approval = decision.requires_approval
    return ToolRegistry(specs)


async def _via_capability(
    ctx: ToolContext, capability: str, payload: dict, demo: ToolResult
) -> ToolResult:
    if ctx.mode != "real":
        return demo
    if ctx.integrations is None:
        return ToolResult("FAILED", "No integration resolver is configured.", {})
    return await ctx.integrations.run_capability(
        ctx.workspace_id, capability, payload, idempotency_key=ctx.idempotency_key
    )


async def _search_logs(args: BaseModel, ctx: ToolContext) -> ToolResult:
    payload = args if isinstance(args, SearchLogsArgs) else SearchLogsArgs.model_validate(args)
    bundle = demo_data.evidence_for(ctx.scenario_key, ctx.started_at)
    demo = ToolResult("EXECUTED", f"Returned {len(bundle['logs'])} log lines.", {"entries": bundle["logs"]})
    return await _via_capability(
        ctx,
        "logs.search",
        {
            "service": payload.service,
            "environment": payload.environment,
            "search_terms": "",
            "limit": 50,
        },
        demo,
    )


async def _deployments(args: BaseModel, ctx: ToolContext) -> ToolResult:
    bundle = demo_data.evidence_for(ctx.scenario_key, ctx.started_at)
    rows = bundle["deployments"]
    current = next((item["version"] for item in rows if item["status"] == "active"), "unknown")
    demo = ToolResult("EXECUTED", f"Active deployment is {current}.", {"deployments": rows})
    return await _via_capability(ctx, "deployment.list", {"service": ctx.service}, demo)


async def _commits(args: BaseModel, ctx: ToolContext) -> ToolResult:
    payload = args if isinstance(args, CommitsArgs) else CommitsArgs.model_validate(args)
    bundle = demo_data.evidence_for(ctx.scenario_key, ctx.started_at)
    commits = bundle["commits"][: payload.limit]
    head = commits[0]["sha"] if commits else "none"
    demo = ToolResult("EXECUTED", f"Notable commit {head}.", {"commits": commits})
    return await _via_capability(
        ctx,
        "source.recent_commits",
        {"service": payload.service, "repo": _repo(payload.service), "limit": payload.limit},
        demo,
    )


async def _previous(args: BaseModel, ctx: ToolContext) -> ToolResult:
    from app.rag.retriever import search_similar

    payload = (
        args if isinstance(args, PreviousIncidentsArgs) else PreviousIncidentsArgs.model_validate(args)
    )
    if ctx.session is not None:
        try:
            async with ctx.session.begin_nested():
                rows = await search_similar(
                    ctx.session, payload.query, payload.limit, ctx.workspace_id
                )
            if rows:
                top = rows[0]
                summary = f"Top match {top['external_id']} ({top['similarity']:.2f})."
                return ToolResult("EXECUTED", summary, {"incidents": rows})
            return ToolResult("EXECUTED", "No prior incidents in this workspace.", {"incidents": []})
        except Exception:
            logger.warning("vector_search_failed", exc_info=True)
            return ToolResult(
                "EXECUTED", "No prior incidents in this workspace.", {"incidents": []}
            )
    return ToolResult("EXECUTED", "No prior incidents in this workspace.", {"incidents": []})


async def _reports(args: BaseModel, ctx: ToolContext) -> ToolResult:
    bundle = demo_data.evidence_for(ctx.scenario_key, ctx.started_at)
    reports = [item for item in bundle["customer_reports"] if item["service"] == ctx.service]
    if ctx.mode == "real" and ctx.session is not None:
        from sqlalchemy import select

        from app.models import CustomerReport

        result = await ctx.session.scalars(
            select(CustomerReport).where(
                CustomerReport.service == ctx.service,
                CustomerReport.workspace_id == ctx.workspace_id,
            )
        )
        reports = [
            {
                "external_ref": row.external_ref,
                "service": row.service,
                "title": row.title,
                "body": row.body,
                "source": row.source,
                "created_at": row.created_at.isoformat(),
            }
            for row in result
        ]
    return ToolResult("EXECUTED", f"Found {len(reports)} customer reports.", {"reports": reports})


async def _issue(args: BaseModel, ctx: ToolContext) -> ToolResult:
    payload = args if isinstance(args, GitHubIssueArgs) else GitHubIssueArgs.model_validate(args)
    demo = ToolResult(
        "EXECUTED",
        f"Simulated GitHub issue in {payload.repo}.",
        {
            "simulated": True,
            "provider": "github",
            "repository": payload.repo,
            "external_issue_id": "4821",
            "external_url": f"https://github.com/{payload.repo}/issues/4821",
            "repo": payload.repo,
            "url": f"https://github.com/{payload.repo}/issues/4821",
            "number": 4821,
            "title": payload.title,
        },
    )
    return await _via_capability(
        ctx,
        "action.create_issue",
        {"repo": payload.repo, "title": payload.title, "body": payload.body},
        demo,
    )


async def _draft_slack(args: BaseModel, ctx: ToolContext) -> ToolResult:
    payload = args if isinstance(args, SlackArgs) else SlackArgs.model_validate(args)
    return ToolResult(
        "EXECUTED",
        f"Draft stored for {payload.channel}. Not sent.",
        {"channel": payload.channel, "text": payload.text, "delivered": False},
    )


async def _send_slack(args: BaseModel, ctx: ToolContext) -> ToolResult:
    payload = args if isinstance(args, SlackArgs) else SlackArgs.model_validate(args)
    demo = ToolResult(
        "EXECUTED",
        f"Simulated Slack post to {payload.channel}.",
        {"simulated": True, "channel": payload.channel, "delivered": True},
    )
    return await _via_capability(
        ctx, "communication.send", {"channel": payload.channel, "text": payload.text}, demo
    )


async def _draft_email(args: BaseModel, ctx: ToolContext) -> ToolResult:
    payload = args if isinstance(args, EmailArgs) else EmailArgs.model_validate(args)
    return ToolResult(
        "EXECUTED",
        f"Draft stored for {payload.to_group}. Not sent.",
        {
            "to_group": payload.to_group,
            "subject": payload.subject,
            "body": payload.body,
            "delivered": False,
        },
    )


async def _send_email(args: BaseModel, ctx: ToolContext) -> ToolResult:
    payload = args if isinstance(args, EmailArgs) else EmailArgs.model_validate(args)
    demo = ToolResult(
        "EXECUTED",
        f"Simulated email to group {payload.to_group}.",
        {"simulated": True, "to_group": payload.to_group, "delivered": True},
    )
    return await _via_capability(
        ctx,
        "email.send",
        {"to_group": payload.to_group, "subject": payload.subject, "body": payload.body},
        demo,
    )


async def _rollback(args: BaseModel, ctx: ToolContext) -> ToolResult:
    payload = args if isinstance(args, RollbackArgs) else RollbackArgs.model_validate(args)
    body = payload.model_dump()
    demo = ToolResult(
        "EXECUTED",
        f"Simulated rollback of {payload.service} from {payload.from_version} to {payload.to_version}.",
        {
            "simulated": True,
            "service": payload.service,
            "from_version": payload.from_version,
            "to_version": payload.to_version,
            "resulting_version": payload.to_version,
        },
    )
    return await _via_capability(ctx, "deployment.rollback", body, demo)


async def _restart(args: BaseModel, ctx: ToolContext) -> ToolResult:
    payload = args if isinstance(args, RestartArgs) else RestartArgs.model_validate(args)
    body = payload.model_dump()
    demo = ToolResult(
        "EXECUTED",
        f"Simulated restart of {payload.service} in {payload.environment}.",
        {"simulated": True, **body, "ready": True},
    )
    return await _via_capability(ctx, "service.restart", body, demo)


def _repo(service: str) -> str:
    if service == "cache-service":
        return "opspilot-demo/cache-service"
    if service == "payment-service":
        return "opspilot-demo/payment-service"
    return "opspilot-demo/platform"
