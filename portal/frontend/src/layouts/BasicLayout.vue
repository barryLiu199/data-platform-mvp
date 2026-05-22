<template>
  <a-layout class="layout">
    <!-- 左侧菜单 -->
    <a-layout-sider
      :collapsed="collapsed"
      :width="220"
      :collapsed-width="64"
      collapsible
      :hide-trigger="false"
      breakpoint="xl"
      @collapse="onCollapse"
      class="layout-sider"
    >
      <!-- Logo -->
      <div class="logo" :class="{ collapsed }" @click="router.push('/dashboard')" style="cursor: pointer;">
        <div class="logo-icon">
          <svg width="28" height="28" viewBox="0 0 36 36" fill="none">
            <defs>
              <linearGradient id="logo-grad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#2B5AED"/>
                <stop offset="100%" stop-color="#00C9A7"/>
              </linearGradient>
            </defs>
            <rect width="36" height="36" rx="8" fill="url(#logo-grad)"/>
            <path d="M9 10h18v2.5H11.5v5h13v2.5h-13v5H27V27.5H9V10z" fill="white"/>
          </svg>
        </div>
        <transition name="fade">
          <span v-if="!collapsed" class="logo-text">数据中台</span>
        </transition>
      </div>

      <!-- 菜单 -->
      <a-menu
        :selected-keys="selectedKeys"
        :default-open-keys="['develop', 'ops', 'assets', 'system']"
        @menu-item-click="onMenuClick"
        class="side-menu"
      >
        <a-menu-item key="/dashboard">
          <template #icon><icon-dashboard /></template>
          工作台
        </a-menu-item>

        <a-sub-menu key="develop">
          <template #icon><icon-code /></template>
          <template #title>数据开发</template>
          <a-menu-item key="/workflows">
            <template #icon><icon-branch /></template>
            工作流开发
          </a-menu-item>
          <a-menu-item key="/sql-dev">
            <template #icon><icon-code-block /></template>
            组件开发
          </a-menu-item>
        </a-sub-menu>

        <a-sub-menu key="ops">
          <template #icon><icon-calendar /></template>
          <template #title>运维中心</template>
          <a-menu-item key="/scheduler/history">
            <template #icon><icon-history /></template>
            运行实例
          </a-menu-item>
          <a-menu-item key="/backfill">
            <template #icon><icon-history /></template>
            补数据
          </a-menu-item>
          <a-menu-item key="/alerts">
            <template #icon><icon-notification /></template>
            监控规则
          </a-menu-item>
        </a-sub-menu>

        <a-sub-menu key="assets">
          <template #icon><icon-file /></template>
          <template #title>数据资产</template>
          <a-menu-item key="/data-assets">
            <template #icon><icon-apps /></template>
            数据目录
          </a-menu-item>
          <a-menu-item key="/field-assets">
            <template #icon><icon-list /></template>
            词根管理
          </a-menu-item>
          <a-menu-item key="/lineage">
            <template #icon><icon-relation /></template>
            数据血缘
          </a-menu-item>
        </a-sub-menu>

        <a-sub-menu key="system">
          <template #icon><icon-settings /></template>
          <template #title>系统管理</template>
          <a-menu-item key="/datasources">
            <template #icon><icon-link /></template>
            数据源管理
          </a-menu-item>
          <a-menu-item key="/monitor">
            <template #icon><icon-computer /></template>
            系统监控
          </a-menu-item>
          <a-menu-item v-if="userStore.hasPermission('user:manage')" key="/admin/users">
            <template #icon><icon-user /></template>
            用户管理
          </a-menu-item>
          <a-menu-item v-if="userStore.hasPermission('role:manage')" key="/admin/roles">
            <template #icon><icon-idcard /></template>
            角色管理
          </a-menu-item>
          <a-menu-item v-if="userStore.hasPermission('system:config')" key="/admin/notify">
            <template #icon><icon-notification /></template>
            通知配置
          </a-menu-item>
          <a-menu-item v-if="userStore.hasPermission('system:config')" key="/admin/sso">
            <template #icon><icon-lock /></template>
            SSO 配置
          </a-menu-item>
        </a-sub-menu>
      </a-menu>

      <!-- 底部用户信息 -->
      <div class="sider-footer" v-if="!collapsed">
        <div class="user-pill">
          <span class="online-dot"></span>
          <span class="user-name">{{ userInfo?.username || 'admin' }}</span>
          <span class="user-role">{{ userInfo?.real_name || '管理员' }}</span>
        </div>
      </div>
    </a-layout-sider>

    <!-- 右侧内容区 -->
    <a-layout>
      <!-- 顶部导航 -->
      <a-layout-header class="layout-header">
        <div class="header-left">
          <a-breadcrumb>
            <a-breadcrumb-item>首页</a-breadcrumb-item>
            <a-breadcrumb-item>{{ currentTitle }}</a-breadcrumb-item>
          </a-breadcrumb>
        </div>
        <div class="header-right">
          <a-space :size="16">
            <a-dropdown trigger="click" @popup-visible-change="onNotifToggle">
              <a-badge :count="unreadCount" dot :offset="[-4, 4]">
                <div class="icon-btn">
                  <icon-notification style="color: #86909C; font-size: 18px;" />
                </div>
              </a-badge>
              <template #content>
                <div class="notif-panel" @click.stop>
                  <div class="notif-header">
                    <span>通知</span>
                    <a-button v-if="unreadCount > 0" type="text" size="mini" @click="markAllRead">全部已读</a-button>
                  </div>
                  <div v-if="notifList.length === 0" class="notif-empty">暂无通知</div>
                  <div v-for="n in notifList" :key="n.id" class="notif-item" :class="{ unread: !n.is_read }" @click="readNotif(n)">
                    <span class="notif-dot" :class="n.type === 'alert' ? 'alert' : 'info'"></span>
                    <div class="notif-body">
                      <div class="notif-title">{{ n.title }}</div>
                      <div class="notif-time">{{ n.created_at }}</div>
                    </div>
                  </div>
                  <div v-if="notifList.length > 0" class="notif-footer" @click="$router.push('/scheduler/history')">查看运行实例</div>
                </div>
              </template>
            </a-dropdown>
            <a-dropdown>
              <div class="user-btn">
                <div class="avatar">A</div>
                <icon-down style="color: #86909C; font-size: 12px;" />
              </div>
              <template #content>
                <a-doption disabled><icon-user /> 个人中心</a-doption>
                <a-doption @click="handleLogout"><icon-export /> 退出登录</a-doption>
              </template>
            </a-dropdown>
          </a-space>
        </div>
      </a-layout-header>

      <!-- 内容 -->
      <a-layout-content class="layout-content">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '../stores/user'
import { getNotifications, markNotifRead, markAllRead as apiMarkAllRead } from '../api'
import {
  IconDashboard, IconLink, IconSync,
  IconCalendar, IconFile, IconApps, IconRelation,
  IconComputer, IconNotification, IconDown, IconUser, IconExport,
  IconSettings, IconHistory, IconCode, IconBranch,
  IconList, IconCodeBlock, IconIdcard, IconLock,
} from '@arco-design/web-vue/es/icon'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const collapsed = ref(false)

const selectedKeys = computed(() => [route.path])
const currentTitle = computed(() => (route.meta?.title as string) || '工作台')
const userInfo = computed(() => userStore.userInfo)

// 通知
const unreadCount = ref(0)
const notifList = ref<any[]>([])

async function loadNotifs() {
  try {
    const res: any = await getNotifications({ pageSize: 5 })
    notifList.value = res?.list || []
    unreadCount.value = res?.unread || 0
  } catch {}
}

function onNotifToggle(visible: boolean) {
  if (visible) loadNotifs()
}

async function readNotif(n: any) {
  if (!n.is_read) {
    await markNotifRead(n.id)
    n.is_read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  }
}

async function markAllRead() {
  await apiMarkAllRead()
  notifList.value.forEach(n => n.is_read = true)
  unreadCount.value = 0
}

function onCollapse(val: boolean) { collapsed.value = val }
function onMenuClick(key: string) { router.push(key) }
function handleLogout() { userStore.logout(); router.push('/login') }

onMounted(() => {
  userStore.fetchUser()
  loadNotifs()
})
</script>

<style scoped>
.layout { height: 100vh; background: #F5F7FA; }

/* 侧边栏 */
.layout-sider {
  background: #FFFFFF !important;
  border-right: 1px solid #E5E8ED;
  z-index: 10;
  display: flex;
  flex-direction: column;
}

.logo {
  height: 56px;
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 10px;
  border-bottom: 1px solid #E5E8ED;
  flex-shrink: 0;
}
.logo.collapsed { justify-content: center; padding: 0; }
.logo-text {
  color: #1D2129;
  font-size: 15px;
  font-weight: 600;
  white-space: nowrap;
  letter-spacing: 1px;
}

.side-menu { background: transparent !important; border: none !important; flex: 1; overflow-y: auto; }

/* 底部用户 */
.sider-footer {
  padding: 12px 16px;
  border-top: 1px solid #E5E8ED;
  flex-shrink: 0;
}
.user-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #F7F8FA;
}
.online-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #00B42A;
  flex-shrink: 0;
}
.user-name { color: #1D2129; font-size: 13px; font-weight: 500; }
.user-role { color: #86909C; font-size: 12px; margin-left: auto; }

/* 顶部导航 */
.layout-header {
  background: #FFFFFF !important;
  border-bottom: 1px solid #E5E8ED;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  line-height: 56px;
  z-index: 9;
}

.header-left, .header-right { display: flex; align-items: center; }

.icon-btn {
  width: 32px; height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}
.icon-btn:hover { background: #F7F8FA; }

.user-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 8px;
  transition: background 0.15s;
}
.user-btn:hover { background: #F7F8FA; }
.avatar {
  width: 28px; height: 28px;
  border-radius: 50%;
  background: linear-gradient(135deg, #2B5AED, #00C9A7);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 内容区 */
.layout-content {
  padding: 20px;
  background: #F5F7FA;
  overflow-y: auto;
  min-height: 0;
}

/* 菜单浅色覆盖 */
:deep(.arco-menu-item),
:deep(.arco-menu-inline-header) { color: #4E5969 !important; }
:deep(.arco-menu-item:hover),
:deep(.arco-menu-inline-header:hover) { color: #2B5AED !important; background: #F2F3F5 !important; }
:deep(.arco-menu-item.arco-menu-selected) {
  color: #2B5AED !important;
  background: #EFF4FF !important;
}
:deep(.arco-menu-item.arco-menu-selected::before) {
  background: #2B5AED !important;
  width: 3px !important;
}
:deep(.arco-menu-icon) { color: inherit !important; }

/* 折叠按钮 */
:deep(.arco-layout-sider-trigger) {
  background: #FFFFFF !important;
  border-top: 1px solid #E5E8ED;
  color: #86909C !important;
}

/* 通知面板 */
.notif-panel { width: 320px; padding: 8px 0; }
.notif-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 16px; font-size: 14px; font-weight: 600; color: #1D2129; }
.notif-empty { padding: 24px 16px; text-align: center; color: #86909C; font-size: 13px; }
.notif-item { display: flex; gap: 10px; padding: 10px 16px; cursor: pointer; transition: background 0.15s; }
.notif-item:hover { background: #F7F8FA; }
.notif-item.unread { background: #FAFBFC; }
.notif-dot { width: 6px; height: 6px; border-radius: 50%; margin-top: 6px; flex-shrink: 0; }
.notif-dot.alert { background: #F53F3F; }
.notif-dot.info { background: #00B42A; }
.notif-body { flex: 1; min-width: 0; }
.notif-title { font-size: 13px; color: #1D2129; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.notif-time { font-size: 11px; color: #C9CDD4; margin-top: 2px; }
.notif-footer { padding: 8px 16px; text-align: center; font-size: 12px; color: #2B5AED; cursor: pointer; border-top: 1px solid #E5E8ED; }

/* fade transition */
.fade-enter-active { transition: opacity 0.2s; }
.fade-leave-active { transition: opacity 0.1s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* page transition */
.page-enter-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.page-leave-active { transition: opacity 0.1s ease, transform 0.1s ease; }
.page-enter-from { opacity: 0; transform: translateY(6px); }
.page-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
