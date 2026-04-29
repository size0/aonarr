import { onMounted, onUnmounted, ref, type Ref } from 'vue'
import type { Project } from '../types'
import {
  pageFromPath,
  requiresAuth,
  type PageName,
  type SettingsPanel,
  type WorkbenchMainPanel,
  type WorkbenchSidePanel,
  type WorkspaceNavItem,
  type WorkspaceTask,
} from './useWorkspace'

type UseNavigationSource = {
  eventSource: Ref<EventSource | null>
  loadWorkspace: () => Promise<void>
  selectedProject: Ref<Project | null>
  selectedProjectId: Ref<string>
  setNotice: (message: string) => void
  syncProjectFormFromSelectedProject: () => void
  token: Ref<string>
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unexpected error'
}

export function useNavigation(source: UseNavigationSource) {
  const currentPage = ref<PageName>(pageFromPath(window.location.pathname))
  const showCreateProjectModal = ref(false)
  const workbenchMainPanel = ref<WorkbenchMainPanel>('run')
  const workbenchSidePanel = ref<WorkbenchSidePanel>('bible')
  const settingsPanel = ref<SettingsPanel>('llm')

  function navigateTo(page: PageName) {
    currentPage.value = page
    const path = page === 'studio' ? '/studio' : `/${page}`
    if (window.location.pathname !== path) {
      window.history.pushState({}, '', path)
    }
    if (requiresAuth(page) && source.token.value) {
      source.loadWorkspace().catch((error) => source.setNotice(errorMessage(error)))
    }
  }

  function syncPageFromHistory() {
    currentPage.value = pageFromPath(window.location.pathname)
    if (requiresAuth(currentPage.value) && !source.token.value) {
      navigateTo('login')
    }
    if (requiresAuth(currentPage.value) && source.token.value) {
      source.loadWorkspace().catch((error) => source.setNotice(errorMessage(error)))
    }
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

  function handleWorkspaceTask(task: WorkspaceTask) {
    if (task.createProject || (task.page === 'workbench' && !source.selectedProject.value)) {
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

  function selectWorkspaceProject(projectId: string) {
    if (!projectId) {
      showCreateProjectModal.value = true
      return
    }
    source.selectedProjectId.value = projectId
    source.syncProjectFormFromSelectedProject()
    workbenchMainPanel.value = 'run'
    navigateTo('workbench')
  }

  function openCreateProjectModal() {
    showCreateProjectModal.value = true
  }

  onMounted(() => {
    if (window.location.pathname === '/') {
      window.history.replaceState({}, '', '/studio')
    }
    syncPageFromHistory()
    window.addEventListener('popstate', syncPageFromHistory)
  })

  onUnmounted(() => {
    source.eventSource.value?.close()
    window.removeEventListener('popstate', syncPageFromHistory)
  })

  return {
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
  }
}
