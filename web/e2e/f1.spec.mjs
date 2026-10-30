import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const localHosts = new Set(["localhost", "127.0.0.1"]);

function trackExternalRequests(page) {
  const external = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (["http:", "https:", "ws:", "wss:"].includes(url.protocol) && !localHosts.has(url.hostname)) {
      external.push(url.href);
    }
  });
  return external;
}

test("inbox renders real cases and supports keyboard selection", async ({ page }) => {
  const external = trackExternalRequests(page);
  await page.goto("/");
  await expect(page.locator(".desktop-case-table tbody tr")).toHaveCount(15);
  await expect(page.getByRole("tab", { name: /Prüfung nötig/ })).toBeVisible();

  const rows = page.locator(".desktop-case-table tbody tr");
  await rows.first().click();
  await page.keyboard.press("j");
  await expect(rows.nth(1)).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("/");
  await expect(page.locator('input[type="search"]')).toBeFocused();
  await page.keyboard.press("Escape");
  await rows.nth(1).click();
  await page.keyboard.press("?");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await rows.nth(1).click();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#\/staff\/case\//);
  await expect(external).toEqual([]);
});

test("review form uses a newly submitted custom case only", async ({ page, request }) => {
  const external = trackExternalRequests(page);
  const response = await request.post("/api/submit", {
    data: {
      login: "F1 Review Tester",
      request: {
        applicant: {
          name: "F1 Review Tester",
          organisation: "Local Research Unit",
          country: "AT",
        },
        requested_as: "health data request",
        purpose: "Research on chronic kidney disease prevalence.",
        question: "How many adults have chronic kidney disease?",
        definitions: ["Chronic kidney disease = ICD-10 code starting with N18."],
      },
    },
  });
  expect(response.ok()).toBeTruthy();
  const { id } = await response.json();

  await page.goto(`/#/staff/case/${id}`);
  await page.getByRole("button", { name: "Prüfen" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.locator("#review-reason").fill("1234567890");
  await page.locator("#reviewer-name").fill("Staff reviewer");
  await page.getByRole("button", { name: "Prüfung speichern" }).click();
  await expect(page.getByText("Die Begründung muss mindestens 20 Zeichen enthalten.")).toBeVisible();

  await page.locator("#review-reason").fill(
    "The cohort and purpose have been reviewed for this custom case.",
  );
  await page.getByRole("button", { name: "Prüfung speichern" }).click();
  await expect(page.getByText("Freigegeben", { exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(external).toEqual([]);
});

test("R05 shows five safes and R02 highlights purpose evidence", async ({ page }) => {
  const external = trackExternalRequests(page);
  await page.goto("/#/staff/case/R05");
  await expect(page.locator(".five-safes-table tbody tr")).toHaveCount(5);
  for (const name of ["Wer fragt?", "Wozu?", "Welche Daten?", "Wo wird gerechnet?", "Was verlässt die Stelle?"]) {
    await expect(page.locator(".five-safes-table")).toContainText(name);
  }

  await page.goto("/#/staff/case/R02");
  await expect(page.locator(".case-panel mark")).toHaveText(["insurance premiums"]);
  await expect(external).toEqual([]);
});

test("applicant results use the regional map, age-band bars, and small-cell hatching", async ({ page }) => {
  const external = trackExternalRequests(page);
  await page.goto("/#/apply/case/R01");
  await page.locator("#identity-switch").selectOption({ label: "Dr. Sophie Lechner" });
  await expect(page.locator("path.map-region")).toHaveCount(9);
  await expect(page.locator(".result-layout .data-table tbody tr")).toHaveCount(9);

  await page.locator("#identity-switch").selectOption({ label: "Mag. Petra Wimmer" });
  await page.goto("/#/apply/case/R03");
  await expect(page.locator(".chart-bar")).toHaveCount(3);

  await page.locator("#identity-switch").selectOption({ label: "Prof. Elena Rossi" });
  await page.goto("/#/apply/case/R08");
  await expect(page.locator("path.map-region")).toHaveCount(9);
  await expect(page.locator(".value-cell--hidden").first()).toBeVisible();
  await expect(external).toEqual([]);
});

test("letter and transparency register expose only their permitted content", async ({ page }) => {
  const external = trackExternalRequests(page);
  await page.goto("/#/letter/R05");
  await expect(page.locator(".letter-page")).toContainText("Datengenehmigung");
  await expect(page.locator(".letter-page")).toContainText("1.152");

  await page.goto("/#/register");
  const register = page.locator(".register-table");
  await expect(register).toContainText("HDAB-AT/2026/R01");
  await expect(register).not.toContainText("Lechner");
  await expect(register).not.toContainText("532");
  await expect(register).not.toContainText("6.2");
  await expect(register).not.toContainText("p-");
  await expect(external).toEqual([]);
});

test("D05 shows the differencing explanation; audit and evaluation run", async ({ page }) => {
  const external = trackExternalRequests(page);
  await page.goto("/#/apply/case/D05");
  await page.locator("#identity-switch").selectOption({ label: "Dr. Sophie Lechner" });
  await expect(page.locator(".differencing-notes")).toContainText("Vorarlberg");
  await expect(page.locator(".differencing-notes")).toContainText("R01");

  await page.goto("/#/staff/audit");
  await page.getByRole("button", { name: "Kette prüfen" }).click();
  await expect(page.getByRole("status")).toContainText("Kette intakt");

  await page.goto("/#/staff/eval");
  await page.getByRole("button", { name: "Auswertung starten" }).click();
  await expect(page.locator(".evaluation-results")).toContainText("10 / 10");
  await expect(page.locator(".evaluation-results")).toContainText("29 / 29");
  await expect(external).toEqual([]);
});

test("builder templates, Art. 54 pre-check, and submission use the selected applicant", async ({ page }) => {
  const external = trackExternalRequests(page);
  await page.goto("/#/apply/new");
  await page.locator("#identity-switch").selectOption({ label: "Dr. Sophie Lechner" });
  await page.locator("#template-select").selectOption("prevalence-region");
  await expect(page.locator(".precheck-panel")).toContainText("COPD");
  await expect(page.locator(".precheck-panel")).toContainText("Kohortengröße");

  await page.locator("#builder-purpose").fill(
    "We are launching an advertising campaign to promote a new product based on the results.",
  );
  await page.locator("#builder-question").fill(
    "Which regions have the most prescriptions so that our campaign can focus there?",
  );
  await expect(page.locator(".precheck-panel")).toContainText("Art. 54");
  await expect(page.locator(".precheck-panel")).toContainText("advertising campaign");

  await page.locator("#builder-purpose").fill("Scientific research on diabetes prevention in adults.");
  await page.getByRole("button", { name: "Antrag einreichen" }).click();
  await expect(page).toHaveURL(/#\/apply\/case\/U\d+/);
  await expect(external).toEqual([]);
});

test("SPE workspace blocks raw download and permits reviewed aggregate CSV only", async ({ page }) => {
  const external = trackExternalRequests(page);
  await page.goto("/#/apply/case/R05");
  await page.locator("#identity-switch").selectOption({ label: "Dr. Amir Hadžić" });
  await page.getByRole("button", { name: "Zum SPE-Arbeitsbereich" }).click();
  await expect(page).toHaveURL(/#\/apply\/spe\/DP-R05-/);
  await page.waitForLoadState("networkidle");
  const workspaceUrl = page.url();

  await page.getByRole("button", { name: "Rohdaten herunterladen" }).click();
  await expect(page.getByText(/Download blocked/)).toBeVisible();
  await page.locator("#spe-sql").fill("SELECT patient_id FROM cohort LIMIT 10");
  await page.getByRole("button", { name: "Abfrage ausführen" }).click();
  await expect(page.locator(".spe-query-result")).toContainText("patient_id");
  await page.getByRole("button", { name: "Export zur Prüfung einreichen" }).click();
  await page.locator("#export-title").fill("Patient rows");
  await page.locator("#export-note").fill("Testing the automatic identifier block.");
  await page.getByRole("button", { name: "Einreichen", exact: true }).click();
  await expect(page.locator(".spe-exports")).toContainText("rejected_auto");
  await page.goto("/#/staff/exports");
  const failedExport = page.locator("tbody tr").filter({ hasText: "Patient rows" });
  await failedExport.getByRole("button", { name: "Details" }).click();
  await expect(page.getByRole("button", { name: "Freigeben" })).toBeDisabled();
  await page.goto(workspaceUrl);

  await page.locator("#spe-sql").fill("SELECT COUNT(*) AS n FROM cohort");
  await page.getByRole("button", { name: "Abfrage ausführen" }).click();
  await page.getByRole("button", { name: "Export zur Prüfung einreichen" }).click();
  await page.locator("#export-title").fill("Aggregate cohort count");
  await page.locator("#export-note").fill("One aggregate cohort count for review.");
  await page.getByRole("button", { name: "Einreichen", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".spe-exports")).toContainText("pending_review");

  await page.goto("/#/staff/exports");
  const exportRow = page.locator("tbody tr").filter({ hasText: "Aggregate cohort count" });
  await exportRow.getByRole("button", { name: "Details" }).click();
  await page.getByRole("button", { name: "Freigeben" }).click();
  await page.locator("#export-review-reason").fill("Aggregate reviewed; it contains no identifiers or small cells.");
  await page.locator("#export-reviewer").fill("Staff reviewer");
  await page.getByRole("button", { name: "Prüfung speichern" }).click();

  await page.goto(workspaceUrl);
  await expect(page.locator(".spe-exports")).toContainText("approved");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: /CSV laden|Download CSV/ }).click();
  expect((await downloadPromise).suggestedFilename()).toMatch(/^export_X\d+\.csv$/);
  await expect(external).toEqual([]);
});

test("F1 and F2 screenshot routes have no serious or critical accessibility violations in both themes", async ({ page }) => {
  const r05Response = await page.request.get("http://127.0.0.1:8090/api/cases/R05");
  const permit = (await r05Response.json()).result.spe.permit_id;
  const routes = [
    { path: "/#/staff/inbox" },
    { path: "/#/staff/case/R05" },
    { path: "/#/staff/case/R05", tab: "Daten" },
    { path: "/#/staff/case/R05", tab: "Personen" },
    { path: "/#/staff/case/R02" },
    { path: "/#/staff/case/R02", tab: "Entscheidung" },
    { path: "/#/apply/case/R01", identity: "Dr. Sophie Lechner" },
    { path: "/#/apply/case/R03", identity: "Mag. Petra Wimmer" },
    { path: "/#/apply/case/R08", identity: "Prof. Elena Rossi" },
    { path: "/#/apply/case/D05", identity: "Dr. Sophie Lechner" },
    { path: "/#/apply/case/R05", identity: "Dr. Amir Hadžić" },
    { path: "/#/apply/case/D05", identity: "Dr. Sophie Lechner" },
    { path: "/#/apply/new", identity: "Dr. Sophie Lechner" },
    { path: "/#/apply/new", identity: "Dr. Sophie Lechner", template: "prevalence-region" },
    { path: "/#/apply/new", identity: "Dr. Sophie Lechner", art54: true },
    { path: `/#/apply/spe/${permit}`, identity: "Dr. Amir Hadžić" },
    { path: `/#/apply/spe/${permit}`, identity: "Dr. Amir Hadžić", blocked: true },
    { path: "/#/letter/R05" },
    { path: "/#/register" },
    { path: "/#/staff/exports" },
    { path: "/#/staff/audit", verifyAudit: true },
    { path: "/#/staff/eval", runEvaluation: true },
  ];
  const external = trackExternalRequests(page);
  await page.goto("/");
  for (const theme of ["white", "g100"]) {
    await page.evaluate((value) => localStorage.setItem("accessdesk.theme", value), theme);
    await page.reload();
    for (const route of routes) {
      await page.goto(route.path);
      if (route.identity) {
        await page.locator("#identity-switch").selectOption({ label: route.identity });
      }
      if (route.tab) await page.getByRole("tab", { name: route.tab }).click();
      if (route.template) await page.locator("#template-select").selectOption(route.template);
      if (route.art54) {
        await page.locator("#builder-purpose").fill("We are launching an advertising campaign for a new product.");
        await page.locator("#builder-question").fill("Where are prescriptions highest to focus the campaign?");
      }
      if (route.verifyAudit) await page.getByRole("button", { name: "Kette prüfen" }).click();
      if (route.runEvaluation) {
        await page.getByRole("button", { name: "Auswertung starten" }).click();
        await page.locator(".evaluation-results").waitFor();
      }
      if (route.blocked) {
        await page.getByRole("button", { name: "Rohdaten herunterladen" }).click();
      }
      await expect(page.locator("#page-title")).toBeVisible();
      await page.waitForLoadState("networkidle");
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      const critical = results.violations.filter((violation) =>
        violation.impact === "serious" || violation.impact === "critical",
      );
      expect(critical.map((violation) => ({
        id: violation.id,
        help: violation.help,
        nodes: violation.nodes.map((node) => node.target),
      }))).toEqual([]);
    }
  }
  await expect(external).toEqual([]);
});
