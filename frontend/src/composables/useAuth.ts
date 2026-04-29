import { computed, ref, type Ref } from 'vue'
import { apiRequest } from '../api'
import type { PageName } from './useWorkspace'

type UseAuthSource = {
  eventSource: Ref<EventSource | null>
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unexpected error'
}

export function useAuth(source: UseAuthSource) {
  let navigateTo: (page: PageName) => void = () => {}
  const token = ref(localStorage.getItem('swe_token') ?? sessionStorage.getItem('swe_token') ?? '')
  const username = ref('admin')
  const password = ref('')
  const notice = ref('就绪')
  const busy = ref(false)
  const remember = ref(true)
  const showDevLoginHint = import.meta.env.DEV
  const canLoginSubmit = computed(() => username.value.trim().length > 0 && password.value.trim().length > 0)

  function setNotice(message: string) {
    notice.value = message
  }

  function fillDevLogin() {
    username.value = 'admin'
    password.value = 'change-me'
  }

  function setNavigator(nextNavigateTo: (page: PageName) => void) {
    navigateTo = nextNavigateTo
  }

  async function login() {
    if (!canLoginSubmit.value) return
    busy.value = true
    try {
      const result = await apiRequest<{ token: string }>('/api/v1/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username: username.value, password: password.value }),
      })
      token.value = result.token
      if (remember.value) {
        localStorage.setItem('swe_token', result.token)
        sessionStorage.removeItem('swe_token')
      } else {
        sessionStorage.setItem('swe_token', result.token)
        localStorage.removeItem('swe_token')
      }
      setNotice('Logged in')
      navigateTo('index')
    } catch (error) {
      setNotice(errorMessage(error))
    } finally {
      busy.value = false
    }
  }

  async function logout() {
    try {
      await apiRequest('/api/v1/auth/logout', { method: 'POST' })
    } catch {
      // Ignore logout failures in local MVP mode.
    }
    source.eventSource.value?.close()
    token.value = ''
    localStorage.removeItem('swe_token')
    sessionStorage.removeItem('swe_token')
    setNotice('Logged out')
    navigateTo('login')
  }

  return {
    busy,
    canLoginSubmit,
    fillDevLogin,
    login,
    logout,
    notice,
    password,
    remember,
    setNavigator,
    setNotice,
    showDevLoginHint,
    token,
    username,
  }
}
