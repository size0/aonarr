import apiClient from './client'

export interface Platform {
  id: string
  name: string
  url: string
  login_ready: boolean
  login_status: string
  modified_at: string | null
}

export interface PublishJob {
  id: string
  novel_id: string
  chapter_id: string
  platform: string
  status: string
  scheduled_at: string | null
  published_at: string | null
  retry_count: number
  error_message: string
  created_at: string | null
}

export const publishingApi = {
  listPlatforms: () =>
    apiClient.get<Platform[]>('/publishing/platforms').then(r => r.data),

  getLoginStatus: (platform: string) =>
    apiClient.get(`/publishing/platforms/${platform}/login-status`).then(r => r.data),

  captureLogin: (platform: string, timeout = 300) =>
    apiClient.post(
      `/publishing/platforms/${platform}/capture-login?timeout_seconds=${timeout}`,
      null,
      { timeout: (timeout + 30) * 1000 },
    ).then(r => r.data),

  clearLogin: (platform: string) =>
    apiClient.delete(`/publishing/platforms/${platform}/login`).then(r => r.data),

  listJobs: (params?: { novel_id?: string; platform?: string; status?: string }) =>
    apiClient.get<PublishJob[]>('/publishing/jobs', { params }).then(r => r.data),

  schedule: (data: { novel_id: string; platform: string; chapter_ids?: string[]; scheduled_at?: string }) =>
    apiClient.post('/publishing/schedule', data).then(r => r.data),

  cancelJob: (jobId: string) =>
    apiClient.delete(`/publishing/jobs/${jobId}`).then(r => r.data),

  retryJob: (jobId: string) =>
    apiClient.post(`/publishing/jobs/${jobId}/retry`).then(r => r.data),

  getStats: (novelId: string, platform?: string) =>
    apiClient.get(`/publishing/stats/${novelId}`, { params: { platform } }).then(r => r.data),

  schedulerStatus: () =>
    apiClient.get('/publishing/scheduler/status').then(r => r.data),
}
