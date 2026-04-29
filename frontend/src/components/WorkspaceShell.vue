<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NIcon, NInput } from 'naive-ui'
import {
  BulbOutline,
  ChevronDownOutline,
  DocumentTextOutline,
  HelpCircleOutline,
  ImageOutline,
  MailOutline,
  MenuOutline,
  NotificationsOutline,
  ReaderOutline,
  SearchOutline,
  SettingsOutline,
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
  activeWorkspaceNavLabel: string
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

const genreOptions = ['玄幻', '都市', '科幻', '悬疑', '武侠', '历史', '仙侠', '现实']
const styleTags = ['女强', '爽文', '群像', '古风', '成长', '悬疑', '热血', '轻松']

const completedCreateFields = computed(() => [
  props.newProjectForm.title.trim(),
  props.newProjectForm.genre.trim(),
  props.newProjectForm.style_goal.trim(),
].filter(Boolean).length)

function applyStyleTag(tag: string) {
  if (props.newProjectForm.style_goal.includes(tag)) return
  props.newProjectForm.style_goal = [props.newProjectForm.style_goal, tag].filter(Boolean).join(' · ')
}

function notifyCreateSetting(message: string) {
  emit('setNotice', message)
}

function isWorkspaceNavActive(item: WorkspaceNavItem) {
  return item.label === props.activeWorkspaceNavLabel
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

      <div v-if="showModal" class="workspace-modal-backdrop create-novel-backdrop" @click.self="showModal = false">
        <section class="create-novel-modal" aria-label="新建小说">
          <header class="create-novel-header">
            <button class="create-back-button" type="button" @click="showModal = false">‹ 返回</button>
            <div>
              <h1>新建小说</h1>
              <p>创建你的新作品，开启创作之旅 ✨</p>
            </div>
            <button class="create-close-button" type="button" aria-label="关闭" @click="showModal = false">×</button>
          </header>

          <div class="create-stepper" aria-label="创建步骤">
            <span class="active"><em>1</em>基本信息</span>
            <span><em>2</em>故事设定</span>
            <span><em>3</em>其他设置</span>
          </div>

          <div class="create-novel-layout">
            <form class="create-novel-card" @submit.prevent="emit('createProject')">
              <div class="create-section-head">
                <h2>作品基本信息</h2>
                <span>{{ completedCreateFields }}/3 必填项</span>
              </div>

              <div class="create-form-grid">
                <label class="create-field">
                  <span>作品名称 <em>*</em></span>
                  <input v-model="newProjectForm.title" required maxlength="30" placeholder="请输入作品名称（2-30个字）" />
                  <small>{{ newProjectForm.title.length }}/30</small>
                </label>

                <label class="create-field">
                  <span>作品分类 <em>*</em></span>
                  <select v-model="newProjectForm.genre" required>
                    <option v-for="genre in genreOptions" :key="genre" :value="genre">{{ genre }}</option>
                  </select>
                </label>

                <label class="create-field wide">
                  <span>作品简介 <em>*</em></span>
                  <textarea
                    v-model="newProjectForm.style_goal"
                    required
                    maxlength="500"
                    placeholder="请输入作品简介、主线目标、人物冲突或你希望保持的创作风格"
                  ></textarea>
                  <small>{{ newProjectForm.style_goal.length }}/500</small>
                </label>

                <label class="create-field">
                  <span>目标章节数</span>
                  <input v-model.number="newProjectForm.target_chapter_count" type="number" min="1" />
                </label>

                <label class="create-field">
                  <span>每章目标字数</span>
                  <input v-model.number="newProjectForm.target_words_per_chapter" type="number" min="500" />
                </label>

                <div class="create-field wide">
                  <span>作品标签</span>
                  <div class="create-tag-list">
                    <button v-for="tag in styleTags" :key="tag" type="button" @click="applyStyleTag(tag)">{{ tag }}</button>
                  </div>
                </div>

                <div class="create-field wide">
                  <span>封面图</span>
                  <div class="cover-uploader" @click="notifyCreateSetting('封面上传将在后续版本开放；当前可先创建作品。')">
                    <n-icon :component="ImageOutline" />
                    <strong>点击上传封面</strong>
                    <p>支持 JPG、PNG，建议尺寸 600×800px</p>
                  </div>
                </div>

                <div class="create-field wide">
                  <span>作品状态</span>
                  <div class="visibility-options">
                    <button class="selected" type="button" @click="notifyCreateSetting('作品将以公开连载状态创建。')">
                      <strong>公开连载</strong>
                      <small>作品公开，读者可见并追更</small>
                    </button>
                    <button type="button" @click="notifyCreateSetting('私密创作将在后续版本开放。')">
                      <strong>私密创作</strong>
                      <small>仅自己可见，专注创作</small>
                    </button>
                  </div>
                </div>
              </div>

              <footer class="create-actions">
                <button class="create-secondary-button" type="button" @click="showModal = false">取消</button>
                <button class="create-primary-button" type="submit" :disabled="busy">
                  {{ busy ? '创建中...' : '创建并进入工作台' }}
                </button>
              </footer>
            </form>

            <aside class="create-helper-column">
              <section class="create-helper-card">
                <div class="helper-title">
                  <n-icon :component="BulbOutline" />
                  <strong>创作小贴士</strong>
                </div>
                <h3>好的开始是成功的一半</h3>
                <p>尽量用一句话说明作品核心卖点，再补充主角目标、主要冲突和风格方向。</p>
                <ul>
                  <li>选择合适的分类和标签</li>
                  <li>写一个吸引人的作品简介</li>
                  <li>设置目标章节数和每章字数</li>
                </ul>
              </section>

              <section class="create-helper-card">
                <div class="helper-title">
                  <n-icon :component="SettingsOutline" />
                  <strong>创作设置</strong>
                </div>
                <button type="button" @click="notifyCreateSetting('字数统计会在章节生成后自动更新。')">
                  <span><n-icon :component="DocumentTextOutline" />字数统计</span>
                  <em class="on">开</em>
                </button>
                <button type="button" @click="notifyCreateSetting('自动保存会跟随浏览器本地状态逐步增强。')">
                  <span><n-icon :component="StarOutline" />自动保存</span>
                  <em class="on">开</em>
                </button>
                <button type="button" @click="notifyCreateSetting('创作提醒将在任务中心中开放。')">
                  <span><n-icon :component="HelpCircleOutline" />创作提醒</span>
                  <em>关</em>
                </button>
              </section>

              <section class="create-helper-card subtle">
                <div class="helper-title">
                  <n-icon :component="ReaderOutline" />
                  <strong>创建后你可以</strong>
                </div>
                <p>创建章节、完善故事设定、配置提示词模板，并进入自动连载生产流程。</p>
              </section>
            </aside>
          </div>
        </section>
      </div>
    </section>
  </main>
</template>
