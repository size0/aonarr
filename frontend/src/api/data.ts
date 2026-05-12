import apiClient from './client'

/* ── Types ───────────────────────────────────────────────── */

export interface DailyTrend {
  date: string
  reads: number
  favorites: number
  recommends: number
  comments: number
  revenue: number
}

export interface OverviewData {
  period_days: number
  totals: {
    reads: number
    favorites: number
    recommends: number
    comments: number
    revenue: number
  }
  trend: DailyTrend[]
  data_points: number
}

export interface ChapterStat {
  number: number
  title: string
  word_count: number
  cumulative_words: number
  status: string
  tension_score: number
}

export interface ChapterStatsResponse {
  novel_id: string
  novel_title: string
  total_chapters: number
  total_words: number
  chapters: ChapterStat[]
}

export interface NovelSummary {
  id: string
  title: string
  genre: string
  chapter_count: number
  word_count: number
  status: string
  latest_reads: number
  latest_favorites: number
}

export interface EvaluateRequest {
  genre?: string
  synopsis?: string
  first_chapters?: string
  title?: string
  tags?: string[]
}

export interface EvaluateResult {
  method: string
  estimated_daily_reads: string
  follow_rate: string
  signing_probability: string
  genre_heat: string
  overall_score: number
  risk_warnings: string[]
  optimization_suggestions: string[]
  competitive_analysis?: string
  best_publish_time?: string
  model_used?: string
}

/* ── Fanqie Author Stats ─────────────────────────────────── */

export interface FanqieBook {
  book_id: string
  title: string
  cover_url: string
  word_count: number
  read_count: number
  favorite_count: number
  comment_count: number
  chapter_count: number
  creation_status: string
  category: string
  last_chapter_time: string
}

export interface FanqieBookStats {
  ok: boolean
  book_id: string
  stats: {
    book_name: string
    reader_uv_daily: number
    reader_uv_daily_incr: string
    reader_uv_14day: number
    reader_uv_14day_incr: string
    shelf_cnt_daily: number
    shelf_cnt_daily_incr: string
    read_completion_rate: string
    pursue_read_rate: string
    mark_score: string
    mark_score_incr: string
    rank_cat: number
    risk_rate: number
    main_intro: string
    sub_intro: string
  }
}

/* ── Data API ────────────────────────────────────────────── */

export const dataApi = {
  overview: (params?: { novel_id?: string; platform?: string; days?: number }) =>
    apiClient.get<OverviewData>('/data/overview', { params }).then(r => r.data),

  chapterStats: (novelId: string) =>
    apiClient.get<ChapterStatsResponse>('/data/chapter-stats', { params: { novel_id: novelId } }).then(r => r.data),

  history: (novelId: string, platform?: string, limit?: number) =>
    apiClient.get('/data/history', { params: { novel_id: novelId, platform, limit } }).then(r => r.data),

  novelsSummary: () =>
    apiClient.get<NovelSummary[]>('/data/novels-summary').then(r => r.data),

  fanqieBooks: () =>
    apiClient.get<{ ok: boolean; books: FanqieBook[] }>('/data/fanqie-books').then(r => r.data),

  fanqieBookStats: (bookId: string, statsType = 1) =>
    apiClient.get<FanqieBookStats>(`/data/fanqie-book-stats/${bookId}`, { params: { stats_type: statsType } }).then(r => r.data),

  triggerCollect: () =>
    apiClient.post<{ ok: boolean; books_count: number; saved: number }>('/data/trigger-collect').then(r => r.data),

  importCookies: (platform: string, cookieString: string) =>
    apiClient.post<{ ok: boolean; message: string }>('/data/import-cookies', { platform, cookie_string: cookieString }).then(r => r.data),

  cookieStatus: () =>
    apiClient.get<Record<string, { platform: string; ready: boolean; message: string; modified_at: string | null }>>('/data/cookie-status').then(r => r.data),
}

/* ── Prediction API ──────────────────────────────────────── */

export const predictionApi = {
  evaluate: (data: EvaluateRequest) =>
    apiClient.post<EvaluateResult>('/prediction/evaluate', data).then(r => r.data),

  readTrend: (novelId: string, platform?: string, daysAhead?: number) =>
    apiClient.post('/prediction/read-trend', {
      novel_id: novelId,
      platform: platform || 'fanqie',
      days_ahead: daysAhead || 7,
    }).then(r => r.data),
}
