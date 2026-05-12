<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { publishingApi, type Platform } from '@/api/publishing'

// ── 类型 ─────────────────────────────────────────────────────────

interface LLMProfile {
  id: string
  name: string
  protocol: string
  base_url: string
  api_key_masked: string
  model: string
  temperature: number
  max_tokens: number
  timeout_seconds: number
}

interface StageBinding {
  stage: string
  stage_label: string
  profile_id: string
  model_override: string
  profile_name: string
  model: string
  preset_name: string
}

interface StageInfo {
  stage: string
  label: string
}

// ── 状态 ─────────────────────────────────────────────────────────

const activeTab = ref('llm')
const tabs = [
  { key: 'llm', label: '模型配置', icon: '🧠' },
  { key: 'publish', label: '发布账号', icon: '📡' },
  { key: 'scheduler', label: '定时任务', icon: '⏰' },
  { key: 'system', label: '系统', icon: '💻' },
]

const activePreset = ref('practical')
const profiles = ref<LLMProfile[]>([])
const bindings = ref<StageBinding[]>([])
const stages = ref<StageInfo[]>([])
const loading = ref(false)

const presets = [
  { value: 'practical', label: '实用版', icon: '🔥', desc: '性价比最优，适合日常创作', color: '#22c55e', bg: '#dcfce7' },
  { value: 'flagship', label: '旗舰版', icon: '👑', desc: '顶级模型，最佳质量', color: '#f59e0b', bg: '#fef3c7' },
  { value: 'custom', label: '自定义', icon: '⚙️', desc: '按需配置每个阶段', color: '#6b7280', bg: '#f3f4f6' },
]

const profileOptions = computed(() =>
  profiles.value.map(p => ({ label: `${p.name} (${p.model})`, value: p.id }))
)

// ── 阶段图标 ────────────────────────────────────────────────
const stageIcons: Record<string, string> = {
  outline: '📐', beats: '🎵', chapter: '✍️', post_pipeline: '🔧',
  audit: '🔍', prediction: '📈', default: '🤖',
}

// ── 新建 Profile 表单 ────────────────────────────────────────────

const showNewProfile = ref(false)
const newProfile = ref({
  name: '', protocol: 'openai', base_url: '', api_key: '', model: '',
  temperature: 0.7, max_tokens: 4096, timeout_seconds: 300,
})
const protocolOptions = [
  { value: 'openai', label: 'OpenAI Compatible', icon: '🟢' },
  { value: 'anthropic', label: 'Anthropic', icon: '🟠' },
  { value: 'gemini', label: 'Gemini', icon: '🔵' },
]

const showBindings = ref(false)

// ── API ──────────────────────────────────────────────────────────

async function loadConfig() {
  loading.value = true
  try {
    const resp = await fetch('/api/v1/settings/llm/config')
    const data = await resp.json()
    activePreset.value = data.active_preset
    profiles.value = data.profiles
    bindings.value = data.bindings
    stages.value = data.available_stages
  } catch (e) {
    console.error('加载配置失败', e)
  } finally {
    loading.value = false
  }
}

async function applyPreset(preset: string) {
  if (preset === 'custom') return
  activePreset.value = preset
  await fetch('/api/v1/settings/llm/apply-preset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ preset_name: preset }),
  })
  await loadConfig()
}

async function bindStage(stage: string, profileId: string, modelOverride: string = '') {
  await fetch('/api/v1/settings/llm/bind-stage', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stage, profile_id: profileId, model_override: modelOverride }),
  })
  await loadConfig()
}

async function createProfile() {
  await fetch('/api/v1/settings/llm/profiles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(newProfile.value),
  })
  showNewProfile.value = false
  newProfile.value = { name: '', protocol: 'openai', base_url: '', api_key: '', model: '', temperature: 0.7, max_tokens: 4096, timeout_seconds: 300 }
  await loadConfig()
}

// ── 模型连接测试 ──────────────────────────────────────────────
const message = useMessage()
const testingId = ref<string | null>(null)

async function testProfile(profileId: string) {
  testingId.value = profileId
  try {
    const resp = await fetch(`/api/v1/settings/llm/profiles/${profileId}/test`, { method: 'POST' })
    const data = await resp.json()
    if (resp.ok && data.success !== false) {
      message.success(`连接成功: ${data.message || data.model || 'OK'}`)
    } else {
      message.error(`连接失败: ${data.detail || data.error || '未知错误'}`)
    }
  } catch (e: any) {
    message.error(`测试失败: ${e.message}`)
  } finally {
    testingId.value = null
  }
}

async function deleteProfile(profileId: string) {
  if (!confirm('确定要删除此 Profile？')) return
  await fetch(`/api/v1/settings/llm/profiles/${profileId}`, { method: 'DELETE' })
  await loadConfig()
  message.success('已删除')
}

// ── 编辑 Profile ──────────────────────────────────────────────────
const editingProfile = ref<LLMProfile | null>(null)
const editForm = ref({ name: '', protocol: 'openai', base_url: '', api_key: '', model: '', temperature: 0.7, max_tokens: 4096, timeout_seconds: 300 })

function startEdit(p: LLMProfile) {
  editingProfile.value = p
  editForm.value = {
    name: p.name,
    protocol: p.protocol,
    base_url: p.base_url,
    api_key: '',
    model: p.model,
    temperature: p.temperature,
    max_tokens: p.max_tokens,
    timeout_seconds: p.timeout_seconds,
  }
}

async function saveEdit() {
  if (!editingProfile.value) return
  const payload: Record<string, unknown> = { ...editForm.value }
  if (!payload.api_key) delete payload.api_key  // 不传则保持原 key
  try {
    await fetch(`/api/v1/settings/llm/profiles/${editingProfile.value.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    editingProfile.value = null
    await loadConfig()
    message.success('已保存')
  } catch (e: any) {
    message.error(`保存失败: ${e.message}`)
  }
}

// ── 拉取远程模型列表 ──────────────────────────────────────────────
const fetchingModels = ref(false)
const remoteModels = ref<{ id: string; owned_by: string }[]>([])

async function fetchModels(profileId: string) {
  fetchingModels.value = true
  remoteModels.value = []
  try {
    const resp = await fetch(`/api/v1/settings/llm/fetch-models/${profileId}`)
    if (!resp.ok) {
      const err = await resp.json()
      message.error(`拉取失败: ${err.detail || resp.statusText}`)
      return
    }
    const data = await resp.json()
    remoteModels.value = data.models || []
    message.success(`拉取到 ${data.count} 个模型`)
  } catch (e: any) {
    message.error(`拉取失败: ${e.message}`)
  } finally {
    fetchingModels.value = false
  }
}

function pickModel(modelId: string) {
  editForm.value.model = modelId
  remoteModels.value = []
}

async function fetchModelsForNew() {
  fetchingModels.value = true
  remoteModels.value = []
  const baseUrl = newProfile.value.base_url.trim()
  const apiKey = newProfile.value.api_key.trim()
  try {
    const params = new URLSearchParams({ base_url: baseUrl })
    if (apiKey) params.append('api_key', apiKey)
    const resp = await fetch(`/api/v1/settings/llm/fetch-models?${params}`)
    if (!resp.ok) {
      const err = await resp.json()
      message.error(`拉取失败: ${err.detail || resp.statusText}`)
      return
    }
    const data = await resp.json()
    remoteModels.value = data.models || []
    message.success(`拉取到 ${data.count} 个模型`)
  } catch (e: any) {
    message.error(`拉取失败: ${e.message}`)
  } finally {
    fetchingModels.value = false
  }
}

// ── 发布平台 ──────────────────────────────────────────────────
const platforms = ref<Platform[]>([])
const loadingPlatforms = ref(false)

const platformIcons: Record<string, string> = {
  fanqie: '🍅', qidian: '📖', zongheng: '📕', ciweimao: '🐱',
}

async function loadPlatforms() {
  loadingPlatforms.value = true
  try {
    platforms.value = await publishingApi.listPlatforms()
  } finally {
    loadingPlatforms.value = false
  }
}

// ── 定时任务 ──────────────────────────────────────────────────
const schedulerStatus = ref<{ running: boolean; scheduled_jobs: any[] } | null>(null)

async function loadScheduler() {
  try {
    schedulerStatus.value = await publishingApi.schedulerStatus()
  } catch {}
}

function getBindingForStage(stage: string): StageBinding | undefined {
  return bindings.value.find(b => b.stage === stage)
}

// ── 系统信息 ──────────────────────────────────────────────────
const sysInfo = [
  { label: '前端版本', value: '0.1.0', icon: '📦' },
  { label: '后端地址', value: 'http://127.0.0.1:8100', icon: '🌐' },
  { label: '数据库', value: 'SQLite', icon: '💾' },
  { label: '前端框架', value: 'Vue 3 + Naive UI', icon: '🖼️' },
  { label: '后端框架', value: 'FastAPI + SQLAlchemy', icon: '⚡' },
  { label: '向量存储', value: 'ChromaDB', icon: '🔮' },
]

onMounted(async () => {
  await Promise.all([loadConfig(), loadPlatforms(), loadScheduler()])
})
</script>

<template>
  <div class="st-page">
    <!-- Header -->
    <div class="st-header">
      <div>
        <h1 class="st-title">设置</h1>
        <p class="st-desc">模型配置、发布账号、定时任务和系统信息</p>
      </div>
    </div>

    <!-- Custom Tabs -->
    <div class="st-tabs">
      <button
        v-for="t in tabs" :key="t.key"
        :class="['st-tab', { active: activeTab === t.key }]"
        @click="activeTab = t.key"
      >
        <span class="tab-icon">{{ t.icon }}</span>
        {{ t.label }}
      </button>
    </div>

    <!-- ═══════════ 模型配置 ═══════════ -->
    <div v-show="activeTab === 'llm'" class="st-content">

      <!-- 预设卡片 -->
      <section class="st-section">
        <div class="section-head">
          <h3 class="section-title">预设方案</h3>
          <span class="section-hint">一键应用推荐配置</span>
        </div>
        <div class="preset-grid">
          <div
            v-for="p in presets" :key="p.value"
            :class="['preset-card', { active: activePreset === p.value }]"
            @click="applyPreset(p.value)"
          >
            <div class="preset-top">
              <span class="preset-icon" :style="{ background: p.bg, color: p.color }">{{ p.icon }}</span>
              <span v-if="activePreset === p.value" class="preset-check">✓</span>
            </div>
            <div class="preset-name">{{ p.label }}</div>
            <div class="preset-desc">{{ p.desc }}</div>
          </div>
        </div>
      </section>

      <!-- 阶段绑定 -->
      <section class="st-section">
        <div class="section-head clickable" @click="showBindings = !showBindings">
          <div style="display:flex;align-items:center;gap:8px">
            <h3 class="section-title">阶段模型绑定</h3>
            <span class="binding-count">{{ stages.length }} 个阶段</span>
          </div>
          <span class="toggle-arrow" :class="{ open: showBindings }">▸</span>
        </div>
        <Transition name="fold">
          <div v-if="showBindings" class="binding-list">
            <div v-for="s in stages" :key="s.stage" class="binding-row">
              <div class="binding-label">
                <span class="binding-icon">{{ stageIcons[s.stage] || stageIcons.default }}</span>
                {{ s.label }}
              </div>
              <div class="binding-control">
                <select
                  class="st-select"
                  :value="getBindingForStage(s.stage)?.profile_id || ''"
                  @change="bindStage(s.stage, ($event.target as HTMLSelectElement).value, getBindingForStage(s.stage)?.model_override || '')"
                >
                  <option value="">全局默认</option>
                  <option v-for="po in profileOptions" :key="po.value" :value="po.value">{{ po.label }}</option>
                </select>
              </div>
              <input
                class="st-input st-input-sm model-override-input"
                :value="getBindingForStage(s.stage)?.model_override || ''"
                placeholder="覆盖模型(留空用Profile默认)"
                @change="bindStage(s.stage, getBindingForStage(s.stage)?.profile_id || '', ($event.target as HTMLInputElement).value)"
              />
              <span class="binding-model" v-if="getBindingForStage(s.stage)">
                {{ getBindingForStage(s.stage)?.model }}
              </span>
              <span class="binding-model default" v-else>默认</span>
            </div>
          </div>
        </Transition>
      </section>

      <!-- LLM Profiles -->
      <section class="st-section">
        <div class="section-head">
          <h3 class="section-title">LLM Profiles</h3>
          <button class="btn btn-primary btn-sm" @click="showNewProfile = !showNewProfile">
            {{ showNewProfile ? '取消' : '+ 新建' }}
          </button>
        </div>

        <!-- 新建表单 -->
        <Transition name="fold">
          <div v-if="showNewProfile" class="new-profile-form">
            <div class="form-row">
              <label>名称</label>
              <input v-model="newProfile.name" class="st-input" placeholder="如: My Claude" />
            </div>
            <div class="form-row">
              <label>协议</label>
              <div class="protocol-options">
                <button
                  v-for="po in protocolOptions" :key="po.value"
                  :class="['protocol-btn', { active: newProfile.protocol === po.value }]"
                  @click="newProfile.protocol = po.value"
                >
                  {{ po.icon }} {{ po.label }}
                </button>
              </div>
            </div>
            <div class="form-row">
              <label>Base URL</label>
              <input v-model="newProfile.base_url" class="st-input" placeholder="https://api.openai.com/v1" />
            </div>
            <div class="form-row">
              <label>API Key</label>
              <input v-model="newProfile.api_key" class="st-input" type="password" placeholder="sk-..." />
            </div>
            <div class="form-row">
              <label>模型名</label>
              <div style="display:flex;gap:8px;align-items:center">
                <input v-model="newProfile.model" class="st-input" style="flex:1" placeholder="gpt-4o / claude-sonnet-4-20250514" />
                <button class="btn btn-ghost btn-sm" :disabled="fetchingModels || !newProfile.base_url" @click="fetchModelsForNew">
                  {{ fetchingModels ? '拉取中...' : '拉取模型' }}
                </button>
              </div>
              <div v-if="remoteModels.length" class="model-picker">
                <div v-for="m in remoteModels" :key="m.id" class="model-option" @click="newProfile.model = m.id; remoteModels = []">
                  <span class="model-id">{{ m.id }}</span>
                  <span class="model-owner">{{ m.owned_by }}</span>
                </div>
              </div>
            </div>
            <div class="form-actions">
              <button class="btn btn-ghost" @click="showNewProfile = false">取消</button>
              <button class="btn btn-primary" @click="createProfile">创建 Profile</button>
            </div>
          </div>
        </Transition>

        <!-- Profile 列表 -->
        <div v-if="profiles.length" class="profile-list">
          <div v-for="p in profiles" :key="p.id" class="profile-card">
            <div class="profile-left">
              <div class="profile-avatar" :class="p.protocol">
                {{ p.protocol === 'openai' ? '🟢' : p.protocol === 'anthropic' ? '🟠' : '🔵' }}
              </div>
              <div class="profile-info">
                <div class="profile-name">{{ p.name }}</div>
                <div class="profile-meta">
                  <span class="profile-tag">{{ p.protocol }}</span>
                  <span class="profile-model">{{ p.model }}</span>
                  <span class="profile-key">{{ p.api_key_masked }}</span>
                </div>
              </div>
            </div>
            <div class="profile-actions">
              <button class="btn-icon" title="编辑" @click="startEdit(p)">✏️</button>
              <button
                class="btn-icon"
                :class="{ loading: testingId === p.id }"
                title="测试连接"
                @click="testProfile(p.id)"
              >
                {{ testingId === p.id ? '⏳' : '🔗' }}
              </button>
              <button class="btn-icon danger" title="删除" @click="deleteProfile(p.id)">🗑️</button>
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-else class="empty-state">
          <div class="empty-icon">🤖</div>
          <div class="empty-title">尚未配置任何 LLM Profile</div>
          <div class="empty-desc">点击上方「+ 新建」添加你的第一个模型配置</div>
        </div>
      </section>

      <!-- 编辑 Profile 弹窗 -->
      <Transition name="fade">
        <div v-if="editingProfile" class="modal-overlay" @click.self="editingProfile = null">
          <div class="modal-card">
            <h3 class="modal-title">编辑 Profile: {{ editingProfile.name }}</h3>
            <div class="form-row">
              <label>名称</label>
              <input v-model="editForm.name" class="st-input" />
            </div>
            <div class="form-row">
              <label>协议</label>
              <select v-model="editForm.protocol" class="st-input">
                <option value="openai">OpenAI Compatible</option>
                <option value="anthropic">Anthropic</option>
                <option value="gemini">Gemini</option>
              </select>
            </div>
            <div class="form-row">
              <label>Base URL</label>
              <input v-model="editForm.base_url" class="st-input" placeholder="http://..." />
            </div>
            <div class="form-row">
              <label>API Key</label>
              <input v-model="editForm.api_key" class="st-input" type="password" placeholder="留空不修改" />
            </div>
            <div class="form-row">
              <label>模型</label>
              <div style="display:flex;gap:8px;align-items:center">
                <input v-model="editForm.model" class="st-input" style="flex:1" placeholder="gpt-5.5" />
                <button class="btn btn-ghost btn-sm" :disabled="fetchingModels" @click="fetchModels(editingProfile!.id)">
                  {{ fetchingModels ? '拉取中...' : '拉取模型' }}
                </button>
              </div>
              <div v-if="remoteModels.length" class="model-picker">
                <div v-for="m in remoteModels" :key="m.id" class="model-option" @click="pickModel(m.id)">
                  <span class="model-id">{{ m.id }}</span>
                  <span class="model-owner">{{ m.owned_by }}</span>
                </div>
              </div>
            </div>
            <div class="form-row-inline">
              <div class="form-row" style="flex:1">
                <label>Temperature</label>
                <input v-model.number="editForm.temperature" class="st-input" type="number" step="0.1" min="0" max="2" />
              </div>
              <div class="form-row" style="flex:1">
                <label>Max Tokens</label>
                <input v-model.number="editForm.max_tokens" class="st-input" type="number" step="1024" />
              </div>
              <div class="form-row" style="flex:1">
                <label>Timeout(s)</label>
                <input v-model.number="editForm.timeout_seconds" class="st-input" type="number" />
              </div>
            </div>
            <div class="form-actions">
              <button class="btn btn-ghost" @click="editingProfile = null; remoteModels = []">取消</button>
              <button class="btn btn-primary" @click="saveEdit">保存</button>
            </div>
          </div>
        </div>
      </Transition>
    </div>

    <!-- ═══════════ 发布账号 ═══════════ -->
    <div v-show="activeTab === 'publish'" class="st-content">
      <section class="st-section">
        <div class="section-head">
          <h3 class="section-title">发布平台</h3>
          <span class="section-hint">前往「发布中心」配置登录</span>
        </div>
        <div v-if="platforms.length" class="platform-grid">
          <div v-for="p in platforms" :key="p.id" class="platform-card">
            <div class="platform-icon">{{ platformIcons[p.id] || '📖' }}</div>
            <div class="platform-info">
              <div class="platform-name">{{ p.name }}</div>
              <div class="platform-status" :class="{ ready: p.login_ready }">
                <span class="status-dot"></span>
                {{ p.login_ready ? '已登录' : '未配置' }}
              </div>
            </div>
            <div v-if="p.modified_at" class="platform-time">
              {{ new Date(p.modified_at).toLocaleDateString('zh-CN') }}
            </div>
          </div>
        </div>
        <div v-else class="empty-state small">
          <div class="empty-icon">📡</div>
          <div class="empty-title">暂无平台</div>
          <div class="empty-desc">前往「发布中心」配置平台登录</div>
        </div>
      </section>
    </div>

    <!-- ═══════════ 定时任务 ═══════════ -->
    <div v-show="activeTab === 'scheduler'" class="st-content">
      <section class="st-section">
        <div class="section-head">
          <div style="display:flex;align-items:center;gap:12px">
            <h3 class="section-title">调度器</h3>
            <span v-if="schedulerStatus" class="scheduler-badge" :class="{ running: schedulerStatus.running }">
              <span class="pulse-dot"></span>
              {{ schedulerStatus.running ? '运行中' : '已停止' }}
            </span>
          </div>
          <button class="btn btn-ghost btn-sm" @click="loadScheduler">刷新</button>
        </div>

        <div v-if="schedulerStatus" class="scheduler-stats">
          <div class="stat-item">
            <span class="stat-value">{{ schedulerStatus.scheduled_jobs?.length || 0 }}</span>
            <span class="stat-label">待执行任务</span>
          </div>
        </div>

        <div v-if="schedulerStatus?.scheduled_jobs?.length" class="job-list">
          <div v-for="(job, i) in schedulerStatus.scheduled_jobs" :key="i" class="job-row">
            <span class="job-icon">📋</span>
            <div class="job-info">
              <div class="job-name">{{ job.id || job.job_id }}</div>
              <div class="job-time">{{ job.next_run_time || '立即执行' }}</div>
            </div>
          </div>
        </div>
        <div v-else-if="schedulerStatus" class="empty-state small">
          <div class="empty-icon">✨</div>
          <div class="empty-title">暂无待执行任务</div>
        </div>
      </section>
    </div>

    <!-- ═══════════ 系统 ═══════════ -->
    <div v-show="activeTab === 'system'" class="st-content">
      <section class="st-section">
        <div class="section-head">
          <h3 class="section-title">系统信息</h3>
        </div>
        <div class="sys-grid">
          <div v-for="s in sysInfo" :key="s.label" class="sys-card">
            <span class="sys-icon">{{ s.icon }}</span>
            <div>
              <div class="sys-label">{{ s.label }}</div>
              <div class="sys-value">{{ s.value }}</div>
            </div>
          </div>
        </div>
      </section>

      <section class="st-section">
        <div class="section-head">
          <h3 class="section-title">快捷操作</h3>
        </div>
        <div class="quick-actions">
          <button class="action-btn" @click="loadConfig(); loadPlatforms(); loadScheduler()">
            <span>🔄</span> 刷新所有配置
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.st-page{max-width:860px}

/* Header */
.st-header{margin-bottom:20px}
.st-title{font-size:22px;font-weight:800;color:var(--gray-900);letter-spacing:-.3px}
.st-desc{font-size:13px;color:var(--gray-400);margin-top:6px}

/* Tabs */
.st-tabs{display:flex;gap:6px;margin-bottom:20px;background:var(--gray-100);padding:4px;border-radius:12px}
.st-tab{display:flex;align-items:center;gap:6px;padding:9px 18px;border:none;background:none;
  border-radius:10px;font-size:13px;font-weight:500;color:var(--gray-500);
  cursor:pointer;transition:all .18s;white-space:nowrap}
.st-tab:hover{color:var(--gray-700);background:rgba(255,255,255,.5)}
.st-tab.active{background:#fff;color:var(--gray-800);box-shadow:0 1px 3px rgba(0,0,0,.08);font-weight:600}
.tab-icon{font-size:14px}

/* Content */
.st-content{animation:fadeIn .2s}
@keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}

/* Section */
.st-section{background:#fff;border:1px solid var(--gray-200);border-radius:16px;padding:22px;margin-bottom:16px}
.section-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.section-head.clickable{cursor:pointer;user-select:none}
.section-head.clickable:hover .section-title{color:var(--primary)}
.section-title{font-size:15px;font-weight:600;color:var(--gray-800);transition:color .15s}
.section-hint{font-size:12px;color:var(--gray-400)}

/* Preset */
.preset-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.preset-card{position:relative;padding:18px;border:2px solid var(--gray-200);border-radius:14px;
  cursor:pointer;transition:all .18s}
.preset-card:hover{border-color:var(--gray-300);transform:translateY(-2px);box-shadow:0 4px 16px rgba(0,0,0,.06)}
.preset-card.active{border-color:var(--primary);background:var(--primary-light)}
.preset-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.preset-icon{width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px}
.preset-check{width:20px;height:20px;border-radius:50%;background:var(--primary);color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700}
.preset-name{font-size:14px;font-weight:600;color:var(--gray-800);margin-bottom:2px}
.preset-desc{font-size:12px;color:var(--gray-400);line-height:1.4}

/* Bindings */
.binding-count{font-size:11px;color:var(--gray-400);background:var(--gray-100);padding:2px 8px;border-radius:10px}
.toggle-arrow{font-size:12px;color:var(--gray-400);transition:transform .2s;display:inline-block}
.toggle-arrow.open{transform:rotate(90deg)}
.binding-list{display:flex;flex-direction:column;gap:8px}
.binding-row{display:flex;align-items:center;gap:12px;padding:10px 14px;background:var(--gray-50);border-radius:10px}
.binding-label{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:500;color:var(--gray-700);min-width:140px}
.binding-icon{font-size:16px}
.binding-control{flex:1}
.st-select{width:100%;padding:6px 10px;border:1px solid var(--gray-200);border-radius:var(--radius-xs);
  font-size:13px;color:var(--gray-700);background:#fff;outline:none}
.st-select:focus{border-color:var(--primary)}
.binding-model{font-size:11px;color:var(--primary);background:var(--primary-light);padding:2px 8px;
  border-radius:10px;white-space:nowrap}
.binding-model.default{color:var(--gray-400);background:var(--gray-100)}
.model-override-input{width:140px;font-size:12px!important;padding:4px 8px!important}
.st-input-sm{height:28px;font-size:12px}

/* Profile list */
.profile-list{display:flex;flex-direction:column;gap:8px}
.profile-card{display:flex;align-items:center;justify-content:space-between;padding:16px 18px;
  background:var(--gray-50);border-radius:12px;transition:all .12s}
.profile-card:hover{background:var(--gray-100)}
.profile-left{display:flex;align-items:center;gap:12px}
.profile-avatar{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;
  justify-content:center;font-size:18px;background:#fff;border:1px solid var(--gray-200)}
.profile-info{display:flex;flex-direction:column;gap:2px}
.profile-name{font-size:14px;font-weight:600;color:var(--gray-800)}
.profile-meta{display:flex;align-items:center;gap:8px;font-size:12px}
.profile-tag{color:var(--primary);background:var(--primary-light);padding:1px 6px;border-radius:6px;font-weight:500}
.profile-model{color:var(--gray-600)}
.profile-key{color:var(--gray-300)}
.profile-actions{display:flex;gap:4px}
.btn-icon{width:32px;height:32px;border:none;background:none;border-radius:var(--radius-xs);
  cursor:pointer;font-size:14px;display:flex;align-items:center;justify-content:center;transition:all .12s}
.btn-icon:hover{background:var(--gray-200)}
.btn-icon.danger:hover{background:#fee2e2}
.btn-icon.loading{opacity:.6;pointer-events:none}

/* New Profile form */
.new-profile-form{padding:18px;background:var(--gray-50);border-radius:14px;margin-bottom:16px;
  border:1px dashed var(--gray-300)}
.form-row{margin-bottom:14px}
.form-row label{display:block;font-size:12px;font-weight:500;color:var(--gray-500);margin-bottom:6px}
.st-input{width:100%;padding:8px 12px;border:1px solid var(--gray-200);border-radius:var(--radius-xs);
  font-size:13px;color:var(--gray-700);outline:none;background:#fff;transition:border-color .15s}
.st-input:focus{border-color:var(--primary)}
.st-input::placeholder{color:var(--gray-300)}
.protocol-options{display:flex;gap:8px}
.protocol-btn{padding:6px 14px;border:1px solid var(--gray-200);border-radius:var(--radius-xs);
  background:#fff;font-size:12px;cursor:pointer;transition:all .12s;color:var(--gray-600)}
.protocol-btn:hover{border-color:var(--gray-300)}
.protocol-btn.active{border-color:var(--primary);background:var(--primary-light);color:var(--primary);font-weight:500}
.form-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:16px}

/* Button sizes */
.btn-sm{padding:5px 14px;font-size:12px}

/* Empty state */
.empty-state{text-align:center;padding:48px 20px}
.empty-state.small{padding:32px 20px}
.empty-icon{font-size:32px;margin-bottom:10px}
.empty-title{font-size:14px;font-weight:600;color:var(--gray-500);margin-bottom:4px}
.empty-desc{font-size:12px;color:var(--gray-400)}

/* Platform grid */
.platform-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.platform-card{display:flex;align-items:center;gap:14px;padding:18px;background:var(--gray-50);
  border-radius:14px;transition:all .15s}
.platform-card:hover{background:var(--gray-100);box-shadow:0 2px 8px rgba(0,0,0,.03)}
.platform-card:hover{background:var(--gray-100)}
.platform-icon{font-size:28px;width:48px;height:48px;background:#fff;border-radius:12px;
  display:flex;align-items:center;justify-content:center;border:1px solid var(--gray-200)}
.platform-info{flex:1}
.platform-name{font-size:14px;font-weight:600;color:var(--gray-800);margin-bottom:4px}
.platform-status{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--gray-400)}
.platform-status.ready{color:var(--success)}
.status-dot{width:6px;height:6px;border-radius:50%;background:currentColor}
.platform-time{font-size:11px;color:var(--gray-300)}

/* Scheduler */
.scheduler-badge{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:12px;
  font-size:12px;font-weight:500;background:var(--gray-100);color:var(--gray-500)}
.scheduler-badge.running{background:#dcfce7;color:#16a34a}
.pulse-dot{width:6px;height:6px;border-radius:50%;background:currentColor}
.scheduler-badge.running .pulse-dot{animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

.scheduler-stats{display:flex;gap:24px;margin-bottom:16px}
.stat-item{display:flex;flex-direction:column;align-items:center;padding:18px 28px;
  background:var(--gray-50);border-radius:14px;min-width:120px}
.stat-value{font-size:28px;font-weight:700;color:var(--gray-800)}
.stat-label{font-size:12px;color:var(--gray-400);margin-top:2px}

.job-list{display:flex;flex-direction:column;gap:6px}
.job-row{display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--gray-50);border-radius:10px}
.job-icon{font-size:16px}
.job-info{flex:1}
.job-name{font-size:13px;font-weight:500;color:var(--gray-700)}
.job-time{font-size:11px;color:var(--gray-400)}

/* System */
.sys-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.sys-card{display:flex;align-items:center;gap:14px;padding:16px;background:var(--gray-50);border-radius:12px;transition:all .12s}
.sys-card:hover{background:var(--gray-100)}
.sys-icon{font-size:20px;width:40px;height:40px;background:#fff;border-radius:10px;
  display:flex;align-items:center;justify-content:center;border:1px solid var(--gray-200);flex-shrink:0}
.sys-label{font-size:12px;color:var(--gray-400);margin-bottom:2px}
.sys-value{font-size:13px;font-weight:500;color:var(--gray-700)}

.quick-actions{display:flex;gap:8px}
.action-btn{display:flex;align-items:center;gap:8px;padding:10px 20px;background:var(--gray-50);
  border:1px solid var(--gray-200);border-radius:12px;font-size:13px;color:var(--gray-600);
  cursor:pointer;transition:all .15s}
.action-btn:hover{background:var(--gray-100);border-color:var(--gray-300);box-shadow:0 2px 8px rgba(0,0,0,.04)}

/* Fold transition */
.fold-enter-active,.fold-leave-active{transition:all .2s ease;overflow:hidden}
.fold-enter-from,.fold-leave-to{opacity:0;max-height:0;margin-top:0;margin-bottom:0;padding-top:0;padding-bottom:0}
.fold-enter-to,.fold-leave-from{opacity:1;max-height:800px}

/* Modal */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;z-index:1000;backdrop-filter:blur(2px)}
.modal-card{background:#fff;border-radius:16px;padding:28px;width:520px;max-width:90vw;max-height:80vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.15)}
.modal-title{font-size:16px;font-weight:700;margin-bottom:18px;color:var(--gray-800)}
.form-row-inline{display:flex;gap:12px}

/* Model picker dropdown */
.model-picker{margin-top:8px;max-height:180px;overflow-y:auto;border:1px solid var(--gray-200);border-radius:10px;background:var(--gray-50)}
.model-option{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;cursor:pointer;transition:background .12s;border-bottom:1px solid var(--gray-100)}
.model-option:last-child{border-bottom:none}
.model-option:hover{background:var(--primary-light,#ede9fe)}
.model-id{font-size:13px;font-weight:500;color:var(--gray-800)}
.model-owner{font-size:11px;color:var(--gray-400)}

/* Fade transition */
.fade-enter-active,.fade-leave-active{transition:opacity .2s}
.fade-enter-from,.fade-leave-to{opacity:0}
</style>
