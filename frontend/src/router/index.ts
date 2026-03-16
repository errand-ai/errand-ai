import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import KanbanBoard from '../components/KanbanBoard.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: KanbanBoard,
    },
    {
      path: '/archived',
      name: 'archived',
      component: () => import('../pages/ArchivedTasksPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../pages/LoginPage.vue'),
      meta: { requiresAuth: false },
    },
    {
      path: '/setup',
      name: 'setup',
      component: () => import('../pages/SetupWizard.vue'),
      meta: { requiresAuth: false },
    },
    {
      path: '/settings',
      component: () => import('../pages/SettingsPage.vue'),
      meta: { requiresAdmin: true },
      children: [
        {
          path: '',
          redirect: { name: 'settings-agent' },
        },
        {
          path: 'agent',
          name: 'settings-agent',
          component: () => import('../pages/settings/AgentConfigurationPage.vue'),
        },
        {
          path: 'tasks',
          name: 'settings-tasks',
          component: () => import('../pages/settings/TaskManagementPage.vue'),
        },
        {
          path: 'security',
          name: 'settings-security',
          component: () => import('../pages/settings/SecurityPage.vue'),
        },
        {
          path: 'integrations',
          name: 'settings-integrations',
          component: () => import('../pages/settings/IntegrationsPage.vue'),
        },
        {
          path: 'profiles',
          name: 'settings-profiles',
          component: () => import('../pages/settings/TaskProfilesPage.vue'),
        },
        {
          path: 'cloud',
          name: 'settings-cloud',
          component: () => import('../pages/settings/CloudServicePage.vue'),
        },
        {
          path: 'users',
          name: 'settings-users',
          component: () => import('../pages/settings/UserManagementPage.vue'),
        },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()

  // Public routes that don't need auth
  if (to.name === 'login' || to.name === 'setup') {
    // /login only in local mode
    if (to.name === 'login' && auth.authMode !== 'local') {
      return { name: 'home' }
    }
    // /setup only in setup mode
    if (to.name === 'setup' && auth.authMode !== 'setup') {
      return { name: 'home' }
    }
    return
  }

  if (!auth.isAuthenticated) {
    if (auth.authMode === 'local') return { name: 'login' }
    if (auth.authMode === 'setup') return { name: 'setup' }
    if (auth.authMode === null) return // Still booting — allow navigation, App.vue will redirect after fetching auth status
    return false // SSO handles redirect in App.vue
  }

  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: 'home' }
  }
})

export default router
