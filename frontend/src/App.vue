<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import {
  pageFromPath,
  requiresAuth,
  type PageName,
  type SettingsPanel,
  type WorkbenchMainPanel,
  type WorkbenchSidePanel,
  type WorkspaceNavItem,
  type WorkspaceTask,
} from './composables/useWorkspace'
import { useAuth } from './composables/useAuth'
import { useWorkspaceActions } from './composables/useWorkspaceActions'
import { useWorkspaceDashboard } from './composables/useWorkspaceDashboard'
import { useWorkspaceData } from './composables/useWorkspaceData'
import DashboardPage from './components/DashboardPage.vue'
import LoginPage from './components/LoginPage.vue'
import SettingsPage from './components/SettingsPage.vue'
import StudioPage from './components/StudioPage.vue'
import WorkbenchPage from './components/WorkbenchPage.vue'
import WorkspaceShell from './components/WorkspaceShell.vue'
import {
  createDefaultBibleForm,
  createDefaultLLMForm,
  createDefaultProjectForm,
  createDefaultRunForm,
} from './formDefaults'

const currentPage = ref<PageName>(pageFromPath(window.location.pathname))
const eventSource = ref<EventSource | null>(null)
const {
  busy,
  canLoginSubmit,
  fillDevLogin,
  login,
  logout,
  notice,
  password,
  remember,
  setNotice,
  showDevLoginHint,
  token,
  username,
} = useAuth({ eventSource, navigateTo })
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

function openCreateProjectModal() {
  showCreateProjectModal.value = true
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
    <DashboardPage
      v-if="currentPage === 'index'"
      :accepted-drafts="acceptedDrafts"
      :drafts="drafts"
      :notice="notice"
      :runs="runs"
      :selected-project-title="selectedProject?.title ?? '未选择项目'"
      :username="username"
      :workspace-data-summary="workspaceDataSummary"
      :workspace-metrics="workspaceMetrics"
      :workspace-tasks="workspaceTasks"
      :workspace-works="workspaceWorks"
      @open-create-project="openCreateProjectModal"
      @refresh="loadWorkspace"
      @select-workspace-project="selectWorkspaceProject"
      @workspace-task="handleWorkspaceTask"
    />

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
