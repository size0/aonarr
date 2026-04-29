<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NIcon } from 'naive-ui'
import { DocumentTextOutline, SparklesOutline, StatsChartOutline } from '@vicons/ionicons5'
import type { createDefaultLLMForm } from '../formDefaults'
import type { LLMProfile, PromptTemplate, RuntimeSettings } from '../types'
import {
  displayProfileName,
  displayProviderType,
  displayRuntimeMode,
  displayStatus,
  displayStorageBackend,
  type SettingsPanel,
} from '../composables/useWorkspace'

type LLMForm = ReturnType<typeof createDefaultLLMForm>

const props = defineProps<{
  llmForm: LLMForm
  llmProfiles: LLMProfile[]
  promptTemplates: PromptTemplate[]
  runtimeSettings: RuntimeSettings | null
  settingsPanel: SettingsPanel
}>()

const emit = defineEmits<{
  createLLMProfile: []
  refresh: []
  resetPromptTemplate: [templateId: string]
  savePromptTemplate: [template: PromptTemplate]
  testLLM: [profileId: string]
  'update:settingsPanel': [value: SettingsPanel]
}>()

const settingsPanelModel = computed({
  get: () => props.settingsPanel,
  set: (value: SettingsPanel) => emit('update:settingsPanel', value),
})
</script>

<template>
  <section class="content settings-content">
    <div class="welcome-row">
      <div>
        <h1>系统设置</h1>
        <p>模型配置、提示词模板和运行环境从作品首页拆出，集中在这里维护。</p>
      </div>
      <n-button secondary type="primary" @click="emit('refresh')">刷新设置</n-button>
    </div>

    <section class="settings-layout">
      <aside class="panel settings-nav-panel">
        <button :class="{ active: settingsPanelModel === 'llm' }" type="button" @click="settingsPanelModel = 'llm'">
          <n-icon :component="SparklesOutline" />
          模型配置
        </button>
        <button :class="{ active: settingsPanelModel === 'prompts' }" type="button" @click="settingsPanelModel = 'prompts'">
          <n-icon :component="DocumentTextOutline" />
          提示词模板
        </button>
        <button :class="{ active: settingsPanelModel === 'runtime' }" type="button" @click="settingsPanelModel = 'runtime'">
          <n-icon :component="StatsChartOutline" />
          运行环境
        </button>
      </aside>

      <section class="panel settings-detail-panel">
        <div v-if="settingsPanelModel === 'llm'" class="settings-section">
          <div class="panel-head">
            <h2>模型配置</h2>
            <button type="button" @click="emit('refresh')">刷新</button>
          </div>
          <div class="settings-two-column">
            <div class="engine-box">
              <h3>创建模型配置</h3>
              <input v-model="llmForm.name" placeholder="配置名称" />
              <input v-model="llmForm.base_url" placeholder="接口地址" />
              <input v-model="llmForm.model" placeholder="模型名称" />
              <input v-model="llmForm.api_key" placeholder="接口密钥" type="password" />
              <button class="primary-button" type="button" @click="emit('createLLMProfile')">创建模型</button>
            </div>
            <div class="profile-list">
              <button v-for="profile in llmProfiles" :key="profile.id" type="button" @click="emit('testLLM', profile.id)">
                <strong>{{ displayProfileName(profile.name) }}</strong>
                <span>{{ displayProviderType(profile.provider_type) }} · {{ profile.model }}</span>
                <em>{{ displayStatus(profile.status) }}</em>
              </button>
            </div>
          </div>
        </div>

        <div v-else-if="settingsPanelModel === 'prompts'" class="settings-section">
          <div class="panel-head">
            <h2>提示词中心</h2>
            <button type="button" @click="emit('refresh')">刷新模板</button>
          </div>
          <article v-for="template in promptTemplates" :key="template.id" class="template-card">
            <div class="template-header">
              <div>
                <h3>{{ template.name }}</h3>
                <p>{{ template.id }} · {{ template.purpose }}</p>
              </div>
              <div class="button-row">
                <button class="small-button" type="button" @click="emit('savePromptTemplate', template)">保存</button>
                <button class="small-button" type="button" @click="emit('resetPromptTemplate', template.id)">重置</button>
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
            <button type="button" @click="emit('refresh')">刷新</button>
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
</template>
