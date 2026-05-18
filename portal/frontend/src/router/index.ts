import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('../views/Login.vue'),
    },
    {
      path: '/oauth-callback',
      name: 'OAuthCallback',
      component: () => import('../views/OAuthCallback.vue'),
    },
    {
      path: '/',
      component: () => import('../layouts/BasicLayout.vue'),
      redirect: '/dashboard',
      children: [
        {
          path: 'dashboard',
          name: 'Dashboard',
          component: () => import('../views/Dashboard.vue'),
          meta: { title: '工作台' },
        },
        {
          path: 'datasources',
          name: 'DataSources',
          component: () => import('../views/DataSource.vue'),
          meta: { title: '数据源管理' },
        },
        {
          path: 'sync-tasks',
          redirect: '/sql-dev',
        },
        {
          path: 'sql-dev',
          name: 'SqlDev',
          component: () => import('../views/SqlDev.vue'),
          meta: { title: '组件开发' },
        },
        {
          path: 'workflows/:id/edit',
          name: 'WorkflowEditor',
          component: () => import('../views/WorkflowEditor.vue'),
          meta: { title: '编辑工作流', hideLayout: true },
        },
        {
          path: 'components',
          name: 'Components',
          component: () => import('../views/Component.vue'),
          meta: { title: '组件管理' },
        },
        {
          path: 'workflows',
          name: 'Workflows',
          component: () => import('../views/Workflow.vue'),
          meta: { title: '工作流开发' },
        },
        {
          path: 'scheduler',
          redirect: '/scheduler/history',
        },
        {
          path: 'scheduler/tasks',
          redirect: '/workflows',
        },
        {
          path: 'scheduler/history',
          name: 'RunInstances',
          component: () => import('../views/SchedulerHistory.vue'),
          meta: { title: '运行实例' },
        },
        {
          path: 'alerts',
          name: 'Alerts',
          component: () => import('../views/AlertCenter.vue'),
          meta: { title: '监控规则' },
        },
        {
          path: 'ops/instances/:id',
          name: 'InstanceDetail',
          component: () => import('../views/InstanceDetail.vue'),
          meta: { title: '实例详情' },
        },
        {
          path: 'data-assets',
          name: 'DataAssets',
          component: () => import('../views/DataAssets.vue'),
          meta: { title: '数据目录' },
        },
        {
          path: 'field-assets',
          name: 'FieldAssets',
          component: () => import('../views/FieldAssets.vue'),
          meta: { title: '词根管理' },
        },
        {
          path: 'lineage',
          name: 'DataLineage',
          component: () => import('../views/DataLineage.vue'),
          meta: { title: '数据血缘' },
        },
        {
          path: 'monitor',
          name: 'Monitor',
          component: () => import('../views/Monitor.vue'),
          meta: { title: '系统监控' },
        },
        // 系统管理
        {
          path: 'admin/users',
          name: 'AdminUsers',
          component: () => import('../views/admin/Users.vue'),
          meta: { title: '用户管理', permission: 'user:manage' },
        },
        {
          path: 'admin/roles',
          name: 'AdminRoles',
          component: () => import('../views/admin/Roles.vue'),
          meta: { title: '角色管理', permission: 'role:manage' },
        },
        {
          path: 'admin/sso',
          name: 'AdminSso',
          component: () => import('../views/admin/Sso.vue'),
          meta: { title: 'SSO 配置', permission: 'system:config' },
        },
        {
          path: 'admin/notify',
          name: 'AdminNotify',
          component: () => import('../views/admin/Notify.vue'),
          meta: { title: '通知配置', permission: 'system:config' },
        },
      ],
    },
    {
      path: '/403',
      name: 'Forbidden',
      component: () => import('../views/Forbidden.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'NotFound',
      redirect: '/dashboard',
    },
  ],
})

router.beforeEach(async (to, _from, next) => {
  if (to.path === '/login' || to.path === '/oauth-callback') {
    next()
    return
  }

  const { useUserStore } = await import('../stores/user')
  const store = useUserStore()

  // 未初始化时先拉用户信息（依赖 httponly cookie，axios withCredentials）
  if (!store.userInfo) {
    await store.fetchUser()
  }

  if (!store.isLoggedIn) {
    next('/login')
    return
  }

  const permission = to.meta?.permission as string | undefined
  if (permission && !store.hasPermission(permission)) {
    next('/403')
    return
  }

  next()
})

export default router
