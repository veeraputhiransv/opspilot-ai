"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { useAuth } from "@/components/auth-provider";
import { useStream } from "@/components/stream";
import { api, isForbidden } from "@/lib/api";
import { formatLatency } from "@/lib/format";
import type { AgentRun } from "@/lib/types";

export default function AgentRunsPage() {
  const { revision } = useStream();
  const { workspaceId } = useAuth();
  const [rows, setRows] = useState<AgentRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    api<AgentRun[]>("/api/v1/agent-runs")
      .then((next) => {
        setRows(next);
        setError(null);
      })
      .catch((err: Error) => setError(isForbidden(err) ? "Permission denied." : err.message));
  }, [revision, workspaceId]);

  if (error && !rows) return <p className="text-sm">{error}</p>;
  if (!rows) return <div className="h-40 animate-pulse rounded-md bg-surface" />;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-medium">Agent runs</h1>
        <p className="mt-1 text-sm text-muted">
          Persisted graph steps and tool calls. No hidden chain-of-thought.
        </p>
      </div>
      {rows.length === 0 ? (
        <div className="rounded-md border border-line bg-surface p-8 text-sm text-muted">
          No agent runs in this workspace yet.
        </div>
      ) : (
        rows.map((run, index) => (
          <article key={run.id} className="rounded-md border border-line bg-surface p-5 shadow-card">
            <div className="flex flex-wrap justify-between gap-3 text-sm">
              <div>
                <p className="text-xs uppercase tracking-wide text-muted">Incident Investigation</p>
                <p className="mt-1 font-mono text-sm">
                  Run #{String(rows.length - index).padStart(5, "0")}
                </p>
              </div>
              <div className="text-right text-xs text-muted">
                <p>{run.status} · {formatLatency(run.latency_ms)}</p>
                {run.incident_id ? (
                  <Link className="text-primary" href={`/incidents/${run.incident_id}`}>
                    Open incident
                  </Link>
                ) : null}
              </div>
            </div>
            <p className="mt-2 text-xs text-muted">
              {run.graph_name ?? "incident_response"} · {run.model} · {run.input_tokens}/{run.output_tokens}{" "}
              tokens
            </p>
            <ul className="mt-4 space-y-2">
              {run.steps.map((step) => (
                <li key={step.id} className="rounded-md bg-bg px-3 py-2 text-sm">
                  <button
                    type="button"
                    className="flex w-full justify-between"
                    onClick={() => setOpen(open === step.id ? null : step.id)}
                  >
                    <span>
                      {step.node_name} · {step.status}
                    </span>
                    <span className="font-mono text-xs text-muted">{formatLatency(step.latency_ms)}</span>
                  </button>
                  {open === step.id ? (
                    <div className="mt-2 space-y-1 text-xs text-muted">
                      <p>Output summary: {step.summary}</p>
                      {step.evidence?.length ? <p>Evidence used: {step.evidence.join("; ")}</p> : null}
                      <p>
                        Token usage {step.input_tokens}/{step.output_tokens}
                      </p>
                      {step.error ? <p>{step.error}</p> : null}
                      {step.tools.map((tool) => (
                        <p key={tool.id}>
                          Tool call {tool.tool_name} · {tool.status} · {tool.result_summary}
                        </p>
                      ))}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          </article>
        ))
      )}
    </div>
  );
}
