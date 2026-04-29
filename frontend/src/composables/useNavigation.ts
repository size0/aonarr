import { onMounted, onUnmounted, ref, type Ref } from 'vue'
import type { Project } from '../types'
import {
  pageFromPath,
  requiresAuth,
  type PageName,
  type SettingsPanel,
  type WorkspaceIndexPanel,
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

const workspaceIndexNavLabels: Record<WorkspaceIndexPanel, string> = {
  overview: '工作台',
  works: '作品管理',
  stats: '数据统计',
  fans: '粉丝互动',
  tasks: '任务中心',
}

export function useNavigation(source: UseNavigationSource) {
  const currentPage = ref<PageName>(pageFromPath(window.location.pathname))
  const showCreateProjectModal = ref(false)
  const workbenchMainPanel = ref<WorkbenchMainPanel>('run')
  const workbenchSidePanel = ref<WorkbenchSidePanel>('bible')
  const settingsPanel = ref<SettingsPanel>('llm')
  const workspaceIndexPanel = ref<WorkspaceIndexPanel>('overview')
  const activeWorkspaceNavLabel = ref('')

  function defaultWorkspaceNavLabel(page: PageName) {
    if (page === 'index') return '工作台'
    if (page === 'settings') return '设置'
    if (page === 'workbench') {
      if (workbenchMainPanel.value === 'events') return '运行日志'
      if (workbenchMainPanel.value === 'drafts') return '章节管理'
      if (workbenchMainPanel.value === 'plans') return '大纲管理'
      if (workbenchMainPanel.value === 'world') return '世界观设定'
      return '成本管理'
    }
    return ''
  }

  function navigateTo(page: PageName, workspaceNavLabel?: string) {
    currentPage.value = page
    if (page !== 'index') {
      workspaceIndexPanel.value = 'overview'
    }
    activeWorkspaceNavLabel.value = workspaceNavLabel ?? defaultWorkspaceNavLabel(page)
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
    workspaceIndexPanel.value = 'overview'
    activeWorkspaceNavLabel.value = defaultWorkspaceNavLabel(currentPage.value)
    if (requiresAuth(currentPage.value) && !source.token.value) {
      navigateTo('login')
    }
    if (requiresAuth(currentPage.value) && source.token.value) {
      source.loadWorkspace().catch((error) => source.setNotice(errorMessage(error)))
    }
  }

  function handleWorkspaceNav(item: WorkspaceNavItem) {
    if (item.indexPanel) {
      workspaceIndexPanel.value = item.indexPanel
    }
    if (item.mainPanel) {
      workbenchMainPanel.value = item.mainPanel
    }
    if (item.sidePanel) {
      workbenchSidePanel.value = item.sidePanel
    }
    if (item.settingsPanel) {
      settingsPanel.value = item.settingsPanel
    }
    navigateTo(item.page, item.label)
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

  function selectWorkspaceIndexPanel(panel: WorkspaceIndexPanel) {
    workspaceIndexPanel.value = panel
    navigateTo('index', workspaceIndexNavLabels[panel])
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
    activeWorkspaceNavLabel,
    currentPage,
    handleWorkspaceNav,
    handleWorkspaceTask,
    navigateTo,
    openCreateProjectModal,
    selectWorkspaceProject,
    selectWorkspaceIndexPanel,
    settingsPanel,
    showCreateProjectModal,
    workspaceIndexPanel,
    workbenchMainPanel,
    workbenchSidePanel,
  }
}
