"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { SeverityBadge, StatusText } from "@/components/status";
import { useStream } from "@/components/stream";
import { api } from "@/lib/api";
import { formatWhen } from "@/lib/format";
import type { IncidentList } from "@/lib/types";

const FILTERS = ["", "investigating", "awaiting_approval", "executing", "resolved"];

export default function IncidentsPage() {
  const { revision } = useStream();
  const { workspaceId } = useAuth();
  const [status, setStatus] = useState("");
  const [data, setData] = useState<IncidentList | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const query = status ? `?status=${status}` : "";
    api<IncidentList>(`/api/v1/incidents${query}`)
      .then((next) => {
        setData(next);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, [status, revision, workspaceId]);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-medium">Incidents</h1>
      <div className="flex flex-wrap gap-2">
        {FILTERS.map((item) => (
          <button
            key={item || "all"}
            type="button"
            onClick={() => setStatus(item)}
            className={`rounded-md px-3 py-1 text-sm capitalize ${
              status === item ? "bg-elevated" : "text-muted"
            }`}
          >
            {item ? item.replaceAll("_", " ") : "All"}
          </button>
        ))}
      </div>
      {error ? <p className="text-sm text-[#ff8d8d]">{error}</p> : null}
      {!data ? <div className="h-40 animate-pulse rounded-md bg-surface" /> : null}
      {data && data.items.length === 0 ? (
        <div className="rounded-md border border-line bg-surface p-8 text-sm text-muted">
          No incidents in this workspace. Ingest an event from the dashboard.
        </div>
      ) : null}
      {data && data.items.length > 0 ? (
        <div className="overflow-hidden rounded-md border border-line bg-surface">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-3 font-medium">Incident</th>
                <th className="px-4 py-3 font-medium">Service</th>
                <th className="px-4 py-3 font-medium">Severity</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Started</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((incident) => (
                <tr key={incident.id} className="border-t border-line">
                  <td className="px-4 py-3">
                    <Link href={`/incidents/${incident.id}`} className="font-mono">
                      {incident.incident_number}
                    </Link>
                    <div className="text-xs text-muted">{incident.title}</div>
                  </td>
                  <td className="px-4 py-3">{incident.service}</td>
                  <td className="px-4 py-3">
                    <SeverityBadge severity={incident.severity} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusText status={incident.status} />
                  </td>
                  <td className="px-4 py-3 text-muted">{formatWhen(incident.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
