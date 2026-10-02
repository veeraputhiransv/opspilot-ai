import { expect, test } from "@playwright/test";

import { API_URL, fetchIncident, highRiskExecuted, resetDemo, waitForIncident } from "./helpers";

test("try demo triggers the hero scenario through approval and RCA", async ({ page }) => {
  resetDemo();
  const status = await page.request.get(`${API_URL}/api/v1/auth/demo/status`);
  test.skip(status.ok() === false || (await status.json()).available !== true, "demo workspace is not seeded");

  await page.goto("/");
  await page.getByRole("button", { name: "Try Demo" }).first().click();
  await page.waitForURL("**/dashboard");
  await expect(page.getByText(/Here's what OpsPilot is watching/)).toBeVisible();

  await page.getByRole("button", { name: "Run Incident Scenario" }).click();
  await expect(page.getByRole("dialog", { name: /Payment API degradation/i })).toBeVisible();
  await page.getByRole("button", { name: "Trigger Incident" }).click();
  await page.waitForURL(/\/incidents\/[0-9a-f-]{36}$/);
  const match = page.url().match(/\/incidents\/([0-9a-f-]{36})$/);
  expect(match).toBeTruthy();
  const incidentId = match![1];

  await waitForIncident(page, incidentId, (incident) =>
    incident.approvals.some((item) => item.status === "PENDING_APPROVAL" && item.tool_name === "rollback_deployment"),
  );
  await expect(page.getByRole("heading", { name: /Payment API Error Rate Spike/i })).toBeVisible();
  const rollback = page.locator('[data-tool-name="rollback_deployment"]');
  await expect(rollback.getByRole("button", { name: "Approve rollback" })).toBeVisible();
  await rollback.getByRole("button", { name: "Approve rollback" }).click();

  const resolved = await waitForIncident(page, incidentId, (incident) => incident.status === "resolved" && incident.rca !== null);
  expect(highRiskExecuted(resolved)).toBeTruthy();
  expect(resolved.rca?.root_cause.toLowerCase()).toContain("pool");
  const persisted = await fetchIncident(page, incidentId);
  expect(persisted.id).toBe(incidentId);
});
