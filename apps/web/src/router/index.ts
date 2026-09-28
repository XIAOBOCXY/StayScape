import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/visitor' },
    { path: '/login', component: () => import('../views/LoginView.vue') },
    {
      path: '/hotel', component: () => import('../layouts/AdminLayout.vue'), meta: { role: 'HOTEL' },
      children: [
        { path: '', redirect: '/hotel/dashboard' },
        { path: 'dashboard', component: () => import('../views/hotel/DashboardView.vue') },
        { path: 'rooms', component: () => import('../views/hotel/RoomsView.vue') },
        { path: 'services', component: () => import('../views/hotel/ServicesView.vue') },
        { path: 'resources', component: () => import('../views/hotel/ResourcesView.vue') },
        { path: 'products', component: () => import('../views/hotel/ProductPoolView.vue') },
        { path: 'products/generate', component: () => import('../views/hotel/ProductGeneratorView.vue') },
        { path: 'knowledge', component: () => import('../views/hotel/KnowledgeView.vue') },
        { path: 'settings', component: () => import('../views/hotel/SettingsView.vue') },
        { path: 'agent-access', component: () => import('../views/hotel/AgentAccessView.vue') },
        // The one-sentence generator now lives inside 生成产品; keep the old
        // URL working for bookmarks and the Feishu entry point.
        { path: 'ai-operations', redirect: '/hotel/products/generate' },
        { path: 'products/:id', component: () => import('../views/hotel/ProductDetailView.vue') },
        { path: 'operations', component: () => import('../views/hotel/DynamicOperationsView.vue') },
        { path: 'intents', component: () => import('../views/hotel/IntentView.vue') },
        { path: 'skill-logs', component: () => import('../views/hotel/SkillLogsView.vue') }
      ]
    },
    {
      // The partner console was folded into the hotel workbench: resources are
      // created, priced and packaged from 合作资源池, so these URLs redirect.
      path: '/merchant',
      redirect: '/hotel/resources',
      children: []
    },
    {
      path: '/visitor', component: () => import('../layouts/VisitorLayout.vue'),
      children: [
        // One storefront page: the list already carries the search, topics and
        // filters, so the separate home page was removed.
        { path: '', redirect: '/visitor/products' },
        // Keep the retired recommendation bookmark working instead of rendering a blank route.
        { path: 'recommend', redirect: '/visitor/products' },
        { path: 'products', component: () => import('../views/visitor/ProductListView.vue') },
        { path: 'assistant', component: () => import('../views/visitor/AssistantView.vue') },
        { path: 'products/:id', component: () => import('../views/visitor/ProductDetailView.vue') }
      ]
    }
  ]
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  const requiredRole = to.matched.find((record) => record.meta.role)?.meta.role as string | undefined
  if (requiredRole && (!auth.isLoggedIn || auth.role !== requiredRole)) return { path: '/login', query: { redirect: to.fullPath } }
  return true
})

export default router
