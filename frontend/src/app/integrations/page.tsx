"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { api, isForbidden } from "@/lib/api";

interface Connection {
  provider: string;
  connected: boolean;
  display_name: string;
  status: string;
  last_verified_at: string | null;
  last_error: string | null;
  capabilities: string[];
  has_credentials: boolean;
}

export default function IntegrationsPage() {
  const { workspaceId } = useAuth();
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState("");

  async function load() {
    const data = await api<{ connections: Connection[] }>("/api/v1/integrations");
    setConnections(data.connections);
  }

  useEffect(() => {
    load()
      .then(() => setError(null))
      .catch((err: Error) => setError(isForbidden(err) ? "Permission denied." : err.message));
  }, [workspaceId]);

  async function connectGithub() {
    await api("/api/v1/integrations/github/connect", {
      method: "POST",
      body: JSON.stringify({
        provider: "github",
        display_name: "GitHub",
        secrets: { token },
        configuration: { allowed_repos: ["opspilot-demo/payment-service"] },
      }),
    });
    setToken("");
    await load();
  }

  if (error) return <p className="text-sm">{error}</p>;
  if (!connections) return <div className="h-40 animate-pulse rounded-md bg-surface" />;

  return (
    <div className="max-w-3xl space-y-4">
      <div>
        <h1 className="text-2xl font-medium">Integrations</h1>
        <p className="mt-1 text-sm text-muted">
          Credentials are encrypted in the workspace vault and never returned to the browser.
        </p>
      </div>
      <section className="rounded-md border border-line bg-surface p-4">
        <h2 className="text-sm">Connect GitHub</h2>
        <div className="mt-3 flex gap-2">
          <input
            className="h-10 flex-1 rounded-md border border-line bg-bg px-3 text-sm"
            type="password"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="Fine-grained token"
            aria-label="GitHub token"
          />
          <Button type="button" disabled={!token} onClick={() => void connectGithub()}>
            Save
          </Button>
        </div>
      </section>
      <section className="rounded-md border border-line bg-surface">
        <ul>
          {connections.map((item) => (
            <li key={item.provider} className="border-b border-line px-4 py-3 text-sm last:border-b-0">
              <div className="flex justify-between gap-3">
                <span className="font-mono text-xs">{item.provider}</span>
                <span className="text-muted">{item.status}</span>
              </div>
              <p className="mt-1 text-xs text-muted">{item.capabilities.join(", ")}</p>
              {item.last_error ? <p className="mt-1 text-xs text-[#ff8d8d]">{item.last_error}</p> : null}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
