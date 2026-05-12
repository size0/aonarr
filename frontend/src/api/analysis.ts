import apiClient from './client'

export interface AnalysisJob {
  id: string
  novel_title: string
  source_file: string
  status: string  // pending | scanning | extracting | aggregating | done | failed
  progress: number
  chapter_count: number
  result_summary: Record<string, any>
  error_message: string
  created_at: string | null
  finished_at: string | null
}

export interface AnalysisChapter {
  id: string
  job_id: string
  chapter_number: number
  chapter_title: string
  characters: any[]
  events: any[]
  relationships: any[]
  foreshadows: any[]
  summary: string
  word_count: number
}

export const analysisApi = {
  listJobs: () => apiClient.get<AnalysisJob[]>('/analysis/jobs').then(r => r.data),

  getJob: (jobId: string) => apiClient.get<AnalysisJob>(`/analysis/jobs/${jobId}`).then(r => r.data),

  getJobChapters: (jobId: string) =>
    apiClient.get<AnalysisChapter[]>(`/analysis/jobs/${jobId}/chapters`).then(r => r.data),

  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return apiClient.post<AnalysisJob>('/analysis/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    }).then(r => r.data)
  },

  deleteJob: (jobId: string) => apiClient.delete(`/analysis/jobs/${jobId}`),
}
