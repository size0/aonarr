export type LLMProfile = {
  id: string
  name: string
  provider_type: string
  base_url: string
  model: string
  secret_ref: string | null
  status: string
}

export type Project = {
  id: string
  title: string
  genre: string
  target_chapter_count: number
  target_words_per_chapter: number
  style_goal: string
  default_llm_profile_id: string | null
  status: string
}

export type SerialRun = {
  id: string
  project_id: string
  status: string
  mode: string
  start_chapter_number: number
  target_chapter_count: number
  completed_chapter_count: number
  estimated_cost: number
  failure_code: string | null
  failure_message: string | null
}

export type RunEvent = {
  id: string
  serial_run_id: string
  project_id: string
  level: string
  event_type: string
  message: string
  step?: string
  chapter_number?: number
  token_input?: number
  token_output?: number
  quality_score?: number | null
  estimated_cost?: number
  created_at: string
}

export type ChapterPlan = {
  id: string
  chapter_number: number
  title_hint: string
  goal: string
  conflict: string
  hook: string
  status: string
}

export type ChapterDraft = {
  id: string
  chapter_number: number
  title: string
  body: string
  word_count: number
  version: number
  status: string
  quality_score?: number
  review_summary?: string
}

export type Readiness = {
  ready: boolean
  missing: Array<{ section: string; message: string }>
}

export type RuntimeSettings = {
  llm_mode: 'mock' | 'live' | string
  revision_max_attempts: number
  storage_backend: 'json' | 'postgres' | string
}

export type PromptTemplate = {
  id: string
  name: string
  purpose: string
  system_template: string
  user_template: string
  temperature: number
  max_tokens: number | null
  required_variables: string[]
  is_default: boolean
}
