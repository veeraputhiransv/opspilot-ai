"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { startDemoSession } from "@/lib/demo";

export default function LandingPage() {
  const router = useRouter();
  const [available, setAvailable] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.classList.add("dark");
    api<{ available: boolean }>("/api/v1/auth/demo/status")
      .then((status) => setAvailable(status.available))
      .catch(() => setAvailable(false));
  }, []);

  async function tryDemo() {
    setBusy(true);
    setError(null);
    try {
      await startDemoSession();
      router.push("/dashboard");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Demo session is unavailable.");
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-bg text-text">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <div>
          <p className="text-sm font-semibold tracking-wide">OpsPilot AI</p>
          <p className="text-xs text-muted">AI-powered incident investigation with human-controlled remediation.</p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link href="/login">Sign in</Link>
          </Button>
          <Button asChild size="sm">
            <Link href="/architecture">View Architecture</Link>
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 pb-20">
        <section className="grid gap-10 py-16 lg:grid-cols-[1.2fr_0.8fr] lg:items-center">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-muted">Detect. Investigate. Explain. Approve. Resolve.</p>
            <h1 className="mt-4 text-4xl font-semibold leading-tight md:text-5xl">
              Resolve incidents with AI.
              <span className="mt-2 block text-muted">Keep humans in control.</span>
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-muted">
              OpsPilot investigates production incidents, correlates evidence across your stack, proposes
              remediation, and pauses high-risk actions for human approval.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button disabled={busy || available === false} onClick={() => void tryDemo()}>
                {busy ? "Opening demo…" : "Try Demo"}
              </Button>
              <Button asChild variant="outline">
                <Link href="/architecture">View Architecture</Link>
              </Button>
            </div>
            {available === false ? (
              <p className="mt-4 text-sm text-muted">
                Demo workspace is not seeded. Enable <code>OPSPILOT_DEMO_SEED_ENABLED</code> and run{" "}
                <code>python scripts/seed_demo.py</code>.
              </p>
            ) : null}
            {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
          </div>
          <aside className="rounded-md border border-line bg-surface p-6 shadow-card">
            <p className="text-xs uppercase tracking-wide text-muted">Hero scenario</p>
            <h2 className="mt-2 text-xl font-medium">INC-1024 · Payment API Error Rate Spike</h2>
            <p className="mt-2 text-sm text-muted">payment-service · production · SEV-1</p>
            <ol className="mt-6 space-y-3 text-sm">
              {[
                "Alert received",
                "Logs, deploy, and commit correlated",
                "Historical incident INC-0087 retrieved",
                "HIGH-risk rollback pauses for approval",
                "Human approves. Adapter executes. RCA written.",
              ].map((item) => (
                <li key={item} className="flex gap-3">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                  <span>{item}</span>
                </li>
              ))}
            </ol>
          </aside>
        </section>

        <Section title="The problem" body="When a payment API fails, teams spend the first minutes collecting the same evidence: logs, the last deploy, the commit in that deploy, and similar incidents. The dangerous moment is execution — an agent that can both diagnose and roll back production without a human gate." />
        <div className="grid gap-4 md:grid-cols-2">
          <Card title="How OpsPilot works" body="A fixed LangGraph investigates the incident: triage, logs, deployments, source control, historical search, hypothesis, plan, and risk policy. The graph pauses in Postgres until an operator decides." />
          <Card title="Evidence-driven investigation" body="Conclusions are scored from independent evidence signals. The console labels an investigation score, never a probability." />
          <Card title="Human-in-the-loop safety" body="Policy code decides risk. High-risk tools cannot run until a named operator approves that specific row. The UI cannot mark approval by itself." />
          <Card title="Agent observability" body="Every node, tool call, latency, and token count is persisted. There is no hidden chain-of-thought." />
          <Card title="Integrations" body="GitHub, Slack, email, logs, and deployment adapters sit behind capability protocols. Demo adapters are labeled Simulation." />
          <Card title="Security" body="Workspace isolation, JWT sessions, hashed ingest keys, AES-256-GCM vault, audit logs, and RBAC. Demo sessions cannot change security configuration." />
        </div>
        <Section
          title="Architecture"
          body="Next.js talks to FastAPI. Auth and RBAC sit in front of ingest, LangGraph, the policy engine, and the tool layer. PostgreSQL with pgvector is the system of record. Redis fans out live updates."
        />
        <div className="mt-6">
          <Link href="/architecture" className="text-sm text-primary">
            Open the architecture page
          </Link>
        </div>
        <section className="mt-16 rounded-md border border-line bg-surface px-8 py-10 text-center shadow-card">
          <h2 className="text-2xl font-semibold">Watch the investigation, then decide.</h2>
          <p className="mx-auto mt-3 max-w-xl text-sm text-muted">
            The AcmeFlow demo uses the same workflow, database, and approval policy as a registered workspace.
          </p>
          <Button className="mt-6" disabled={busy || available === false} onClick={() => void tryDemo()}>
            Try Demo
          </Button>
        </section>
      </main>
    </div>
  );
}

function Section({ title, body }: { title: string; body: string }) {
  return (
    <section className="py-8">
      <h2 className="text-xl font-medium">{title}</h2>
      <p className="mt-3 max-w-3xl text-sm leading-7 text-muted">{body}</p>
    </section>
  );
}

function Card({ title, body }: { title: string; body: string }) {
  return (
    <article className="rounded-md border border-line bg-surface p-5 shadow-card">
      <h3 className="text-sm font-medium">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-muted">{body}</p>
    </article>
  );
}
