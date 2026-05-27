# Playwright 冒烟测试

## 运行

```bash
# 1. 安装 Playwright 浏览器(首次)
pnpm exec playwright install chromium

# 2. 跑冒烟(默认指向线上 http://47.92.236.44)
pnpm test:e2e

# 3. 指向本地后端
BASE_URL=http://localhost:5173 pnpm test:e2e
```

## 覆盖

| # | 用例 | 目的 |
|---|------|------|
| 1 | 登录页加载 | 前端静态资源 + 路由 OK |
| 2 | /api/health 200 | 后端进程 OK,Nginx 反代 OK |
| 3 | admin/admin123 登录跳转 | 认证链路 + Cookie/JWT 颁发 OK |
| 4 | 未登录访问 dashboard 被拦截 | 路由守卫 OK |
| 5 | 错误密码不跳转 | 登录失败处理 OK |

## 何时跑

- 本地改动后:手动跑一遍
- 上线前:必跑(`pnpm test:e2e` 必须全绿)
- CI:后续接入 GitHub Actions 时挂上
