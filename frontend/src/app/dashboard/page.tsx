"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { useAuth } from "@/components/auth-provider";
import { SeverityBadge, StatusText } from "@/components/status";
import { useStream } from "@/components/stream";
import { Button } from "@/components/ui/button";
import { api, isForbidden } from "@/lib/api";
import { formatClock, formatDuration, formatPercent, greeting } from "@/lib/format";
import type { Approval, Dashboard, DemoScenario, IncidentCreated } from "@/lib/types";

export default function DashboardPage() {
  const router = useRouter();
  const { revision, connected } = useStream();
  const { me, workspaceId } = useAuth();
  const [data, setData] = useState<Dashboard | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [busy, setBusy] = useState(false);
  const [scenarioOpen, setScenarioOpen] = useState(false);
  const [scenarios, setScenarios] = useState<DemoScenario[]>([]);
  const [integrations, setIntegrations] = useState<
    Array<{ provider: string; status: string; simulation?: boolean }>
  >([]);
  const [service, setService] = useState("payment-service");
  const [environment, setEnvironment] = useState("production");
  const [eventType, setEventType] = useState("error_rate_spike");
  const [errorRate, setErrorRate] = useState("18.4");
  const [message, setMessage] = useState("Checkout 5xx rate exceeded the page threshold");
  const workspace = me?.workspaces.find((item) => item.id === workspaceId) ?? me?.workspaces[0];
  const isDemo = Boolean(me?.demo && workspace?.slug === "acmeflow-production");

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
    api<Approval[]>("/api/v1/approvals?status=PENDING_APPROVAL")
      .then((rows) => {
        if (!cancelled) setApprovals(rows);
      })
      .catch(() => undefined);
    api<{ connections: Array<{ provider: string; status: string; simulation?: boolean }> }>("/api/v1/integrations")
      .then((payload) => {
        if (!cancelled) setIntegrations(payload.connections);
      })
      .catch(() => undefined);
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

  async function openScenario() {
    try {
      const rows = await api<DemoScenario[]>("/api/v1/demo/scenarios");
      setScenarios(rows);
      setScenarioOpen(true);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Scenarios unavailable");
    }
  }

  async function triggerScenario(key: string) {
    setBusy(true);
    try {
      const created = await api<IncidentCreated>(`/api/v1/demo/scenarios/${key}/trigger`, {
        method: "POST",
      });
      setScenarioOpen(false);
      router.push(`/incidents/${created.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Unable to trigger scenario");
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

  const hero = scenarios.find((item) => item.key === "db_pool") ?? scenarios[0];
  const active = data.recent_incidents.filter(
    (item) => item.status !== "resolved" && item.status !== "closed",
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-medium">{greeting(me?.full_name ?? "operator")}</h1>
          <p className="mt-1 text-sm text-muted">
            Here&apos;s what OpsPilot is watching across {workspace?.name ?? "this workspace"}.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {isDemo ? (
            <Button onClick={() => void openScenario()}>Run Incident Scenario</Button>
          ) : null}
          <p className="text-xs text-muted">
            {connected ? "Realtime connected" : "Realtime disconnected — reconnecting"}
          </p>
        </div>
      </div>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Active incidents" value={String(data.active_incidents)} />
        <Metric label="Pending approvals" value={String(data.pending_approvals)} />
        <Metric label="Mean investigation time" value={formatDuration(data.mttr_seconds)} />
        <Metric label="Automation success rate" value={formatPercent(data.automation_success_rate)} />
      </section>
      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <section className="rounded-md border border-line bg-surface shadow-card">
          <h2 className="border-b border-line px-4 py-3 text-sm">Active incidents</h2>
          {active.length === 0 ? (
            <p className="px-4 py-8 text-sm text-muted">No active incidents.</p>
          ) : (
            <IncidentList rows={active} />
          )}
        </section>
        <section className="rounded-md border border-line bg-surface shadow-card">
          <h2 className="border-b border-line px-4 py-3 text-sm">Pending approvals</h2>
          {approvals.length === 0 ? (
            <p className="px-4 py-8 text-sm text-muted">No actions waiting for a human.</p>
          ) : (
            <ul>
              {approvals.map((item) => (
                <li key={item.id} className="border-b border-line px-4 py-3 text-sm last:border-b-0">
                  <a href={`/incidents/${item.incident_id}`}>
                    <span className="font-mono text-xs">{item.incident_number}</span>
                    <p className="mt-1">{item.title}</p>
                    <p className="text-xs text-muted">
                      {item.risk_level} · {item.service}
                    </p>
                  </a>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
      <div className="grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
        <section className="rounded-md border border-line bg-surface shadow-card">
          <h2 className="border-b border-line px-4 py-3 text-sm">Recent incidents</h2>
          {data.recent_incidents.length === 0 ? (
            <p className="px-4 py-8 text-sm text-muted">No incidents in this workspace yet.</p>
          ) : (
            <IncidentList rows={data.recent_incidents} />
          )}
        </section>
        <section className="rounded-md border border-line bg-surface shadow-card">
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
      <section className="rounded-md border border-line bg-surface p-5 shadow-card">
        <h2 className="text-sm">System integrations</h2>
        {integrations.length === 0 ? (
          <p className="mt-3 text-sm text-muted">No integration rows yet.</p>
        ) : (
          <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {integrations.map((item) => (
              <li key={item.provider} className="rounded-md border border-line bg-bg px-3 py-2 text-sm">
                <p className="font-mono text-xs">{item.provider}</p>
                <p className="mt-1 text-xs text-muted">
                  {item.simulation ? "Simulation" : item.status.replaceAll("_", " ")}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
      <form onSubmit={ingest} className="rounded-md border border-line bg-surface p-5 shadow-card">
        <h2 className="text-sm">Ingest event</h2>
        <p className="mt-1 text-xs text-muted">
          Creates a persisted incident in this workspace. Retries with the same payload reuse the same incident.
        </p>
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
      {scenarioOpen && hero ? (
        <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/50 p-4" role="presentation">
          <div
            role="dialog"
            aria-labelledby="scenario-title"
            className="w-full max-w-lg rounded-md border border-line bg-surface p-6 shadow-card"
          >
            <p className="text-xs uppercase tracking-wide text-muted">Demo scenario</p>
            <h2 id="scenario-title" className="mt-2 text-xl font-medium">
              {hero.label}
            </h2>
            <p className="mt-3 text-sm leading-6 text-muted">{hero.summary}</p>
            <p className="mt-3 font-mono text-xs text-muted">
              {hero.event.service} · {hero.event.environment} · {hero.event.event_type}
            </p>
            <div className="mt-6 flex flex-wrap gap-2">
              <Button disabled={busy} onClick={() => void triggerScenario(hero.key)}>
                {busy ? "Triggering…" : "Trigger Incident"}
              </Button>
              <Button variant="outline" disabled={busy} onClick={() => setScenarioOpen(false)}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function IncidentList({ rows }: { rows: Dashboard["recent_incidents"] }) {
  return (
    <ul>
      {rows.map((incident) => (
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
