import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { authApi } from '../api'
import type { Role, User } from '../types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('stayscape_token') || '')
  const user = ref<User | null>(JSON.parse(localStorage.getItem('stayscape_user') || 'null'))
  const isLoggedIn = computed(() => Boolean(token.value && user.value))
  const role = computed<Role | null>(() => user.value?.role || null)

  async function login(username: string, password: string) {
    const { data } = await authApi.login({ username, password })
    token.value = data.access_token
    user.value = data.user
    localStorage.setItem('stayscape_token', token.value)
    localStorage.setItem('stayscape_user', JSON.stringify(user.value))
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('stayscape_token')
    localStorage.removeItem('stayscape_user')
  }

  return { token, user, role, isLoggedIn, login, logout }
})

