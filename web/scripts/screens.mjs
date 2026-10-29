import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outputRoot = path.resolve(webRoot, "../docs/screens");
const baseUrl = process.env.BASE_URL ?? "http://127.0.0.1:8001";
const routes = [
  { name: "inbox", route: "/staff/inbox" },
  { name: "case-R05", route: "/staff/case/R05" },
  { name: "case-R02", route: "/staff/case/R02" },
  { name: "apply-R01", route: "/apply/case/R01", identity: "Dr. Sophie Lechner" },
  { name: "apply-R03", route: "/apply/case/R03", identity: "Mag. Petra Wimmer" },
  { name: "apply-R08", route: "/apply/case/R08", identity: "Prof. Elena Rossi" },
  { name: "letter-R05", route: "/letter/R05" },
  { name: "register", route: "/register" },
];
const nonLocalRequests = [];

await fs.mkdir(outputRoot, { recursive: true });
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  for (const theme of ["white", "g100"]) {
    for (const width of [1440, 390]) {
      for (const route of routes) {
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
        if (route.name === "inbox") {
          const inboxRows = width < 672
            ? ".mobile-case-list .mobile-case-row"
            : ".desktop-case-table tbody tr";
          await page.locator(inboxRows).first().waitFor();
        }
        if (route.name.startsWith("case-")) await page.locator(".five-safes-table tbody tr").first().waitFor();
        if (route.name.startsWith("apply-R01")) await page.locator("path.map-region").first().waitFor();
        if (route.name === "apply-R03") await page.locator(".chart-bar").first().waitFor();
        if (route.name === "register") await page.locator(".register-table tbody tr").first().waitFor();
        if (route.name === "letter-R05") await page.locator(".letter-page").waitFor();
        await page.evaluate(() => document.fonts.ready);
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
