"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { ApprovalCard } from "@/components/approval-card";
import { SeverityBadge, StatusText } from "@/components/status";
import { useStream } from "@/components/stream";
import { Button } from "@/components/ui/button";
import { accessToken, api, apiBase } from "@/lib/api";
import { formatClock, formatLatency, formatWhen, investigationScore, liveDuration } from "@/lib/format";
import type { IncidentAction, IncidentDetail } from "@/lib/types";

export function IncidentView({ id }: { id: string }) {
  const { revision, reconnecting, connected } = useStream();
  const [incident, setIncident] = useState<IncidentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(() => Date.now());
  const [openEvidence, setOpenEvidence] = useState<string | null>(null);
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

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

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

  async function copyRca() {
    if (!incident?.rca) return;
    const report = incident.rca;
    const text = [
      "Executive Summary",
      report.executive_summary,
      "",
      "Impact",
      report.impact,
      "",
      "Detection",
      report.detection,
      "",
      "Timeline",
      report.timeline_narrative,
      "",
      "Root Cause",
      report.root_cause,
      "",
      "Contributing Factors",
      ...report.contributing_factors.map((item) => `- ${item}`),
      "",
      "Resolution",
      report.resolution,
      "",
      "Corrective Actions",
      ...report.corrective_actions.map((item) => `- ${item}`),
      "",
      "Preventive Actions",
      ...report.preventive_actions.map((item) => `- ${item}`),
      "",
      "Evidence",
      ...report.evidence_sources.map((item) => `- ${item}`),
      "",
      "AI Disclosure",
      report.disclosure,
    ].join("\n");
    await navigator.clipboard.writeText(text);
    toast.success("RCA copied");
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
  const working = incident.status === "investigating" || incident.status === "executing";
  const duration = liveDuration(incident.started_at, incident.resolved_at);
  void now;

  return (
    <div className="space-y-6">
      <header className="rounded-md border border-line bg-surface p-6 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-mono text-2xl">{incident.incident_number}</h1>
              <SeverityBadge severity={incident.severity} />
              <StatusText status={incident.status} />
            </div>
            <h2 className="mt-2 text-xl font-medium">{incident.title}</h2>
            <p className="mt-2 text-sm text-muted">
              {incident.service} · {incident.environment} · started {formatWhen(incident.started_at)} ·
              duration {duration}
            </p>
            <p className="mt-3 text-sm">
              {working ? (
                <span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-primary" />
              ) : null}
              {incident.current_activity}
            </p>
          </div>
          <div className="text-right text-xs text-muted">
            <div>{incident.model_used ?? "opspilot-deterministic-v1"}</div>
            <div>
              {incident.input_tokens + incident.output_tokens} tokens · {incident.execution_time_ms ?? 0} ms
              compute
            </div>
            {incident.status !== "resolved" ? (
              <Button className="mt-3" variant="outline" size="sm" onClick={() => void resolve()}>
                Mark resolved
              </Button>
            ) : null}
          </div>
        </div>
      </header>

      {reconnecting || !connected ? (
        <p className="rounded-md border border-line bg-surface px-4 py-3 text-sm">
          {reconnecting ? "Realtime stream reconnecting…" : "Realtime stream disconnected."}
        </p>
      ) : null}
      {incident.last_error ? (
        <p className="rounded-md border border-line bg-surface px-4 py-3 text-sm text-danger">
          Investigation error: {incident.last_error}
        </p>
      ) : null}
      {incident.actions.some((item) => item.status === "FAILED") ? (
        <p className="rounded-md border border-line bg-surface px-4 py-3 text-sm text-danger">
          An approved action failed. The incident was not marked successful from the browser.
        </p>
      ) : null}

      <div className="grid items-start gap-6 xl:grid-cols-[320px_1fr]">
        <section className="rounded-md border border-line bg-surface p-5 shadow-card">
          <h2 className="text-sm font-medium">Investigation timeline</h2>
          <ol className="mt-4 space-y-4 border-l border-line pl-4">
            {incident.timeline.map((event, index) => {
              const current = index === incident.timeline.length - 1 && working;
              return (
                <li key={event.id} className="relative">
                  <span
                    className={`absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full ${
                      current ? "animate-pulse bg-primary" : "bg-line"
                    }`}
                  />
                  <time className="font-mono text-xs text-muted">{formatClock(event.occurred_at)}</time>
                  <p className="text-sm">{event.title}</p>
                  {event.detail ? <p className="text-xs leading-5 text-muted">{event.detail}</p> : null}
                </li>
              );
            })}
          </ol>
        </section>

        <div className="space-y-6">
          <section id="investigation" className="rounded-md border border-line bg-surface p-5 shadow-card">
            <h2 className="text-sm font-medium">AI Investigation</h2>
            {primary ? (
              <>
                <p className="mt-1 text-xs text-muted">Primary hypothesis from correlated evidence</p>
                <div className="mt-3 flex items-end justify-between gap-4">
                  <p className="text-xl">{primary.title}</p>
                  <div className="text-right">
                    <p className="text-xs uppercase tracking-wide text-muted">Investigation score</p>
                    <p className="font-mono text-2xl">{investigationScore(primary.confidence)}</p>
                  </div>
                </div>
                <div className="mt-3 h-1.5 rounded-full bg-elevated">
                  <div
                    className="h-1.5 rounded-full bg-primary"
                    style={{ width: `${Math.round(primary.confidence * 100)}%` }}
                  />
                </div>
                <p className="mt-3 text-sm text-muted">{primary.description}</p>
                <h3 className="mt-5 text-xs uppercase tracking-wide text-muted">Supporting evidence</h3>
                <ul className="mt-2 space-y-2 text-sm">
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
                      <span className="font-mono text-muted">{investigationScore(item.confidence)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>

          {incident.approvals.map((approval) => (
            <ApprovalCard key={approval.id} approval={approval} onChanged={() => void load()} />
          ))}

          <ExecutionPanel actions={incident.actions} />
          <EvidencePanel incident={incident} openId={openEvidence} onToggle={setOpenEvidence} />
          <AgentActivity incident={incident} openStep={openStep} onToggle={setOpenStep} />

          {incident.status === "resolved" && incident.rca ? (
            <section className="rounded-md border border-line bg-surface p-5 shadow-card">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-medium">Resolution</h2>
                  <p className="mt-1 text-sm text-muted">
                    {incident.service} recovered. Duration {duration}. Peak error rate{" "}
                    {incident.error_rate == null ? "—" : `${incident.error_rate}%`}.
                  </p>
                </div>
                <a href="#rca" className="text-sm text-primary">
                  View RCA
                </a>
              </div>
            </section>
          ) : null}

          {incident.rca ? (
            <section id="rca" className="rounded-md border border-line bg-surface p-5 shadow-card">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-sm font-medium">RCA</h2>
                <div className="flex gap-3">
                  <button type="button" className="text-sm text-primary" onClick={() => void copyRca()}>
                    Copy RCA
                  </button>
                  <button type="button" className="text-sm text-primary" onClick={() => void downloadRca()}>
                    Export
                  </button>
                </div>
              </div>
              <RcaBlock title="Executive Summary" body={incident.rca.executive_summary} />
              <RcaBlock title="Impact" body={incident.rca.impact} />
              <RcaBlock title="Detection" body={incident.rca.detection} />
              <RcaBlock title="Timeline" body={incident.rca.timeline_narrative} />
              <RcaBlock title="Root Cause" body={incident.rca.root_cause} />
              <RcaList title="Contributing Factors" items={incident.rca.contributing_factors} />
              <RcaBlock title="Resolution" body={incident.rca.resolution} />
              <RcaList title="Corrective Actions" items={incident.rca.corrective_actions} />
              <RcaList title="Preventive Actions" items={incident.rca.preventive_actions} />
              <RcaList title="Evidence" items={incident.rca.evidence_sources} />
              <RcaBlock title="AI Disclosure" body={incident.rca.disclosure} />
              <p className="mt-4 text-xs text-muted">
                Investigation score {investigationScore(incident.rca.confidence)} · version {incident.rca.version}
              </p>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function ExecutionPanel({ actions }: { actions: IncidentAction[] }) {
  if (actions.length === 0) {
    return (
      <section id="execution" className="rounded-md border border-line bg-surface p-5 shadow-card">
        <h2 className="text-sm font-medium">Execution</h2>
        <p className="mt-3 text-sm text-muted">No actions proposed yet.</p>
      </section>
    );
  }
  return (
    <section id="execution" className="rounded-md border border-line bg-surface p-5 shadow-card">
      <h2 className="text-sm font-medium">Execution</h2>
      <ul className="mt-3 divide-y divide-line">
        {actions.map((action) => (
          <li key={action.id} className="py-3 text-sm">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p>{action.title}</p>
                <p className="text-xs text-muted">
                  {action.tool_name} · {action.risk_level}
                </p>
                {action.execution_id ? (
                  <p className="mt-1 font-mono text-xs text-muted">execution {action.execution_id}</p>
                ) : null}
                {action.provider_ref ? (
                  <p className="font-mono text-xs text-muted">ref {action.provider_ref}</p>
                ) : null}
                {action.executed_at ? (
                  <p className="text-xs text-muted">started {formatWhen(action.executed_at)}</p>
                ) : null}
              </div>
              <span className="font-mono text-xs">{action.status}</span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function EvidencePanel({
  incident,
  openId,
  onToggle,
}: {
  incident: IncidentDetail;
  openId: string | null;
  onToggle: (id: string | null) => void;
}) {
  const cards = useMemo(() => {
    const rows: Array<{ id: string; category: string; title: string; summary: string; meta: string }> = [];
    const structured = incident.evidence.items ?? [];
    if (structured.length > 0) {
      for (const item of structured) {
        rows.push({
          id: item.id,
          category: item.source_type,
          title: item.title,
          summary: item.summary,
          meta: item.source_reference ?? "n/a",
        });
      }
      return rows;
    }
    incident.evidence.logs.forEach((log, index) => {
      rows.push({
        id: `log-${index}`,
        category: "Logs",
        title: `${log.service} ${log.level}`,
        summary: log.message,
        meta: formatClock(log.timestamp),
      });
    });
    incident.evidence.deployments.forEach((deploy, index) => {
      rows.push({
        id: `deploy-${index}`,
        category: "Deployment",
        title: deploy.version,
        summary: `${deploy.status} · ${deploy.author} · ${deploy.commit_sha}`,
        meta: formatWhen(deploy.deployed_at),
      });
    });
    incident.evidence.commits.forEach((commit, index) => {
      rows.push({
        id: `commit-${index}`,
        category: "Source Control",
        title: commit.sha,
        summary: commit.message,
        meta: commit.author,
      });
    });
    incident.evidence.related_incidents.forEach((item, index) => {
      rows.push({
        id: `hist-${index}`,
        category: "Historical Incident",
        title: item.external_id,
        summary: `${item.title}. ${item.root_cause}`,
        meta: `similarity ${item.similarity.toFixed(2)}`,
      });
    });
    return rows;
  }, [incident]);

  return (
    <section id="evidence" className="rounded-md border border-line bg-surface p-5 shadow-card">
      <h2 className="text-sm font-medium">Evidence</h2>
      <p className="mt-1 text-xs text-muted">Persisted correlation artifacts, not decorative cards.</p>
      {cards.length === 0 ? (
        <p className="mt-3 text-sm text-muted">No evidence collected yet.</p>
      ) : (
        <ul className="mt-4 grid gap-3 md:grid-cols-2">
          {cards.map((card) => (
            <li key={card.id} className="rounded-md border border-line bg-bg p-3">
              <button
                type="button"
                className="w-full text-left"
                onClick={() => onToggle(openId === card.id ? null : card.id)}
              >
                <p className="text-xs uppercase tracking-wide text-muted">{card.category}</p>
                <p className="mt-1 font-mono text-sm">{card.title}</p>
                <p className="mt-1 text-xs text-muted">{card.meta}</p>
                {openId === card.id ? <p className="mt-2 text-sm leading-6">{card.summary}</p> : null}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function AgentActivity({
  incident,
  openStep,
  onToggle,
}: {
  incident: IncidentDetail;
  openStep: string | null;
  onToggle: (id: string | null) => void;
}) {
  const run = incident.agent_runs[0];
  return (
    <section className="rounded-md border border-line bg-surface p-5 shadow-card">
      <h2 className="text-sm font-medium">Agent activity</h2>
      <p className="mt-1 text-xs text-muted">Graph steps only. No hidden reasoning transcript.</p>
      {!run ? (
        <p className="mt-3 text-sm text-muted">No agent run yet.</p>
      ) : (
        <ul className="mt-4 space-y-2">
          {run.steps.map((step) => (
            <li key={step.id} className="rounded-md bg-bg px-3 py-2 text-sm">
              <button
                type="button"
                className="flex w-full justify-between gap-3 text-left"
                onClick={() => onToggle(openStep === step.id ? null : step.id)}
              >
                <span>
                  {step.node_name} · {step.status}
                  {step.status === "running" ? (
                    <span className="ml-2 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
                  ) : null}
                </span>
                <span className="font-mono text-xs text-muted">{formatLatency(step.latency_ms)}</span>
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
      )}
    </section>
  );
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
