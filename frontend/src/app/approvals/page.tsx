"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { ApprovalCard } from "@/components/approval-card";
import { useStream } from "@/components/stream";
import { api } from "@/lib/api";
import type { Approval } from "@/lib/types";

export default function ApprovalsPage() {
  const { revision } = useStream();
  const { workspaceId } = useAuth();
  const [rows, setRows] = useState<Approval[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    api<Approval[]>("/api/v1/approvals?status=PENDING_APPROVAL")
      .then((next) => {
        setRows(next);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, [revision, nonce, workspaceId]);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-medium">Approvals</h1>
      <p className="text-sm text-muted">
        High-risk actions stay here until an operator decides. The workflow is paused in the database, not in the browser.
      </p>
      {error ? <p className="text-sm text-[#ff8d8d]">{error}</p> : null}
      {!rows ? <div className="h-40 animate-pulse rounded-md bg-surface" /> : null}
      {rows && rows.length === 0 ? (
        <div className="rounded-md border border-line bg-surface p-8 text-sm text-muted">
          No actions are waiting for approval.
        </div>
      ) : null}
      <div className="grid gap-4">
        {rows?.map((approval) => (
          <ApprovalCard key={approval.id} approval={approval} onChanged={() => setNonce((value) => value + 1)} />
        ))}
      </div>
    </div>
  );
}
