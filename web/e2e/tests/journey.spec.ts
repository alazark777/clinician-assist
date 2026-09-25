import { expect, test } from "@playwright/test";

import { MOCK_DEMO_LOGIN, signInWithCredentials } from "../helpers/sign-in";

async function signIn(page: import("@playwright/test").Page) {
  await signInWithCredentials(page, MOCK_DEMO_LOGIN);
}

test.describe("clinician web journeys", () => {
  test("selection → generation → sources → feedback → reload", async ({ page }) => {
    await signIn(page);
    await page.getByTestId("patient-select").selectOption("P001");
    await page.getByTestId("generate-profile").click();
    await expect(page.getByTestId("profile-panel")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("profile-run-id")).toContainText("Run ID:");
    await expect(page.getByTestId("sources-list")).toBeVisible();
    await expect(page.getByTestId("gaps-list")).toBeVisible();
    await expect(page.getByTestId("retrieval-status")).toContainText("incomplete");

    const profileIdText = await page.getByRole("heading", { name: /^Profile / }).textContent();
    const profileId = profileIdText?.replace("Profile ", "").trim() ?? "";

    await page.getByTestId("feedback-accept").click();
    await expect(page.getByTestId("review-status")).toContainText("accepted");

    await page.getByTestId("reload-profile-id").fill(profileId);
    await page.getByTestId("reload-profile").click();
    await expect(page.getByTestId("review-status")).toContainText("accepted");
  });

  test("empty inventory shows gap without inferring negative finding", async ({ page }) => {
    await signIn(page);
    await page.getByTestId("patient-select").selectOption("P002");
    await page.getByTestId("generate-profile").click();
    await expect(page.getByTestId("profile-panel")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("facts-empty")).toBeVisible();
    await expect(page.getByTestId("gaps-list")).toContainText("empty_inventory");
    await expect(page.getByTestId("retrieval-status")).toContainText("complete");
  });

  test("hostile excerpt text is escaped and does not execute scripts", async ({
    page,
  }) => {
    page.on("dialog", () => {
      throw new Error("Unexpected alert dialog — injection was not escaped");
    });
    await signIn(page);
    await page.getByTestId("generate-profile").click();
    await expect(page.getByTestId("profile-panel")).toBeVisible({ timeout: 15_000 });
    const excerpt = page.getByTestId("source-excerpt-rec-lab-1");
    await expect(excerpt).toContainText("<script>alert(1)</script>");
    await expect(excerpt.locator("script")).toHaveCount(0);
  });

  test("duplicate identical submission reuses idempotent profile", async ({ page }) => {
    await signIn(page);
    await page.getByTestId("generate-profile").click();
    await expect(page.getByTestId("profile-panel")).toBeVisible({ timeout: 15_000 });
    const firstRun = await page.getByTestId("profile-run-id").textContent();

    await page.getByTestId("generate-profile").click();
    await expect(page.getByTestId("profile-panel")).toBeVisible({ timeout: 15_000 });
    const secondRun = await page.getByTestId("profile-run-id").textContent();
    expect(secondRun).toBe(firstRun);
  });

  test("patient switch cancels stale view", async ({ page }) => {
    await signIn(page);
    await page.getByTestId("visit-context-input").fill("SLOW_RUN diabetes review");
    await page.getByTestId("generate-profile").click();
    await expect(page.getByTestId("run-status")).toBeVisible();
    await page.getByTestId("patient-select").selectOption("P002");
    await expect(page.getByTestId("profile-panel")).toHaveCount(0);
    await page.getByTestId("generate-profile").click();
    await expect(page.getByTestId("profile-panel")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("facts-empty")).toBeVisible();
  });

  test("interrupted run surfaces restart control", async ({ page }) => {
    await signIn(page);
    await page
      .getByTestId("visit-context-input")
      .fill("FORCE_INTERRUPTED context");
    await page.getByTestId("generate-profile").click();
    await expect(page.getByTestId("error-banner")).toBeVisible();
    await expect(page.getByTestId("restart-run")).toBeVisible();
  });

  test("stale feedback returns safe conflict messaging", async ({ page }) => {
    await signIn(page);
    await page.getByTestId("generate-profile").click();
    await expect(page.getByTestId("profile-panel")).toBeVisible({ timeout: 15_000 });
    await page.route("**/v1/profiles/*/feedback", async (route) => {
      await route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({
          code: "stale_review",
          message: "Review versions stale",
        }),
      });
    });
    await page.getByTestId("feedback-accept").click();
    await expect(page.getByTestId("error-banner")).toContainText("Review out of date");
  });
});
