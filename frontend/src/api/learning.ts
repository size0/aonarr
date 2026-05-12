import apiClient from './client'

/* ── Types ───────────────────────────────────────────────── */

export interface LearningStats {
  knowledge_count: number
  hot_novel_count: number
  chapter_count: number
  opt_log_count: number
  crawling_count: number
  done_count: number
  last_crawl_at: string | null
}

export interface KnowledgeEntry {
  id: string
  category: string
  title: string
  content: Record<string, any>
  source_novel_id: string | null
  source_file: string
  tags: string[]
  quality_score: number
  created_at: string | null
  expires_at?: string | null
}

export interface TutorialScanResult {
  total: number
  by_category: Record<string, number>
  files: { path: string; relative: string; name: string; ext: string; size: number; category: string; folder: string }[]
}

export interface TutorialImportResult {
  status: string
  message: string
}

export interface HotNovel {
  id: string
  platform: string
  source_book_id: string
  title: string
  author: string
  genre: string
  tags: string[]
  word_count: number
  chapter_count: number
  rating: number
  synopsis: string
  cover_url: string
  rank_info: Record<string, any>
  source_url: string
  status: string   // meta | crawling | done | failed
  crawled_at: string | null
}

export interface HotNovelChapter {
  id: string
  chapter_number: number
  title: string
  word_count: number
}

export interface ChapterContent extends HotNovelChapter {
  content: string
}

export interface OptimizationLog {
  id: string
  target: string
  description: string
  before_snapshot: Record<string, any>
  after_snapshot: Record<string, any>
  improvement_score: number
  applied: boolean
  created_at: string | null
}

export interface TriggerResult {
  status: string
  message: string
}

/* ── API ─────────────────────────────────────────────────── */

export const learningApi = {
  /* 统计 */
  getStats: () =>
    apiClient.get<LearningStats>('/learning/stats').then(r => r.data),

  /* 知识库 */
  listKnowledge: (category?: string, limit = 50) =>
    apiClient.get<KnowledgeEntry[]>('/learning/knowledge', { params: { category, limit } }).then(r => r.data),

  getKnowledge: (id: string) =>
    apiClient.get<KnowledgeEntry>(`/learning/knowledge/${id}`).then(r => r.data),

  deleteKnowledge: (id: string) =>
    apiClient.delete(`/learning/knowledge/${id}`).then(r => r.data),

  /* 热门小说 */
  listHotNovels: (platform?: string, limit = 50) =>
    apiClient.get<HotNovel[]>('/learning/hot-novels', { params: { platform, limit } }).then(r => r.data),

  listNovelChapters: (novelId: string) =>
    apiClient.get<HotNovelChapter[]>(`/learning/hot-novels/${novelId}/chapters`).then(r => r.data),

  getChapterContent: (novelId: string, chapterId: string) =>
    apiClient.get<ChapterContent>(`/learning/hot-novels/${novelId}/chapters/${chapterId}`).then(r => r.data),

  /* 优化日志 */
  listOptLogs: (limit = 30) =>
    apiClient.get<OptimizationLog[]>('/learning/optimization-logs', { params: { limit } }).then(r => r.data),

  applyOptLog: (logId: string) =>
    apiClient.post<{ ok: boolean; log_id: string }>(`/learning/optimization-logs/${logId}/apply`).then(r => r.data),

  /* 手动触发 */
  triggerCrawl: () =>
    apiClient.post<TriggerResult>('/learning/trigger-crawl').then(r => r.data),

  triggerLearn: () =>
    apiClient.post<TriggerResult>('/learning/trigger-learn').then(r => r.data),

  triggerOptimize: () =>
    apiClient.post<TriggerResult>('/learning/trigger-optimize').then(r => r.data),

  triggerCoverDownload: () =>
    apiClient.post<TriggerResult>('/learning/trigger-cover-download').then(r => r.data),

  /* 教程导入 */
  scanTutorials: (baseDir: string) =>
    apiClient.post<TutorialScanResult>('/learning/tutorial/scan', null, { params: { base_dir: baseDir } }).then(r => r.data),

  importTutorials: (baseDir: string, useLlm = true, maxFiles = 100) =>
    apiClient.post<TutorialImportResult>('/learning/tutorial/import', null, { params: { base_dir: baseDir, use_llm: useLlm, max_files: maxFiles } }).then(r => r.data),

  importSingleTutorial: (filePath: string, category?: string, useLlm = true) =>
    apiClient.post('/learning/tutorial/import-file', null, { params: { file_path: filePath, category, use_llm: useLlm } }).then(r => r.data),

  getActivityLog: (since = 0) =>
    apiClient.get<{ total: number; logs: { ts: string; level: string; msg: string }[] }>('/learning/activity-log', { params: { since } }).then(r => r.data),

  /* 番茄登录状态（复用发布中心） */
  fanqieLoginStatus: () =>
    apiClient.get<{ logged_in: boolean; cookie_count?: number; msg: string }>('/learning/fanqie/login-status').then(r => r.data),
}
