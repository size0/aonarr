<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { NButton, NCheckbox, NForm, NFormItem, NIcon, NInput, NTag } from 'naive-ui'
import {
  AddOutline,
  ArrowBackOutline,
  ArrowForwardOutline,
  BarChartOutline,
  BookOutline,
  BulbOutline,
  CashOutline,
  CheckboxOutline,
  CheckmarkDoneOutline,
  ChevronBackOutline,
  ChatbubbleEllipsesOutline,
  ChevronDownOutline,
  ChevronForwardOutline,
  CreateOutline,
  DocumentTextOutline,
  EyeOffOutline,
  EyeOutline,
  FolderOpenOutline,
  GlobeOutline,
  HeartOutline,
  HelpCircleOutline,
  HomeOutline,
  ImageOutline,
  LibraryOutline,
  ListOutline,
  LockClosedOutline,
  LogoWechat,
  MailOutline,
  MenuOutline,
  MoonOutline,
  NotificationsOutline,
  PaperPlaneOutline,
  PeopleOutline,
  PhonePortraitOutline,
  PencilOutline,
  ReaderOutline,
  SearchOutline,
  SettingsOutline,
  SparklesOutline,
  StarOutline,
  StatsChartOutline,
} from '@vicons/ionicons5'
import { apiRequest, downloadFile, sseUrl } from './api'
import {
  displayEventType,
  displayProfileName,
  displayProviderType,
  displayReadinessSection,
  displayRuntimeMode,
  displayStatus,
  displayStorageBackend,
  pageFromPath,
  requiresAuth,
  type PageName,
  type SettingsPanel,
  type WorkbenchMainPanel,
  type WorkbenchSidePanel,
  type WorkspaceNavItem,
  type WorkspaceTask,
  type WorkspaceWork,
} from './composables/useWorkspace'
import type { ChapterDraft, ChapterPlan, LLMProfile, Project, PromptTemplate, Readiness, RunEvent, RuntimeSettings, SerialRun } from './types'

const token = ref(localStorage.getItem('swe_token') ?? sessionStorage.getItem('swe_token') ?? '')
const username = ref('admin')
const password = ref('change-me')
const notice = ref('就绪')
const busy = ref(false)
const remember = ref(true)

const currentPage = ref<PageName>(pageFromPath(window.location.pathname))

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
const eventSource = ref<EventSource | null>(null)
const showCreateProjectModal = ref(false)
const workbenchMainPanel = ref<WorkbenchMainPanel>('run')
const workbenchSidePanel = ref<WorkbenchSidePanel>('bible')
const settingsPanel = ref<SettingsPanel>('llm')

const llmForm = ref({
  name: '本地 OpenAI 兼容模型',
  provider_type: 'openai_compatible',
  base_url: 'http://localhost:11434/v1',
  model: 'demo-model',
  api_key: 'demo-key',
})

const newProjectForm = ref({
  title: '长夜星火',
  genre: '玄幻',
  target_chapter_count: 120,
  target_words_per_chapter: 3000,
  style_goal: '节奏紧凑，冲突清晰，章末有钩子',
})

const projectForm = ref({ ...newProjectForm.value })

const bibleForm = ref({
  premise: '灵气衰退的时代，少年在废弃宗门中发现旧纪元传承。',
  world_summary: '宗门衰败，诸城割据，灵脉成为各方争夺的核心。',
  tone_profile: '第三人称，冷静克制，少解释，多行动。',
})

const runForm = ref({
  target_chapter_count: 3,
  cost_limit: 1,
})

const selectedProject = computed(() => projects.value.find((item) => item.id === selectedProjectId.value) ?? null)
const selectedRun = computed(() => runs.value.find((item) => item.id === selectedRunId.value) ?? null)
const acceptedDrafts = computed(() => drafts.value.filter((item) => item.status === 'accepted'))
const needsRevisionDrafts = computed(() => drafts.value.filter((item) => item.status === 'needs_revision'))
const llmModeLabel = computed(() => displayRuntimeMode(runtimeSettings.value?.llm_mode))
const canLoginSubmit = computed(() => username.value.trim().length > 0 && password.value.trim().length > 0)

const loginFeatures = [
  { title: '自动连载', desc: '规划、起草、审阅和修订串成稳定生产线。', icon: CreateOutline },
  { title: '作品资料库', desc: '项目设定、故事设定、提示词模板集中管理。', icon: FolderOpenOutline },
  { title: '运行监控', desc: '实时日志、成本估算和质量门状态实时可见。', icon: StatsChartOutline },
]

const studioSideNav = [
  { label: '概览', icon: HomeOutline, active: false },
  { label: '作品', icon: BookOutline, active: true },
  { label: '章节', icon: DocumentTextOutline, active: false },
  { label: '角色', icon: PeopleOutline, active: false },
  { label: '世界观', icon: GlobeOutline, active: false },
  { label: '资料库', icon: LibraryOutline, active: false },
  { label: '统计', icon: StatsChartOutline, active: false },
  { label: '设置', icon: SettingsOutline, active: false },
]

const studioOutlines = [
  { title: '第一卷：启程', done: 12, total: 20 },
  { title: '第二卷：迷雾之地', done: 8, total: 20 },
  { title: '第三卷：命运的交汇', done: 0, total: 20 },
]

const studioCharacters = [
  { name: '艾琳·星语', role: '女主角', short: '艾', tone: 'silver' },
  { name: '洛恩·夜影', role: '男主角', short: '洛', tone: 'blue' },
  { name: '凯瑟琳', role: '重要配角', short: '凯', tone: 'pink' },
  { name: '卡斯塔', role: '反派角色', short: '卡', tone: 'dark' },
]

const studioChartBars = [
  { day: '5.12', value: 22 },
  { day: '5.13', value: 38 },
  { day: '5.14', value: 56 },
  { day: '5.15', value: 42 },
  { day: '5.16', value: 66 },
  { day: '5.17', value: 90 },
  { day: '5.18', value: 76 },
]

const studioFeatures = [
  { title: '灵感管理', desc: '随时记录灵感，建立灵感库，让每一个想法都不被错过。', icon: BulbOutline },
  { title: '大纲与章节', desc: '可视化大纲结构，灵活管理章节，让故事脉络清晰可见。', icon: DocumentTextOutline },
  { title: '角色与设定', desc: '详细的角色档案与关系设定，让人物真正立在纸上。', icon: PeopleOutline },
  { title: '世界观构建', desc: '自定义世界设定、历史背景、地理文化等元素，一处管理。', icon: GlobeOutline },
]

const workspaceNavItems: WorkspaceNavItem[] = [
  { label: '工作台', icon: HomeOutline, page: 'index' },
  { label: '作品管理', icon: DocumentTextOutline, page: 'index' },
  { label: '章节管理', icon: ReaderOutline, page: 'workbench', mainPanel: 'drafts' },
  { label: '人物管理', icon: PeopleOutline, page: 'workbench', sidePanel: 'project' },
  { label: '大纲管理', icon: ListOutline, page: 'workbench', mainPanel: 'plans' },
  { label: '世界观设定', icon: GlobeOutline, page: 'workbench', sidePanel: 'bible' },
  { label: '素材库', icon: ImageOutline, page: 'workbench', sidePanel: 'project' },
  { label: '数据统计', icon: StatsChartOutline, page: 'index' },
  { label: '粉丝互动', icon: HeartOutline, page: 'index' },
  { label: '成本管理', icon: CashOutline, page: 'workbench', mainPanel: 'run' },
  { label: '运行日志', icon: MailOutline, page: 'workbench', badge: '实时', mainPanel: 'events' },
  { label: '任务中心', icon: CheckboxOutline, page: 'index', badge: '3' },
  { label: '设置', icon: SettingsOutline, page: 'settings', settingsPanel: 'llm' },
]

const weekDays = ['一', '二', '三', '四', '五', '六', '日']
const calendarDays = [
  ...['29', '30'].map((label) => ({ label, muted: true, marked: false, active: false })),
  ...Array.from({ length: 31 }, (_, index) => ({
    label: String(index + 1),
    muted: false,
    marked: index + 1 <= 23,
    active: index + 1 === 20,
  })),
  ...['1', '2'].map((label) => ({ label, muted: true, marked: false, active: false })),
]
const chartLines = [42, 82, 122, 162, 202]

const workspaceMetrics = computed(() => [
  {
    label: '章节草稿',
    value: `${drafts.value.length}`,
    delta: `已通过 ${acceptedDrafts.value.length} 章`,
    icon: PencilOutline,
    tone: 'purple',
    color: '#6d4df6',
    points: '0,48 24,36 42,31 62,40 82,42 104,26 123,34 142,22 162,20 184,28 205,18 224,28 244,17 260,14',
  },
  {
    label: '章节计划',
    value: `${plans.value.length}`,
    delta: `待修订 ${needsRevisionDrafts.value.length} 章`,
    icon: BarChartOutline,
    tone: 'blue',
    color: '#2f7df6',
    points: '0,50 24,35 43,28 64,40 86,38 108,24 126,34 148,20 170,18 190,26 212,16 232,30 248,22 260,21',
  },
  {
    label: '运行任务',
    value: `${runs.value.length}`,
    delta: selectedRun.value ? `当前 ${displayStatus(selectedRun.value.status)}` : '暂无运行',
    icon: StarOutline,
    tone: 'green',
    color: '#11aa7d',
    points: '0,50 24,38 44,31 64,42 86,40 108,25 128,36 148,22 170,20 190,30 212,18 232,28 250,20 260,16',
  },
  {
    label: '估算成本',
    value: `$${costSummary.value?.estimated_total_cost ?? 0}`,
    delta: `模型：${llmModeLabel.value}`,
    icon: CashOutline,
    tone: 'orange',
    color: '#ff9a2f',
    points: '0,50 22,37 42,43 64,26 84,38 106,25 128,18 150,21 170,32 192,20 212,30 234,18 248,20 260,15',
  },
])

const workspaceWorks = computed<WorkspaceWork[]>(() => {
  if (!projects.value.length) {
    return [{
      id: '',
      title: newProjectForm.value.title,
      status: '草稿',
      statusType: 'info',
      meta: `${newProjectForm.value.genre} · ${newProjectForm.value.target_chapter_count} 章目标 · ${newProjectForm.value.target_words_per_chapter} 字/章`,
      words: '0',
      reads: '0',
      favorites: '0',
      updated: '未创建',
      cover: newProjectForm.value.title.slice(0, 2),
      coverTone: 'dark',
    }]
  }
  return projects.value.slice(0, 4).map((project, index) => {
    const isSelected = project.id === selectedProjectId.value
    return {
      id: project.id,
      title: project.title,
      status: project.status,
      statusType: project.status === 'active' ? 'success' : 'info',
      meta: `${project.genre} · ${project.target_chapter_count} 章目标 · ${project.target_words_per_chapter} 字/章`,
      words: isSelected ? drafts.value.length.toString() : '0',
      reads: isSelected ? plans.value.length.toString() : '0',
      favorites: isSelected ? acceptedDrafts.value.length.toString() : '0',
      updated: isSelected ? '当前项目' : displayStatus(project.status),
      cover: project.title.slice(0, 2),
      coverTone: index % 3 === 0 ? 'dark' : index % 3 === 1 ? 'rose' : 'steel',
    }
  })
})

const workspaceDataSummary = computed(() => [
  { label: '运行事件', value: `${events.value.length}`, up: '实时' },
  { label: '提示词模板', value: `${promptTemplates.value.length}`, up: '可编辑' },
  { label: '自动修订', value: `${runtimeSettings.value?.revision_max_attempts ?? 0}`, up: '轮' },
  { label: '存储后端', value: displayStorageBackend(runtimeSettings.value?.storage_backend), up: '就绪' },
])

const workspaceTasks = computed<WorkspaceTask[]>(() => [
  {
    title: selectedProject.value ? '项目已选择' : '选择或创建项目',
    progress: selectedProject.value ? selectedProject.value.title : '需要项目后才能运行',
    badge: selectedProject.value ? '已完成' : '待处理',
    type: (selectedProject.value ? 'success' : 'warning') as 'success' | 'warning',
    tone: 'purple',
    createProject: !selectedProject.value,
    page: selectedProject.value ? 'workbench' : undefined,
    mainPanel: 'run',
  },
  {
    title: readiness.value?.ready ? '故事设定已就绪' : '完善故事设定',
    progress: readiness.value?.ready ? '可开始自动连载' : `${readiness.value?.missing.length ?? 0} 项待补全`,
    badge: readiness.value?.ready ? '已完成' : '进行中',
    type: (readiness.value?.ready ? 'success' : 'info') as 'success' | 'info',
    tone: 'green',
    page: 'workbench',
    sidePanel: 'bible',
  },
  {
    title: selectedRun.value ? '运行任务已创建' : '启动自动连载',
    progress: selectedRun.value ? `${selectedRun.value.completed_chapter_count}/${selectedRun.value.target_chapter_count} 章` : '等待启动',
    badge: selectedRun.value ? displayStatus(selectedRun.value.status) : '待启动',
    type: (selectedRun.value ? 'success' : 'warning') as 'success' | 'warning',
    tone: 'orange',
    page: 'workbench',
    mainPanel: 'run',
  },
])

function setNotice(message: string) {
  notice.value = message
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unexpected error'
}

function navigateTo(page: PageName) {
  currentPage.value = page
  const path = page === 'studio' ? '/studio' : `/${page}`
  if (window.location.pathname !== path) {
    window.history.pushState({}, '', path)
  }
  if (requiresAuth(page) && token.value) {
    loadWorkspace().catch((error) => setNotice(errorMessage(error)))
  }
}

function syncPageFromHistory() {
  currentPage.value = pageFromPath(window.location.pathname)
  if (requiresAuth(currentPage.value) && !token.value) {
    navigateTo('login')
  }
  if (requiresAuth(currentPage.value) && token.value) {
    loadWorkspace().catch((error) => setNotice(errorMessage(error)))
  }
}

function isWorkspaceNavActive(item: WorkspaceNavItem) {
  if (item.page !== currentPage.value) return false
  if (item.mainPanel && item.mainPanel !== workbenchMainPanel.value) return false
  if (item.sidePanel && item.sidePanel !== workbenchSidePanel.value) return false
  if (item.settingsPanel && item.settingsPanel !== settingsPanel.value) return false
  return true
}

function handleWorkspaceNav(item: WorkspaceNavItem) {
  if (item.mainPanel) {
    workbenchMainPanel.value = item.mainPanel
  }
  if (item.sidePanel) {
    workbenchSidePanel.value = item.sidePanel
  }
  if (item.settingsPanel) {
    settingsPanel.value = item.settingsPanel
  }
  navigateTo(item.page)
}

function syncProjectFormFromSelectedProject() {
  if (!selectedProject.value) return
  projectForm.value = {
    title: selectedProject.value.title,
    genre: selectedProject.value.genre,
    target_chapter_count: selectedProject.value.target_chapter_count,
    target_words_per_chapter: selectedProject.value.target_words_per_chapter,
    style_goal: selectedProject.value.style_goal,
  }
}

function handleWorkspaceTask(task: WorkspaceTask) {
  if (task.createProject || (task.page === 'workbench' && !selectedProject.value)) {
    showCreateProjectModal.value = true
    return
  }
  if (task.mainPanel) {
    workbenchMainPanel.value = task.mainPanel
  }
  if (task.sidePanel) {
    workbenchSidePanel.value = task.sidePanel
  }
  if (task.page) {
    navigateTo(task.page)
  }
}

function handleProjectSelection() {
  syncProjectFormFromSelectedProject()
  loadProjectData().catch((error) => setNotice(errorMessage(error)))
}

function selectWorkspaceProject(projectId: string) {
  if (!projectId) {
    showCreateProjectModal.value = true
    return
  }
  selectedProjectId.value = projectId
  syncProjectFormFromSelectedProject()
  workbenchMainPanel.value = 'run'
  navigateTo('workbench')
}

async function login() {
  if (!canLoginSubmit.value) return
  busy.value = true
  try {
    const result = await apiRequest<{ token: string }>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username: username.value, password: password.value }),
    })
    token.value = result.token
    if (remember.value) {
      localStorage.setItem('swe_token', result.token)
      sessionStorage.removeItem('swe_token')
    } else {
      sessionStorage.setItem('swe_token', result.token)
      localStorage.removeItem('swe_token')
    }
    setNotice('Logged in')
    navigateTo('index')
  } catch (error) {
    setNotice(errorMessage(error))
  } finally {
    busy.value = false
  }
}

async function logout() {
  try {
    await apiRequest('/api/v1/auth/logout', { method: 'POST' })
  } catch {
    // Ignore logout failures in local MVP mode.
  }
  eventSource.value?.close()
  token.value = ''
  localStorage.removeItem('swe_token')
  sessionStorage.removeItem('swe_token')
  setNotice('Logged out')
  navigateTo('login')
}

async function loadWorkspace() {
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
  syncProjectFormFromSelectedProject()
  await loadProjectData()
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

async function createLLMProfile() {
  busy.value = true
  try {
    await apiRequest('/api/v1/llm-profiles', {
      method: 'POST',
      body: JSON.stringify(llmForm.value),
    })
    setNotice('模型配置已创建')
    await loadWorkspace()
  } catch (error) {
    setNotice(errorMessage(error))
  } finally {
    busy.value = false
  }
}

async function testLLM(profileId: string) {
  const result = await apiRequest<{
    success: boolean
    error_message?: string | null
    mode?: string
  }>(`/api/v1/llm-profiles/${profileId}/test`, { method: 'POST' })
  const mode = result.mode ? `（${displayRuntimeMode(result.mode)}）` : ''
  setNotice(result.success ? `模型测试通过${mode}` : String(result.error_message ?? '模型测试失败'))
  await loadWorkspace()
}

async function savePromptTemplate(template: PromptTemplate) {
  busy.value = true
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
    setNotice(`提示词模板 ${template.id} 已保存`)
    await loadWorkspace()
  } catch (error) {
    setNotice(errorMessage(error))
  } finally {
    busy.value = false
  }
}

async function resetPromptTemplate(templateId: string) {
  busy.value = true
  try {
    await apiRequest<PromptTemplate>(`/api/v1/prompt-templates/${templateId}/reset`, { method: 'POST' })
    setNotice(`提示词模板 ${templateId} 已重置`)
    await loadWorkspace()
  } catch (error) {
    setNotice(errorMessage(error))
  } finally {
    busy.value = false
  }
}

async function setDraftStatus(draft: ChapterDraft, status: 'accepted' | 'needs_revision' | 'rejected') {
  if (!selectedProjectId.value) return
  busy.value = true
  try {
    if (status === 'accepted') {
      await apiRequest<ChapterDraft>(`/api/v1/projects/${selectedProjectId.value}/drafts/${draft.id}/accept`, {
        method: 'POST',
      })
      setNotice('草稿已通过；如果运行仍处于暂停状态，可以继续运行。')
    } else {
      await apiRequest<ChapterDraft>(`/api/v1/projects/${selectedProjectId.value}/drafts/${draft.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      })
      setNotice(`草稿已标记为${displayStatus(status)}`)
    }
    await loadProjectData()
  } catch (error) {
    setNotice(errorMessage(error))
  } finally {
    busy.value = false
  }
}

async function createProject() {
  busy.value = true
  try {
    const profileId = llmProfiles.value[0]?.id ?? null
    const project = await apiRequest<Project>('/api/v1/projects', {
      method: 'POST',
      body: JSON.stringify({ ...newProjectForm.value, default_llm_profile_id: profileId }),
    })
    selectedProjectId.value = project.id
    setNotice('作品已创建')
    showCreateProjectModal.value = false
    await loadWorkspace()
    navigateTo('workbench')
  } catch (error) {
    setNotice(errorMessage(error))
  } finally {
    busy.value = false
  }
}

async function saveBible() {
  if (!selectedProjectId.value) return
  busy.value = true
  try {
    await apiRequest(`/api/v1/projects/${selectedProjectId.value}/bible`, {
      method: 'PUT',
      body: JSON.stringify({
        ...bibleForm.value,
        content_limits: ['不复制参考项目提示词', '不突破已定义世界规则'],
        cast_members: [
          {
            id: 'cast-main',
            name: '陆沉',
            role: 'protagonist',
            motivation: '重建宗门并查明灵气衰退真相',
            voice_hint: '话少，判断直接',
            forbidden_actions: ['无理由背叛同伴'],
          },
        ],
        places: [
          {
            id: 'place-sect',
            name: '玄衡旧宗',
            kind: 'sect',
            summary: '破败宗门遗址，藏有旧纪元阵图',
            parent_place_id: null,
          },
        ],
        plot_lines: [
          {
            id: 'plot-main',
            name: '重启灵脉',
            goal: '找到九处灵脉节点并重启宗门大阵',
            stakes: '失败则宗门遗址被诸城瓜分',
            current_state: '发现第一枚阵钥',
          },
        ],
        constraint_rules: [
          {
            id: 'rule-tone',
            scope: 'style',
            rule: '保持连载爽感，每章必须有推进和钩子',
            severity: 'warn',
          },
        ],
      }),
    })
    setNotice('故事设定已保存')
    await loadProjectData()
  } catch (error) {
    setNotice(errorMessage(error))
  } finally {
    busy.value = false
  }
}

async function startRun() {
  if (!selectedProjectId.value) return
  busy.value = true
  try {
    const run = await apiRequest<SerialRun>(`/api/v1/projects/${selectedProjectId.value}/runs`, {
      method: 'POST',
      body: JSON.stringify({
        mode: 'full_auto',
        start_chapter_number: 1,
        target_chapter_count: runForm.value.target_chapter_count,
        cost_limit: runForm.value.cost_limit,
      }),
    })
    selectedRunId.value = run.id
    setNotice('自动连载已启动')
    await loadProjectData()
    openEventStream().catch((error) => setNotice(errorMessage(error)))
  } catch (error) {
    setNotice(errorMessage(error))
  } finally {
    busy.value = false
  }
}

async function runAction(action: 'pause' | 'resume' | 'cancel') {
  if (!selectedProjectId.value || !selectedRunId.value) return
  try {
    await apiRequest(`/api/v1/projects/${selectedProjectId.value}/runs/${selectedRunId.value}/${action}`, {
      method: 'POST',
    })
    setNotice(`已发送${displayStatus(action)}请求`)
    await loadProjectData()
    if (action === 'resume') openEventStream().catch((error) => setNotice(errorMessage(error)))
  } catch (error) {
    setNotice(errorMessage(error))
  }
}

async function loadEvents() {
  if (!selectedProjectId.value || !selectedRunId.value) {
    events.value = []
    return
  }
  events.value = await apiRequest<RunEvent[]>(`/api/v1/projects/${selectedProjectId.value}/runs/${selectedRunId.value}/events`)
}

async function openEventStream() {
  if (!selectedProjectId.value || !selectedRunId.value) return
  eventSource.value?.close()
  const sseToken = await apiRequest<{ token: string }>('/api/v1/auth/sse-token', { method: 'POST' })
  const source = new EventSource(sseUrl(`/api/v1/projects/${selectedProjectId.value}/runs/${selectedRunId.value}/events/stream`, sseToken.token))
  source.addEventListener('run_event', (event) => {
    const parsed = JSON.parse((event as MessageEvent).data) as RunEvent
    if (!events.value.some((item) => item.id === parsed.id)) {
      events.value.push(parsed)
    }
    loadProjectData().catch(() => undefined)
  })
  source.onerror = () => {
    source.close()
  }
  eventSource.value = source
  setNotice('实时日志已连接')
}

async function exportMarkdown() {
  if (!selectedProjectId.value) return
  try {
    const item = await apiRequest<{ id: string }>(`/api/v1/projects/${selectedProjectId.value}/exports`, {
      method: 'POST',
      body: JSON.stringify({ format: 'markdown' }),
    })
    const blob = await downloadFile(`/api/v1/projects/${selectedProjectId.value}/exports/${item.id}/file`)
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    setNotice('导出任务已创建')
  } catch (error) {
    setNotice(errorMessage(error))
  }
}

onMounted(() => {
  if (window.location.pathname === '/') {
    window.history.replaceState({}, '', '/studio')
  }
  syncPageFromHistory()
  window.addEventListener('popstate', syncPageFromHistory)
})

onUnmounted(() => {
  eventSource.value?.close()
  window.removeEventListener('popstate', syncPageFromHistory)
})
</script>

<template>
  <main v-if="currentPage === 'studio'" class="studio-page">
    <header class="site-header">
      <button class="brand" type="button" @click="navigateTo('studio')">
        <span class="brand-feather" />
        <strong>aonarr</strong>
      </button>

      <nav class="main-nav" aria-label="主导航">
        <button class="active" type="button">首页</button>
        <button type="button">功能</button>
        <button type="button">提示词</button>
        <button type="button">自动修订</button>
        <button type="button">导出</button>
        <button type="button">关于</button>
      </nav>

      <div class="header-actions">
        <n-button quaternary circle aria-label="切换主题">
          <template #icon>
            <n-icon :component="MoonOutline" />
          </template>
        </n-button>
        <n-button secondary size="large" @click="navigateTo('login')">登录</n-button>
        <n-button type="primary" size="large" @click="token ? navigateTo('index') : navigateTo('login')">
          进入工作台
        </n-button>
      </div>
    </header>

    <section class="hero">
      <div class="hero-bg" aria-hidden="true" />

      <section class="hero-copy">
        <div class="pill">
          <n-icon :component="SparklesOutline" />
          专为小说创作者打造的一站式自动连载平台
        </div>

        <h1>
          让灵感成章，
          <span>让连载自动推进</span>
        </h1>

        <p>
          aonarr 将故事设定、章节计划、正文起草、质量审阅、自动修订和导出放进同一个自托管工作台，帮助作者把长篇小说生产流程变得稳定、透明、可持续。
        </p>

        <div class="hero-actions">
          <n-button type="primary" size="large" @click="token ? navigateTo('index') : navigateTo('login')">
            开始创作
            <template #icon>
              <n-icon :component="ArrowForwardOutline" />
            </template>
          </n-button>
          <n-button secondary size="large" @click="navigateTo('login')">查看登录页</n-button>
        </div>

        <div class="hero-stats">
          <div>
            <strong>自动化</strong>
            <span>规划 / 起草 / 审阅</span>
          </div>
          <div>
            <strong>模型</strong>
            <span>模板可编辑</span>
          </div>
          <div>
            <strong>自托管</strong>
            <span>本地自托管</span>
          </div>
        </div>
      </section>

      <section class="product-preview" aria-label="工作台预览">
        <aside class="preview-sidebar">
          <div class="sidebar-heading">
            <span />
            <strong>我的作品</strong>
          </div>
          <button v-for="item in studioSideNav" :key="item.label" :class="{ active: item.active }" type="button">
            <n-icon :component="item.icon" />
            {{ item.label }}
          </button>
        </aside>

        <div class="preview-main">
          <div class="preview-toolbar">
            <n-input placeholder="搜索作品、章节、角色..." round>
              <template #prefix>
                <n-icon :component="SearchOutline" />
              </template>
            </n-input>
            <n-button type="primary">
              <template #icon>
                <n-icon :component="AddOutline" />
              </template>
              新建作品
            </n-button>
          </div>

          <div class="preview-grid">
            <section class="continue-card">
              <h2>继续创作</h2>
              <div class="book-row">
                <div class="book-cover">星火</div>
                <div>
                  <strong>长夜星火</strong>
                  <span>自动运行于 2 分钟前</span>
                  <div class="progress"><i /></div>
                  <em>进度：32%</em>
                </div>
              </div>
            </section>

            <section class="outline-card">
              <h2>章节大纲</h2>
              <div v-for="outline in studioOutlines" :key="outline.title" class="outline-row">
                <span>{{ outline.title }}</span>
                <em>{{ outline.done }}/{{ outline.total }} 章</em>
              </div>
            </section>

            <section class="characters-card">
              <div class="section-head">
                <h2>角色设定</h2>
                <button type="button">查看全部</button>
              </div>
              <div class="character-grid">
                <div v-for="character in studioCharacters" :key="character.name" class="character-card">
                  <div :class="['avatar', character.tone]">{{ character.short }}</div>
                  <strong>{{ character.name }}</strong>
                  <span>{{ character.role }}</span>
                </div>
              </div>
            </section>

            <section class="recent-card">
              <h2>最近运行</h2>
              <div class="recent-row">
                <div>
                  <strong>第三章：迷雾中的相遇</strong>
                  <span>2 分钟前 · 审阅通过</span>
                </div>
                <button type="button" @click="token ? navigateTo('index') : navigateTo('login')">打开</button>
              </div>
            </section>
          </div>
        </div>
      </section>

      <section class="floating-stats">
        <div class="section-head">
          <h2>创作统计</h2>
          <n-tag size="small" :bordered="false">本周</n-tag>
        </div>
        <div class="chart">
          <div v-for="bar in studioChartBars" :key="bar.day" class="bar-wrap">
            <div class="bar" :style="{ height: `${bar.value}%` }" />
            <span>{{ bar.day }}</span>
          </div>
        </div>
        <div class="chart-tip">今日 2,350 字</div>
      </section>
    </section>

    <section class="feature-strip">
      <article v-for="feature in studioFeatures" :key="feature.title" class="feature-item">
        <div class="feature-icon">
          <n-icon :component="feature.icon" />
        </div>
        <div>
          <strong>{{ feature.title }}</strong>
          <p>{{ feature.desc }}</p>
        </div>
      </article>
    </section>
  </main>

  <main v-else-if="currentPage === 'login'" class="login-page">
    <header class="login-header">
      <button class="brand" type="button" @click="navigateTo('studio')">
        <span class="brand-mark">
          <n-icon :component="CreateOutline" />
        </span>
        <span>
          <strong>aonarr</strong>
          <em>长篇小说自动连载工作台</em>
        </span>
      </button>

      <nav class="top-nav" aria-label="产品导航">
        <button type="button" @click="navigateTo('studio')">首页</button>
        <button type="button">功能</button>
        <button type="button">提示词</button>
        <button type="button">运行日志</button>
        <button type="button">导出</button>
      </nav>

      <div class="header-actions">
        <button class="language-btn" type="button">
          <n-icon :component="GlobeOutline" />
          简体中文
          <n-icon :component="ChevronDownOutline" />
        </button>
        <n-button secondary size="large" :disabled="busy" @click="navigateTo('studio')">
          <template #icon>
            <n-icon :component="ArrowBackOutline" />
          </template>
          返回首页
        </n-button>
      </div>
    </header>

    <section class="login-shell">
      <section class="intro-panel">
        <div class="intro-copy">
          <div class="eyebrow">
            <n-icon :component="PaperPlaneOutline" />
            专为网文作者打造
          </div>
          <h1>
            让每一次灵感，
            <span>都自动落成章节</span>
          </h1>
          <p>
            从故事设定、章节规划、正文起草到质量审阅和自动修订，aonarr 帮你把长篇小说生产流程整理成可控、可追踪、可自托管的工作台。
          </p>

          <div class="feature-list">
            <article v-for="feature in loginFeatures" :key="feature.title">
              <span>
                <n-icon :component="feature.icon" />
              </span>
              <div>
                <strong>{{ feature.title }}</strong>
                <p>{{ feature.desc }}</p>
              </div>
            </article>
          </div>

          <div class="quote-card">
            <div class="quote-mark">“</div>
            <p>把提示词、章节计划、修订反馈和运行成本都放进同一条生产线，长篇连载终于不再靠散乱文档硬撑。</p>
            <div class="quote-author">
              <span>S</span>
              <div>
                <strong>aonarr</strong>
                <em>本地自动化原型</em>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="form-panel" aria-label="登录">
        <div class="login-card">
          <div class="login-title">
            <span class="title-icon">
              <n-icon :component="LockClosedOutline" />
            </span>
            <h2>欢迎回来</h2>
            <p>登录你的 aonarr 工作空间</p>
          </div>

          <n-form class="login-form" :show-label="false" @submit.prevent="login">
            <label class="field-label" for="account">邮箱 / 用户名</label>
            <n-form-item>
              <n-input
                id="account"
                v-model:value="username"
                size="large"
                placeholder="请输入邮箱或用户名"
                autocomplete="username"
              >
                <template #prefix>
                  <n-icon :component="MailOutline" />
                </template>
              </n-input>
            </n-form-item>

            <div class="password-head">
              <label class="field-label" for="password">密码</label>
              <button type="button" @click="setNotice('本地 MVP 暂未启用找回密码')">忘记密码？</button>
            </div>
            <n-form-item>
              <n-input
                id="password"
                v-model:value="password"
                size="large"
                type="password"
                show-password-on="click"
                placeholder="请输入密码"
                autocomplete="current-password"
              >
                <template #prefix>
                  <n-icon :component="LockClosedOutline" />
                </template>
                <template #password-visible-icon>
                  <n-icon :component="EyeOutline" />
                </template>
                <template #password-invisible-icon>
                  <n-icon :component="EyeOffOutline" />
                </template>
              </n-input>
            </n-form-item>

            <div class="form-extra">
              <n-checkbox v-model:checked="remember">记住登录状态</n-checkbox>
              <span>{{ notice }}</span>
            </div>

            <n-button
              attr-type="submit"
              type="primary"
              size="large"
              block
              class="login-submit"
              :loading="busy"
              :disabled="!canLoginSubmit"
            >
              登录工作台
            </n-button>
          </n-form>

          <div class="divider">
            <span />
            <em>或使用以下方式登录</em>
            <span />
          </div>

          <div class="social-grid">
            <n-button secondary size="large" @click="setNotice('微信登录暂未启用')">
              <template #icon>
                <n-icon class="wechat" :component="LogoWechat" />
              </template>
              微信
            </n-button>
            <n-button secondary size="large" @click="setNotice('QQ 登录暂未启用')">
              <template #icon>
                <n-icon class="qq" :component="ChatbubbleEllipsesOutline" />
              </template>
              QQ
            </n-button>
            <n-button secondary size="large" @click="setNotice('手机号登录暂未启用')">
              <template #icon>
                <n-icon class="phone" :component="PhonePortraitOutline" />
              </template>
              手机号
            </n-button>
          </div>

          <p class="register-line">
            本地默认账号：
            <button type="button" @click="username = 'admin'; password = 'change-me'">填入 admin / change-me</button>
          </p>
        </div>
      </section>
    </section>
  </main>

  <main v-else-if="requiresAuth(currentPage) && token" class="workspace-page">
    <aside class="sidebar">
      <button class="workspace-brand" type="button" @click="navigateTo('studio')">
        <span class="logo-mark">
          <n-icon :component="ReaderOutline" />
        </span>
        <span>
          <strong>aonarr</strong>
          <em>小说创作与自动连载平台</em>
        </span>
      </button>

      <nav class="side-nav" aria-label="工作台导航">
        <button
          v-for="item in workspaceNavItems"
          :key="item.label"
          :class="{ active: isWorkspaceNavActive(item) }"
          type="button"
          @click="handleWorkspaceNav(item)"
        >
          <n-icon :component="item.icon" />
          <span>{{ item.label }}</span>
          <em v-if="item.badge">{{ item.badge }}</em>
        </button>
      </nav>

      <section class="plan-card">
        <div class="crown">
          <n-icon :component="StarOutline" />
        </div>
        <strong>自托管原型</strong>
        <span>{{ displayStorageBackend(runtimeSettings?.storage_backend) }} · 模型 {{ llmModeLabel }}</span>
        <n-button type="primary" block @click="loadWorkspace">刷新状态</n-button>
      </section>
    </aside>

    <section class="workspace-main">
      <header class="topbar">
        <n-button quaternary circle aria-label="展开导航">
          <template #icon>
            <n-icon :component="MenuOutline" />
          </template>
        </n-button>

        <n-input class="global-search" placeholder="搜索作品、章节、提示词..." round>
          <template #prefix>
            <n-icon :component="SearchOutline" />
          </template>
          <template #suffix>
            <kbd>⌘ K</kbd>
          </template>
        </n-input>

        <div class="top-actions">
          <n-button quaternary circle aria-label="通知" @click="openEventStream">
            <template #icon>
              <n-icon :component="NotificationsOutline" />
            </template>
          </n-button>
          <n-button quaternary circle aria-label="站内信" @click="loadEvents">
            <template #icon>
              <n-icon :component="MailOutline" />
            </template>
          </n-button>
          <n-button quaternary circle aria-label="帮助" @click="navigateTo('settings')">
            <template #icon>
              <n-icon :component="HelpCircleOutline" />
            </template>
          </n-button>

          <button class="user-menu" type="button" @click="logout">
            <span class="avatar">S</span>
            <span>
              <strong>{{ username }}</strong>
              <em>退出登录</em>
            </span>
            <n-icon :component="ChevronDownOutline" />
          </button>
        </div>
      </header>

      <section v-if="currentPage === 'index'" class="content">
        <div class="welcome-row">
          <div>
            <h1>下午好，{{ username }} <span>👋</span></h1>
            <p>{{ notice }} · 当前项目：{{ selectedProject?.title ?? '未选择项目' }}</p>
          </div>
          <n-button type="primary" size="large" class="new-work-btn" @click="showCreateProjectModal = true">
            <template #icon>
              <n-icon :component="AddOutline" />
            </template>
            新建作品
          </n-button>
        </div>

        <section class="metrics-grid">
          <article v-for="metric in workspaceMetrics" :key="metric.label" :class="['metric-card', metric.tone]">
            <div class="metric-icon">
              <n-icon :component="metric.icon" />
            </div>
            <div class="metric-copy">
              <span>{{ metric.label }}</span>
              <strong>{{ metric.value }}</strong>
              <em>{{ metric.delta }}</em>
            </div>
            <svg class="sparkline" viewBox="0 0 260 62" aria-hidden="true">
              <defs>
                <linearGradient :id="`${metric.tone}-fill`" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" :stop-color="metric.color" stop-opacity="0.18" />
                  <stop offset="100%" :stop-color="metric.color" stop-opacity="0" />
                </linearGradient>
              </defs>
              <polygon :points="`${metric.points} 260,62 0,62`" :fill="`url(#${metric.tone}-fill)`" />
              <polyline :points="metric.points" fill="none" :stroke="metric.color" stroke-width="3.2" />
            </svg>
          </article>
        </section>

        <section class="dashboard-grid">
          <article class="panel works-panel">
            <div class="panel-head">
              <h2>我的作品</h2>
              <button type="button" @click="loadWorkspace">
                全部作品
                <n-icon :component="ChevronForwardOutline" />
              </button>
            </div>

            <div class="work-list">
              <div
                v-for="work in workspaceWorks"
                :key="work.id"
                class="work-row"
                @click="selectWorkspaceProject(work.id)"
              >
                <div :class="['book-cover', work.coverTone]">
                  <span>{{ work.cover }}</span>
                </div>
                <div class="work-info">
                  <div>
                    <strong>{{ work.title }}</strong>
                    <n-tag size="small" :type="work.statusType" :bordered="false">{{ displayStatus(work.status) }}</n-tag>
                  </div>
                  <p>{{ work.meta }}</p>
                </div>
                <div class="work-stat">
                  <span>草稿数</span>
                  <strong>{{ work.words }}</strong>
                </div>
                <div class="work-stat">
                  <span>计划数</span>
                  <strong>{{ work.reads }}</strong>
                </div>
                <div class="work-stat">
                  <span>通过数</span>
                  <strong>{{ work.favorites }}</strong>
                </div>
                <div class="work-time">
                  <span>更新时间</span>
                  <strong>{{ work.updated }}</strong>
                </div>
                <button class="more-btn" type="button" aria-label="更多操作">···</button>
              </div>

              <div class="create-row">
                <div class="create-icon">
                  <n-icon :component="AddOutline" />
                </div>
                <div>
                  <strong>创建新作品</strong>
                  <p>创建后进入单本书生产工作台，配置故事设定和自动连载</p>
                </div>
                <n-button secondary type="primary" @click="showCreateProjectModal = true">新建作品</n-button>
              </div>
            </div>
          </article>

          <article class="panel calendar-panel">
            <div class="panel-head">
              <h2>创作日历</h2>
              <button type="button">设置目标</button>
            </div>
            <div class="month-head">
              <n-button quaternary circle size="small">
                <template #icon>
                  <n-icon :component="ChevronBackOutline" />
                </template>
              </n-button>
              <strong>2024年5月</strong>
              <n-button quaternary circle size="small">
                <template #icon>
                  <n-icon :component="ChevronForwardOutline" />
                </template>
              </n-button>
            </div>
            <div class="calendar-grid">
              <span v-for="day in weekDays" :key="day" class="week-day">{{ day }}</span>
              <button
                v-for="day in calendarDays"
                :key="`${day.label}-${day.muted}`"
                :class="{ muted: day.muted, active: day.active, marked: day.marked }"
                type="button"
              >
                {{ day.label }}
              </button>
            </div>
            <div class="calendar-summary">
              <div>
                <span>草稿数</span>
                <strong>{{ drafts.length }}</strong>
              </div>
              <div>
                <span>运行数</span>
                <strong>{{ runs.length }}</strong>
              </div>
              <div>
                <span>连续任务</span>
                <strong>{{ acceptedDrafts.length }} <em>章</em></strong>
              </div>
            </div>
          </article>

          <article class="panel stats-panel">
            <div class="panel-head">
              <h2>数据统计</h2>
              <div class="tabs">
                <button type="button">7天</button>
                <button class="active" type="button">30天</button>
                <button type="button">90天</button>
                <button type="button">自定义</button>
              </div>
            </div>
            <div class="data-summary">
              <div v-for="item in workspaceDataSummary" :key="item.label">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
                <em>↑ {{ item.up }}</em>
              </div>
            </div>
            <svg class="line-chart" viewBox="0 0 820 230" aria-hidden="true">
              <g class="grid-lines">
                <line v-for="y in chartLines" :key="y" x1="0" x2="820" :y1="y" :y2="y" />
              </g>
              <polyline points="0,178 72,138 145,184 218,120 292,86 365,150 438,116 510,160 585,78 656,132 742,118 820,156" />
              <polyline class="blue" points="0,166 72,152 145,128 218,170 292,142 365,94 438,130 510,118 585,150 656,108 742,100 820,138" />
              <polyline class="green" points="0,184 72,166 145,150 218,146 292,174 365,152 438,160 510,135 585,142 656,118 742,106 820,128" />
              <polyline class="orange" points="0,190 72,176 145,180 218,168 292,164 365,148 438,156 510,138 585,150 656,130 742,122 820,136" />
            </svg>
          </article>

          <article class="panel task-panel">
            <div class="panel-head">
              <h2>任务中心</h2>
              <button type="button">
                更多任务
                <n-icon :component="ChevronForwardOutline" />
              </button>
            </div>
            <div class="task-list">
              <button v-for="task in workspaceTasks" :key="task.title" class="task-row task-action" type="button" @click="handleWorkspaceTask(task)">
                <div :class="['task-check', task.tone]">
                  <n-icon :component="CheckmarkDoneOutline" />
                </div>
                <div>
                  <strong>{{ task.title }}</strong>
                  <p>{{ task.progress }}</p>
                </div>
                <n-tag :type="task.type" :bordered="false">{{ task.badge }}</n-tag>
              </button>
            </div>
          </article>
        </section>

      </section>

      <section v-else-if="currentPage === 'workbench'" class="content workbench-content">
        <div class="workspace-breadcrumb">
          <button type="button" @click="navigateTo('index')">
            <n-icon :component="ChevronBackOutline" />
            返回工作台
          </button>
          <select v-if="projects.length" v-model="selectedProjectId" @change="handleProjectSelection">
            <option v-for="project in projects" :key="project.id" :value="project.id">
              {{ project.title }} · {{ displayStatus(project.status) }}
            </option>
          </select>
          <n-button secondary type="primary" @click="showCreateProjectModal = true">新建作品</n-button>
        </div>

        <div v-if="!selectedProject" class="empty-state panel">
          <h2>先选择或创建一个作品</h2>
          <p>生产工作台是单本书的生产空间，用来配置故事设定、启动自动连载、审阅草稿和查看运行日志。</p>
          <n-button type="primary" @click="showCreateProjectModal = true">创建作品</n-button>
        </div>

        <section v-else class="workbench-layout">
          <aside class="panel chapter-rail">
            <div class="panel-head">
              <h2>{{ selectedProject.title }}</h2>
              <button type="button" @click="loadProjectData()">刷新</button>
            </div>
            <div class="run-progress-card">
              <span>当前运行</span>
              <strong>{{ selectedRun ? displayStatus(selectedRun.status) : '未启动' }}</strong>
              <p>{{ selectedRun ? `${selectedRun.completed_chapter_count}/${selectedRun.target_chapter_count} 章 · $${selectedRun.estimated_cost}` : '创建运行后开始监听进度' }}</p>
            </div>
            <div class="chapter-list">
              <button
                v-for="plan in plans"
                :key="plan.id"
                type="button"
                :class="{ active: workbenchMainPanel === 'plans' }"
                @click="workbenchMainPanel = 'plans'"
              >
                <span>第{{ plan.chapter_number }}章</span>
                <strong>{{ plan.title_hint }}</strong>
                <em>{{ displayStatus(plan.status) }}</em>
              </button>
              <button
                v-for="draft in drafts"
                :key="draft.id"
                type="button"
                :class="{ active: workbenchMainPanel === 'drafts' }"
                @click="workbenchMainPanel = 'drafts'"
              >
                <span>第{{ draft.chapter_number }}章</span>
                <strong>{{ draft.title }}</strong>
                <em>{{ displayStatus(draft.status) }}</em>
              </button>
            </div>
          </aside>

          <section class="workbench-center">
            <div class="workbench-tabs">
              <button :class="{ active: workbenchMainPanel === 'run' }" type="button" @click="workbenchMainPanel = 'run'">生产驾驶舱</button>
              <button :class="{ active: workbenchMainPanel === 'plans' }" type="button" @click="workbenchMainPanel = 'plans'">章节计划</button>
              <button :class="{ active: workbenchMainPanel === 'drafts' }" type="button" @click="workbenchMainPanel = 'drafts'">草稿审阅</button>
              <button :class="{ active: workbenchMainPanel === 'events' }" type="button" @click="workbenchMainPanel = 'events'">运行日志</button>
            </div>

            <article v-if="workbenchMainPanel === 'run'" class="panel cockpit-panel">
              <div class="panel-head">
                <h2>生产驾驶舱</h2>
                <button type="button" @click="openEventStream">连接实时日志</button>
              </div>
              <div class="cockpit-grid">
                <div class="engine-box">
                  <h3>运行目标</h3>
                  <label>
                    目标章节
                    <input v-model.number="runForm.target_chapter_count" type="number" min="1" />
                  </label>
                  <label>
                    成本上限
                    <input v-model.number="runForm.cost_limit" type="number" min="0" step="0.01" />
                  </label>
                  <select v-if="runs.length" v-model="selectedRunId" @change="loadEvents()">
                    <option v-for="run in runs" :key="run.id" :value="run.id">
                      {{ displayStatus(run.status) }} · {{ run.completed_chapter_count }}/{{ run.target_chapter_count }} · ${{ run.estimated_cost }}
                    </option>
                  </select>
                </div>
                <div class="run-meter">
                  <strong>{{ selectedRun ? Math.round((selectedRun.completed_chapter_count / Math.max(selectedRun.target_chapter_count, 1)) * 100) : 0 }}%</strong>
                  <span>{{ selectedRun ? displayStatus(selectedRun.status) : '待启动' }}</span>
                  <p>已完成 {{ selectedRun?.completed_chapter_count ?? 0 }} / {{ selectedRun?.target_chapter_count ?? runForm.target_chapter_count }} 章</p>
                </div>
                <div class="engine-box">
                  <h3>控制</h3>
                  <div class="button-row">
                    <button class="primary-button" type="button" :disabled="busy || !selectedProject" @click="startRun">启动</button>
                    <button class="ghost-button" type="button" :disabled="!selectedRun" @click="runAction('pause')">暂停</button>
                    <button class="ghost-button" type="button" :disabled="!selectedRun" @click="runAction('resume')">继续</button>
                    <button class="ghost-button" type="button" :disabled="!selectedRun" @click="runAction('cancel')">取消</button>
                  </div>
                  <p class="panel-note">{{ notice }}</p>
                </div>
              </div>
            </article>

            <article v-else-if="workbenchMainPanel === 'plans'" class="panel">
              <div class="panel-head">
                <h2>章节计划</h2>
                <button type="button" @click="loadProjectData()">刷新计划</button>
              </div>
              <div class="plan-list">
                <article v-for="plan in plans" :key="plan.id" class="plan-row">
                  <span>第{{ plan.chapter_number }}章 · {{ displayStatus(plan.status) }}</span>
                  <h3>{{ plan.title_hint }}</h3>
                  <p>{{ plan.goal }}</p>
                  <p>{{ plan.conflict }}</p>
                  <em>{{ plan.hook }}</em>
                </article>
              </div>
            </article>

            <article v-else-if="workbenchMainPanel === 'drafts'" class="panel">
              <div class="panel-head">
                <h2>草稿审阅</h2>
                <button type="button" :disabled="!acceptedDrafts.length" @click="exportMarkdown">导出文稿</button>
              </div>
              <article v-for="draft in drafts" :key="draft.id" class="draft-card">
                <h3>{{ draft.title }}</h3>
                <div class="draft-meta">
                  <span>{{ displayStatus(draft.status) }}</span>
                  <span v-if="draft.quality_score !== undefined && draft.quality_score !== null">评分 {{ draft.quality_score }}</span>
                  <span>版本 {{ draft.version }}</span>
                </div>
                <div class="button-row">
                  <button class="small-button" type="button" :disabled="busy" @click="setDraftStatus(draft, 'accepted')">通过</button>
                  <button class="small-button" type="button" :disabled="busy" @click="setDraftStatus(draft, 'needs_revision')">需要修订</button>
                  <button class="small-button" type="button" :disabled="busy" @click="setDraftStatus(draft, 'rejected')">拒绝</button>
                </div>
                <p v-if="draft.review_summary" class="review-summary">{{ draft.review_summary }}</p>
                <p>{{ draft.body }}</p>
              </article>
            </article>

            <article v-else class="panel">
              <div class="panel-head">
                <h2>运行日志</h2>
                <button type="button" @click="loadEvents()">刷新日志</button>
              </div>
              <div class="event-log">
                <article v-for="event in events" :key="event.id" class="event-row">
                  <span>{{ displayEventType(event.event_type) }}</span>
                  <p>{{ event.message }}</p>
                  <small>{{ event.created_at }}</small>
                </article>
              </div>
            </article>
          </section>

          <aside class="panel settings-side-panel">
            <div class="panel-head">
              <h2>作品资料</h2>
              <button type="button" @click="workbenchSidePanel = 'export'">导出</button>
            </div>
            <div class="workbench-tabs side-tabs">
              <button :class="{ active: workbenchSidePanel === 'bible' }" type="button" @click="workbenchSidePanel = 'bible'">故事设定</button>
              <button :class="{ active: workbenchSidePanel === 'project' }" type="button" @click="workbenchSidePanel = 'project'">项目设定</button>
              <button :class="{ active: workbenchSidePanel === 'export' }" type="button" @click="workbenchSidePanel = 'export'">导出</button>
            </div>
            <div v-if="workbenchSidePanel === 'bible'" class="side-panel-body">
              <textarea v-model="bibleForm.premise" placeholder="故事前提"></textarea>
              <textarea v-model="bibleForm.world_summary" placeholder="世界观摘要"></textarea>
              <textarea v-model="bibleForm.tone_profile" placeholder="文风设定"></textarea>
              <button class="primary-button" type="button" :disabled="!selectedProject" @click="saveBible">保存故事设定</button>
              <div v-if="readiness" class="readiness" :class="{ ready: readiness.ready }">
                <strong>{{ readiness.ready ? '可以开始运行' : '尚未就绪' }}</strong>
                <p v-for="item in readiness.missing" :key="item.section">{{ displayReadinessSection(item.section) }}：{{ item.message }}</p>
              </div>
            </div>
            <div v-else-if="workbenchSidePanel === 'project'" class="side-panel-body">
              <input v-model="projectForm.title" placeholder="作品名称" />
              <input v-model="projectForm.genre" placeholder="作品类型" />
              <input v-model.number="projectForm.target_chapter_count" type="number" />
              <input v-model.number="projectForm.target_words_per_chapter" type="number" />
              <textarea v-model="projectForm.style_goal" placeholder="风格目标"></textarea>
              <button class="ghost-button" type="button" @click="setNotice('当前版本先支持创建时写入项目设定')">保存项目设定</button>
            </div>
            <div v-else class="side-panel-body">
              <strong>文稿导出</strong>
              <p>导出当前项目已通过章节，适合进入后续排版或发布流程。</p>
              <button class="primary-button" type="button" :disabled="!acceptedDrafts.length" @click="exportMarkdown">导出文稿</button>
            </div>
          </aside>
        </section>
      </section>

      <section v-else-if="currentPage === 'settings'" class="content settings-content">
        <div class="welcome-row">
          <div>
            <h1>系统设置</h1>
            <p>模型配置、提示词模板和运行环境从作品首页拆出，集中在这里维护。</p>
          </div>
          <n-button secondary type="primary" @click="loadWorkspace">刷新设置</n-button>
        </div>

        <section class="settings-layout">
          <aside class="panel settings-nav-panel">
            <button :class="{ active: settingsPanel === 'llm' }" type="button" @click="settingsPanel = 'llm'">
              <n-icon :component="SparklesOutline" />
              模型配置
            </button>
            <button :class="{ active: settingsPanel === 'prompts' }" type="button" @click="settingsPanel = 'prompts'">
              <n-icon :component="DocumentTextOutline" />
              提示词模板
            </button>
            <button :class="{ active: settingsPanel === 'runtime' }" type="button" @click="settingsPanel = 'runtime'">
              <n-icon :component="StatsChartOutline" />
              运行环境
            </button>
          </aside>

          <section class="panel settings-detail-panel">
            <div v-if="settingsPanel === 'llm'" class="settings-section">
              <div class="panel-head">
                <h2>模型配置</h2>
                <button type="button" @click="loadWorkspace">刷新</button>
              </div>
              <div class="settings-two-column">
                <div class="engine-box">
                  <h3>创建模型配置</h3>
                  <input v-model="llmForm.name" placeholder="配置名称" />
                  <input v-model="llmForm.base_url" placeholder="接口地址" />
                  <input v-model="llmForm.model" placeholder="模型名称" />
                  <input v-model="llmForm.api_key" placeholder="接口密钥" type="password" />
                  <button class="primary-button" type="button" @click="createLLMProfile">创建模型</button>
                </div>
                <div class="profile-list">
                  <button v-for="profile in llmProfiles" :key="profile.id" type="button" @click="testLLM(profile.id)">
                    <strong>{{ displayProfileName(profile.name) }}</strong>
                    <span>{{ displayProviderType(profile.provider_type) }} · {{ profile.model }}</span>
                    <em>{{ displayStatus(profile.status) }}</em>
                  </button>
                </div>
              </div>
            </div>

            <div v-else-if="settingsPanel === 'prompts'" class="settings-section">
              <div class="panel-head">
                <h2>提示词中心</h2>
                <button type="button" @click="loadWorkspace">刷新模板</button>
              </div>
              <article v-for="template in promptTemplates" :key="template.id" class="template-card">
                <div class="template-header">
                  <div>
                    <h3>{{ template.name }}</h3>
                    <p>{{ template.id }} · {{ template.purpose }}</p>
                  </div>
                  <div class="button-row">
                    <button class="small-button" type="button" @click="savePromptTemplate(template)">保存</button>
                    <button class="small-button" type="button" @click="resetPromptTemplate(template.id)">重置</button>
                  </div>
                </div>
                <input v-model="template.name" placeholder="模板名称" />
                <input v-model="template.purpose" placeholder="用途说明" />
                <label>
                  系统提示词
                  <textarea v-model="template.system_template"></textarea>
                </label>
                <label>
                  用户提示词
                  <textarea v-model="template.user_template"></textarea>
                </label>
                <div class="form-grid two">
                  <input v-model.number="template.temperature" type="number" min="0" max="2" step="0.1" />
                  <input v-model.number="template.max_tokens" type="number" min="1" placeholder="最大 Token 数" />
                </div>
                <small>{{ template.required_variables.join(', ') }}</small>
              </article>
            </div>

            <div v-else class="settings-section">
              <div class="panel-head">
                <h2>运行环境</h2>
                <button type="button" @click="loadWorkspace">刷新</button>
              </div>
              <div class="runtime-grid">
                <article>
                  <span>模型调用模式</span>
                  <strong>{{ displayRuntimeMode(runtimeSettings?.llm_mode) }}</strong>
                </article>
                <article>
                  <span>存储后端</span>
                  <strong>{{ displayStorageBackend(runtimeSettings?.storage_backend) }}</strong>
                </article>
                <article>
                  <span>自动修订次数</span>
                  <strong>{{ runtimeSettings?.revision_max_attempts ?? 0 }}</strong>
                </article>
                <article>
                  <span>模型配置数</span>
                  <strong>{{ llmProfiles.length }}</strong>
                </article>
              </div>
            </div>
          </section>
        </section>
      </section>

      <div v-if="showCreateProjectModal" class="workspace-modal-backdrop" @click.self="showCreateProjectModal = false">
        <section class="workspace-modal">
          <div class="panel-head">
            <h2>创建新作品</h2>
            <button type="button" @click="showCreateProjectModal = false">关闭</button>
          </div>
          <div class="side-panel-body">
            <input v-model="newProjectForm.title" placeholder="作品名称" />
            <input v-model="newProjectForm.genre" placeholder="作品类型" />
            <input v-model.number="newProjectForm.target_chapter_count" type="number" min="1" />
            <input v-model.number="newProjectForm.target_words_per_chapter" type="number" min="1" />
            <textarea v-model="newProjectForm.style_goal" placeholder="风格目标"></textarea>
            <button class="primary-button" type="button" :disabled="busy" @click="createProject">创建并进入生产工作台</button>
          </div>
        </section>
      </div>
    </section>
  </main>
</template>
