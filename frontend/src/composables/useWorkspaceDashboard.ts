import { computed, type ComputedRef, type Ref } from 'vue'
import { BarChartOutline, CashOutline, PencilOutline, StarOutline } from '@vicons/ionicons5'
import type { createDefaultProjectForm } from '../formDefaults'
import type { ChapterDraft, ChapterPlan, Project, PromptTemplate, Readiness, RunEvent, RuntimeSettings, SerialRun } from '../types'
import { displayStatus, displayStorageBackend, type WorkspaceTask, type WorkspaceWork } from './useWorkspace'

type ProjectForm = ReturnType<typeof createDefaultProjectForm>

type WorkspaceDashboardSource = {
  projects: Ref<Project[]>
  runs: Ref<SerialRun[]>
  events: Ref<RunEvent[]>
  plans: Ref<ChapterPlan[]>
  drafts: Ref<ChapterDraft[]>
  promptTemplates: Ref<PromptTemplate[]>
  readiness: Ref<Readiness | null>
  costSummary: Ref<{ estimated_total_cost?: number } | null>
  runtimeSettings: Ref<RuntimeSettings | null>
  selectedProjectId: Ref<string>
  selectedProject: ComputedRef<Project | null>
  selectedRun: ComputedRef<SerialRun | null>
  newProjectForm: Ref<ProjectForm>
  llmModeLabel: ComputedRef<string>
  acceptedDrafts: ComputedRef<ChapterDraft[]>
}

export function useWorkspaceDashboard(source: WorkspaceDashboardSource) {
  const needsRevisionDrafts = computed(() => source.drafts.value.filter((item) => item.status === 'needs_revision'))

  const workspaceMetrics = computed(() => [
    {
      label: '章节草稿',
      value: `${source.drafts.value.length}`,
      delta: `已通过 ${source.acceptedDrafts.value.length} 章`,
      icon: PencilOutline,
      tone: 'purple',
      color: '#6d4df6',
      points: '0,48 24,36 42,31 62,40 82,42 104,26 123,34 142,22 162,20 184,28 205,18 224,28 244,17 260,14',
    },
    {
      label: '章节计划',
      value: `${source.plans.value.length}`,
      delta: `待修订 ${needsRevisionDrafts.value.length} 章`,
      icon: BarChartOutline,
      tone: 'blue',
      color: '#2f7df6',
      points: '0,50 24,35 43,28 64,40 86,38 108,24 126,34 148,20 170,18 190,26 212,16 232,30 248,22 260,21',
    },
    {
      label: '运行任务',
      value: `${source.runs.value.length}`,
      delta: source.selectedRun.value ? `当前 ${displayStatus(source.selectedRun.value.status)}` : '暂无运行',
      icon: StarOutline,
      tone: 'green',
      color: '#11aa7d',
      points: '0,50 24,38 44,31 64,42 86,40 108,25 128,36 148,22 170,20 190,30 212,18 232,28 250,20 260,16',
    },
    {
      label: '估算成本',
      value: `$${source.costSummary.value?.estimated_total_cost ?? 0}`,
      delta: `模型：${source.llmModeLabel.value}`,
      icon: CashOutline,
      tone: 'orange',
      color: '#ff9a2f',
      points: '0,50 22,37 42,43 64,26 84,38 106,25 128,18 150,21 170,32 192,20 212,30 234,18 248,20 260,15',
    },
  ])

  const workspaceWorks = computed<WorkspaceWork[]>(() => {
    if (!source.projects.value.length) {
      return [{
        id: '',
        title: source.newProjectForm.value.title,
        status: '草稿',
        statusType: 'info',
        meta: `${source.newProjectForm.value.genre} · ${source.newProjectForm.value.target_chapter_count} 章目标 · ${source.newProjectForm.value.target_words_per_chapter} 字/章`,
        words: '0',
        reads: '0',
        favorites: '0',
        updated: '未创建',
        cover: source.newProjectForm.value.title.slice(0, 2),
        coverTone: 'dark',
      }]
    }
    return source.projects.value.slice(0, 4).map((project, index) => {
      const isSelected = project.id === source.selectedProjectId.value
      return {
        id: project.id,
        title: project.title,
        status: project.status,
        statusType: project.status === 'active' ? 'success' : 'info',
        meta: `${project.genre} · ${project.target_chapter_count} 章目标 · ${project.target_words_per_chapter} 字/章`,
        words: isSelected ? source.drafts.value.length.toString() : '0',
        reads: isSelected ? source.plans.value.length.toString() : '0',
        favorites: isSelected ? source.acceptedDrafts.value.length.toString() : '0',
        updated: isSelected ? '当前项目' : displayStatus(project.status),
        cover: project.title.slice(0, 2),
        coverTone: index % 3 === 0 ? 'dark' : index % 3 === 1 ? 'rose' : 'steel',
      }
    })
  })

  const workspaceDataSummary = computed(() => [
    { label: '运行事件', value: `${source.events.value.length}`, up: '实时' },
    { label: '提示词模板', value: `${source.promptTemplates.value.length}`, up: '可编辑' },
    { label: '自动修订', value: `${source.runtimeSettings.value?.revision_max_attempts ?? 0}`, up: '轮' },
    { label: '存储后端', value: displayStorageBackend(source.runtimeSettings.value?.storage_backend), up: '就绪' },
  ])

  const workspaceTasks = computed<WorkspaceTask[]>(() => [
    {
      title: source.selectedProject.value ? '项目已选择' : '选择或创建项目',
      progress: source.selectedProject.value ? source.selectedProject.value.title : '需要项目后才能运行',
      badge: source.selectedProject.value ? '已完成' : '待处理',
      type: source.selectedProject.value ? 'success' : 'warning',
      tone: 'purple',
      createProject: !source.selectedProject.value,
      page: source.selectedProject.value ? 'workbench' : undefined,
      mainPanel: 'run',
    },
    {
      title: source.readiness.value?.ready ? '故事设定已就绪' : '完善故事设定',
      progress: source.readiness.value?.ready ? '可开始自动连载' : `${source.readiness.value?.missing.length ?? 0} 项待补全`,
      badge: source.readiness.value?.ready ? '已完成' : '进行中',
      type: source.readiness.value?.ready ? 'success' : 'info',
      tone: 'green',
      page: 'workbench',
      sidePanel: 'bible',
    },
    {
      title: source.selectedRun.value ? '运行任务已创建' : '启动自动连载',
      progress: source.selectedRun.value ? `${source.selectedRun.value.completed_chapter_count}/${source.selectedRun.value.target_chapter_count} 章` : '等待启动',
      badge: source.selectedRun.value ? displayStatus(source.selectedRun.value.status) : '待启动',
      type: source.selectedRun.value ? 'success' : 'warning',
      tone: 'orange',
      page: 'workbench',
      mainPanel: 'run',
    },
  ])

  return {
    workspaceDataSummary,
    workspaceMetrics,
    workspaceTasks,
    workspaceWorks,
  }
}
