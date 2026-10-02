"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { RiskBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { api, isForbidden } from "@/lib/api";
import type { IngestKey, PublicSettings } from "@/lib/types";

export default function SettingsPage() {
  const { me, workspaceId } = useAuth();
  const [settings, setSettings] = useState<PublicSettings | null>(null);
  const [keys, setKeys] = useState<IngestKey[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);
  const [keyName, setKeyName] = useState("Ingest");

  useEffect(() => {
    api<PublicSettings>("/api/v1/settings")
      .then(setSettings)
      .catch((err: Error) => setError(isForbidden(err) ? "Permission denied." : err.message));
    api<IngestKey[]>("/api/v1/auth/api-keys")
      .then(setKeys)
      .catch(() => setKeys([]));
  }, [workspaceId]);

  async function createKey() {
    try {
      const result = await api<{ key: string }>("/api/v1/auth/api-keys", {
        method: "POST",
        body: JSON.stringify({ name: keyName }),
      });
      setCreated(result.key);
      setKeys(await api<IngestKey[]>("/api/v1/auth/api-keys"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create key");
    }
  }

  async function revoke(id: string) {
    await api(`/api/v1/auth/api-keys/${id}/revoke`, { method: "POST" });
    setKeys(await api<IngestKey[]>("/api/v1/auth/api-keys"));
  }

  if (error && !settings) return <p className="text-sm">{error}</p>;
  if (!settings) return <div className="h-40 animate-pulse rounded-md bg-surface" />;

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-medium">Settings</h1>
        <p className="mt-1 text-sm text-muted">Workspace policy and ingest keys. Credentials never appear here.</p>
      </div>
      <section className="rounded-md border border-line bg-surface p-5 text-sm">
        <dl className="grid gap-3 sm:grid-cols-2">
          <Item label="Signed in as" value={me?.email ?? "—"} />
          <Item label="Mode" value={settings.mode} />
          <Item label="Reasoning" value={settings.reasoning_model} />
          <Item label="LLM narrative" value={settings.llm_enabled ? "enabled" : "off"} />
        </dl>
      </section>
      <section className="rounded-md border border-line bg-surface p-5">
        <h2 className="text-sm">Ingest API keys</h2>
        <p className="mt-1 text-xs text-muted">Use `ops_live_…` keys for POST /api/v1/events. Shown once at creation.</p>
        <div className="mt-3 flex gap-2">
          <input
            value={keyName}
            onChange={(event) => setKeyName(event.target.value)}
            className="h-10 flex-1 rounded-md border border-line bg-bg px-3 text-sm"
            aria-label="Key name"
          />
          <Button type="button" onClick={() => void createKey()}>
            Create key
          </Button>
        </div>
        {created ? <p className="mt-3 break-all font-mono text-xs">{created}</p> : null}
        <ul className="mt-4 space-y-2 text-sm">
          {keys?.length === 0 ? <li className="text-muted">No ingest keys yet.</li> : null}
          {keys?.map((key) => (
            <li key={key.id} className="flex items-center justify-between gap-3">
              <span>
                {key.name} · {key.prefix}… {key.revoked_at ? "(revoked)" : ""}
              </span>
              {!key.revoked_at ? (
                <button type="button" className="text-xs text-muted" onClick={() => void revoke(key.id)}>
                  Revoke
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      </section>
      <section className="rounded-md border border-line bg-surface">
        <h2 className="border-b border-line px-4 py-3 text-sm">Tool policy</h2>
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-2 font-medium">Tool</th>
              <th className="px-4 py-2 font-medium">Risk</th>
              <th className="px-4 py-2 font-medium">Approval</th>
            </tr>
          </thead>
          <tbody>
            {settings.policies.map((policy) => (
              <tr key={policy.tool_name} className="border-t border-line">
                <td className="px-4 py-2 font-mono text-xs">{policy.tool_name}</td>
                <td className="px-4 py-2">
                  <RiskBadge risk={policy.risk} />
                </td>
                <td className="px-4 py-2">{policy.requires_approval ? "Required" : "Automatic"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-1 font-mono">{value}</dd>
    </div>
  );
}
