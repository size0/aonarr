import { computed, ref, type Ref } from 'vue'
import { apiRequest } from '../api'
import type {
  ChapterDraft,
  ChapterPlan,
  LLMProfile,
  Project,
  PromptTemplate,
  Readiness,
  RunEvent,
  RuntimeSettings,
  SerialRun,
} from '../types'
import { displayRuntimeMode } from './useWorkspace'

export function useWorkspaceData(token: Ref<string>) {
  const llmProfiles = ref<LLMProfile[]>([])
  const projects = ref<Project[]>([])
  const runs = ref<SerialRun[]>([])
  const events = ref<RunEvent[]>([])
  const plans = ref<ChapterPlan[]>([])
  const drafts = ref<ChapterDraft[]>([])
  const promptTemplates = ref<PromptTemplate[]>([])
  const readiness = ref<Readiness | null>(null)
  const costSummary = ref<{ estimated_total_cost?: number } | null>(null)
  const runtimeSettings = ref<RuntimeSettings | null>(null)

  const selectedProjectId = ref('')
  const selectedRunId = ref('')

  const selectedProject = computed(() => projects.value.find((item) => item.id === selectedProjectId.value) ?? null)
  const selectedRun = computed(() => runs.value.find((item) => item.id === selectedRunId.value) ?? null)
  const acceptedDrafts = computed(() => drafts.value.filter((item) => item.status === 'accepted'))
  const llmModeLabel = computed(() => displayRuntimeMode(runtimeSettings.value?.llm_mode))

  async function loadEvents() {
    if (!selectedProjectId.value || !selectedRunId.value) {
      events.value = []
      return
    }
    events.value = await apiRequest<RunEvent[]>(
      `/api/v1/projects/${selectedProjectId.value}/runs/${selectedRunId.value}/events`
    )
  }

  async function loadProjectData() {
    if (!selectedProjectId.value) return
    const projectId = selectedProjectId.value
    const [runsResult, plansResult, draftsResult, readinessResult, costResult] = await Promise.all([
      apiRequest<SerialRun[]>(`/api/v1/projects/${projectId}/runs`),
      apiRequest<ChapterPlan[]>(`/api/v1/projects/${projectId}/plans`),
      apiRequest<ChapterDraft[]>(`/api/v1/projects/${projectId}/drafts`),
      apiRequest<Readiness>(`/api/v1/projects/${projectId}/bible/readiness`),
      apiRequest<{ estimated_total_cost?: number }>(`/api/v1/projects/${projectId}/cost-summary`),
    ])
    runs.value = runsResult
    plans.value = plansResult
    drafts.value = draftsResult
    readiness.value = readinessResult
    costSummary.value = costResult
    if (!selectedRunId.value && runsResult.length > 0) {
      selectedRunId.value = runsResult[0].id
    }
    await loadEvents()
  }

  async function loadWorkspace(afterWorkspaceLoaded?: () => void) {
    if (!token.value) return
    const [settingsResult, profilesResult, projectsResult, templatesResult] = await Promise.all([
      apiRequest<RuntimeSettings>('/api/v1/runtime/settings'),
      apiRequest<LLMProfile[]>('/api/v1/llm-profiles'),
      apiRequest<Project[]>('/api/v1/projects'),
      apiRequest<PromptTemplate[]>('/api/v1/prompt-templates'),
    ])
    runtimeSettings.value = settingsResult
    llmProfiles.value = profilesResult
    projects.value = projectsResult
    promptTemplates.value = templatesResult
    if (!selectedProjectId.value && projectsResult.length > 0) {
      selectedProjectId.value = projectsResult[0].id
    }
    afterWorkspaceLoaded?.()
    await loadProjectData()
  }

  return {
    acceptedDrafts,
    costSummary,
    drafts,
    events,
    llmModeLabel,
    llmProfiles,
    loadEvents,
    loadProjectData,
    loadWorkspace,
    plans,
    projects,
    promptTemplates,
    readiness,
    runtimeSettings,
    runs,
    selectedProject,
    selectedProjectId,
    selectedRun,
    selectedRunId,
  }
}
