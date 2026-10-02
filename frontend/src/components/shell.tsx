"use client";

import {
  Activity,
  BookOpen,
  LayoutDashboard,
  LogOut,
  Moon,
  Plug,
  Settings,
  ShieldCheck,
  Siren,
  Sun,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { useStream } from "@/components/stream";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Approval, PublicSettings } from "@/lib/types";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/incidents", label: "Incidents", icon: Siren },
  { href: "/approvals", label: "Approvals", icon: ShieldCheck },
  { href: "/knowledge", label: "Knowledge", icon: BookOpen },
  { href: "/agent-runs", label: "Agent Runs", icon: Activity },
  { href: "/integrations", label: "Integrations", icon: Plug },
  { href: "/audit", label: "Audit", icon: ShieldCheck },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { connected, reconnecting, revision } = useStream();
  const { me, workspaceId, switchWorkspace, logout } = useAuth();
  const [pending, setPending] = useState(0);
  const [mode, setMode] = useState("demo");
  const [dark, setDark] = useState(true);
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem("opspilot-theme");
    const next = stored ? stored === "dark" : true;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api<Approval[]>("/api/v1/approvals?status=PENDING_APPROVAL")
      .then((rows) => {
        if (!cancelled) {
          setPending(rows.length);
          setDenied(false);
        }
      })
      .catch((error: Error & { status?: number }) => {
        if (!cancelled) {
          setPending(0);
          setDenied(error.status === 403);
        }
      });
    api<PublicSettings>("/api/v1/settings")
      .then((settings) => {
        if (!cancelled) setMode(settings.mode);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [revision, workspaceId]);

  function toggleTheme() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    window.localStorage.setItem("opspilot-theme", next ? "dark" : "light");
  }

  const workspace = me?.workspaces.find((item) => item.id === workspaceId) ?? me?.workspaces[0];

  return (
    <div className="min-h-screen md:grid md:grid-cols-[240px_1fr]">
      <aside className="border-b border-line bg-surface md:min-h-screen md:border-b-0 md:border-r">
        <div className="flex items-center justify-between px-5 py-5">
          <Link href="/dashboard" className="block">
            <div className="text-sm font-semibold tracking-wide">OpsPilot</div>
            <div className="text-xs text-muted">Incident response</div>
          </Link>
          <button
            type="button"
            onClick={toggleTheme}
            className="rounded-md border border-line p-2 text-muted"
            aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
          >
            {dark ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </div>
        <div className="px-3 pb-3">
          <label className="px-2 text-[10px] uppercase tracking-wide text-muted" htmlFor="workspace">
            Workspace
          </label>
          <select
            id="workspace"
            className="mt-1 w-full rounded-md border border-line bg-bg px-2 py-2 text-sm"
            value={workspace?.id ?? ""}
            onChange={(event) => void switchWorkspace(event.target.value)}
          >
            {me?.workspaces.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:block md:space-y-1 md:px-3">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
                  active ? "bg-elevated text-text" : "text-muted hover:bg-elevated hover:text-text",
                )}
              >
                <Icon size={16} />
                <span>{item.label}</span>
                {item.href === "/approvals" && pending > 0 ? (
                  <span className="ml-auto rounded-md bg-[#3a2a12] px-1.5 font-mono text-xs text-[#f5c16c]">
                    {pending}
                  </span>
                ) : null}
              </Link>
            );
          })}
        </nav>
        <div className="hidden items-center gap-2 px-5 py-4 text-xs text-muted md:flex">
          <span className={cn("h-2 w-2 rounded-full", connected ? "bg-[#7ddeb4]" : "bg-[#ff8d8d]")} />
          {connected ? "Live" : reconnecting ? "Reconnecting" : "Disconnected"} · {mode}
        </div>
        <div className="hidden border-t border-line px-5 py-4 md:block">
          <p className="truncate text-sm">{me?.full_name}</p>
          <p className="truncate text-xs text-muted">{me?.email}</p>
          <button
            type="button"
            onClick={() => void logout()}
            className="mt-3 inline-flex items-center gap-2 text-xs text-muted"
          >
            <LogOut size={14} />
            Sign out
          </button>
        </div>
      </aside>
      <main className="min-w-0 px-4 py-6 md:px-8">
        {denied ? (
          <div className="mb-4 rounded-md border border-line bg-surface px-4 py-3 text-sm">
            Permission denied for this workspace.
          </div>
        ) : null}
        {children}
      </main>
    </div>
  );
}
