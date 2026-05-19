<template>
  <div class="admin-page">
    <PageHeader title="SSO 配置" />

    <a-row :gutter="16">
      <a-col v-for="p in providers" :key="p.provider" :span="8">
        <a-card :bordered="false" class="sso-card">
          <div class="sso-header">
            <div class="sso-logo" :style="{ background: p.color }">{{ p.abbr }}</div>
            <div>
              <div class="sso-name">{{ p.label }}</div>
              <a-badge
                :status="getConfig(p.provider)?.enabled ? 'success' : 'default'"
                :text="getConfig(p.provider)?.enabled ? '已启用' : '未启用'"
              />
            </div>
          </div>

          <a-form layout="vertical" style="margin-top: 16px">
            <a-form-item label="App ID / Client ID">
              <a-input v-model="forms[p.provider].app_id" placeholder="应用 ID" />
            </a-form-item>
            <a-form-item label="App Secret">
              <a-input-password v-model="forms[p.provider].app_secret" placeholder="应用密钥" />
            </a-form-item>
            <a-form-item label="回调地址">
              <a-input v-model="forms[p.provider].redirect_uri" placeholder="https://your-domain/auth/oauth/callback" />
            </a-form-item>
            <a-form-item label="启用">
              <a-switch v-model="forms[p.provider].enabled" />
            </a-form-item>
          </a-form>

          <a-button type="primary" block @click="save(p.provider)" :loading="saving[p.provider]">保存</a-button>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import { adminListSso, adminUpdateSso } from '../../api'
import PageHeader from '../../components/PageHeader.vue'

const providers = [
  { provider: 'dingtalk', label: '钉钉', abbr: 'DD', color: '#1677FF' },
  { provider: 'feishu',   label: '飞书', abbr: 'FS', color: '#3370FF' },
  { provider: 'wecom',    label: '企业微信', abbr: 'WX', color: '#07C160' },
]

const configs = ref<any[]>([])
const saving = reactive<Record<string, boolean>>({})
const forms = reactive<Record<string, any>>({
  dingtalk: { app_id: '', app_secret: '', redirect_uri: '', enabled: false },
  feishu:   { app_id: '', app_secret: '', redirect_uri: '', enabled: false },
  wecom:    { app_id: '', app_secret: '', redirect_uri: '', enabled: false },
})

function getConfig(provider: string) {
  return configs.value.find(c => c.provider === provider)
}

async function loadConfigs() {
  try {
    const res: any = await adminListSso()
    configs.value = res || []
    for (const c of configs.value) {
      if (forms[c.provider]) {
        forms[c.provider].app_id = c.app_id || ''
        forms[c.provider].redirect_uri = c.redirect_uri || ''
        forms[c.provider].enabled = c.enabled || false
        // 不回填 secret
      }
    }
  } catch {}
}

async function save(provider: string) {
  saving[provider] = true
  try {
    const payload: any = { ...forms[provider] }
    if (!payload.app_secret) delete payload.app_secret
    await adminUpdateSso(provider, payload)
    Message.success('已保存')
    loadConfigs()
  } finally {
    saving[provider] = false
  }
}

onMounted(loadConfigs)
</script>

<style scoped>
.admin-page { padding: 0; }
.sso-card { height: 100%; }
.sso-header { display: flex; align-items: center; gap: 12px; }
.sso-logo {
  width: 40px; height: 40px;
  border-radius: 10px;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.sso-name { font-size: 15px; font-weight: 600; color: #1D2129; }
</style>
