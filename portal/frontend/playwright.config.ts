import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright 冒烟测试配置
 * 默认指向 BASE_URL (.env 或 CI 中注入),本地缺省走线上 http://39.98.46.227
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: process.env.BASE_URL || 'http://39.98.46.227',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
