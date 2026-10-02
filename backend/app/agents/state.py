"""Graph state and the evidence passed into the reasoner."""

from dataclasses import dataclass, field
from typing import TypedDict


class IncidentState(TypedDict, total=False):
    incident_id: str
    run_id: str
    workspace_id: str
    phase: str
    step_sequence: int
    awaiting_approval: bool
    auto_resolve: bool
    resolved_now: bool
    model_used: str
    token_usage: dict[str, int]
    errors: list[str]
    actor: str
    proposed: list[dict]


@dataclass
class Evidence:
    event: dict
    logs: list[dict] = field(default_factory=list)
    deployments: list[dict] = field(default_factory=list)
    commits: list[dict] = field(default_factory=list)
    related_incidents: list[dict] = field(default_factory=list)
    customer_reports: list[dict] = field(default_factory=list)


@dataclass
class Hypothesis:
    key: str
    title: str
    description: str
    confidence: float
    evidence: list[str]
    is_primary: bool = False


@dataclass
class ProposedAction:
    tool_name: str
    title: str
    reason: str
    expected_impact: str
    confidence: float
    arguments: dict
    evidence: list[str]


@dataclass
class RcaDraft:
    executive_summary: str
    impact: str
    detection: str
    timeline_narrative: str
    root_cause: str
    contributing_factors: list[str]
    resolution: str
    corrective_actions: list[str]
    preventive_actions: list[str]
    confidence: float
    evidence_sources: list[str]
