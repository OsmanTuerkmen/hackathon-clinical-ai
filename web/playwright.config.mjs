import { defineConfig } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(webRoot, "..");
const python = process.platform === "win32"
  ? path.join(repoRoot, ".venv", "Scripts", "python.exe")
  : path.join(repoRoot, ".venv", "bin", "python");
const runtime = mkdtempSync(path.join(os.tmpdir(), "accessdesk-e2e-"));

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.mjs",
  timeout: 45_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8090",
    browserName: "chromium",
    channel: "chrome",
    headless: true,
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
  },
  webServer: {
    command: `"${python}" "${path.join(repoRoot, "start.py")}" --no-browser --host 127.0.0.1 --port 8090 --runtime "${runtime}"`,
    env: { ...process.env, ACCESSDESK_AI: "off" },
    url: "http://127.0.0.1:8090/api/health",
    reuseExistingServer: false,
    timeout: 120_000,
  },
  reporter: "list",
});
