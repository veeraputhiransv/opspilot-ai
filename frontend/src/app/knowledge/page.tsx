"use client";

import { FormEvent, useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { useStream } from "@/components/stream";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { KnowledgeDoc, SearchHit } from "@/lib/types";

export default function KnowledgePage() {
  const { workspaceId } = useAuth();
  const { revision } = useStream();
  const [docs, setDocs] = useState<KnowledgeDoc[] | null>(null);
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [query, setQuery] = useState("database connection timeout");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<KnowledgeDoc[]>("/api/v1/knowledge")
      .then(setDocs)
      .catch((err: Error) => setError(err.message));
  }, [workspaceId, revision]);

  async function search(event: FormEvent) {
    event.preventDefault();
    try {
      const next = await api<SearchHit[]>("/api/v1/knowledge/search", {
        method: "POST",
        body: JSON.stringify({ query, limit: 3 }),
      });
      setHits(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-medium">Incident memory</h1>
        <p className="mt-1 text-sm text-muted">Previous incidents retrieved with pgvector during an investigation.</p>
      </div>
      <form onSubmit={search} className="flex flex-wrap gap-2">
        <label className="sr-only" htmlFor="knowledge-query">
          Search incidents
        </label>
        <input
          id="knowledge-query"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="h-10 min-w-72 flex-1 rounded-md border border-line bg-surface px-3 text-sm"
        />
        <Button type="submit">Search</Button>
      </form>
      {error ? <p className="text-sm text-[#ff8d8d]">{error}</p> : null}
      {hits ? (
        <section className="space-y-3">
          <h2 className="text-sm">Nearest incidents</h2>
          {hits.map((hit) => (
            <article key={hit.external_id} className="rounded-md border border-line bg-surface p-4">
              <div className="flex justify-between">
                <span className="font-mono text-sm">{hit.external_id}</span>
                <span className="font-mono text-sm">{hit.similarity.toFixed(2)}</span>
              </div>
              <p className="mt-1">{hit.title}</p>
              <p className="mt-2 text-sm text-muted">{hit.root_cause}</p>
            </article>
          ))}
        </section>
      ) : null}
      {!docs ? <div className="h-40 animate-pulse rounded-md bg-surface" /> : null}
      {docs && docs.length === 0 ? (
        <p className="text-sm text-muted">No indexed incident memory in this workspace yet.</p>
      ) : null}
      <section className="grid gap-3">
        {docs?.map((doc) => (
          <article key={doc.id} className="rounded-md border border-line bg-surface p-4">
            <p className="font-mono text-xs text-muted">
              {doc.external_id} · {doc.service}
            </p>
            <h2 className="mt-1 text-base">{doc.title}</h2>
            <p className="mt-2 text-sm text-muted">{doc.root_cause}</p>
          </article>
        ))}
      </section>
    </div>
  );
}
