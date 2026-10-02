import type { IncidentCreated } from "@/lib/types";

const CONFIGURED_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ACCESS_KEY = "opspilot-access-token";
const REFRESH_KEY = "opspilot-refresh-token";
const WORKSPACE_KEY = "opspilot-workspace-id";

export function apiBase(): string {
  if (typeof window === "undefined") return CONFIGURED_API_URL;
  try {
    const url = new URL(CONFIGURED_API_URL);
    if (url.hostname === "localhost" || url.hostname === "127.0.0.1") {
      url.hostname = window.location.hostname;
      return url.origin;
    }
  } catch {
    return CONFIGURED_API_URL;
  }
  return CONFIGURED_API_URL;
}

export const API_URL = CONFIGURED_API_URL;

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export function accessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_KEY);
}

export function refreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

export function storedWorkspaceId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(WORKSPACE_KEY);
}

export function storeSession(access: string, refresh: string, workspaceId?: string) {
  window.localStorage.setItem(ACCESS_KEY, access);
  window.localStorage.setItem(REFRESH_KEY, refresh);
  if (workspaceId) window.localStorage.setItem(WORKSPACE_KEY, workspaceId);
}

export function clearSession() {
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
  window.localStorage.removeItem(WORKSPACE_KEY);
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = accessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${apiBase()}${path}`, { ...init, headers, cache: "no-store" });
  if (response.status === 401 && typeof window !== "undefined" && !path.startsWith("/api/v1/auth/")) {
    clearSession();
    window.location.href = "/login";
  }
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { error?: { message?: string }; detail?: unknown };
      message = body.error?.message ?? message;
    } catch {
      message = `Request failed (${response.status})`;
    }
    throw new ApiError(message, response.status);
  }
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export function triggerIncident(event: Record<string, unknown>) {
  return api<IncidentCreated>("/api/v1/events", {
    method: "POST",
    body: JSON.stringify(event),
  });
}

export function isForbidden(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403;
}
