import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outputRoot = path.resolve(webRoot, "../docs/screens");
const baseUrl = process.env.BASE_URL ?? "http://127.0.0.1:8001";
const r05 = await fetch(`${baseUrl}/api/cases/R05`).then((response) => response.json());
const permitId = r05.summary.permit_id;
const routes = [
  { name: "inbox", route: "/staff/inbox" },
  { name: "case-R05", route: "/staff/case/R05" },
  { name: "case-R05-daten", route: "/staff/case/R05", tab: "Daten" },
  { name: "case-R05-personen", route: "/staff/case/R05", tab: "Personen" },
  { name: "case-R02", route: "/staff/case/R02" },
  { name: "case-R02-entscheidung", route: "/staff/case/R02", tab: "Entscheidung" },
  { name: "apply-R01", route: "/apply/case/R01", identity: "Dr. Sophie Lechner" },
  { name: "apply-R03", route: "/apply/case/R03", identity: "Mag. Petra Wimmer" },
  { name: "apply-R08", route: "/apply/case/R08", identity: "Prof. Elena Rossi" },
  { name: "apply-R05", route: "/apply/case/R05", identity: "Dr. Amir Hadžić" },
  { name: "apply-D05", route: "/apply/case/D05", identity: "Dr. Sophie Lechner" },
  { name: "case-D05-ergebnis", route: "/apply/case/D05", identity: "Dr. Sophie Lechner" },
  { name: "builder-empty", route: "/apply/new", identity: "Dr. Sophie Lechner" },
  { name: "builder-template", route: "/apply/new", identity: "Dr. Sophie Lechner", action: "template" },
  { name: "builder-art54", route: "/apply/new", identity: "Dr. Sophie Lechner", action: "art54" },
  { name: "spe-R05-console", route: `/apply/spe/${permitId}`, identity: "Dr. Amir Hadžić" },
  { name: "spe-R05-blocked", route: `/apply/spe/${permitId}`, identity: "Dr. Amir Hadžić", action: "blocked" },
  { name: "exports", route: "/staff/exports" },
  { name: "audit", route: "/staff/audit", action: "audit" },
  { name: "eval", route: "/staff/eval", action: "eval" },
  { name: "letter-R05", route: "/letter/R05" },
  { name: "register", route: "/register" },
];
const selectedNames = process.env.SCREEN_ROUTES?.split(",").map((name) => name.trim()).filter(Boolean);
const selectedRoutes = selectedNames
  ? routes.filter((route) => selectedNames.includes(route.name))
  : routes;
if (selectedNames && selectedRoutes.length !== selectedNames.length) {
  const missing = selectedNames.find((name) => !routes.some((route) => route.name === name));
  throw new Error(`Unknown screen name: ${missing}`);
}
const nonLocalRequests = [];

await fs.mkdir(outputRoot, { recursive: true });
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  for (const theme of ["white", "g100"]) {
    for (const width of [1440, 390]) {
      for (const route of selectedRoutes) {
        const context = await browser.newContext({
          viewport: { width, height: width < 500 ? 844 : 1000 },
        });
        await context.addInitScript(({ selectedTheme, identity }) => {
          localStorage.setItem("accessdesk.theme", selectedTheme);
          localStorage.setItem("accessdesk.language", "de");
          if (identity) localStorage.setItem("accessdesk.identity", identity);
        }, { selectedTheme: theme, identity: route.identity });
        const page = await context.newPage();
        page.on("request", (request) => {
          const url = new URL(request.url());
          if (["http:", "https:", "ws:", "wss:"].includes(url.protocol)
            && !["localhost", "127.0.0.1"].includes(url.hostname)) {
            nonLocalRequests.push(url.href);
          }
        });
        await page.emulateMedia({ reducedMotion: "reduce" });
        await page.goto(`${baseUrl}/#${route.route}`, { waitUntil: "networkidle" });
        await page.locator("#page-title").waitFor();
        if (route.tab) await page.getByRole("tab", { name: route.tab }).click();
        if (route.action === "template") {
          await page.locator("#template-select").selectOption("prevalence-region");
          await page.locator(".precheck-panel").waitFor();
        }
        if (route.action === "art54") {
          await page.locator("#builder-purpose").fill(
            "We are launching an advertising campaign to promote a new product.",
          );
          await page.getByText("REJECT [54]").waitFor();
          await page.locator(".precheck-panel").getByText(/advertising campaign/).waitFor();
        }
        if (route.action === "blocked") {
          await page.getByRole("button", { name: "Rohdaten herunterladen" }).click();
          await page.getByText(/Download blockiert|Download blocked/).waitFor();
        }
        if (route.action === "audit") {
          await page.getByRole("button", { name: "Kette prüfen" }).click();
          await page.getByRole("status").waitFor();
        }
        if (route.action === "eval") {
          await page.getByRole("button", { name: "Auswertung starten" }).click();
          await page.locator(".evaluation-results").waitFor();
        }
        if (route.name === "inbox") {
          const inboxRows = width < 672
            ? ".mobile-case-list .mobile-case-row"
            : ".desktop-case-table tbody tr";
          await page.locator(inboxRows).first().waitFor();
        }
        if (/^case-R/.test(route.name)) await page.locator(".five-safes-table tbody tr").first().waitFor();
        if (route.name.startsWith("apply-R01") || route.name === "apply-D05" || route.name === "case-D05-ergebnis") {
          await page.locator("path.map-region").first().waitFor();
        }
        if (route.name === "apply-R03") await page.locator(".chart-bar").first().waitFor();
        if (route.name.startsWith("spe-R05")) await page.locator(".permit-details").waitFor();
        if (route.name === "exports") await page.locator(".page-heading").waitFor();
        if (route.name === "register") await page.locator(".register-table tbody tr").first().waitFor();
        if (route.name === "letter-R05") await page.locator(".letter-page").waitFor();
        await page.evaluate(() => document.fonts.ready);
        const horizontalOverflow = await page.evaluate(
          () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
        );
        if (horizontalOverflow) throw new Error(`Horizontal page overflow at ${route.name} (${width}px)`);
        const screenshot = path.join(outputRoot, `${route.name}-${width}-${theme === "white" ? "light" : "dark"}.png`);
        await page.screenshot({ path: screenshot, fullPage: true, animations: "disabled" });
        console.log(screenshot);

        if (route.name === "letter-R05" && width === 1440 && theme === "white") {
          await page.emulateMedia({ media: "print" });
          const pdf = path.join(outputRoot, "letter-R05-de.pdf");
          await page.pdf({ path: pdf, format: "A4", printBackground: true, preferCSSPageSize: true });
          console.log(pdf);
        }
        await context.close();
      }
    }
  }
  if (nonLocalRequests.length > 0) {
    throw new Error(`Non-local browser requests: ${nonLocalRequests.join(", ")}`);
  }
} finally {
  await browser.close();
}
