import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import { setUpAuthenticatorApp, signIn, watchForCspViolations } from "./helpers";

const BJORN_PASSWORD = "bjørns egen lange adgangssætning";

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `e2e-results/screens/admin-${name}.png`, fullPage: true });
}

test("the admin panel, from adding a user to their first sign-in", async ({ browser }) => {
  const adminContext = await browser.newContext();
  const admin = await adminContext.newPage();
  const violations = watchForCspViolations(admin);

  await signIn(admin, "e2e-admin");
  await expect(admin).toHaveURL(/\/sign-in\/set-up$/);
  await setUpAuthenticatorApp(admin);
  await admin.getByRole("link", { name: "Admin" }).click();

  // Users: the list, then adding Bjørn as a technician and reviewer.
  await expect(admin.getByRole("heading", { name: "Users" })).toBeVisible();
  await expect(admin.getByRole("row", { name: /Ingrid Admin/ })).toContainText("Break-glass");
  await shot(admin, "1-users");
  await admin.getByRole("link", { name: "Add user" }).click();
  await admin.getByLabel("Full name").fill("Bjørn Havn");
  await admin.getByLabel("Username").fill("bjorn");
  await admin.getByRole("checkbox", { name: /^Technician\b/ }).check();
  await admin.getByRole("checkbox", { name: /^Reviewer\b/ }).check();
  await shot(admin, "2-add-user");
  await admin.getByRole("button", { name: "Add user" }).click();
  const temporary = (await admin.getByLabel("Temporary password").textContent()) ?? "";
  expect(temporary).toMatch(/^([a-z2-9]{4}-){3}[a-z2-9]{4}$/);
  await shot(admin, "3-temporary-password");
  await admin.getByRole("link", { name: "Open user" }).click();
  await expect(admin.getByText("Awaiting first sign-in")).toBeVisible();

  // Bjørn, in his own browser: temporary password, his own password, a second factor.
  const bjornContext = await browser.newContext();
  const bjorn = await bjornContext.newPage();
  await signIn(bjorn, "bjorn", temporary);
  await expect(bjorn).toHaveURL(/\/sign-in\/new-password$/);
  await shot(bjorn, "4-new-password");
  await bjorn.getByLabel("New password", { exact: true }).fill(BJORN_PASSWORD);
  await bjorn.getByLabel("Repeat password").fill(BJORN_PASSWORD);
  await bjorn.getByRole("button", { name: "Save password" }).click();

  // The breach check calls out to the internet; an offline run gets a clear refusal.
  const setUp = bjorn.getByRole("heading", { name: "Set up your second step" });
  await expect(setUp.or(bjorn.getByRole("alert"))).toBeVisible();
  test.skip(!(await setUp.isVisible()), "the breach check service could not be reached");

  await setUpAuthenticatorApp(bjorn);
  await expect(bjorn.getByText("Reviewer, Technician")).toBeVisible();
  await expect(bjorn.getByRole("link", { name: "Admin" })).toHaveCount(0);
  await bjorn.goto("/admin/users");
  await expect(bjorn.getByText("You don't have access to the admin panel.")).toBeVisible();

  // Back to the administrator: Bjørn is active now; reset his second factor.
  await admin.reload();
  await expect(admin.getByText("Active", { exact: true })).toBeVisible();
  await expect(admin.locator("li", { hasText: "Authenticator app" })).toBeVisible();
  await shot(admin, "5-user");
  await admin.getByRole("button", { name: "Reset second factors" }).click();
  await admin.getByRole("dialog").getByRole("button", { name: "Reset second factors" }).click();
  await expect(admin.getByText("None set up yet.")).toBeVisible();
  await bjorn.reload();
  await expect(bjorn).toHaveURL(/\/sign-in$/);

  // Security: a change is saved; an allowlist that shuts this browser out is refused.
  await admin.getByRole("link", { name: "Security" }).click();
  await admin.getByLabel("Keep it locked for").fill("20");
  await admin.getByRole("button", { name: "Save settings" }).click();
  await expect(admin.getByRole("status")).toContainText("Saved");
  await admin.getByLabel("Allowed addresses").fill("10.99.0.0/24");
  await admin.getByRole("button", { name: "Save settings" }).click();
  await expect(admin.getByRole("alert")).toContainText("lock you out");
  await shot(admin, "6-security");

  // Server: the keys are there; the company can be renamed.
  await admin.getByRole("link", { name: "Server" }).click();
  await expect(admin.getByText("Present")).toHaveCount(3);
  await admin.getByLabel("Company name").fill("Nordlys IT A/S");
  await admin.getByRole("button", { name: "Save" }).click();
  await expect(admin.getByRole("status")).toContainText("Saved");
  await shot(admin, "7-server");

  // Audit log: the chain checks out, filters work, and the export downloads.
  await admin.getByRole("link", { name: "Audit log" }).click();
  await expect(admin.getByText("Chain intact")).toBeVisible();
  await admin.getByLabel("What").selectOption("admin.*");
  await admin.getByRole("button", { name: "Show" }).click();
  const actions = admin.locator("tbody td:nth-child(4)");
  await expect(actions.first()).toContainText("admin.");
  for (const action of await actions.allTextContents()) expect(action).toMatch(/^admin\./);
  await shot(admin, "8-audit");
  const [download] = await Promise.all([
    admin.waitForEvent("download"),
    admin.getByRole("link", { name: "Export CSV" }).click(),
  ]);
  const csv = await readFile((await download.path()) ?? "", "utf8");
  // CSV rows end in CRLF (RFC 4180).
  expect(csv.split("\r\n")[0]).toBe(
    "seq,occurred_at,actor_id,actor_name,action,target_type,target_id,ip,details,hash",
  );
  expect(csv).toContain("admin.user_created");

  // Your account: the theme follows the choice at once.
  await admin.getByRole("link", { name: "Your account" }).click();
  await admin.getByLabel("Dark").check();
  await admin.getByRole("button", { name: "Save", exact: true }).click();
  await expect(admin.locator("html")).toHaveAttribute("data-theme", "dark");
  await shot(admin, "9-account-dark");
  await admin.getByLabel("Same as this device").check();
  await admin.getByRole("button", { name: "Save", exact: true }).click();
  await expect(admin.locator("html")).not.toHaveAttribute("data-theme", /.+/);

  expect(violations).toEqual([]);
  await adminContext.close();
  await bjornContext.close();
});
