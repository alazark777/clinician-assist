import { expect, type Page } from "@playwright/test";

/** Demo credentials from agent-service/secrets/demo-sessions.json (not the contract mock). */
export const REAL_DEMO_LOGIN = {
  username: "reviewer",
  passphrase: "local-demo",
} as const;

/** Credentials wired to e2e/mock-api/server.mjs only. */
export const MOCK_DEMO_LOGIN = {
  username: "demo-clinician",
  passphrase: "demo-pass",
} as const;

export async function signInWithCredentials(
  page: Page,
  login: { username: string; passphrase: string },
) {
  await page.goto("/");
  await page.getByLabel("Username").fill(login.username);
  await page.getByLabel("Passphrase").fill(login.passphrase);
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("profile-workspace")).toBeVisible();
}
