import type { Component } from 'vue'

export type PageName = 'studio' | 'login' | 'index' | 'workbench' | 'settings'
export type WorkbenchMainPanel = 'run' | 'plans' | 'drafts' | 'events' | 'world'
export type WorkbenchSidePanel = 'bible' | 'project' | 'export'
export type SettingsPanel = 'llm' | 'prompts' | 'runtime'
export type WorkspaceIndexPanel = 'overview' | 'works' | 'stats' | 'fans' | 'tasks'

export type WorkspaceNavItem = {
  label: string
  icon: Component
  page: PageName
  badge?: string
  indexPanel?: WorkspaceIndexPanel
  mainPanel?: WorkbenchMainPanel
  sidePanel?: WorkbenchSidePanel
  settingsPanel?: SettingsPanel
}

export type WorkspaceTask = {
  title: string
  progress: string
  badge: string
  type: 'success' | 'warning' | 'info'
  tone: string
  createProject?: boolean
  page?: PageName
  mainPanel?: WorkbenchMainPanel
  sidePanel?: WorkbenchSidePanel
}

export type WorkspaceWork = {
  id: string
  title: string
  status: string
  statusType: 'success' | 'info'
  meta: string
  words: string
  reads: string
  favorites: string
  updated: string
  cover: string
  coverTone: string
}

export function pageFromPath(pathname: string): PageName {
  if (pathname === '/login') return 'login'
  if (pathname === '/index') return 'index'
  if (pathname === '/workbench') return 'workbench'
  if (pathname === '/settings') return 'settings'
  return 'studio'
}

export function requiresAuth(page: PageName) {
  return page === 'index' || page === 'workbench' || page === 'settings'
}

export function displayStatus(status?: string | null) {
  if (!status) return '未知'
  const statusMap: Record<string, string> = {
    active: '进行中',
    draft: '草稿',
    pending: '等待中',
    queued: '排队中',
    running: '运行中',
    paused: '已暂停',
    pause: '暂停',
    resume: '继续',
    completed: '已完成',
    succeeded: '已成功',
    failed: '失败',
    cancelled: '已取消',
    cancel: '取消',
    accepted: '已通过',
    needs_revision: '需修订',
    rejected: '已拒绝',
    planned: '已规划',
    generated: '已生成',
    in_progress: '进行中',
    untested: '未测试',
    ready: '已就绪',
    enabled: '已启用',
    disabled: '已停用',
  }
  return statusMap[status] ?? status.replace(/_/g, ' ')
}

export function displayProviderType(providerType?: string | null) {
  if (!providerType) return '未知供应商'
  const providerMap: Record<string, string> = {
    openai_compatible: 'OpenAI 兼容接口',
    openai: 'OpenAI 官方接口',
    deepseek: 'DeepSeek 接口',
    mock: '模拟模型',
  }
  return providerMap[providerType] ?? providerType.replace(/_/g, ' ')
}

export function displayRuntimeMode(mode?: string | null) {
  if (!mode) return '未知'
  const modeMap: Record<string, string> = {
    mock: '模拟模式',
    live: '真实调用',
  }
  return modeMap[mode] ?? mode
}

export function displayStorageBackend(storageBackend?: string | null) {
  if (!storageBackend) return '未知'
  const storageMap: Record<string, string> = {
    json: '本地 JSON',
    postgres: 'PostgreSQL',
  }
  return storageMap[storageBackend] ?? storageBackend
}

export function displayProfileName(name: string) {
  if (name === 'Local OpenAI Compatible') return '本地 OpenAI 兼容模型'
  return name
}

export function displayEventType(eventType?: string | null) {
  if (!eventType) return '事件'
  const eventMap: Record<string, string> = {
    run_started: '运行开始',
    run_completed: '运行完成',
    run_failed: '运行失败',
    chapter_planned: '章节已规划',
    draft_generated: '草稿已生成',
    draft_reviewed: '草稿已审阅',
    revision_requested: '请求修订',
    cost_updated: '成本更新',
    info: '信息',
    warning: '警告',
    error: '错误',
  }
  return eventMap[eventType] ?? eventType.replace(/_/g, ' ')
}

export function displayReadinessSection(section?: string | null) {
  if (!section) return '检查项'
  const sectionMap: Record<string, string> = {
    premise: '故事前提',
    world_summary: '世界观摘要',
    tone_profile: '文风设定',
    llm_profile: '模型配置',
    prompt_templates: '提示词模板',
  }
  return sectionMap[section] ?? section.replace(/_/g, ' ')
}
