"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { useAuth } from "@/components/auth-provider";
import { SeverityBadge, StatusText } from "@/components/status";
import { useStream } from "@/components/stream";
import { Button } from "@/components/ui/button";
import { api, isForbidden } from "@/lib/api";
import { formatClock, formatDuration, formatPercent } from "@/lib/format";
import type { Dashboard, IncidentCreated } from "@/lib/types";

export default function DashboardPage() {
  const router = useRouter();
  const { revision, connected } = useStream();
  const { workspaceId } = useAuth();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [busy, setBusy] = useState(false);
  const [service, setService] = useState("payment-service");
  const [environment, setEnvironment] = useState("production");
  const [eventType, setEventType] = useState("error_rate_spike");
  const [errorRate, setErrorRate] = useState("18.4");
  const [message, setMessage] = useState("Checkout 5xx rate exceeded the page threshold");

  useEffect(() => {
    let cancelled = false;
    api<Dashboard>("/api/v1/dashboard")
      .then((next) => {
        if (!cancelled) {
          setData(next);
          setError(null);
          setForbidden(false);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setForbidden(isForbidden(err));
          setError(err.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [revision, workspaceId]);

  async function ingest(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const created = await api<IncidentCreated>("/api/v1/events", {
        method: "POST",
        body: JSON.stringify({
          service,
          environment,
          event_type: eventType,
          error_rate: Number(errorRate),
          message,
        }),
      });
      toast.success(
        created.replayed ? `${created.incident_number} already exists` : `${created.incident_number} opened`,
      );
      router.push(`/incidents/${created.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Unable to ingest event");
    } finally {
      setBusy(false);
    }
  }

  if (forbidden) {
    return <p className="text-sm">Permission denied.</p>;
  }
  if (error && !data) {
    return (
      <div className="rounded-md border border-line bg-surface p-6">
        <p>The console cannot reach the API.</p>
        <p className="mt-2 text-sm text-muted">{error}</p>
      </div>
    );
  }
  if (!data) return <div className="h-48 animate-pulse rounded-md bg-surface" />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-medium">Operations</h1>
          <p className="mt-1 text-sm text-muted">Live investigations, approvals, and recovery.</p>
        </div>
        <p className="text-xs text-muted">{connected ? "Realtime connected" : "Realtime disconnected — reconnecting"}</p>
      </div>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Metric label="Active incidents" value={String(data.active_incidents)} />
        <Metric label="MTTR" value={formatDuration(data.mttr_seconds)} />
        <Metric label="AI investigations" value={String(data.ai_investigations)} />
        <Metric label="Pending approvals" value={String(data.pending_approvals)} />
        <Metric label="Automation success" value={formatPercent(data.automation_success_rate)} />
      </section>
      <form onSubmit={ingest} className="rounded-md border border-line bg-surface p-5">
        <h2 className="text-sm">Ingest event</h2>
        <p className="mt-1 text-xs text-muted">Creates a persisted incident in this workspace. Retries with the same payload reuse the same incident.</p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <Field label="Service" value={service} onChange={setService} />
          <label className="text-sm">
            Environment
            <select
              className="mt-1 h-10 w-full rounded-md border border-line bg-bg px-3 text-sm"
              value={environment}
              onChange={(event) => setEnvironment(event.target.value)}
            >
              <option value="production">production</option>
              <option value="staging">staging</option>
              <option value="development">development</option>
            </select>
          </label>
          <Field label="Event type" value={eventType} onChange={setEventType} />
          <Field label="Error rate" value={errorRate} onChange={setErrorRate} />
          <label className="text-sm md:col-span-2">
            Message
            <input
              className="mt-1 h-10 w-full rounded-md border border-line bg-bg px-3 text-sm"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              required
            />
          </label>
        </div>
        <Button className="mt-4" disabled={busy} type="submit">
          {busy ? "Ingesting…" : "Ingest incident"}
        </Button>
      </form>
      <div className="grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
        <section className="rounded-md border border-line bg-surface">
          <h2 className="border-b border-line px-4 py-3 text-sm">Recent incidents</h2>
          {data.recent_incidents.length === 0 ? (
            <p className="px-4 py-8 text-sm text-muted">No incidents in this workspace yet.</p>
          ) : (
            <ul>
              {data.recent_incidents.map((incident) => (
                <li key={incident.id} className="border-b border-line last:border-b-0">
                  <a href={`/incidents/${incident.id}`} className="grid gap-2 px-4 py-3 text-sm md:grid-cols-[110px_1fr_auto]">
                    <span className="font-mono">{incident.incident_number}</span>
                    <span>
                      {incident.title}
                      <span className="mt-1 block text-xs text-muted">{incident.current_activity}</span>
                    </span>
                    <span className="flex items-center gap-2">
                      <SeverityBadge severity={incident.severity} />
                      <StatusText status={incident.status} />
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="rounded-md border border-line bg-surface">
          <h2 className="border-b border-line px-4 py-3 text-sm">Agent activity</h2>
          {data.activity.length === 0 ? (
            <p className="px-4 py-8 text-sm text-muted">Waiting for the first alert.</p>
          ) : (
            <ul>
              {data.activity.map((event) => (
                <li key={event.id} className="border-b border-line px-4 py-3 text-sm last:border-b-0">
                  <div className="flex justify-between gap-3">
                    <span className="font-mono text-xs text-muted">{event.incident_number}</span>
                    <time className="font-mono text-xs text-muted">{formatClock(event.occurred_at)}</time>
                  </div>
                  <p className="mt-1">{event.title}</p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="text-sm">
      {label}
      <input
        className="mt-1 h-10 w-full rounded-md border border-line bg-bg px-3 text-sm"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required
      />
    </label>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-surface px-4 py-3 shadow-card">
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-2 font-mono text-2xl">{value}</p>
    </div>
  );
}
