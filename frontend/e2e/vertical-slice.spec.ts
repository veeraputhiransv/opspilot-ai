import { expect, test } from "@playwright/test";

import {
  fetchIncident,
  highRiskExecuted,
  ingestUniqueIncident,
  registerOperator,
  rejectPendingApprovals,
  waitForIncident,
} from "./helpers";

test("approve resumes the same incident through execution and RCA", async ({ page }) => {
  await registerOperator(page, "E2E Approver", `E2E Approve Org ${Date.now()}`);
  const incidentId = await ingestUniqueIncident(page);
  await expect(page.getByRole("heading", { name: /INC-\d+/ })).toBeVisible();

  const waiting = await waitForIncident(page, incidentId, (incident) =>
    incident.approvals.some((item) => item.status === "PENDING_APPROVAL"),
  );
  expect(waiting.evidence).toBeTruthy();
  expect(waiting.hypotheses.length).toBeGreaterThan(0);
  expect(waiting.hypotheses.some((item) => item.is_primary)).toBe(true);

  await expect(page.getByText("Likely root cause")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Evidence", exact: true })).toBeVisible();
  const approve = page.getByRole("button", { name: /Approve/ }).first();
  await expect(approve).toBeVisible();
  await approve.click();
  await expect(page.getByText("Approval recorded")).toBeVisible();

  const resolved = await waitForIncident(
    page,
    incidentId,
    (incident) =>
      incident.status === "resolved" &&
      incident.rca !== null &&
      incident.approvals.some((item) => item.status === "APPROVED") &&
      incident.actions.some((item) => item.status === "EXECUTED"),
  );
  expect(resolved.rca?.executive_summary.length).toBeGreaterThan(20);
  expect(resolved.rca?.root_cause.length).toBeGreaterThan(8);
  expect(highRiskExecuted(resolved)).toBe(true);

  await expect(page.getByText("resolved", { exact: false }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "RCA", exact: true })).toBeVisible();
  await expect(page.getByText(resolved.rca!.executive_summary.slice(0, 40))).toBeVisible();
});

test("reject records the decision and does not execute high-risk actions", async ({ page }) => {
  await registerOperator(page, "E2E Rejector", `E2E Reject Org ${Date.now()}`);
  const incidentId = await ingestUniqueIncident(page);

  await waitForIncident(page, incidentId, (incident) =>
    incident.approvals.some((item) => item.status === "PENDING_APPROVAL"),
  );
  const reject = page.getByRole("button", { name: "Reject" }).first();
  await expect(reject).toBeVisible();
  const rejected = await rejectPendingApprovals(page, incidentId);
  await expect(page.getByText("Rejection recorded").first()).toBeVisible();
  expect(rejected.status).not.toBe("resolved");
  expect(rejected.rca).toBeNull();
  expect(highRiskExecuted(rejected)).toBe(false);
  expect(rejected.approvals.some((item) => item.status === "APPROVED")).toBe(false);
  expect(rejected.approvals.every((item) => item.status === "REJECTED")).toBe(true);
  expect(
    rejected.actions.some((item) => item.tool_name === "rollback_deployment" && item.status === "REJECTED"),
  ).toBe(true);

  await expect(page.getByText("REJECTED").first()).toBeVisible();
  await expect(page.getByText("Remediation was not approved")).toBeVisible();
  const after = await fetchIncident(page, incidentId);
  expect(after.actions.find((item) => item.status === "REJECTED")?.result).toBeNull();
});
