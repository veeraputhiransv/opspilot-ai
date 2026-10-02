"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { api, storeSession } from "@/lib/api";
import { startDemoSession } from "@/lib/demo";
import { Button } from "@/components/ui/button";
import type { TokenResponse } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const tokens = await api<TokenResponse>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      storeSession(tokens.access_token, tokens.refresh_token, tokens.workspace_id);
      router.push("/dashboard");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      setPending(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <p className="text-sm font-semibold tracking-wide">OpsPilot AI</p>
      <h1 className="mt-2 text-2xl font-semibold">Sign in</h1>
      <p className="mt-2 text-sm text-muted">
        Email and password for your organization workspace. Incident ingest uses a separate API key.
      </p>
      <form className="mt-8 space-y-4" onSubmit={onSubmit}>
        <label className="block text-sm">
          Email
          <input
            className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </label>
        <label className="block text-sm">
          Password
          <input
            className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        {error ? <p className="text-sm text-red-400">{error}</p> : null}
        <Button type="submit" disabled={pending}>
          {pending ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <Button
        className="mt-6"
        variant="outline"
        type="button"
        disabled={pending}
        onClick={() => {
          setPending(true);
          startDemoSession()
            .then(() => {
              router.push("/dashboard");
              router.refresh();
            })
            .catch((err: unknown) => {
              setError(err instanceof Error ? err.message : "Demo session is unavailable.");
              setPending(false);
            });
        }}
      >
        Try Demo
      </Button>
      <p className="mt-6 text-sm text-muted">
        New workspace? <Link href="/register">Create an account</Link>
      </p>
    </main>
  );
}
