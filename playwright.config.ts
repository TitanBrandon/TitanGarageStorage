import { defineConfig } from '@playwright/test';
import { existsSync } from 'node:fs';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  use: {
    baseURL: process.env.TITAN_TEST_BASE_URL || 'http://127.0.0.1:5173',
    httpCredentials: process.env.TITAN_TEST_SITE_PASSWORD ? { username: 'titan', password: process.env.TITAN_TEST_SITE_PASSWORD } : undefined,
    viewport: { width: 1440, height: 1000 },
    launchOptions: {
      executablePath: process.env.CHROMIUM_PATH || (existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined),
      args: ['--no-sandbox', '--enable-unsafe-swiftshader', '--use-angle=swiftshader'],
    },
  },
  webServer: process.env.TITAN_TEST_BASE_URL ? undefined : { command: 'npm run dev:ui', url: 'http://127.0.0.1:5173', reuseExistingServer: true, timeout: 30_000 },
});
