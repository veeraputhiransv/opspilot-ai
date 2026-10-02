"""Risk classification and argument allowlists.

Every tool has a fixed risk. A caller may pass `llm_suggested_risk`; it is stored
on the decision and ignored. HIGH always requires a human. LOW is read-only and
may run immediately. MEDIUM requires a human when the tool writes to a system
outside OpsPilot. Drafting a message is not sending it.
"""

from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.core.errors import PolicyViolation, UnknownTool

# Fixed table. Do not derive this from a prompt.
TOOL_RISK: dict[str, str] = {
    "search_logs": "LOW",
    "get_recent_deployments": "LOW",
    "get_recent_commits": "LOW",
    "search_previous_incidents": "LOW",
    "search_customer_reports": "LOW",
    "create_github_issue": "MEDIUM",
    "draft_slack_message": "MEDIUM",
    "draft_customer_email": "MEDIUM",
    "send_slack_message": "HIGH",
    "send_customer_email": "HIGH",
    "rollback_deployment": "HIGH",
    "restart_service": "HIGH",
}

# External writes. Draft tools only store text inside OpsPilot.
EXTERNAL_WRITE = {
    "create_github_issue",
    "send_slack_message",
    "send_customer_email",
    "rollback_deployment",
    "restart_service",
}

MITIGATING_TOOLS = {"rollback_deployment", "restart_service"}


@dataclass(frozen=True)
class RiskDecision:
    tool_name: str
    risk: str
    requires_approval: bool
    ignored_suggestion: str | None = None


class RiskPolicyService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def evaluate(
        self,
        tool_name: str,
        llm_suggested_risk: str | None = None,
        environment: str | None = None,
    ) -> RiskDecision:
        if tool_name not in TOOL_RISK:
            raise UnknownTool(f"Tool is not registered: {tool_name}")
        risk = TOOL_RISK[tool_name]
        requires = risk == "HIGH" or tool_name in EXTERNAL_WRITE
        if risk == "LOW":
            requires = False
        if environment == "production" and tool_name in EXTERNAL_WRITE:
            requires = True
        return RiskDecision(
            tool_name=tool_name,
            risk=risk,
            requires_approval=requires,
            ignored_suggestion=llm_suggested_risk,
        )

    def authorize(self, tool_name: str, approval_status: str | None) -> RiskDecision:
        decision = self.evaluate(tool_name)
        if decision.requires_approval and approval_status != "APPROVED":
            raise PolicyViolation(f"{tool_name} requires human approval before it can run.")
        return decision

    def validate_arguments(
        self,
        tool_name: str,
        arguments: dict,
        *,
        known_versions: set[str],
    ) -> None:
        """Reject arguments that would widen the tool beyond the incident evidence."""
        self.evaluate(tool_name)
        if tool_name == "rollback_deployment":
            self._validate_rollback(arguments, known_versions)
        elif tool_name == "restart_service":
            self._validate_restart(arguments)
        elif tool_name == "send_slack_message" or tool_name == "draft_slack_message":
            channel = str(arguments.get("channel", ""))
            if channel not in self._settings.csv_set(self._settings.slack_allowed_channels):
                raise PolicyViolation(f"Slack channel is not allowlisted: {channel}")
        elif tool_name == "create_github_issue":
            repo = str(arguments.get("repo", ""))
            if repo not in self._settings.csv_set(self._settings.github_allowed_repos):
                raise PolicyViolation(f"GitHub repository is not allowlisted: {repo}")
        elif tool_name == "send_customer_email" or tool_name == "draft_customer_email":
            group = str(arguments.get("to_group", ""))
            if group not in self._settings.csv_set(self._settings.mail_allowed_groups):
                raise PolicyViolation(f"Mail group is not allowlisted: {group}")

    def _validate_rollback(self, arguments: dict, known_versions: set[str]) -> None:
        current = str(arguments.get("from_version", ""))
        target = str(arguments.get("to_version", ""))
        if current not in known_versions or target not in known_versions:
            raise PolicyViolation("Rollback versions must both appear in deployment evidence.")
        if current == target:
            raise PolicyViolation("Rollback target must differ from the current version.")

    def _validate_restart(self, arguments: dict) -> None:
        environment = str(arguments.get("environment", ""))
        if environment not in {"production", "staging", "development"}:
            raise PolicyViolation("Restart environment is not allowed.")

    def catalog(self) -> list[dict[str, str | bool]]:
        rows: list[dict[str, str | bool]] = []
        for name in TOOL_RISK:
            decision = self.evaluate(name)
            rows.append(
                {
                    "tool_name": decision.tool_name,
                    "risk": decision.risk,
                    "requires_approval": decision.requires_approval,
                }
            )
        return rows
