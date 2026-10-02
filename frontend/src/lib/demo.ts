import { api, storeSession } from "@/lib/api";
import type { TokenResponse } from "@/lib/types";

export async function startDemoSession(): Promise<void> {
  const tokens = await api<TokenResponse>("/api/v1/auth/demo", { method: "POST" });
  storeSession(tokens.access_token, tokens.refresh_token, tokens.workspace_id);
}
