import { expect, test } from "@playwright/test";

import { API_URL, apiRequest, ingestUniqueIncident, registerOperator, waitForIncident } from "./helpers";

test("workspace B cannot read workspace A incident artifacts", async ({ browser, page }) => {
  const alice = await registerOperator(page, "Alice Operator", `Workspace A ${Date.now()}`);
  const incidentId = await ingestUniqueIncident(page);
  const aliceIncident = await waitForIncident(page, incidentId, (incident) =>
    Boolean(incident.incident_number && incident.approvals.length >= 0),
  );
  const approvalId = aliceIncident.approvals[0]?.id;
  const runId = (
    await (
      await apiRequest(page, "GET", `/api/v1/incidents/${incidentId}/agent-runs`, alice.token)
    ).json()
  )[0]?.id as string | undefined;

  const bobContext = await browser.newContext();
  const bobPage = await bobContext.newPage();
  const bob = await registerOperator(bobPage, "Bob Operator", `Workspace B ${Date.now()}`);
  await expect(bobPage.getByText(aliceIncident.incident_number)).toHaveCount(0);

  await bobPage.goto(`/incidents/${incidentId}`);
  await expect(bobPage.getByText("Incident not found.")).toBeVisible();

  const forbidden = [
    `/api/v1/incidents/${incidentId}`,
    `/api/v1/incidents/${incidentId}/timeline`,
    `/api/v1/incidents/${incidentId}/agent-runs`,
    `/api/v1/incidents/${incidentId}/rca`,
  ];
  for (const path of forbidden) {
    const response = await apiRequest(bobPage, "GET", path, bob.token);
    expect(response.status(), path).toBe(404);
  }
  if (approvalId) {
    const approval = await apiRequest(
      bobPage,
      "POST",
      `/api/v1/approvals/${approvalId}/approve`,
      bob.token,
      { comment: "cross-tenant" },
    );
    expect(approval.status()).toBe(404);
  }
  const aliceStillOwns = await apiRequest(page, "GET", `/api/v1/incidents/${incidentId}`, alice.token);
  expect(aliceStillOwns.status()).toBe(200);
  if (runId) {
    const runs = await apiRequest(bobPage, "GET", `/api/v1/incidents/${incidentId}/agent-runs`, bob.token);
    expect(runs.status()).toBe(404);
  }
  expect(API_URL).toMatch(/^http/);
  await bobContext.close();
});
