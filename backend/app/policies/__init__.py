"""Deterministic safety policy. The model does not get a vote."""

from app.policies.risk_policy import RiskDecision, RiskPolicyService

__all__ = ["RiskDecision", "RiskPolicyService"]
