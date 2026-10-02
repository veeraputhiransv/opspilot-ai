"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { ApprovalCard } from "@/components/approval-card";
import { SeverityBadge, StatusText } from "@/components/status";
import { useStream } from "@/components/stream";
import { Button } from "@/components/ui/button";
import { api, accessToken, apiBase } from "@/lib/api";
import { confidenceLabel, formatClock, formatWhen } from "@/lib/format";
import type { IncidentDetail } from "@/lib/types";

export function IncidentView({ id }: { id: string }) {
  const { revision, reconnecting, connected } = useStream();
  const [incident, setIncident] = useState<IncidentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [evidenceTab, setEvidenceTab] = useState<
    "items" | "logs" | "deployments" | "commits" | "history" | "reports"
  >("items");
  const [openStep, setOpenStep] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const next = await api<IncidentDetail>(`/api/v1/incidents/${id}`);
      setIncident(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load incident");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load, revision]);

  async function downloadRca() {
    const token = accessToken();
    const response = await fetch(`${apiBase()}/api/v1/incidents/${id}/rca/export`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (!response.ok) {
      toast.error("Unable to download RCA");
      return;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${incident?.incident_number ?? "incident"}-rca.html`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function resolve() {
    try {
      await api(`/api/v1/incidents/${id}/resolve`, { method: "POST" });
      toast.success("Incident resolved");
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Resolve failed");
    }
  }

  if (loading && !incident) {
    return <div className="h-64 animate-pulse rounded-md bg-surface" />;
  }
  if (error && !incident) {
    return (
      <div className="rounded-md border border-line bg-surface p-6">
        <p>{error}</p>
        <Button className="mt-4" onClick={() => void load()}>
          Retry
        </Button>
      </div>
    );
  }
  if (!incident) return null;

  const primary = incident.hypotheses.find((item) => item.is_primary) ?? incident.hypotheses[0];
  const alternatives = incident.hypotheses.filter((item) => item !== primary);
  const pending = incident.approvals.filter((item) => item.status === "PENDING_APPROVAL");
  const working = incident.status === "investigating" || incident.status === "executing";

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-2xl">{incident.incident_number}</h1>
            <SeverityBadge severity={incident.severity} />
            <StatusText status={incident.status} />
          </div>
          <p className="mt-2 text-lg">{incident.title}</p>
          <p className="mt-1 text-sm text-muted">
            {incident.service} · {incident.environment} · error rate{" "}
            {incident.error_rate == null ? "—" : `${incident.error_rate}%`} · started{" "}
            {formatWhen(incident.started_at)}
          </p>
          <p className="mt-2 text-sm">
            {working ? <span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-[#9eb8f5]" /> : null}
            {incident.current_activity}
          </p>
        </div>
        <div className="text-right text-xs text-muted">
          <div>{incident.model_used ?? "opspilot-deterministic-v1"}</div>
          <div>
            {incident.input_tokens + incident.output_tokens} tokens · {incident.execution_time_ms ?? 0} ms compute
          </div>
          {incident.status !== "resolved" ? (
            <Button className="mt-3" variant="outline" size="sm" onClick={() => void resolve()}>
              Mark resolved
            </Button>
          ) : null}
        </div>
      </header>

      {reconnecting || !connected ? (
        <p className="rounded-md border border-line bg-surface px-4 py-3 text-sm">
          {reconnecting ? "Realtime stream reconnecting…" : "Realtime stream disconnected."}
        </p>
      ) : null}
      {incident.last_error ? (
        <p className="rounded-md border border-[#6b2a2a] bg-[#3a1717] px-4 py-3 text-sm text-[#ffb4b4]">
          Investigation error: {incident.last_error}
        </p>
      ) : null}
      {incident.actions.some((item) => item.status === "FAILED") ? (
        <p className="rounded-md border border-[#6b2a2a] bg-[#3a1717] px-4 py-3 text-sm text-[#ffb4b4]">
          An approved action failed. The incident was not marked successful from the browser.
        </p>
      ) : null}
      {incident.actions.some((item) => item.status === "EXECUTING") ? (
        <p className="rounded-md border border-line bg-surface px-4 py-3 text-sm">
          Action execution in progress. Refresh is safe; the server will not double-run it.
        </p>
      ) : null}
      {incident.approvals.some((item) => item.status === "EXPIRED") ? (
        <p className="rounded-md border border-line bg-surface px-4 py-3 text-sm">This approval expired.</p>
      ) : null}
      {incident.status === "investigating" && incident.current_activity?.includes("Waiting") ? (
        <p className="rounded-md border border-line bg-surface px-4 py-3 text-sm">Investigation is stalled pending input.</p>
      ) : null}

      <div className="grid items-start gap-6 xl:grid-cols-[340px_1fr]">
        <section className="rounded-md border border-line bg-surface p-5">
          <h2 className="text-sm font-medium">Incident timeline</h2>
          <ol className="mt-4 space-y-4 border-l border-line pl-4">
            {incident.timeline.map((event, index) => (
              <li key={event.id} className="relative">
                <span
                  className={`absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full ${
                    index === incident.timeline.length - 1 ? "bg-[#9eb8f5]" : "bg-line"
                  }`}
                />
                <time className="font-mono text-xs text-muted">{formatClock(event.occurred_at)}</time>
                <p className="text-sm">{event.title}</p>
                {event.detail ? <p className="text-xs leading-5 text-muted">{event.detail}</p> : null}
              </li>
            ))}
          </ol>
        </section>

        <div className="space-y-6">
          <section className="rounded-md border border-line bg-surface p-5">
            <h2 className="text-sm font-medium">Likely root cause</h2>
            {primary ? (
              <>
                <div className="mt-3 flex items-end justify-between gap-4">
                  <p className="text-xl">{primary.title}</p>
                  <p className="font-mono text-2xl">{confidenceLabel(primary.confidence)}</p>
                </div>
                <div className="mt-3 h-1.5 rounded-full bg-elevated">
                  <div
                    className="h-1.5 rounded-full bg-[#9eb8f5]"
                    style={{ width: `${Math.round(primary.confidence * 100)}%` }}
                  />
                </div>
                <p className="mt-3 text-sm text-muted">{primary.description}</p>
                <ul className="mt-4 space-y-2 text-sm">
                  {primary.evidence.map((item) => (
                    <li key={item}>• {item}</li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="mt-3 text-sm text-muted">The agent has not ranked a hypothesis yet.</p>
            )}
            {alternatives.length > 0 ? (
              <div className="mt-5 border-t border-line pt-4">
                <h3 className="text-xs uppercase tracking-wide text-muted">Alternative hypotheses</h3>
                <ul className="mt-2 space-y-2">
                  {alternatives.map((item) => (
                    <li key={item.id} className="flex items-center justify-between text-sm">
                      <span>{item.title}</span>
                      <span className="font-mono text-muted">{confidenceLabel(item.confidence)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>

          {pending.map((approval) => (
            <ApprovalCard key={approval.id} approval={approval} onChanged={() => void load()} />
          ))}

          <section className="rounded-md border border-line bg-surface p-5">
            <h2 className="text-sm font-medium">Evidence</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {(["items", "logs", "deployments", "commits", "history", "reports"] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setEvidenceTab(tab)}
                  className={`rounded-md px-3 py-1 text-xs capitalize ${
                    evidenceTab === tab ? "bg-elevated text-text" : "text-muted"
                  }`}
                >
                  {tab === "history" ? "Similar incidents" : tab === "items" ? "Collected" : tab}
                </button>
              ))}
            </div>
            <div className="mt-4">
              {evidenceTab === "items" ? <EvidenceItems incident={incident} /> : null}
              {evidenceTab === "logs" ? <LogList incident={incident} /> : null}
              {evidenceTab === "deployments" ? <DeployList incident={incident} /> : null}
              {evidenceTab === "commits" ? <CommitList incident={incident} /> : null}
              {evidenceTab === "history" ? <HistoryList incident={incident} /> : null}
              {evidenceTab === "reports" ? <ReportList incident={incident} /> : null}
            </div>
          </section>

          <section className="rounded-md border border-line bg-surface p-5">
            <h2 className="text-sm font-medium">Actions</h2>
            {incident.actions.length === 0 ? (
              <p className="mt-3 text-sm text-muted">No actions proposed yet.</p>
            ) : (
              <ul className="mt-3 divide-y divide-line">
                {incident.actions.map((action) => (
                  <li key={action.id} className="flex items-start justify-between gap-4 py-3 text-sm">
                    <div>
                      <p>{action.title}</p>
                      <p className="text-xs text-muted">
                        {action.tool_name} · {action.risk_level}
                      </p>
                    </div>
                    <span className="font-mono text-xs">{action.status}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="rounded-md border border-line bg-surface p-5">
            <h2 className="text-sm font-medium">Agent run inspector</h2>
            <p className="mt-1 text-xs text-muted">Steps, tools, and timings. No hidden reasoning transcript.</p>
            {incident.agent_runs.length === 0 ? (
              <p className="mt-3 text-sm text-muted">No agent run yet.</p>
            ) : (
              incident.agent_runs.map((run) => (
                <div key={run.id} className="mt-4">
                  <p className="font-mono text-xs text-muted">
                    {run.status} · {run.model} · {run.latency_ms ?? 0} ms · {run.input_tokens}/{run.output_tokens} tokens
                  </p>
                  <ul className="mt-2 space-y-2">
                    {run.steps.map((step) => (
                      <li key={step.id} className="rounded-md bg-bg px-3 py-2 text-sm">
                        <button
                          type="button"
                          className="flex w-full justify-between gap-3 text-left"
                          onClick={() => setOpenStep(openStep === step.id ? null : step.id)}
                        >
                          <span>
                            {step.node_name} · {step.status}
                          </span>
                          <span className="font-mono text-xs text-muted">{step.latency_ms ?? 0} ms</span>
                        </button>
                        {openStep === step.id ? (
                          <div className="mt-2 space-y-1 text-xs text-muted">
                            <p>{step.summary}</p>
                            {step.evidence?.length ? <p>Evidence used: {step.evidence.join("; ")}</p> : null}
                            <p>
                              Tokens {step.input_tokens}/{step.output_tokens}
                            </p>
                            {step.error ? <p>{step.error}</p> : null}
                            {step.tools.map((tool) => (
                              <p key={tool.id} className="font-mono">
                                {tool.tool_name} · {tool.risk_level} · {tool.result_summary}
                              </p>
                            ))}
                          </div>
                        ) : (
                          <p className="text-xs text-muted">{step.summary}</p>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              ))
            )}
          </section>

          {incident.rca ? (
            <section className="rounded-md border border-line bg-surface p-5">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-medium">RCA</h2>
                <button type="button" className="text-sm text-primary" onClick={() => void downloadRca()}>
                  Download HTML
                </button>
              </div>
              <RcaBlock title="Executive summary" body={incident.rca.executive_summary} />
              <RcaBlock title="Impact" body={incident.rca.impact} />
              <RcaBlock title="Detection" body={incident.rca.detection} />
              <RcaBlock title="Timeline" body={incident.rca.timeline_narrative} />
              <RcaBlock title="Root cause" body={incident.rca.root_cause} />
              <RcaList title="Contributing factors" items={incident.rca.contributing_factors} />
              <RcaBlock title="Resolution" body={incident.rca.resolution} />
              <RcaList title="Corrective actions" items={incident.rca.corrective_actions} />
              <RcaList title="Preventive actions" items={incident.rca.preventive_actions} />
              <RcaList title="Evidence sources" items={incident.rca.evidence_sources} />
              <p className="mt-4 text-xs text-muted">
                Confidence {confidenceLabel(incident.rca.confidence)} · version {incident.rca.version}
              </p>
              <p className="mt-2 text-xs text-muted">{incident.rca.disclosure}</p>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function EvidenceItems({ incident }: { incident: IncidentDetail }) {
  if (!incident.evidence.items?.length) return <Empty>No structured evidence yet.</Empty>;
  return (
    <ul className="space-y-3 text-sm">
      {incident.evidence.items.map((item) => (
        <li key={item.id}>
          <p className="font-mono text-xs text-muted">
            {item.source_type} · {item.source_reference ?? "n/a"}
          </p>
          <p>{item.title}</p>
          <p className="text-xs text-muted">{item.summary}</p>
        </li>
      ))}
    </ul>
  );
}

function LogList({ incident }: { incident: IncidentDetail }) {
  if (incident.evidence.logs.length === 0) return <Empty>No logs yet.</Empty>;
  return (
    <ul className="space-y-2 font-mono text-xs">
      {incident.evidence.logs.map((log) => (
        <li key={`${log.timestamp}-${log.message}`}>
          <span className="text-muted">{formatClock(log.timestamp)}</span>{" "}
          <span className={log.level === "ERROR" ? "text-[#ff8d8d]" : "text-muted"}>{log.level}</span>{" "}
          {log.message}
        </li>
      ))}
    </ul>
  );
}

function DeployList({ incident }: { incident: IncidentDetail }) {
  if (incident.evidence.deployments.length === 0) return <Empty>No deployments yet.</Empty>;
  return (
    <ul className="space-y-2 text-sm">
      {incident.evidence.deployments.map((deploy) => (
        <li key={deploy.version} className="flex justify-between gap-3">
          <span className="font-mono">
            {deploy.version} · {deploy.status}
          </span>
          <span className="text-muted">{deploy.author}</span>
        </li>
      ))}
    </ul>
  );
}

function CommitList({ incident }: { incident: IncidentDetail }) {
  if (incident.evidence.commits.length === 0) return <Empty>No commits yet.</Empty>;
  return (
    <ul className="space-y-2 text-sm">
      {incident.evidence.commits.map((commit) => (
        <li key={commit.sha}>
          <span className="font-mono text-xs">{commit.sha}</span> {commit.message}
          <div className="text-xs text-muted">{commit.author}</div>
        </li>
      ))}
    </ul>
  );
}

function HistoryList({ incident }: { incident: IncidentDetail }) {
  if (incident.evidence.related_incidents.length === 0) return <Empty>No similar incidents yet.</Empty>;
  return (
    <ul className="space-y-3 text-sm">
      {incident.evidence.related_incidents.map((item) => (
        <li key={item.external_id}>
          <div className="flex justify-between">
            <span className="font-mono text-xs">{item.external_id}</span>
            <span className="font-mono text-xs">{item.similarity.toFixed(2)}</span>
          </div>
          <p>{item.title}</p>
          <p className="text-xs text-muted">{item.root_cause}</p>
        </li>
      ))}
    </ul>
  );
}

function ReportList({ incident }: { incident: IncidentDetail }) {
  if (incident.evidence.customer_reports.length === 0) return <Empty>No customer reports.</Empty>;
  return (
    <ul className="space-y-3 text-sm">
      {incident.evidence.customer_reports.map((report) => (
        <li key={report.external_ref}>
          <p className="font-mono text-xs text-muted">{report.external_ref}</p>
          <p>{report.title}</p>
          <p className="text-xs text-muted">{report.body}</p>
        </li>
      ))}
    </ul>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-muted">{children}</p>;
}

function RcaBlock({ title, body }: { title: string; body: string }) {
  return (
    <div className="mt-4">
      <h3 className="text-xs uppercase tracking-wide text-muted">{title}</h3>
      <p className="mt-1 text-sm leading-6">{body}</p>
    </div>
  );
}

function RcaList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="mt-4">
      <h3 className="text-xs uppercase tracking-wide text-muted">{title}</h3>
      <ul className="mt-1 space-y-1 text-sm">
        {items.map((item) => (
          <li key={item}>• {item}</li>
        ))}
      </ul>
    </div>
  );
}
