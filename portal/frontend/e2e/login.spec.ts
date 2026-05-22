import { test, expect } from '@playwright/test'

/**
 * 冒烟 1:登录页可达,渲染表单
 */
test('登录页加载且包含用户名/密码输入框', async ({ page }) => {
  await page.goto('/login')
  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByPlaceholder(/用户名|账号|username/i).first()).toBeVisible()
  await expect(page.getByPlaceholder(/密码|password/i).first()).toBeVisible()
})

/**
 * 冒烟 2:健康检查 API 200
 */
test('后端 /api/health 返回 ok', async ({ request }) => {
  const r = await request.get('/api/health')
  expect(r.status()).toBe(200)
  const body = await r.json()
  expect(body.status).toBe('ok')
})

/**
 * 冒烟 3:使用默认管理员登录,跳转到工作台
 */
test('admin 登录跳转 dashboard', async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder(/用户名|账号|username/i).first().fill('admin')
  await page.getByPlaceholder(/密码|password/i).first().fill('admin123')
  await page.getByRole('button', { name: /登录|login|sign in/i }).first().click()
  // 跳到非 /login 路径即认为成功(可能是 /dashboard 或 /)
  await expect(page).not.toHaveURL(/\/login/, { timeout: 10_000 })
})

/**
 * 冒烟 4:dashboard 受保护 — 未登录访问应被拦截
 */
test('未登录访问 /dashboard 被重定向至 /login', async ({ page, context }) => {
  await context.clearCookies()
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/login/, { timeout: 5_000 })
})

/**
 * 冒烟 5:登录失败的密码弹错提示
 */
test('错误密码登录提示失败', async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder(/用户名|账号|username/i).first().fill('admin')
  await page.getByPlaceholder(/密码|password/i).first().fill('wrong-password-xxx')
  await page.getByRole('button', { name: /登录|login|sign in/i }).first().click()
  // 应仍在登录页(未跳转)
  await page.waitForTimeout(1500)
  await expect(page).toHaveURL(/\/login/)
})
