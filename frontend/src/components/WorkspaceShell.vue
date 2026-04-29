<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NIcon, NInput } from 'naive-ui'
import {
  ChevronDownOutline,
  HelpCircleOutline,
  MailOutline,
  MenuOutline,
  NotificationsOutline,
  ReaderOutline,
  SearchOutline,
  StarOutline,
} from '@vicons/ionicons5'
import type { createDefaultProjectForm } from '../formDefaults'
import type { RuntimeSettings } from '../types'
import {
  displayStorageBackend,
  type PageName,
  type SettingsPanel,
  type WorkbenchMainPanel,
  type WorkbenchSidePanel,
  type WorkspaceNavItem,
} from '../composables/useWorkspace'
import { workspaceNavItems } from '../workspaceConfig'

type ProjectForm = ReturnType<typeof createDefaultProjectForm>

const props = defineProps<{
  busy: boolean
  currentPage: PageName
  llmModeLabel: string
  newProjectForm: ProjectForm
  runtimeSettings: RuntimeSettings | null
  settingsPanel: SettingsPanel
  showCreateProjectModal: boolean
  username: string
  workbenchMainPanel: WorkbenchMainPanel
  workbenchSidePanel: WorkbenchSidePanel
}>()

const emit = defineEmits<{
  createProject: []
  loadEvents: []
  logout: []
  navigate: [page: PageName]
  openEventStream: []
  refresh: []
  setNotice: [message: string]
  'update:showCreateProjectModal': [value: boolean]
  workspaceNav: [item: WorkspaceNavItem]
}>()

const showModal = computed({
  get: () => props.showCreateProjectModal,
  set: (value: boolean) => emit('update:showCreateProjectModal', value),
})

function isWorkspaceNavActive(item: WorkspaceNavItem) {
  if (item.page !== props.currentPage) return false
  if (item.mainPanel && item.mainPanel !== props.workbenchMainPanel) return false
  if (item.sidePanel && item.sidePanel !== props.workbenchSidePanel) return false
  if (item.settingsPanel && item.settingsPanel !== props.settingsPanel) return false
  return true
}
</script>

<template>
  <main class="workspace-page">
    <aside class="sidebar">
      <button class="workspace-brand" type="button" @click="emit('navigate', 'studio')">
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
          @click="emit('workspaceNav', item)"
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
        <n-button type="primary" block @click="emit('refresh')">刷新状态</n-button>
      </section>
    </aside>

    <section class="workspace-main">
      <header class="topbar">
        <n-button quaternary circle aria-label="展开导航" @click="emit('setNotice', '侧边栏当前已展开；移动端折叠导航将在后续版本开放。')">
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
          <n-button quaternary circle aria-label="通知" @click="emit('openEventStream')">
            <template #icon>
              <n-icon :component="NotificationsOutline" />
            </template>
          </n-button>
          <n-button quaternary circle aria-label="站内信" @click="emit('loadEvents')">
            <template #icon>
              <n-icon :component="MailOutline" />
            </template>
          </n-button>
          <n-button quaternary circle aria-label="帮助" @click="emit('navigate', 'settings')">
            <template #icon>
              <n-icon :component="HelpCircleOutline" />
            </template>
          </n-button>

          <button class="user-menu" type="button" @click="emit('logout')">
            <span class="avatar">S</span>
            <span>
              <strong>{{ username }}</strong>
              <em>退出登录</em>
            </span>
            <n-icon :component="ChevronDownOutline" />
          </button>
        </div>
      </header>

      <slot />

      <div v-if="showModal" class="workspace-modal-backdrop" @click.self="showModal = false">
        <section class="workspace-modal">
          <div class="panel-head">
            <h2>创建新作品</h2>
            <button type="button" @click="showModal = false">关闭</button>
          </div>
          <div class="side-panel-body">
            <input v-model="newProjectForm.title" placeholder="作品名称" />
            <input v-model="newProjectForm.genre" placeholder="作品类型" />
            <input v-model.number="newProjectForm.target_chapter_count" type="number" min="1" />
            <input v-model.number="newProjectForm.target_words_per_chapter" type="number" min="1" />
            <textarea v-model="newProjectForm.style_goal" placeholder="风格目标"></textarea>
            <button class="primary-button" type="button" :disabled="busy" @click="emit('createProject')">
              创建并进入生产工作台
            </button>
          </div>
        </section>
      </div>
    </section>
  </main>
</template>
