import apiClient from './client'

export interface NovelDTO {
  id: string
  title: string
  genre: string
  tags: string[]
  synopsis: string
  premise: string
  world_setting: string
  target_word_count: number
  target_chapter_count: number
  words_per_chapter: number
  current_word_count: number
  chapter_count: number
  status: string
  auto_approve_mode: boolean
  created_at: string
  updated_at: string
}

export interface ChapterDTO {
  id: string
  novel_id: string
  number: number
  title: string
  content: string
  summary: string
  word_count: number
  status: string
  tension_score: number
  model_used: string
  created_at: string
  updated_at: string
}

export interface CharacterDTO {
  id: string
  novel_id: string
  name: string
  role: string
  description: string
  traits: string[]
  first_appearance: number
  created_at: string
}

export const novelApi = {
  list: () => apiClient.get<NovelDTO[]>('/novels/').then(r => r.data),
  create: (data: Partial<NovelDTO>) => apiClient.post<NovelDTO>('/novels/', data).then(r => r.data),
  get: (id: string) => apiClient.get<NovelDTO>(`/novels/${id}`).then(r => r.data),
  update: (id: string, data: Partial<NovelDTO>) => apiClient.patch<NovelDTO>(`/novels/${id}`, data).then(r => r.data),
  delete: (id: string) => apiClient.delete(`/novels/${id}`),

  listChapters: (novelId: string) => apiClient.get<ChapterDTO[]>(`/novels/${novelId}/chapters`).then(r => r.data),
  createChapter: (novelId: string, data: Partial<ChapterDTO>) =>
    apiClient.post<ChapterDTO>(`/novels/${novelId}/chapters`, data).then(r => r.data),

  listCharacters: (novelId: string) => apiClient.get<CharacterDTO[]>(`/novels/${novelId}/characters`).then(r => r.data),
}
