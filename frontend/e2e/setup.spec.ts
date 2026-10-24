import { expect, test, type Page } from "@playwright/test";
import { addVirtualPasskey, PASSWORD, saveRecoveryCodes, watchForCspViolations } from "./helpers";

const SETUP_TOKEN = process.env.E2E_SETUP_TOKEN ?? "";

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `e2e-results/screens/setup-${name}.png`, fullPage: true });
}

test("before setup, every page leads to the wizard", async ({ page }) => {
  for (const path of ["/", "/sign-in", "/sign-in/verify"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/setup$/);
  }
});

test("the setup wizard, start to finish", async ({ page }) => {
  const violations = watchForCspViolations(page);
  await addVirtualPasskey(page);
  await page.goto("/setup");

  await expect(page.getByText("Step 1 of 6")).toBeVisible();
  await shot(page, "1-token");
  await page.getByLabel("Setup token").fill("AAAA-AAAA-AAAA-AAAA-AAAA-AAAA");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("alert")).toContainText("setup token isn't right");
  await page.getByLabel("Setup token").fill(SETUP_TOKEN.toLowerCase());
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByRole("heading", { name: "Company and server" })).toBeVisible();
  await expect(page.getByText("https://localhost", { exact: true })).toBeVisible();
  await shot(page, "2-company");
  await page.getByLabel("Company name").fill("Nordlys IT ApS");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByRole("heading", { name: "Security settings" })).toBeVisible();
  await expect(page.getByLabel("Minimum password length")).toHaveValue("12");
  await page.getByLabel("Lock an account after").fill("8");
  await shot(page, "3-security");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByRole("heading", { name: "Create the administrator" })).toBeVisible();
  await page.getByLabel("Full name").fill("Ingrid Admin");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByLabel("Repeat password").fill(`${PASSWORD} typo`);
  await page.getByRole("button", { name: "Create administrator" }).click();
  await expect(page.getByRole("alert")).toContainText("don't match");
  await page.getByLabel("Repeat password").fill(PASSWORD);
  await shot(page, "4-administrator");
  await page.getByRole("button", { name: "Create administrator" }).click();

  // The breach check calls api.pwnedpasswords.com; if it can't be reached, the
  // wizard offers to go on without it, which is the path an offline server takes.
  const offline = page.getByRole("button", { name: "Continue without the check" });
  const protect = page.getByRole("heading", { name: "Protect the administrator" });
  await expect(offline.or(protect)).toBeVisible();
  if (await offline.isVisible()) await offline.click();

  await expect(protect).toBeVisible();
  await shot(page, "5-second-factor");
  await page.getByRole("button", { name: /Passkey or security key/ }).click();
  await saveRecoveryCodes(page);

  await expect(page.getByRole("heading", { name: "Save the recovery kit" })).toBeVisible();
  for (const key of ["Master key", "Backup key"]) {
    const value = page.locator("dt", { hasText: key }).locator("+ dd");
    await expect(value).toHaveText(/^([A-Z2-7]{4} ){12}[A-Z2-7]{4}$/);
  }
  await shot(page, "6-recovery-kit");
  const finish = page.getByRole("button", { name: "Finish setup" });
  await expect(finish).toBeDisabled();
  await page.getByLabel(/I have saved the recovery kit/).check();
  await finish.click();

  await expect(page.getByRole("heading", { name: "Welcome, Ingrid Admin" })).toBeVisible();
  await expect(page.getByText("Administrator", { exact: true })).toBeVisible();
  await shot(page, "7-done");
  expect(violations).toEqual([]);
});

test("after setup, the wizard is closed", async ({ page }) => {
  await page.goto("/setup");
  await expect(page).toHaveURL(/\/sign-in$/);
});
