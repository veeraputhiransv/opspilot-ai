"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { api, isForbidden } from "@/lib/api";

interface AuditRow {
  id: string;
  actor: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  created_at: string | null;
}

export default function AuditPage() {
  const { workspaceId } = useAuth();
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<AuditRow[]>("/api/v1/audit")
      .then(setRows)
      .catch((err: Error) => setError(isForbidden(err) ? "Permission denied." : err.message));
  }, [workspaceId]);

  if (error) return <p className="text-sm">{error}</p>;
  if (!rows) return <div className="h-40 animate-pulse rounded-md bg-surface" />;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-medium">Audit</h1>
        <p className="mt-1 text-sm text-muted">Workspace-admin trail. Secrets are never stored in these rows.</p>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">No audit events yet.</p>
      ) : (
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-3 py-2">When</th>
              <th className="px-3 py-2">Actor</th>
              <th className="px-3 py-2">Action</th>
              <th className="px-3 py-2">Resource</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-line">
                <td className="px-3 py-2 font-mono text-xs">{row.created_at}</td>
                <td className="px-3 py-2">{row.actor}</td>
                <td className="px-3 py-2">{row.action}</td>
                <td className="px-3 py-2 text-muted">
                  {row.resource_type} {row.resource_id ?? ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
