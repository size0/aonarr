import apiClient from './client'

export interface AutopilotStatus {
  novel_id: string
  state: 'idle' | 'running' | 'paused' | 'stopping' | 'completed' | 'failed'
  current_chapter: number
  target_end_chapter: number
  chapters_completed: number
  total_words_written: number
  started_at: string | null
  message: string
  errors: string[]
}

export const creationApi = {
  /** SSE 流式章节写作 — 返回 EventSource URL（由组件自行构建 EventSource） */
  getStreamUrl: (novelId: string, chapterNumber: number) =>
    `/api/v1/creation/${novelId}/chapter/${chapterNumber}/stream`,

  /** 保存章节内容 */
  saveChapter: (novelId: string, chapterId: string, data: { content: string; title?: string }) =>
    apiClient.patch(`/novels/${novelId}/chapters/${chapterId}`, data).then(r => r.data),

  /** 生成宏观大纲 */
  generateOutline: (novelId: string, data: { premise: string; genre?: string; synopsis?: string; target_chapters?: number }) =>
    apiClient.post(`/creation/${novelId}/outline`, data).then(r => r.data),

  /** 生成章节节拍 */
  generateBeats: (novelId: string, chapterNumber: number) =>
    apiClient.post(`/creation/${novelId}/chapter/${chapterNumber}/beats`).then(r => r.data),

  /** 非流式生成章节 */
  generateChapter: (novelId: string, chapterNumber: number, beats?: object[]) =>
    apiClient.post(`/creation/${novelId}/chapter/${chapterNumber}/generate`, { beats }).then(r => r.data),

  /** 触发章后管线 */
  runPostPipeline: (novelId: string, chapterNumber: number) =>
    apiClient.post(`/creation/${novelId}/chapter/${chapterNumber}/post-pipeline`).then(r => r.data),

  /** 全托管 — 启动 */
  autopilotStart: (novelId: string, data: { start_chapter: number; end_chapter: number; auto_beats?: boolean }) =>
    apiClient.post<AutopilotStatus>(`/creation/${novelId}/autopilot/start`, data).then(r => r.data),

  /** 全托管 — 停止 */
  autopilotStop: (novelId: string) =>
    apiClient.post<AutopilotStatus>(`/creation/${novelId}/autopilot/stop`).then(r => r.data),

  /** 全托管 — 暂停 */
  autopilotPause: (novelId: string) =>
    apiClient.post<AutopilotStatus>(`/creation/${novelId}/autopilot/pause`).then(r => r.data),

  /** 全托管 — 恢复 */
  autopilotResume: (novelId: string) =>
    apiClient.post<AutopilotStatus>(`/creation/${novelId}/autopilot/resume`).then(r => r.data),

  /** 全托管 — 查询状态 */
  autopilotStatus: (novelId: string) =>
    apiClient.get<AutopilotStatus>(`/creation/${novelId}/autopilot/status`).then(r => r.data),

  /** 全托管 — SSE 流式输出 URL */
  getAutopilotStreamUrl: (novelId: string) =>
    `/api/v1/creation/${novelId}/autopilot/stream`,
}
