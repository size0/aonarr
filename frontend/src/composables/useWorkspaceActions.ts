import type { ComputedRef, Ref } from 'vue'
import { apiRequest, downloadFile, sseUrl } from '../api'
import { createBiblePayload } from '../biblePayload'
import type {
  createDefaultBibleForm,
  createDefaultLLMForm,
  createDefaultProjectForm,
  createDefaultRunForm,
} from '../formDefaults'
import type { ChapterDraft, LLMProfile, Project, PromptTemplate, RunEvent, SerialRun } from '../types'
import { displayRuntimeMode, displayStatus, type PageName } from './useWorkspace'

type LLMForm = ReturnType<typeof createDefaultLLMForm>
type ProjectForm = ReturnType<typeof createDefaultProjectForm>
type BibleForm = ReturnType<typeof createDefaultBibleForm>
type RunForm = ReturnType<typeof createDefaultRunForm>
type DraftStatus = 'accepted' | 'needs_revision' | 'rejected'
type RunControlAction = 'pause' | 'resume' | 'cancel'

type WorkspaceActionsSource = {
  bibleForm: Ref<BibleForm>
  busy: Ref<boolean>
  eventSource: Ref<EventSource | null>
  events: Ref<RunEvent[]>
  llmForm: Ref<LLMForm>
  llmProfiles: Ref<LLMProfile[]>
  loadProjectData: () => Promise<void>
  loadWorkspace: () => Promise<void>
  navigateTo: (page: PageName) => void
  newProjectForm: Ref<ProjectForm>
  runForm: Ref<RunForm>
  selectedProjectId: Ref<string>
  selectedRunId: Ref<string>
  setNotice: (message: string) => void
  showCreateProjectModal: Ref<boolean>
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unexpected error'
}

export function useWorkspaceActions(source: WorkspaceActionsSource) {
  async function createLLMProfile() {
    source.busy.value = true
    try {
      await apiRequest('/api/v1/llm-profiles', {
        method: 'POST',
        body: JSON.stringify(source.llmForm.value),
      })
      source.setNotice('模型配置已创建')
      await source.loadWorkspace()
    } catch (error) {
      source.setNotice(errorMessage(error))
    } finally {
      source.busy.value = false
    }
  }

  async function testLLM(profileId: string) {
    const result = await apiRequest<{
      success: boolean
      error_message?: string | null
      mode?: string
    }>(`/api/v1/llm-profiles/${profileId}/test`, { method: 'POST' })
    const mode = result.mode ? `（${displayRuntimeMode(result.mode)}）` : ''
    source.setNotice(result.success ? `模型测试通过${mode}` : String(result.error_message ?? '模型测试失败'))
    await source.loadWorkspace()
  }

  async function savePromptTemplate(template: PromptTemplate) {
    source.busy.value = true
    try {
      await apiRequest<PromptTemplate>(`/api/v1/prompt-templates/${template.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          name: template.name,
          purpose: template.purpose,
          system_template: template.system_template,
          user_template: template.user_template,
          temperature: Number(template.temperature),
          max_tokens: template.max_tokens === null ? undefined : Number(template.max_tokens),
        }),
      })
      source.setNotice(`提示词模板 ${template.id} 已保存`)
      await source.loadWorkspace()
    } catch (error) {
      source.setNotice(errorMessage(error))
    } finally {
      source.busy.value = false
    }
  }

  async function resetPromptTemplate(templateId: string) {
    source.busy.value = true
    try {
      await apiRequest<PromptTemplate>(`/api/v1/prompt-templates/${templateId}/reset`, { method: 'POST' })
      source.setNotice(`提示词模板 ${templateId} 已重置`)
      await source.loadWorkspace()
    } catch (error) {
      source.setNotice(errorMessage(error))
    } finally {
      source.busy.value = false
    }
  }

  async function setDraftStatus(draft: ChapterDraft, status: DraftStatus) {
    if (!source.selectedProjectId.value) {
      source.setNotice('请先选择作品')
      return
    }
    source.busy.value = true
    try {
      if (status === 'accepted') {
        await apiRequest<ChapterDraft>(`/api/v1/projects/${source.selectedProjectId.value}/drafts/${draft.id}/accept`, {
          method: 'POST',
        })
        source.setNotice('草稿已通过；如果运行仍处于暂停状态，可以继续运行。')
      } else {
        await apiRequest<ChapterDraft>(`/api/v1/projects/${source.selectedProjectId.value}/drafts/${draft.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ status }),
        })
        source.setNotice(`草稿已标记为${displayStatus(status)}`)
      }
      await source.loadProjectData()
    } catch (error) {
      source.setNotice(errorMessage(error))
    } finally {
      source.busy.value = false
    }
  }

  async function createProject() {
    source.busy.value = true
    try {
      const profileId = source.llmProfiles.value[0]?.id ?? null
      const project = await apiRequest<Project>('/api/v1/projects', {
        method: 'POST',
        body: JSON.stringify({ ...source.newProjectForm.value, default_llm_profile_id: profileId }),
      })
      source.selectedProjectId.value = project.id
      source.setNotice('作品已创建')
      source.showCreateProjectModal.value = false
      await source.loadWorkspace()
      source.navigateTo('workbench')
    } catch (error) {
      source.setNotice(errorMessage(error))
    } finally {
      source.busy.value = false
    }
  }

  async function saveBible() {
    if (!source.selectedProjectId.value) {
      source.setNotice('请先选择作品')
      return
    }
    source.busy.value = true
    try {
      await apiRequest(`/api/v1/projects/${source.selectedProjectId.value}/bible`, {
        method: 'PUT',
        body: JSON.stringify(createBiblePayload(source.bibleForm.value)),
      })
      source.setNotice('故事设定已保存')
      await source.loadProjectData()
    } catch (error) {
      source.setNotice(errorMessage(error))
    } finally {
      source.busy.value = false
    }
  }

  async function startRun() {
    if (!source.selectedProjectId.value) {
      source.setNotice('请先选择作品')
      return
    }
    source.busy.value = true
    try {
      const run = await apiRequest<SerialRun>(`/api/v1/projects/${source.selectedProjectId.value}/runs`, {
        method: 'POST',
        body: JSON.stringify({
          mode: 'full_auto',
          start_chapter_number: 1,
          target_chapter_count: source.runForm.value.target_chapter_count,
          cost_limit: source.runForm.value.cost_limit,
        }),
      })
      source.selectedRunId.value = run.id
      source.setNotice('自动连载已启动')
      await source.loadProjectData()
      openEventStream().catch((error) => source.setNotice(errorMessage(error)))
    } catch (error) {
      source.setNotice(errorMessage(error))
    } finally {
      source.busy.value = false
    }
  }

  async function runAction(action: RunControlAction) {
    if (!source.selectedProjectId.value || !source.selectedRunId.value) {
      source.setNotice('请先选择运行任务')
      return
    }
    try {
      await apiRequest(
        `/api/v1/projects/${source.selectedProjectId.value}/runs/${source.selectedRunId.value}/${action}`,
        { method: 'POST' }
      )
      source.setNotice(`已发送${displayStatus(action)}请求`)
      await source.loadProjectData()
      if (action === 'resume') openEventStream().catch((error) => source.setNotice(errorMessage(error)))
    } catch (error) {
      source.setNotice(errorMessage(error))
    }
  }

  async function openEventStream() {
    if (!source.selectedProjectId.value || !source.selectedRunId.value) {
      source.setNotice('请先选择运行任务')
      return
    }
    source.eventSource.value?.close()
    const sseToken = await apiRequest<{ token: string }>('/api/v1/auth/sse-token', { method: 'POST' })
    const eventsPath = [
      `/api/v1/projects/${source.selectedProjectId.value}`,
      `/runs/${source.selectedRunId.value}/events/stream`,
    ].join('')
    const eventSource = new EventSource(sseUrl(eventsPath, sseToken.token))
    eventSource.addEventListener('run_event', (event) => {
      const parsed = JSON.parse((event as MessageEvent).data) as RunEvent
      if (!source.events.value.some((item) => item.id === parsed.id)) {
        source.events.value.push(parsed)
      }
      source.loadProjectData().catch(() => undefined)
    })
    eventSource.onerror = () => {
      eventSource.close()
    }
    source.eventSource.value = eventSource
    source.setNotice('实时日志已连接')
  }

  async function exportMarkdown() {
    if (!source.selectedProjectId.value) {
      source.setNotice('请先选择作品')
      return
    }
    try {
      const item = await apiRequest<{ id: string }>(`/api/v1/projects/${source.selectedProjectId.value}/exports`, {
        method: 'POST',
        body: JSON.stringify({ format: 'markdown' }),
      })
      const blob = await downloadFile(`/api/v1/projects/${source.selectedProjectId.value}/exports/${item.id}/file`)
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank')
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
      source.setNotice('导出任务已创建')
    } catch (error) {
      source.setNotice(errorMessage(error))
    }
  }

  return {
    createLLMProfile,
    createProject,
    exportMarkdown,
    openEventStream,
    resetPromptTemplate,
    runAction,
    saveBible,
    savePromptTemplate,
    setDraftStatus,
    startRun,
    testLLM,
  }
}
