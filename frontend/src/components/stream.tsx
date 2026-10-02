"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { api, apiBase } from "@/lib/api";

interface StreamState {
  revision: number;
  connected: boolean;
  reconnecting: boolean;
}

const StreamContext = createContext<StreamState>({
  revision: 0,
  connected: false,
  reconnecting: false,
});

export function StreamProvider({ children }: { children: React.ReactNode }) {
  const { workspaceId } = useAuth();
  const [state, setState] = useState<StreamState>({
    revision: 0,
    connected: false,
    reconnecting: false,
  });
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!workspaceId) return undefined;
    let closed = false;
    let source: EventSource | null = null;

    async function connect() {
      if (closed) return;
      try {
        const issued = await api<{ ticket: string }>("/api/v1/realtime/tickets", {
          method: "POST",
          body: JSON.stringify({}),
        });
        if (closed) return;
        const next = new EventSource(
          `${apiBase()}/api/v1/events/stream?ticket=${encodeURIComponent(issued.ticket)}`,
        );
        source = next;
        next.onopen = () =>
          setState((current) => ({ ...current, connected: true, reconnecting: false }));
        next.onerror = () => {
          setState((current) => ({ ...current, connected: false, reconnecting: true }));
          next.close();
          if (!closed) {
            timer.current = window.setTimeout(() => void connect(), 2000);
          }
        };
        next.onmessage = () =>
          setState((current) => ({
            connected: true,
            reconnecting: false,
            revision: current.revision + 1,
          }));
      } catch {
        setState((current) => ({ ...current, connected: false, reconnecting: true }));
        if (!closed) {
          timer.current = window.setTimeout(() => void connect(), 2000);
        }
      }
    }

    void connect();
    return () => {
      closed = true;
      source?.close();
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [workspaceId]);

  return <StreamContext.Provider value={state}>{children}</StreamContext.Provider>;
}

export function useStream() {
  return useContext(StreamContext);
}
