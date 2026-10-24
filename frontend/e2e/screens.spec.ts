import { test } from "@playwright/test";
import { signIn, totp } from "./helpers";

// Not assertions: screenshots of each screen in both themes and at phone width,
// written to e2e-results/screens for a person to look over.
for (const colorScheme of ["light", "dark"] as const) {
  for (const [label, viewport] of [
    ["desktop", { width: 1280, height: 800 }],
    ["phone", { width: 390, height: 844 }],
  ] as const) {
    test(`screens: ${colorScheme}, ${label}`, async ({ browser }) => {
      const context = await browser.newContext({ colorScheme, viewport });
      const page = await context.newPage();
      const username = `e2e-screens-${colorScheme}-${label}`;
      const shot = (name: string) =>
        page.screenshot({
          path: `e2e-results/screens/${name}-${colorScheme}-${label}.png`,
          fullPage: true,
        });

      await page.goto("/sign-in");
      await page.getByRole("heading", { name: "Sign in" }).waitFor();
      await shot("1-sign-in");

      await signIn(page, "e2e-wrong", "not the right password at all");
      await page.getByRole("alert").waitFor();
      await shot("2-sign-in-error");

      await signIn(page, username);
      await page.getByRole("heading", { name: "Set up your second step" }).waitFor();
      await page.mouse.move(0, 0);
      await shot("3-set-up");

      await page.getByRole("button", { name: /Authenticator app/ }).click();
      await page.getByRole("img", { name: /QR code/ }).waitFor();
      await shot("4-authenticator-app");

      const secret = (await page.locator(".secret").textContent()) ?? "";
      await page.getByLabel("6-digit code").fill(totp(secret));
      await page.getByRole("button", { name: "Confirm" }).click();
      await page.getByRole("heading", { name: "Save your recovery codes" }).waitFor();
      await shot("5-recovery-codes");

      await page.getByLabel("I have saved these codes somewhere safe").check();
      await page.getByRole("button", { name: "Continue" }).click();
      await page.getByRole("heading", { name: /Welcome/ }).waitFor();
      await shot("6-home");

      await page.getByRole("button", { name: "Sign out" }).click();
      await signIn(page, username);
      await page.getByRole("heading", { name: "Confirm it's you" }).waitFor();
      await shot("7-verify");
      await context.close();
    });
  }
}
