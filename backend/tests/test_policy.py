"""Risk policy is deterministic and cannot be talked out of a HIGH rating."""

import pytest

from app.core.errors import PolicyViolation, UnknownTool
from app.policies.risk_policy import RiskPolicyService


def test_risk_table_is_fixed_and_ignores_model_suggestion() -> None:
    policy = RiskPolicyService()
    decision = policy.evaluate("rollback_deployment", llm_suggested_risk="LOW")
    assert decision.risk == "HIGH"
    assert decision.requires_approval is True
    assert decision.ignored_suggestion == "LOW"


def test_high_tools_always_need_approval() -> None:
    policy = RiskPolicyService()
    for name in (
        "send_customer_email",
        "send_slack_message",
        "rollback_deployment",
        "restart_service",
    ):
        decision = policy.evaluate(name)
        assert decision.risk == "HIGH"
        assert decision.requires_approval is True
        with pytest.raises(PolicyViolation):
            policy.authorize(name, approval_status=None)
        policy.authorize(name, approval_status="APPROVED")


def test_medium_external_write_needs_approval_and_drafts_do_not() -> None:
    policy = RiskPolicyService()
    issue = policy.evaluate("create_github_issue")
    assert issue.risk == "MEDIUM"
    assert issue.requires_approval is True
    draft = policy.evaluate("draft_slack_message")
    assert draft.risk == "MEDIUM"
    assert draft.requires_approval is False
    policy.authorize("draft_customer_email", approval_status=None)


def test_read_tools_are_low() -> None:
    policy = RiskPolicyService()
    for name in (
        "search_logs",
        "get_recent_deployments",
        "get_recent_commits",
        "search_previous_incidents",
        "search_customer_reports",
    ):
        decision = policy.evaluate(name)
        assert decision.risk == "LOW"
        assert decision.requires_approval is False


def test_unknown_tool_is_rejected() -> None:
    policy = RiskPolicyService()
    for name in ("bash", "run_command", "shell", "exec"):
        with pytest.raises(UnknownTool):
            policy.evaluate(name)


def test_rollback_target_must_be_an_observed_version() -> None:
    policy = RiskPolicyService()
    known = {"v2.8.1", "v2.8.0"}
    policy.validate_arguments(
        "rollback_deployment",
        {"service": "payment-service", "from_version": "v2.8.1", "to_version": "v2.8.0"},
        known_versions=known,
    )
    with pytest.raises(PolicyViolation):
        policy.validate_arguments(
            "rollback_deployment",
            {"service": "payment-service", "from_version": "v2.8.1", "to_version": "v9.9.9"},
            known_versions=known,
        )


def test_channel_and_repo_allowlists() -> None:
    policy = RiskPolicyService()
    with pytest.raises(PolicyViolation):
        policy.validate_arguments(
            "send_slack_message",
            {"channel": "#random", "text": "hello"},
            known_versions=set(),
        )
    with pytest.raises(PolicyViolation):
        policy.validate_arguments(
            "create_github_issue",
            {"repo": "evil/org", "title": "x", "body": "y"},
            known_versions=set(),
        )


def test_production_mutations_always_need_approval() -> None:
    policy = RiskPolicyService()
    decision = policy.evaluate("create_github_issue", environment="production")
    assert decision.requires_approval is True
    rollback = policy.evaluate(
        "rollback_deployment", llm_suggested_risk="LOW", environment="production"
    )
    assert rollback.risk == "HIGH"
    assert rollback.requires_approval is True
    assert rollback.ignored_suggestion == "LOW"


def test_llm_cannot_authorize_without_human() -> None:
    policy = RiskPolicyService()
    with pytest.raises(PolicyViolation):
        policy.authorize("rollback_deployment", approval_status="LOW")
    with pytest.raises(PolicyViolation):
        policy.authorize("send_customer_email", approval_status="PENDING_APPROVAL")
