import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

import { expect, type APIResponse, type Page } from "@playwright/test";

const REPO_ROOT = path.join(__dirname, "../..");

export const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
export const PASSWORD = "correct-horse-battery";

export interface IncidentDetail {
  id: string;
  incident_number: string;
  status: string;
  current_activity: string | null;
  hypotheses: Array<{ title: string; is_primary: boolean }>;
  evidence: { items?: unknown[]; logs?: unknown[] } | null;
  timeline: Array<{ id: string; title: string }>;
  actions: Array<{ tool_name: string; status: string; result: Record<string, unknown> | null }>;
  approvals: Array<{ id: string; status: string; tool_name: string; title: string }>;
  rca: { executive_summary: string; root_cause: string; version: number } | null;
  agent_runs?: Array<{ id: string; status: string; steps: unknown[] }>;
}

export function uniqueSuffix(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export async function registerOperator(
  page: Page,
  name: string,
  organization: string,
): Promise<{ email: string; token: string }> {
  const email = `e2e-${uniqueSuffix()}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill(name);
  await page.getByLabel("Organization").fill(organization);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password (12+ characters)").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("**/dashboard");
  await expect(page.getByRole("button", { name: "Ingest incident" })).toBeVisible({
    timeout: 30_000,
  });
  const token = await page.evaluate(() => window.localStorage.getItem("opspilot-access-token"));
  expect(token, "authenticated session token").toBeTruthy();
  return { email, token: token as string };
}

export async function ingestUniqueIncident(page: Page): Promise<string> {
  const marker = uniqueSuffix();
  await page.getByLabel("Error rate").fill("40");
  await page.getByLabel("Message").fill(`database connection pool exhausted ${marker}`);
  await page.getByRole("button", { name: "Ingest incident" }).click();
  await page.waitForURL(/\/incidents\/[0-9a-f-]{36}$/);
  const match = page.url().match(/\/incidents\/([0-9a-f-]{36})$/);
  expect(match, "incident id in URL").toBeTruthy();
  return match![1];
}

export async function apiRequest(
  page: Page,
  method: "GET" | "POST",
  path: string,
  token?: string,
  body?: unknown,
): Promise<APIResponse> {
  const auth = token ?? (await page.evaluate(() => window.localStorage.getItem("opspilot-access-token")));
  expect(auth, "API bearer token").toBeTruthy();
  return page.request.fetch(`${API_URL}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${auth}`,
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    data: body,
  });
}

export async function fetchIncident(page: Page, incidentId: string, token?: string): Promise<IncidentDetail> {
  const response = await apiRequest(page, "GET", `/api/v1/incidents/${incidentId}`, token);
  expect(response.status(), `GET incident ${incidentId}`).toBe(200);
  return (await response.json()) as IncidentDetail;
}

export async function waitForIncident(
  page: Page,
  incidentId: string,
  predicate: (incident: IncidentDetail) => boolean | Promise<boolean>,
  timeoutMs = 120_000,
): Promise<IncidentDetail> {
  let latest: IncidentDetail | null = null;
  await expect
    .poll(
      async () => {
        latest = await fetchIncident(page, incidentId);
        return Boolean(await predicate(latest));
      },
      { timeout: timeoutMs, intervals: [250, 500, 1000, 2000] },
    )
    .toBe(true);
  return latest as IncidentDetail;
}

export async function rejectPendingApprovals(page: Page, incidentId: string): Promise<IncidentDetail> {
  return waitForIncident(page, incidentId, async (incident) => {
    const pending = incident.approvals.filter((item) => item.status === "PENDING_APPROVAL");
    if (pending.length === 0) {
      return (
        incident.approvals.some((item) => item.status === "REJECTED") &&
        incident.current_activity === "Remediation was not approved"
      );
    }
    const reject = page.getByRole("button", { name: "Reject" }).first();
    if (await reject.isVisible()) {
      await reject.click();
    }
    return false;
  });
}

export function evidenceCount(incident: IncidentDetail): number {
  const evidence = incident.evidence;
  if (!evidence) return 0;
  return (evidence.items?.length ?? 0) + (evidence.logs?.length ?? 0);
}

export function hasPendingRollback(incident: IncidentDetail): boolean {
  return incident.approvals.some(
    (item) => item.tool_name === "rollback_deployment" && item.status === "PENDING_APPROVAL",
  );
}

export function rollbackAction(incident: IncidentDetail) {
  return incident.actions.find((item) => item.tool_name === "rollback_deployment");
}

export function resetDemo(): void {
  const venvPython = path.join(REPO_ROOT, "backend/.venv/bin/python");
  const python = process.env.OPSPILOT_PYTHON ?? (existsSync(venvPython) ? venvPython : "python3");
  execFileSync(python, [path.join(REPO_ROOT, "scripts/reset_demo.py")], {
    cwd: REPO_ROOT,
    env: process.env,
    stdio: "inherit",
  });
}

export function highRiskExecuted(incident: IncidentDetail): boolean {
  return incident.actions.some(
    (action) =>
      ["rollback_deployment", "restart_service", "send_customer_email", "send_slack_message"].includes(
        action.tool_name,
      ) && action.status === "EXECUTED",
  );
}
