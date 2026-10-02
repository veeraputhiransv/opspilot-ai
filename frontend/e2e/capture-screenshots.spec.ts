import { expect, test } from "@playwright/test";
import path from "node:path";

import {
  API_URL,
  evidenceCount,
  hasPendingRollback,
  resetDemo,
  rollbackAction,
  waitForIncident,
} from "./helpers";

const DEST = path.join(__dirname, "../../docs/screenshots");

test("capture documentation screenshots", async ({ page }) => {
  test.skip(process.env.CAPTURE_SCREENSHOTS !== "1", "set CAPTURE_SCREENSHOTS=1 to write PNG files");

  resetDemo();
  const status = await page.request.get(`${API_URL}/api/v1/auth/demo/status`);
  expect(status.ok(), "demo status").toBeTruthy();
  expect((await status.json()).available).toBe(true);

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await page.getByRole("button", { name: "Try Demo" }).first().click();
  await page.waitForURL("**/dashboard");
  await expect(page.getByText(/Here's what OpsPilot is watching across AcmeFlow Production/)).toBeVisible();
  await expect(page.getByLabel("Workspace")).toHaveValue(/.+/);
  await expect(page.getByText("No active incidents.")).toBeVisible();
  await settle(page);
  await page.screenshot({ path: path.join(DEST, "01-dashboard.png") });

  await page.getByRole("button", { name: "Run Incident Scenario" }).click();
  await expect(page.getByRole("dialog", { name: /Payment API degradation/i })).toBeVisible();
  await page.getByRole("button", { name: "Trigger Incident" }).click();
  await page.waitForURL(/\/incidents\/[0-9a-f-]{36}$/);
  const incidentId = page.url().match(/\/incidents\/([0-9a-f-]{36})$/)![1];

  await waitForIncident(page, incidentId, (incident) => {
    const run = incident.agent_runs?.[0];
    return Boolean(run) && evidenceCount(incident) > 0 && incident.timeline.length >= 3;
  });
  await expect(page.getByRole("heading", { name: /INC-\d+/ })).toBeVisible();
  await settle(page);
  await page.screenshot({ path: path.join(DEST, "02-live-investigation.png") });

  await waitForIncident(
    page,
    incidentId,
    (incident) =>
      incident.hypotheses.some((item) => item.is_primary) && evidenceCount(incident) > 0,
  );
  await expect(page.getByRole("heading", { name: "AI Investigation", exact: true })).toBeVisible();
  await page.locator("#investigation").scrollIntoViewIfNeeded();
  await settle(page);
  await page.locator("#investigation").screenshot({ path: path.join(DEST, "03-evidence-correlation.png") });

  const pending = await waitForIncident(page, incidentId, hasPendingRollback);
  const rollback = pending.approvals.find(
    (item) => item.tool_name === "rollback_deployment" && item.status === "PENDING_APPROVAL",
  );
  expect(rollback, "pending rollback_deployment approval").toBeTruthy();
  const card = page.locator('[data-tool-name="rollback_deployment"]');
  await expect(card).toBeVisible();
  await expect(card.getByRole("button", { name: "Approve rollback" })).toBeVisible();
  await card.scrollIntoViewIfNeeded();
  await settle(page);
  await card.screenshot({ path: path.join(DEST, "04-human-approval.png") });

  await card.getByRole("button", { name: "Approve rollback" }).click();
  await waitForIncident(page, incidentId, (incident) => {
    const action = rollbackAction(incident);
    return Boolean(
      action &&
        ["APPROVED", "EXECUTING", "EXECUTED", "SUCCEEDED"].includes(action.status) &&
        incident.approvals.some(
          (item) => item.tool_name === "rollback_deployment" && item.status === "APPROVED",
        ),
    );
  });
  await page.locator("[data-sonner-toast]").waitFor({ state: "hidden", timeout: 8_000 }).catch(() => undefined);
  await page.locator("#execution").scrollIntoViewIfNeeded();
  await settle(page);
  await page.locator("#execution").screenshot({ path: path.join(DEST, "05-execution.png") });

  await waitForIncident(
    page,
    incidentId,
    (incident) => incident.status === "resolved" && incident.rca !== null,
  );
  await page.locator("#rca").scrollIntoViewIfNeeded();
  await expect(page.getByRole("heading", { name: "RCA", exact: true })).toBeVisible();
  await settle(page);
  await page.locator("#rca").screenshot({ path: path.join(DEST, "06-rca.png") });

  await page.goto("/agent-runs");
  await expect(page.getByRole("heading", { name: "Agent runs" })).toBeVisible();
  await expect(page.getByText("Incident Investigation").first()).toBeVisible();
  await settle(page);
  await page.screenshot({ path: path.join(DEST, "07-agent-run.png") });
});

async function settle(page: import("@playwright/test").Page): Promise<void> {
  await page.waitForTimeout(200);
}
