export type ApiError = {
  error: {
    code: string
    message: string
    details?: Array<Record<string, unknown>>
  }
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('swe_token') ?? sessionStorage.getItem('swe_token')
  const headers = new Headers(options.headers)

  if (!headers.has('Content-Type') && options.body) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(path, { ...options, headers })
  if (response.status === 204) {
    return undefined as T
  }

  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const message = payload?.error?.message ?? `HTTP ${response.status}`
    throw new Error(message)
  }
  return payload.data as T
}

export async function downloadFile(path: string): Promise<Blob> {
  const token = localStorage.getItem('swe_token') ?? sessionStorage.getItem('swe_token')
  const headers = new Headers()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const response = await fetch(path, { headers })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    const message = payload?.error?.message ?? `HTTP ${response.status}`
    throw new Error(message)
  }
  return response.blob()
}

export function sseUrl(path: string, token: string): string {
  const url = new URL(path, window.location.origin)
  url.searchParams.set('sse_token', token)
  return `${url.pathname}${url.search}`
}
