"""Capability catalog. Policy and agents resolve capabilities, not vendor names."""

from dataclasses import dataclass

PROVIDERS = ("github", "slack", "email", "logs", "deployments")

CAPABILITIES: dict[str, tuple[str, ...]] = {
    "github": ("source.recent_commits", "source.pull_requests", "action.create_issue"),
    "slack": ("communication.draft", "communication.send"),
    "email": ("email.draft", "email.send"),
    "logs": ("logs.search",),
    "deployments": ("deployment.list", "deployment.rollback", "service.restart"),
}

TOOL_CAPABILITY: dict[str, str] = {
    "get_recent_commits": "source.recent_commits",
    "create_github_issue": "action.create_issue",
    "draft_slack_message": "communication.draft",
    "send_slack_message": "communication.send",
    "draft_customer_email": "email.draft",
    "send_customer_email": "email.send",
    "search_logs": "logs.search",
    "get_recent_deployments": "deployment.list",
    "rollback_deployment": "deployment.rollback",
    "restart_service": "service.restart",
}

RETRY_CLASS: dict[str, str] = {
    "search_logs": "SAFE_TO_RETRY",
    "get_recent_deployments": "SAFE_TO_RETRY",
    "get_recent_commits": "SAFE_TO_RETRY",
    "search_previous_incidents": "SAFE_TO_RETRY",
    "search_customer_reports": "SAFE_TO_RETRY",
    "draft_slack_message": "SAFE_TO_RETRY",
    "draft_customer_email": "SAFE_TO_RETRY",
    "create_github_issue": "REQUIRES_PROVIDER_IDEMPOTENCY",
    "send_slack_message": "REQUIRES_PROVIDER_IDEMPOTENCY",
    "send_customer_email": "REQUIRES_PROVIDER_IDEMPOTENCY",
    "rollback_deployment": "DO_NOT_RETRY",
    "restart_service": "DO_NOT_RETRY",
}


@dataclass(frozen=True)
class ProviderDescriptor:
    provider: str
    capabilities: tuple[str, ...]


def provider_for_capability(capability: str) -> str | None:
    for provider, caps in CAPABILITIES.items():
        if capability in caps:
            return provider
    return None


def capability_for_tool(tool_name: str) -> str | None:
    return TOOL_CAPABILITY.get(tool_name)
