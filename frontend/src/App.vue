<script setup lang="ts">
import { ref } from 'vue'
import {
  requiresAuth,
} from './composables/useWorkspace'
import { useAuth } from './composables/useAuth'
import { useNavigation } from './composables/useNavigation'
import { useWorkspaceActions } from './composables/useWorkspaceActions'
import { useWorkspaceDashboard } from './composables/useWorkspaceDashboard'
import { useWorkspaceData } from './composables/useWorkspaceData'
import { useWorkspaceForms } from './composables/useWorkspaceForms'
import DashboardPage from './components/DashboardPage.vue'
import LoginPage from './components/LoginPage.vue'
import SettingsPage from './components/SettingsPage.vue'
import StudioPage from './components/StudioPage.vue'
import WorkbenchPage from './components/WorkbenchPage.vue'
import WorkspaceShell from './components/WorkspaceShell.vue'

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
  setNavigator,
  setNotice,
  showDevLoginHint,
  token,
  username,
} = useAuth({ eventSource })

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
const {
  bibleForm,
  llmForm,
  newProjectForm,
  projectForm,
  runForm,
  syncProjectFormFromSelectedProject,
} = useWorkspaceForms({ selectedProject })
const {
  activeWorkspaceNavLabel,
  currentPage,
  handleWorkspaceNav,
  handleWorkspaceTask,
  navigateTo,
  openCreateProjectModal,
  selectWorkspaceProject,
  settingsPanel,
  showCreateProjectModal,
  workbenchMainPanel,
  workbenchSidePanel,
} = useNavigation({
  eventSource,
  loadWorkspace,
  selectedProject,
  selectedProjectId,
  setNotice,
  syncProjectFormFromSelectedProject,
  token,
})
setNavigator(navigateTo)
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

function handleProjectSelection() {
  syncProjectFormFromSelectedProject()
  loadProjectData().catch((error) => setNotice(errorMessage(error)))
}

async function loadWorkspace() {
  await loadWorkspaceData(syncProjectFormFromSelectedProject)
}
</script>

<template>
  <StudioPage
    v-if="currentPage === 'studio'"
    :has-token="Boolean(token)"
    @navigate="navigateTo"
    @notice="setNotice"
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
    :active-workspace-nav-label="activeWorkspaceNavLabel"
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
    @set-notice="setNotice"
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
      @set-notice="setNotice"
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
