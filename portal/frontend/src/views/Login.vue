<template>
  <div class="login-page">
    <!-- 左侧品牌区 -->
    <div class="login-hero">
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
        <p class="hero-subtitle">金融行业离线数据统一工作台</p>
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
      <!-- 装饰圆形 -->
      <div class="hero-circle hero-circle-1"></div>
      <div class="hero-circle hero-circle-2"></div>
    </div>

    <!-- 右侧登录表单 -->
    <div class="login-form-area">
      <div class="login-card">
        <div class="login-header">
          <h2 class="login-title">欢迎登录</h2>
          <p class="login-subtitle">Data Platform</p>
        </div>

        <a-form :model="form" @submit-success="handleLogin" layout="vertical">
          <a-form-item field="username" label="用户名" :rules="[{ required: true, message: '请输入用户名' }]">
            <a-input v-model="form.username" placeholder="请输入用户名" size="large" allow-clear>
              <template #prefix><icon-user /></template>
            </a-input>
          </a-form-item>

          <a-form-item field="password" label="密码" :rules="[{ required: true, message: '请输入密码' }]">
            <a-input-password v-model="form.password" placeholder="请输入密码" size="large" allow-clear>
              <template #prefix><icon-lock /></template>
            </a-input-password>
          </a-form-item>

          <a-form-item style="margin-bottom: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
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
          <a-divider style="margin: 16px 0; color: #C9CDD4; font-size: 12px;">或使用企业账号登录</a-divider>
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
          <span>数据中台 MVP</span>
        </div>
      </div>

      <!-- 底部版权 -->
      <div class="copyright">
        &copy; 2026 数据中台 MVP &middot; 金融行业离线数据处理平台
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
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

onMounted(loadSsoProviders)
</script>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  background: #F5F7FA;
  overflow: hidden;
}

/* 左侧品牌区 */
.login-hero {
  flex: 1;
  background: linear-gradient(135deg, #2B5AED, #165DFF, #00C9A7);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  min-width: 0;
}

.hero-content {
  position: relative;
  z-index: 1;
  color: #fff;
  padding: 40px;
  max-width: 420px;
}

.hero-logo { margin-bottom: 24px; }

.hero-title {
  font-size: 32px;
  font-weight: 700;
  margin: 0 0 8px;
  letter-spacing: 2px;
}

.hero-subtitle {
  font-size: 15px;
  margin: 0 0 40px;
  opacity: 0.85;
}

.hero-features { display: flex; flex-direction: column; gap: 16px; }
.feature-item { display: flex; align-items: center; gap: 12px; font-size: 14px; opacity: 0.9; }
.feature-dot { width: 8px; height: 8px; border-radius: 50%; background: rgba(255,255,255,0.7); flex-shrink: 0; }

.hero-circle {
  position: absolute;
  border-radius: 50%;
  border: 1px solid rgba(255,255,255,0.15);
}
.hero-circle-1 { width: 400px; height: 400px; top: -100px; right: -100px; }
.hero-circle-2 { width: 300px; height: 300px; bottom: -80px; left: -80px; }

/* 右侧登录区 */
.login-form-area {
  width: 480px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #FFFFFF;
  padding: 40px;
}

.login-card {
  width: 100%;
  max-width: 360px;
  animation: cardIn 0.4s ease-out;
}

@keyframes cardIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.login-header {
  margin-bottom: 32px;
}

.login-title {
  font-size: 24px;
  font-weight: 600;
  color: #1D2129;
  margin: 0 0 4px;
}

.login-subtitle {
  font-size: 13px;
  color: #86909C;
  margin: 0;
  letter-spacing: 1px;
}

.login-btn {
  height: 42px;
  font-size: 15px;
  font-weight: 500;
  background: linear-gradient(135deg, #2B5AED, #165DFF) !important;
  border: none !important;
  border-radius: 8px !important;
  letter-spacing: 4px;
}
.login-btn:hover {
  background: linear-gradient(135deg, #3A69F5, #2B5AED) !important;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(43,90,237,0.25);
}

.login-footer {
  text-align: center;
  color: #C9CDD4;
  font-size: 12px;
  margin-top: 16px;
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
  height: 38px;
  border-radius: 8px !important;
  font-size: 13px;
  color: #4E5969;
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

.copyright {
  margin-top: auto;
  padding-top: 24px;
  color: #C9CDD4;
  font-size: 12px;
  letter-spacing: 0.5px;
}

/* Arco 样式覆盖 */
:deep(.arco-form-item-label) {
  color: #4E5969 !important;
  font-size: 13px !important;
}

@media (max-width: 900px) {
  .login-hero { display: none; }
  .login-form-area { width: 100%; }
}
</style>
