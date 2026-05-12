import apiClient from './client'

/* ── Types ───────────────────────────────────────────────── */

export interface PromptTemplate {
  id: string
  stage: string
  name: string
  content: string
  description: string
  version: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface PromptCreate {
  stage: string
  name: string
  content?: string
  description?: string
  is_active?: boolean
}

export interface PromptUpdate {
  name?: string
  content?: string
  description?: string
  is_active?: boolean
}

export interface StageMeta {
  label: string
  icon: string
  color: string
  bg: string
}

export interface CharacterItem {
  id: string
  novel_id: string
  name: string
  role: string
  description: string
  traits: string[]
  relationships: { target: string; type: string }[]
  first_appearance: number
  created_at: string
}

/* ── Prompts API ─────────────────────────────────────────── */

export const promptsApi = {
  stages: () =>
    apiClient.get<Record<string, StageMeta>>('/prompts/stages').then(r => r.data),

  list: (stage?: string, activeOnly = false) =>
    apiClient.get<PromptTemplate[]>('/prompts', { params: { stage, active_only: activeOnly || undefined } }).then(r => r.data),

  get: (id: string) =>
    apiClient.get<PromptTemplate>(`/prompts/${id}`).then(r => r.data),

  create: (data: PromptCreate) =>
    apiClient.post<PromptTemplate>('/prompts', data).then(r => r.data),

  update: (id: string, data: PromptUpdate) =>
    apiClient.patch<PromptTemplate>(`/prompts/${id}`, data).then(r => r.data),

  delete: (id: string) =>
    apiClient.delete(`/prompts/${id}`).then(r => r.data),

  duplicate: (id: string) =>
    apiClient.post<PromptTemplate>(`/prompts/${id}/duplicate`).then(r => r.data),
}

/* ── Characters API ──────────────────────────────────────── */

export const charactersApi = {
  list: (novelId: string) =>
    apiClient.get<CharacterItem[]>(`/novels/${novelId}/characters`).then(r => r.data),

  get: (novelId: string, charId: string) =>
    apiClient.get<CharacterItem>(`/novels/${novelId}/characters/${charId}`).then(r => r.data),

  create: (novelId: string, data: Omit<CharacterItem, 'id' | 'novel_id' | 'created_at'>) =>
    apiClient.post<CharacterItem>(`/novels/${novelId}/characters`, data).then(r => r.data),

  update: (novelId: string, charId: string, data: Partial<CharacterItem>) =>
    apiClient.patch<CharacterItem>(`/novels/${novelId}/characters/${charId}`, data).then(r => r.data),

  delete: (novelId: string, charId: string) =>
    apiClient.delete(`/novels/${novelId}/characters/${charId}`).then(r => r.data),
}
