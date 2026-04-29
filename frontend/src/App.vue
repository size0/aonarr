<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { NButton, NIcon, NTag } from 'naive-ui'
import {
  AddOutline,
  CheckmarkDoneOutline,
  ChevronBackOutline,
  ChevronForwardOutline,
} from '@vicons/ionicons5'
import { apiRequest } from './api'
import {
  displayStatus,
  pageFromPath,
  requiresAuth,
  type PageName,
  type SettingsPanel,
  type WorkbenchMainPanel,
  type WorkbenchSidePanel,
  type WorkspaceNavItem,
  type WorkspaceTask,
} from './composables/useWorkspace'
import { useWorkspaceActions } from './composables/useWorkspaceActions'
import { useWorkspaceDashboard } from './composables/useWorkspaceDashboard'
import { useWorkspaceData } from './composables/useWorkspaceData'
import LoginPage from './components/LoginPage.vue'
import SettingsPage from './components/SettingsPage.vue'
import StudioPage from './components/StudioPage.vue'
import WorkbenchPage from './components/WorkbenchPage.vue'
import WorkspaceShell from './components/WorkspaceShell.vue'
import {
  calendarDays,
  chartLines,
  weekDays,
} from './workspaceConfig'
import {
  createDefaultBibleForm,
  createDefaultLLMForm,
  createDefaultProjectForm,
  createDefaultRunForm,
} from './formDefaults'

const token = ref(localStorage.getItem('swe_token') ?? sessionStorage.getItem('swe_token') ?? '')
const username = ref('admin')
const password = ref('')
const notice = ref('就绪')
const busy = ref(false)
const remember = ref(true)
const showDevLoginHint = import.meta.env.DEV

const currentPage = ref<PageName>(pageFromPath(window.location.pathname))

const eventSource = ref<EventSource | null>(null)
const showCreateProjectModal = ref(false)
const workbenchMainPanel = ref<WorkbenchMainPanel>('run')
const workbenchSidePanel = ref<WorkbenchSidePanel>('bible')
const settingsPanel = ref<SettingsPanel>('llm')

const llmForm = ref(createDefaultLLMForm())
const newProjectForm = ref(createDefaultProjectForm())
const projectForm = ref(createDefaultProjectForm())
const bibleForm = ref(createDefaultBibleForm())
const runForm = ref(createDefaultRunForm())

const {
  acceptedDrafts,
  costSummary,
  drafts,
  events,
  llmModeLabel,
  llmProfiles,
  loadEvents,
  loadProjectData,
  loadWorkspace: loadWorkspaceData,
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
} = useWorkspaceData(token)
const canLoginSubmit = computed(() => username.value.trim().length > 0 && password.value.trim().length > 0)
const { workspaceDataSummary, workspaceMetrics, workspaceTasks, workspaceWorks } = useWorkspaceDashboard({
  acceptedDrafts,
  costSummary,
  drafts,
  events,
  llmModeLabel,
  newProjectForm,
  plans,
  projects,
  promptTemplates,
  readiness,
  runtimeSettings,
  runs,
  selectedProject,
  selectedProjectId,
  selectedRun,
})
const {
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
} = useWorkspaceActions({
  bibleForm,
  busy,
  eventSource,
  events,
  llmForm,
  llmProfiles,
  loadProjectData,
  loadWorkspace,
  navigateTo,
  newProjectForm,
  runForm,
  selectedProjectId,
  selectedRunId,
  setNotice,
  showCreateProjectModal,
})

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

function fillDevLogin() {
  username.value = 'admin'
  password.value = 'change-me'
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

function openCreateProjectModal() {
  showCreateProjectModal.value = true
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
  await loadWorkspaceData(syncProjectFormFromSelectedProject)
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
  <StudioPage
    v-if="currentPage === 'studio'"
    :has-token="Boolean(token)"
    @navigate="navigateTo"
  />

  <LoginPage
    v-else-if="currentPage === 'login'"
    v-model:password="password"
    v-model:remember="remember"
    v-model:username="username"
    :busy="busy"
    :can-login-submit="canLoginSubmit"
    :notice="notice"
    :show-dev-login-hint="showDevLoginHint"
    @fill-dev-login="fillDevLogin"
    @login="login"
    @navigate-studio="navigateTo('studio')"
    @notice="setNotice"
  />

  <WorkspaceShell
    v-else-if="requiresAuth(currentPage) && token"
    v-model:show-create-project-modal="showCreateProjectModal"
    :busy="busy"
    :current-page="currentPage"
    :llm-mode-label="llmModeLabel"
    :new-project-form="newProjectForm"
    :runtime-settings="runtimeSettings"
    :settings-panel="settingsPanel"
    :username="username"
    :workbench-main-panel="workbenchMainPanel"
    :workbench-side-panel="workbenchSidePanel"
    @create-project="createProject"
    @load-events="loadEvents"
    @logout="logout"
    @navigate="navigateTo"
    @open-event-stream="openEventStream"
    @refresh="loadWorkspace"
    @workspace-nav="handleWorkspaceNav"
  >
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

    <WorkbenchPage
      v-else-if="currentPage === 'workbench'"
      v-model:selected-project-id="selectedProjectId"
      v-model:selected-run-id="selectedRunId"
      v-model:workbench-main-panel="workbenchMainPanel"
      v-model:workbench-side-panel="workbenchSidePanel"
      :accepted-drafts="acceptedDrafts"
      :bible-form="bibleForm"
      :busy="busy"
      :drafts="drafts"
      :events="events"
      :notice="notice"
      :plans="plans"
      :project-form="projectForm"
      :projects="projects"
      :readiness="readiness"
      :run-form="runForm"
      :runs="runs"
      :selected-project="selectedProject"
      :selected-run="selectedRun"
      @export-markdown="exportMarkdown"
      @load-events="loadEvents"
      @load-project-data="loadProjectData"
      @navigate-index="navigateTo('index')"
      @open-create-project="openCreateProjectModal"
      @open-event-stream="openEventStream"
      @run-action="runAction"
      @save-bible="saveBible"
      @set-draft-status="setDraftStatus"
      @set-notice="setNotice"
      @start-run="startRun"
      @update-project-selection="handleProjectSelection"
    />

    <SettingsPage
      v-else-if="currentPage === 'settings'"
      v-model:settings-panel="settingsPanel"
      :llm-form="llmForm"
      :llm-profiles="llmProfiles"
      :prompt-templates="promptTemplates"
      :runtime-settings="runtimeSettings"
      @create-l-l-m-profile="createLLMProfile"
      @refresh="loadWorkspace"
      @reset-prompt-template="resetPromptTemplate"
      @save-prompt-template="savePromptTemplate"
      @test-l-l-m="testLLM"
    />
  </WorkspaceShell>
</template>
