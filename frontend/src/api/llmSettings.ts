import apiClient from './client'

export interface LLMProfile {
  id: string
  name: string
  protocol: string
  base_url: string
  api_key_masked: string
  model: string
  temperature: number
  max_tokens: number
  timeout_seconds: number
  notes: string
}

export interface StageBinding {
  stage: string
  stage_label: string
  profile_id: string
  profile_name: string
  model: string
  preset_name: string
}

export interface StageModelConfig {
  active_preset: string
  profiles: LLMProfile[]
  bindings: StageBinding[]
  available_stages: { stage: string; label: string }[]
}

export const llmApi = {
  getConfig: () => apiClient.get<StageModelConfig>('/settings/llm/config').then(r => r.data),

  createProfile: (data: Record<string, unknown>) =>
    apiClient.post<LLMProfile>('/settings/llm/profiles', data).then(r => r.data),

  updateProfile: (id: string, data: Record<string, unknown>) =>
    apiClient.patch<LLMProfile>(`/settings/llm/profiles/${id}`, data).then(r => r.data),

  deleteProfile: (id: string) => apiClient.delete(`/settings/llm/profiles/${id}`),

  applyPreset: (preset: string) =>
    apiClient.post('/settings/llm/apply-preset', { preset_name: preset }),

  bindStage: (stage: string, profileId: string) =>
    apiClient.post('/settings/llm/bind-stage', { stage, profile_id: profileId }),
}
