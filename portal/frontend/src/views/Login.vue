<template>
  <div class="login-page">
    <!-- 左侧粒子动画区 -->
    <div class="login-hero">
      <canvas ref="canvasRef" class="particle-canvas"></canvas>
      <div class="hero-content">
        <div class="hero-logo">
          <svg width="48" height="48" viewBox="0 0 36 36" fill="none">
            <defs>
              <linearGradient id="hero-grad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#2B5AED"/>
                <stop offset="100%" stop-color="#00C9A7"/>
              </linearGradient>
            </defs>
            <rect width="36" height="36" rx="8" fill="url(#hero-grad)"/>
            <path d="M9 10h18v2.5H11.5v5h13v2.5h-13v5H27V27.5H9V10z" fill="white"/>
          </svg>
        </div>
        <h1 class="hero-title">数据中台</h1>
        <p class="hero-subtitle">DATA INTELLIGENCE MIDDLEWARE</p>
        <div class="hero-features">
          <div class="feature-item">
            <div class="feature-dot"></div>
            <span>多数据源统一管理</span>
          </div>
          <div class="feature-item">
            <div class="feature-dot"></div>
            <span>可视化调度编排</span>
          </div>
          <div class="feature-item">
            <div class="feature-dot"></div>
            <span>数据血缘自动追踪</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧登录表单 -->
    <div class="login-form-area">
      <div class="login-card">
        <div class="login-header">
          <h2 class="login-title">欢迎登录</h2>
          <p class="login-subtitle">Sign in to your workspace</p>
        </div>

        <a-form :model="form" @submit-success="handleLogin" layout="vertical">
          <a-form-item field="username" :rules="[{ required: true, message: '请输入用户名' }]" hide-label>
            <a-input v-model="form.username" placeholder="用户名" size="large" allow-clear>
              <template #prefix><icon-user /></template>
            </a-input>
          </a-form-item>

          <a-form-item field="password" :rules="[{ required: true, message: '请输入密码' }]" hide-label>
            <a-input-password v-model="form.password" placeholder="密码" size="large" allow-clear>
              <template #prefix><icon-lock /></template>
            </a-input-password>
          </a-form-item>

          <a-form-item style="margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
              <a-checkbox v-model="form.remember">记住密码</a-checkbox>
              <a-link style="font-size: 12px;">忘记密码?</a-link>
            </div>
          </a-form-item>

          <a-form-item>
            <a-button type="primary" html-type="submit" long size="large" :loading="loading" class="login-btn">
              登 录
            </a-button>
          </a-form-item>
        </a-form>

        <!-- SSO 登录区 -->
        <template v-if="enabledProviders.length > 0">
          <a-divider style="margin: 16px 0; color: var(--color-text-disabled); font-size: 12px;">或使用企业账号登录</a-divider>
          <div class="sso-buttons">
            <a-button
              v-for="p in enabledProviders"
              :key="p.provider"
              class="sso-btn"
              @click="ssoLogin(p.provider)"
            >
              <span class="sso-icon" :style="{ background: p.color }">{{ p.abbr }}</span>
              {{ p.label }}登录
            </a-button>
          </div>
        </template>

        <div class="login-footer">
          <span>数据中台 MVP &copy; 2026</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { IconUser, IconLock } from '@arco-design/web-vue/es/icon'
import { useUserStore } from '../stores/user'
import { adminGetSsoPublic } from '../api'

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)

const form = reactive({
  username: '',
  password: '',
  remember: true,
})

const _ALL_PROVIDERS = [
  { provider: 'dingtalk', label: '钉钉', abbr: 'DD', color: '#1677FF' },
  { provider: 'feishu',   label: '飞书', abbr: 'FS', color: '#3370FF' },
  { provider: 'wecom',    label: '企微', abbr: 'WX', color: '#07C160' },
]
const enabledProviders = ref<typeof _ALL_PROVIDERS>([])

async function loadSsoProviders() {
  try {
    const res: any = await adminGetSsoPublic()
    const enabledSet = new Set((res || []).map((c: any) => c.provider))
    enabledProviders.value = _ALL_PROVIDERS.filter(p => enabledSet.has(p.provider))
  } catch {
    enabledProviders.value = []
  }
}

function ssoLogin(provider: string) {
  window.location.href = `/api/auth/oauth/${provider}`
}

async function handleLogin() {
  loading.value = true
  try {
    await userStore.login(form.username, form.password)
    Message.success('登录成功')
    router.push('/dashboard')
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}

// ---- 粒子网络动画 ----
const canvasRef = ref<HTMLCanvasElement | null>(null)
let animationId = 0

interface Particle {
  x: number; y: number; vx: number; vy: number; r: number; alpha: number
}

function initParticles() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  let width = 0
  let height = 0
  const particles: Particle[] = []
  const PARTICLE_COUNT = 60
  const CONNECTION_DIST = 150
  let mouse = { x: -1000, y: -1000 }

  function resize() {
    const rect = canvas!.parentElement!.getBoundingClientRect()
    width = rect.width
    height = rect.height
    canvas!.width = width * window.devicePixelRatio
    canvas!.height = height * window.devicePixelRatio
    ctx!.scale(window.devicePixelRatio, window.devicePixelRatio)
  }

  function createParticles() {
    particles.length = 0
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        r: Math.random() * 2 + 1.5,
        alpha: Math.random() * 0.5 + 0.3,
      })
    }
  }

  function draw() {
    ctx!.clearRect(0, 0, width, height)

    // 连线
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x
        const dy = particles[i].y - particles[j].y
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < CONNECTION_DIST) {
          const opacity = (1 - dist / CONNECTION_DIST) * 0.25
          ctx!.beginPath()
          ctx!.strokeStyle = `rgba(37, 99, 235, ${opacity})`
          ctx!.lineWidth = 0.8
          ctx!.moveTo(particles[i].x, particles[i].y)
          ctx!.lineTo(particles[j].x, particles[j].y)
          ctx!.stroke()
        }
      }
    }

    // 粒子
    for (const p of particles) {
      // 鼠标涟漪
      const mdx = p.x - mouse.x
      const mdy = p.y - mouse.y
      const mDist = Math.sqrt(mdx * mdx + mdy * mdy)
      if (mDist < 120) {
        const force = (120 - mDist) / 120 * 0.3
        p.vx += (mdx / mDist) * force
        p.vy += (mdy / mDist) * force
      }

      p.x += p.vx
      p.y += p.vy

      // 边界反弹
      if (p.x < 0 || p.x > width) p.vx *= -1
      if (p.y < 0 || p.y > height) p.vy *= -1
      p.x = Math.max(0, Math.min(width, p.x))
      p.y = Math.max(0, Math.min(height, p.y))

      // 速度衰减
      p.vx *= 0.998
      p.vy *= 0.998
      // 保持最低速度
      const speed = Math.sqrt(p.vx * p.vx + p.vy * p.vy)
      if (speed < 0.15) {
        p.vx += (Math.random() - 0.5) * 0.1
        p.vy += (Math.random() - 0.5) * 0.1
      }

      ctx!.beginPath()
      ctx!.arc(p.x, p.y, p.r, 0, Math.PI * 2)
      ctx!.fillStyle = `rgba(37, 99, 235, ${p.alpha})`
      ctx!.fill()
    }

    animationId = requestAnimationFrame(draw)
  }

  function onMouseMove(e: MouseEvent) {
    const rect = canvas!.getBoundingClientRect()
    mouse.x = e.clientX - rect.left
    mouse.y = e.clientY - rect.top
  }

  function onMouseLeave() {
    mouse.x = -1000
    mouse.y = -1000
  }

  resize()
  createParticles()
  draw()

  window.addEventListener('resize', resize)
  canvas!.addEventListener('mousemove', onMouseMove)
  canvas!.addEventListener('mouseleave', onMouseLeave)

  // 存储清理函数
  ;(canvas as any)._cleanup = () => {
    cancelAnimationFrame(animationId)
    window.removeEventListener('resize', resize)
    canvas!.removeEventListener('mousemove', onMouseMove)
    canvas!.removeEventListener('mouseleave', onMouseLeave)
  }
}

onMounted(() => {
  loadSsoProviders()
  initParticles()
})

onUnmounted(() => {
  const canvas = canvasRef.value
  if (canvas && (canvas as any)._cleanup) (canvas as any)._cleanup()
})
</script>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  background: linear-gradient(135deg, #f8fafc 0%, #ffffff 100%);
  overflow: hidden;
}

/* 左侧粒子动画区 */
.login-hero {
  flex: 3;
  position: relative;
  overflow: hidden;
  background: linear-gradient(160deg, #f0f5ff 0%, #e8f0fe 50%, #f8fafc 100%);
  min-width: 0;
}

.particle-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.hero-content {
  position: absolute;
  bottom: 60px;
  left: 48px;
  z-index: 1;
}

.hero-logo { margin-bottom: 20px; }

.hero-title {
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
  margin: 0 0 6px;
  letter-spacing: 2px;
}

.hero-subtitle {
  font-size: 12px;
  color: #64748b;
  margin: 0 0 28px;
  letter-spacing: 3px;
  font-weight: 500;
}

.hero-features { display: flex; flex-direction: column; gap: 12px; }
.feature-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: #475569;
}
.feature-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #2563eb;
  flex-shrink: 0;
}

/* 右侧登录区 */
.login-form-area {
  flex: 2;
  max-width: 460px;
  min-width: 380px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 40px;
  background: #ffffff;
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.04);
}

.login-card {
  width: 100%;
  max-width: 340px;
  animation: cardIn 0.5s ease-out;
}

@keyframes cardIn {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}

.login-header {
  margin-bottom: 36px;
}

.login-title {
  font-size: 26px;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 6px;
}

.login-subtitle {
  font-size: 12px;
  color: #94a3b8;
  margin: 0;
  letter-spacing: 1.5px;
}

/* 输入框美化 */
:deep(.arco-input-wrapper) {
  border-radius: 10px !important;
  border-color: #e2e8f0 !important;
  background: #f8fafc !important;
  transition: all 0.25s ease;
}
:deep(.arco-input-wrapper:hover) {
  border-color: #cbd5e1 !important;
}
:deep(.arco-input-wrapper.arco-input-focus) {
  border-color: #2563eb !important;
  background: #ffffff !important;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.08) !important;
}
:deep(.arco-input-prefix) {
  color: #94a3b8;
}

.login-btn {
  height: 44px;
  font-size: 15px;
  font-weight: 500;
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
  border: none !important;
  border-radius: 10px !important;
  letter-spacing: 4px;
  transition: all 0.25s ease;
}
.login-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(37, 99, 235, 0.3);
}

.login-footer {
  text-align: center;
  color: #cbd5e1;
  font-size: 11px;
  margin-top: 24px;
  letter-spacing: 0.5px;
}

.sso-buttons {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sso-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  border-radius: 10px !important;
  font-size: 13px;
  color: #475569;
  border-color: #e2e8f0 !important;
}
.sso-btn:hover {
  border-color: #cbd5e1 !important;
  background: #f8fafc !important;
}

.sso-icon {
  width: 22px;
  height: 22px;
  border-radius: 5px;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

:deep(.arco-form-item) {
  margin-bottom: 20px;
}

@media (max-width: 900px) {
  .login-hero { display: none; }
  .login-form-area { max-width: 100%; min-width: 0; flex: 1; }
}
</style>
