"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { RiskBadge } from "@/components/status";
import { api } from "@/lib/api";
import { formatWhen, investigationScore } from "@/lib/format";
import type { Approval } from "@/lib/types";

export function ApprovalCard({
  approval,
  onChanged,
}: {
  approval: Approval;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [modifying, setModifying] = useState(false);
  const [comment, setComment] = useState("Reviewed from the console.");
  const [argumentsJson, setArgumentsJson] = useState(
    JSON.stringify(approval.proposed_arguments, null, 2),
  );
  const versions = versionPair(approval.proposed_arguments);
  const pending = approval.status === "PENDING_APPROVAL";

  async function decide(path: "approve" | "reject") {
    setBusy(true);
    try {
      await api(`/api/v1/approvals/${approval.id}/${path}`, {
        method: "POST",
        body: JSON.stringify({ comment }),
      });
      toast.success(path === "approve" ? "Approval recorded" : "Rejection recorded");
      onChanged();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Decision failed");
    } finally {
      setBusy(false);
    }
  }

  async function modify() {
    setBusy(true);
    try {
      const parsed = JSON.parse(argumentsJson) as Record<string, string>;
      await api(`/api/v1/approvals/${approval.id}/modify`, {
        method: "POST",
        body: JSON.stringify({ comment, arguments: parsed }),
      });
      toast.success("Proposal updated");
      setModifying(false);
      onChanged();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Modify failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <article
      className="rounded-md border border-line bg-surface p-6 shadow-card"
      data-tool-name={approval.tool_name}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted">Human Approval Required</p>
          <h3 className="mt-2 text-2xl font-medium">{approval.title}</h3>
          <p className="mt-1 font-mono text-xs text-muted">
            {approval.incident_number} · {approval.service}
          </p>
        </div>
        <RiskBadge risk={approval.risk_level} />
      </div>
      {versions ? (
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <div className="rounded-md border border-line bg-bg px-3 py-2">
            <p className="text-xs uppercase tracking-wide text-muted">From</p>
            <p className="mt-1 font-mono text-sm">{versions.from}</p>
          </div>
          <div className="rounded-md border border-line bg-bg px-3 py-2">
            <p className="text-xs uppercase tracking-wide text-muted">To</p>
            <p className="mt-1 font-mono text-sm">{versions.to}</p>
          </div>
        </div>
      ) : null}
      <dl className="mt-4 grid gap-3 text-sm md:grid-cols-2">
        <div>
          <dt className="text-xs uppercase tracking-wide text-muted">Investigation score</dt>
          <dd className="mt-1">{investigationScore(approval.confidence)}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-muted">Status</dt>
          <dd className="mt-1">{approval.status.replaceAll("_", " ")}</dd>
        </div>
      </dl>
      <p className="mt-4 text-sm leading-6">{approval.reason}</p>
      <p className="mt-3 text-sm text-muted">{approval.expected_impact}</p>
      {approval.evidence.length > 0 ? (
        <ul className="mt-4 space-y-1 text-sm text-muted">
          {approval.evidence.map((item) => (
            <li key={item}>• {item}</li>
          ))}
        </ul>
      ) : null}
      {!pending && approval.decided_by ? (
        <p className="mt-4 text-sm">
          {approval.status === "APPROVED" ? "Approved" : approval.status.replaceAll("_", " ")} by{" "}
          {approval.decided_by}
          {approval.decided_at ? ` · ${formatWhen(approval.decided_at)}` : ""}
        </p>
      ) : null}
      {pending ? (
        <div className="mt-5 space-y-3">
          <label className="block text-xs uppercase tracking-wide text-muted" htmlFor={`comment-${approval.id}`}>
            Decision note
          </label>
          <textarea
            id={`comment-${approval.id}`}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            className="min-h-16 w-full rounded-md border border-line bg-bg px-3 py-2 text-sm"
          />
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy} onClick={() => decide("approve")}>
              {approval.tool_name === "rollback_deployment" ? "Approve rollback" : "Approve"}
            </Button>
            <Button variant="outline" disabled={busy} onClick={() => decide("reject")}>
              Reject
            </Button>
            <Button variant="ghost" disabled={busy} onClick={() => setModifying((open) => !open)}>
              Modify
            </Button>
          </div>
          {modifying ? (
            <div className="space-y-2" role="dialog" aria-label="Modify proposed arguments">
              <label className="text-xs uppercase tracking-wide text-muted" htmlFor={`args-${approval.id}`}>
                Arguments
              </label>
              <textarea
                id={`args-${approval.id}`}
                value={argumentsJson}
                onChange={(event) => setArgumentsJson(event.target.value)}
                className="min-h-32 w-full rounded-md border border-line bg-bg px-3 py-2 font-mono text-xs"
              />
              <Button size="sm" disabled={busy} onClick={modify}>
                Save modification
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function versionPair(args: Record<string, string | number | boolean>) {
  if (typeof args.from_version !== "string" || typeof args.to_version !== "string") return null;
  return { from: args.from_version, to: args.to_version };
}
