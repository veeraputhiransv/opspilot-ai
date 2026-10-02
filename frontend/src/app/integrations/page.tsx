"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { api, isForbidden } from "@/lib/api";
import { formatWhen } from "@/lib/format";

interface Connection {
  provider: string;
  connected: boolean;
  display_name: string;
  status: string;
  last_verified_at: string | null;
  last_error: string | null;
  capabilities: string[];
  has_credentials: boolean;
  simulation?: boolean;
}

const LABELS: Record<string, string> = {
  github: "GitHub",
  slack: "Slack",
  email: "Email",
  logs: "Logs",
  deployments: "Deployment Platform",
};

export default function IntegrationsPage() {
  const { me, workspaceId } = useAuth();
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const demo = Boolean(me?.demo);

  async function load() {
    const data = await api<{ connections: Connection[] }>("/api/v1/integrations");
    setConnections(data.connections);
  }

  useEffect(() => {
    load()
      .then(() => setError(null))
      .catch((err: Error) => setError(isForbidden(err) ? "Permission denied." : err.message));
  }, [workspaceId]);

  if (error) return <p className="text-sm">{error}</p>;
  if (!connections) return <div className="h-40 animate-pulse rounded-md bg-surface" />;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-medium">Integrations</h1>
        <p className="mt-1 text-sm text-muted">
          Credentials stay in the workspace vault and are never returned to the browser.
          {demo ? " Demo adapters are labeled Simulation and are not linked to an external account." : ""}
        </p>
      </div>
      <section className="grid gap-4 md:grid-cols-2">
        {connections.map((item) => (
          <article key={item.provider} className="rounded-md border border-line bg-surface p-5 shadow-card">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-sm font-medium">{LABELS[item.provider] ?? item.display_name}</h2>
                <p className="mt-1 font-mono text-xs text-muted">{item.provider}</p>
              </div>
              <span className="text-xs text-muted">
                {item.simulation ? "Simulation" : item.connected ? "Connected" : "Not connected"}
              </span>
            </div>
            <p className="mt-3 text-sm">{item.status.replaceAll("_", " ")}</p>
            <p className="mt-2 text-xs text-muted">{item.capabilities.join(" · ")}</p>
            <p className="mt-3 text-xs text-muted">
              Last verified {item.last_verified_at ? formatWhen(item.last_verified_at) : "never"}
            </p>
            {item.last_error ? <p className="mt-2 text-xs text-danger">{item.last_error}</p> : null}
          </article>
        ))}
      </section>
    </div>
  );
}
