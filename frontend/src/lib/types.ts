export interface IncidentSummary {
  id: string;
  incident_number: string;
  service: string;
  environment: string;
  severity: string | null;
  status: string;
  title: string;
  error_rate: number | null;
  current_activity: string | null;
  started_at: string;
  resolved_at: string | null;
}

export interface TimelineEvent {
  id: string;
  incident_id: string;
  incident_number: string | null;
  occurred_at: string;
  event_type: string;
  title: string;
  detail: string | null;
  actor: string;
}

export interface Hypothesis {
  id: string;
  key: string;
  title: string;
  description: string;
  confidence: number;
  is_primary: boolean;
  evidence: string[];
  evidence_ids: string[];
  rank: number;
}

export interface IncidentAction {
  id: string;
  tool_name: string;
  risk_level: string;
  status: string;
  title: string;
  reason: string;
  expected_impact: string;
  confidence: number;
  arguments: Record<string, string | number | boolean>;
  result: Record<string, unknown> | null;
}

export interface Approval {
  id: string;
  incident_id: string;
  incident_number: string;
  service: string;
  action_id: string;
  status: string;
  tool_name: string;
  title: string;
  reason: string;
  risk_level: string;
  expected_impact: string;
  confidence: number;
  evidence: string[];
  proposed_arguments: Record<string, string | number | boolean>;
  created_at: string;
}

export interface ToolSummary {
  id: string;
  tool_name: string;
  risk_level: string;
  status: string;
  result_summary: string;
  latency_ms: number | null;
}

export interface AgentStep {
  id: string;
  node_name: string;
  sequence: number;
  status: string;
  summary: string;
  evidence: string[] | null;
  confidence: number | null;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number | null;
  error: string | null;
  tools: ToolSummary[];
}

export interface AgentRun {
  id: string;
  incident_id: string | null;
  status: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
  steps: AgentStep[];
}

export interface EvidenceItem {
  id: string;
  source_type: string;
  source_reference: string | null;
  title: string;
  summary: string;
  observed_at: string | null;
  created_at: string;
}

export interface Evidence {
  items: EvidenceItem[];
  logs: Array<{ timestamp: string; level: string; service: string; message: string }>;
  deployments: Array<{
    version: string;
    status: string;
    deployed_at: string;
    commit_sha: string;
    author: string;
  }>;
  commits: Array<{
    sha: string;
    message: string;
    author: string;
    committed_at: string;
    files: string[];
  }>;
  related_incidents: Array<{
    external_id: string;
    title: string;
    service: string;
    root_cause: string;
    similarity: number;
  }>;
  customer_reports: Array<{
    external_ref: string;
    title: string;
    body: string;
    source: string;
  }>;
}

export interface RcaReport {
  executive_summary: string;
  impact: string;
  detection: string;
  timeline_narrative: string;
  root_cause: string;
  contributing_factors: string[];
  resolution: string;
  corrective_actions: string[];
  preventive_actions: string[];
  confidence: number;
  evidence_sources: string[];
  disclosure: string;
  version: number;
  created_at: string;
}

export interface IncidentList {
  items: IncidentSummary[];
  total: number;
}

export interface IncidentDetail extends IncidentSummary {
  event_type: string;
  scenario_key: string;
  summary: string | null;
  message: string;
  model_used: string | null;
  input_tokens: number;
  output_tokens: number;
  execution_time_ms: number | null;
  last_error: string | null;
  hypotheses: Hypothesis[];
  actions: IncidentAction[];
  approvals: Approval[];
  timeline: TimelineEvent[];
  evidence: Evidence;
  agent_runs: AgentRun[];
  rca: RcaReport | null;
}

export interface Dashboard {
  active_incidents: number;
  mttr_seconds: number | null;
  ai_investigations: number;
  pending_approvals: number;
  automation_success_rate: number | null;
  recent_incidents: IncidentSummary[];
  activity: TimelineEvent[];
}

export interface DemoScenario {
  key: string;
  label: string;
  summary: string;
  event: {
    service: string;
    environment: string;
    event_type: string;
    error_rate: number;
    message: string;
  };
}

export interface KnowledgeDoc {
  id: string;
  external_id: string;
  title: string;
  service: string;
  symptoms: string;
  root_cause: string;
  resolution: string;
  created_at: string;
}

export interface SearchHit extends Omit<KnowledgeDoc, "id" | "created_at"> {
  similarity: number;
}

export interface PublicSettings {
  mode: string;
  reasoning_model: string;
  llm_enabled: boolean;
  step_delay_ms: number;
  policies: Array<{ tool_name: string; risk: string; requires_approval: boolean }>;
  integrations: Record<string, boolean>;
}

export interface IncidentCreated {
  id: string;
  incident_number: string;
  status: string;
  replayed?: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  workspace_id: string;
}

export interface Me {
  id: string;
  email: string;
  full_name: string;
  workspaces: Array<{
    id: string;
    organization_id: string;
    name: string;
    slug: string;
    role: string;
  }>;
}

export interface IngestKey {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}
