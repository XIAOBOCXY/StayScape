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
        { path: 'products/:id', component: () => import('../views/hotel/ProductDetailView.vue') },
        { path: 'operations', component: () => import('../views/hotel/DynamicOperationsView.vue') },
        { path: 'intents', component: () => import('../views/hotel/IntentView.vue') },
        { path: 'skill-logs', component: () => import('../views/hotel/SkillLogsView.vue') }
      ]
    },
    {
      path: '/merchant', component: () => import('../layouts/AdminLayout.vue'), meta: { role: 'MERCHANT' },
      children: [
        { path: '', redirect: '/merchant/dashboard' },
        { path: 'dashboard', component: () => import('../views/merchant/DashboardView.vue') },
        { path: 'resources', component: () => import('../views/merchant/ResourcesView.vue') }
      ]
    },
    {
      path: '/visitor', component: () => import('../layouts/VisitorLayout.vue'),
      children: [
        { path: '', component: () => import('../views/visitor/HomeView.vue') },
        { path: 'products', component: () => import('../views/visitor/ProductListView.vue') },
        { path: 'products/:id', component: () => import('../views/visitor/ProductDetailView.vue') },
        { path: 'recommend', component: () => import('../views/visitor/RecommendView.vue') }
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
