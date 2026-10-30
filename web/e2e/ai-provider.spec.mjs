import { expect, test } from "@playwright/test";

test("Gemini provider and model are named in the shell and opinion toggletip", async ({ page }) => {
  await page.route("**/api/info", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.ai = {
      enabled: true,
      provider: "gemini",
      model: "gemini-3.1-flash-lite",
      reason: null,
    };
    await route.fulfill({ response, json: body });
  });
  await page.route("**/api/cases/R01", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.result.ai = {
      status: {
        enabled: true,
        provider: "gemini",
        model: "gemini-3.1-flash-lite",
        reason: null,
      },
      opinion: {
        prohibited: false,
        explanation_de: "Unbedenklich.",
        explanation_en: "No prohibited purpose.",
        evidence_quote: "",
        evidence_quote_verified: false,
      },
      agrees: true,
    };
    await route.fulfill({ response, json: body });
  });

  await page.goto("/#/staff/case/R01");
  await expect(page.locator(".app-header__ai").first()).toHaveText("KI an · Gemini gemini-3.1-flash-lite");
  await page.getByRole("tab", { name: "Entscheidung" }).click();
  await expect(page.getByText("KI · Gemini gemini-3.1-flash-lite")).toBeVisible();

  const toggle = page.locator(".cds--toggletip-button");
  await expect(toggle).toHaveAttribute("aria-label", "KI-Hinweis · Gemini gemini-3.1-flash-lite");
  await expect(page.locator(".cds--toggletip-content"))
    .toContainText("Gemini gemini-3.1-flash-lite gibt nur eine Zweitmeinung");
});
