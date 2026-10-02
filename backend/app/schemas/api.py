"""Request and response models. Extra inbound fields are rejected."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    environment: str = Field(pattern=r"^(production|staging|development)$")
    event_type: str = Field(pattern=r"^[a-z0-9_]{3,64}$")
    error_rate: float = Field(ge=0, le=100)
    message: str = Field(min_length=3, max_length=2000)
    timestamp: datetime | None = None
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)


class IncidentCreated(BaseModel):
    id: UUID
    incident_number: str
    status: str
    replayed: bool = False
    idempotency_key: str | None = None


class IncidentSummary(BaseModel):
    id: UUID
    incident_number: str
    service: str
    environment: str
    severity: str | None
    status: str
    title: str
    error_rate: float | None
    current_activity: str | None
    started_at: datetime
    resolved_at: datetime | None


class IncidentList(BaseModel):
    items: list[IncidentSummary]
    total: int


class TimelineOut(BaseModel):
    id: UUID
    incident_id: UUID
    incident_number: str | None = None
    occurred_at: datetime
    event_type: str
    title: str
    detail: str | None
    actor: str


class HypothesisOut(BaseModel):
    id: UUID
    key: str
    title: str
    description: str
    confidence: float
    is_primary: bool
    evidence: list[str]
    evidence_ids: list[str]
    rank: int


class ActionOut(BaseModel):
    id: UUID
    tool_name: str
    risk_level: str
    status: str
    title: str
    reason: str
    expected_impact: str
    confidence: float
    arguments: dict
    result: dict | None
    execution_id: UUID | None = None
    provider_ref: str | None = None
    executed_at: datetime | None = None
    attempt_count: int = 0


class ApprovalOut(BaseModel):
    id: UUID
    incident_id: UUID
    incident_number: str
    service: str
    action_id: UUID
    status: str
    tool_name: str
    title: str
    reason: str
    risk_level: str
    expected_impact: str
    confidence: float
    evidence: list[str]
    proposed_arguments: dict
    created_at: datetime
    decided_by: str | None = None
    decided_at: datetime | None = None


class ToolSummary(BaseModel):
    id: UUID
    tool_name: str
    risk_level: str
    status: str
    result_summary: str
    latency_ms: int | None


class StepOut(BaseModel):
    id: UUID
    node_name: str
    sequence: int
    status: str
    summary: str
    evidence: list | None
    confidence: float | None
    input_tokens: int
    output_tokens: int
    latency_ms: int | None
    error: str | None
    tools: list[ToolSummary]


class RunOut(BaseModel):
    id: UUID
    incident_id: UUID | None = None
    graph_name: str = "incident_response"
    status: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None
    steps: list[StepOut]


class EvidenceItemOut(BaseModel):
    id: UUID
    source_type: str
    source_reference: str | None
    title: str
    summary: str
    observed_at: datetime | None
    created_at: datetime


class EvidenceOut(BaseModel):
    items: list[EvidenceItemOut]
    logs: list[dict]
    deployments: list[dict]
    commits: list[dict]
    related_incidents: list[dict]
    customer_reports: list[dict]


class RcaOut(BaseModel):
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
    disclosure: str
    version: int
    created_at: datetime


class IncidentDetail(IncidentSummary):
    event_type: str
    scenario_key: str
    summary: str | None
    message: str
    model_used: str | None
    input_tokens: int
    output_tokens: int
    execution_time_ms: int | None
    last_error: str | None
    hypotheses: list[HypothesisOut]
    actions: list[ActionOut]
    approvals: list[ApprovalOut]
    timeline: list[TimelineOut]
    evidence: EvidenceOut
    agent_runs: list[RunOut]
    rca: RcaOut | None


class DashboardOut(BaseModel):
    active_incidents: int
    mttr_seconds: float | None
    ai_investigations: int
    pending_approvals: int
    automation_success_rate: float | None
    recent_incidents: list[IncidentSummary]
    activity: list[TimelineOut]


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str = Field(min_length=2, max_length=2000)
    arguments: dict | None = None


class ModifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str = Field(min_length=2, max_length=2000)
    arguments: dict


class KnowledgeOut(BaseModel):
    id: UUID
    external_id: str
    title: str
    service: str
    symptoms: str
    root_cause: str
    resolution: str
    created_at: datetime


class SearchHit(BaseModel):
    external_id: str
    title: str
    service: str
    symptoms: str
    root_cause: str
    resolution: str
    similarity: float


class SearchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=3, max_length=2000)
    limit: int = Field(default=3, ge=1, le=10)


class PolicyRow(BaseModel):
    tool_name: str
    risk: str
    requires_approval: bool


class SettingsOut(BaseModel):
    mode: str
    reasoning_model: str
    llm_enabled: bool
    step_delay_ms: int
    policies: list[PolicyRow]
    integrations: dict[str, bool]


class HealthOut(BaseModel):
    status: str
    database: str
    mode: str
