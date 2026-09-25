import { expect, test } from "@playwright/test";

import { REAL_DEMO_LOGIN, signInWithCredentials } from "../../helpers/sign-in";

/** Includes synthetic P001 record dates in records-mcp/data/patients/P001.json. */
const REAL_AS_OF = "2026-12-01";

test.describe("real HTTP pipeline (web → agent → records MCP)", () => {
  test("selection → generate → sources → feedback → reload", async ({ page }) => {
    await signInWithCredentials(page, REAL_DEMO_LOGIN);

    await page.getByTestId("as-of-input").fill(REAL_AS_OF);
    await page.getByTestId("patient-select").selectOption("P001");
    await page.getByTestId("generate-profile").click();

    await expect(page.getByTestId("profile-panel")).toBeVisible({ timeout: 90_000 });
    await expect(page.getByTestId("profile-run-id")).toContainText("Run ID:");

    await expect(page.getByTestId("sources-list")).toBeVisible();
    await expect(page.getByTestId("sources-list")).toContainText("P001-R");
    await expect(page.getByTestId("source-excerpt-P001-R3")).toBeVisible();

    await expect(page.getByTestId("retrieval-status")).toBeVisible();

    const profileIdText = await page.getByRole("heading", { name: /^Profile / }).textContent();
    const profileId = profileIdText?.replace("Profile ", "").trim() ?? "";
    expect(profileId.length).toBeGreaterThan(8);

    await page.getByTestId("feedback-accept").click();
    await expect(page.getByTestId("review-status")).toContainText("accepted");

    await page.getByTestId("reload-profile-id").fill(profileId);
    await page.getByTestId("reload-profile").click();
    await expect(page.getByTestId("review-status")).toContainText("accepted");
  });
});
