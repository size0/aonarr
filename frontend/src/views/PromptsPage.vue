<script setup lang="ts">
import { NModal, useMessage } from 'naive-ui'
import { ref, computed, onMounted } from 'vue'
import { promptsApi, type PromptTemplate, type StageMeta } from '@/api/prompts'

const message = useMessage()
const loading = ref(false)
const stages = ref<Record<string, StageMeta>>({})
const prompts = ref<PromptTemplate[]>([])
const activeStage = ref<string | null>(null)
const saving = ref(false)
const searchQuery = ref('')

/* ── Editor modal ────────────────────────────────────────── */
const showEditor = ref(false)
const editMode = ref<'create' | 'edit'>('create')
const editForm = ref({ id: '', stage: '', name: '', content: '', description: '', is_active: true })

const stageEntries = computed(() =>
  Object.entries(stages.value).map(([k, v]) => ({ key: k, ...v }))
)

const filteredPrompts = computed(() => {
  let list = prompts.value
  if (activeStage.value) list = list.filter(p => p.stage === activeStage.value)
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(p => p.name.toLowerCase().includes(q) || p.description?.toLowerCase().includes(q))
  }
  return list
})

function stageCount(stage: string) {
  return prompts.value.filter(p => p.stage === stage).length
}

/* ── Load ────────────────────────────────────────────────── */
async function loadAll() {
  loading.value = true
  try {
    const [s, p] = await Promise.all([promptsApi.stages(), promptsApi.list()])
    stages.value = s
    prompts.value = p
  } catch { /* empty */ } finally { loading.value = false }
}
onMounted(loadAll)

/* ── CRUD actions ────────────────────────────────────────── */
function openCreate(stage?: string) {
  editMode.value = 'create'
  editForm.value = { id: '', stage: stage || '', name: '', content: '', description: '', is_active: true }
  showEditor.value = true
}

function openEdit(p: PromptTemplate) {
  editMode.value = 'edit'
  editForm.value = { id: p.id, stage: p.stage, name: p.name, content: p.content, description: p.description, is_active: p.is_active }
  showEditor.value = true
}

async function savePrompt() {
  if (!editForm.value.stage) { message.warning('请选择阶段'); return }
  if (!editForm.value.name.trim()) { message.warning('请输入名称'); return }
  saving.value = true
  try {
    if (editMode.value === 'create') {
      await promptsApi.create({
        stage: editForm.value.stage,
        name: editForm.value.name,
        content: editForm.value.content,
        description: editForm.value.description,
        is_active: editForm.value.is_active,
      })
      message.success('创建成功')
    } else {
      await promptsApi.update(editForm.value.id, {
        name: editForm.value.name,
        content: editForm.value.content,
        description: editForm.value.description,
        is_active: editForm.value.is_active,
      })
      message.success('保存成功')
    }
    showEditor.value = false
    await loadAll()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '操作失败')
  } finally { saving.value = false }
}

async function deletePrompt(p: PromptTemplate) {
  if (!confirm(`确定删除「${p.name}」?`)) return
  try {
    await promptsApi.delete(p.id)
    message.success('已删除')
    await loadAll()
  } catch { message.error('删除失败') }
}

async function duplicatePrompt(p: PromptTemplate) {
  try {
    await promptsApi.duplicate(p.id)
    message.success('已复制')
    await loadAll()
  } catch { message.error('复制失败') }
}

function getStageMeta(stage: string): StageMeta {
  return stages.value[stage] || { label: stage, icon: '📄', color: '#6b7280', bg: '#f3f4f6' }
}

function contentPreview(content: string): string {
  if (!content) return ''
  return content.replace(/\n/g, ' ').slice(0, 80)
}
</script>

<template>
  <div class="pg">
    <!-- Header -->
    <div class="pg-header">
      <div>
        <h1 class="pg-title">提示词</h1>
        <p class="pg-desc">管理提示词模板，提升创作效率与质量</p>
      </div>
      <button class="btn btn-primary" @click="openCreate()">+ 新建提示词</button>
    </div>

    <!-- Stage Cards -->
    <section class="pg-section">
      <div class="section-head">
        <h3 class="section-title">提示词管理</h3>
      </div>
      <div class="stage-grid" v-if="!loading">
        <div
          v-for="entry in stageEntries" :key="entry.key"
          :class="['stage-card', { active: activeStage === entry.key }]"
          @click="activeStage = activeStage === entry.key ? null : entry.key"
        >
          <div class="sc-top">
            <div class="sc-icon" :style="{ background: entry.bg, color: entry.color }">{{ entry.icon }}</div>
            <span class="sc-count" :class="{ 'has-items': stageCount(entry.key) > 0 }">{{ stageCount(entry.key) }}</span>
          </div>
          <div class="sc-name">{{ entry.label }}</div>
          <div class="sc-sub">{{ stageCount(entry.key) }} 个模板</div>
        </div>
      </div>
      <div v-else class="loading-placeholder">
        <div v-for="i in 6" :key="i" class="skeleton-card"></div>
      </div>
    </section>

    <!-- Prompt List -->
    <section class="pg-section">
      <div class="section-head">
        <div class="section-left">
          <h3 class="section-title">
            {{ activeStage ? getStageMeta(activeStage).label : '全部模板' }}
          </h3>
          <span class="section-count">{{ filteredPrompts.length }} 条</span>
          <button v-if="activeStage" class="clear-filter" @click="activeStage = null">清除筛选</button>
        </div>
        <div class="search-wrap">
          <span class="search-icon">🔍</span>
          <input v-model="searchQuery" class="search-input" placeholder="搜索模板名称..." />
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="filteredPrompts.length === 0 && !loading" class="empty-state">
        <div class="empty-visual">📝</div>
        <div class="empty-title">{{ searchQuery ? '没有匹配的模板' : '暂无提示词模板' }}</div>
        <div class="empty-desc">{{ searchQuery ? '尝试其他关键词' : '创建你的第一个提示词模板，开始定制AI创作流程' }}</div>
        <button v-if="!searchQuery" class="btn btn-primary btn-sm" @click="openCreate(activeStage || undefined)">
          + 创建模板
        </button>
      </div>

      <!-- Prompt items -->
      <div v-else class="prompt-list">
        <div v-for="p in filteredPrompts" :key="p.id" class="pl-row">
          <div class="pl-icon-col">
            <div class="pl-badge" :style="{ background: getStageMeta(p.stage).bg, color: getStageMeta(p.stage).color }">
              {{ getStageMeta(p.stage).icon }}
            </div>
          </div>

          <div class="pl-main">
            <div class="pl-title-row">
              <span class="pl-name">{{ p.name }}</span>
              <span class="pl-version">v{{ p.version }}</span>
              <span v-if="!p.is_active" class="pl-status off">停用</span>
              <span v-else class="pl-status on">启用</span>
            </div>
            <div class="pl-desc" v-if="p.description">{{ p.description }}</div>
            <div class="pl-content-preview" v-else-if="p.content">{{ contentPreview(p.content) }}...</div>
          </div>

          <div class="pl-stage-col">
            <span class="pl-stage-tag" :style="{ color: getStageMeta(p.stage).color, background: getStageMeta(p.stage).bg }">
              {{ getStageMeta(p.stage).label }}
            </span>
          </div>

          <div class="pl-date-col">
            <span class="pl-date">{{ p.created_at?.slice(0, 10) }}</span>
          </div>

          <div class="pl-actions">
            <button class="act-btn" title="编辑" @click.stop="openEdit(p)">✏️</button>
            <button class="act-btn" title="复制" @click.stop="duplicatePrompt(p)">📋</button>
            <button class="act-btn danger" title="删除" @click.stop="deletePrompt(p)">🗑️</button>
          </div>
        </div>
      </div>
    </section>

    <!-- Editor Modal -->
    <n-modal v-model:show="showEditor" :mask-closable="false" style="width:680px;max-width:94vw">
      <div class="editor-modal">
        <div class="em-header">
          <h3>{{ editMode === 'create' ? '新建提示词' : '编辑提示词' }}</h3>
          <button class="em-close" @click="showEditor = false">✕</button>
        </div>

        <div class="em-body">
          <div class="em-row">
            <label>阶段</label>
            <div v-if="editMode === 'edit'" class="em-readonly">
              <span class="em-stage-badge" :style="{ color: getStageMeta(editForm.stage).color, background: getStageMeta(editForm.stage).bg }">
                {{ getStageMeta(editForm.stage).icon }} {{ getStageMeta(editForm.stage).label }}
              </span>
            </div>
            <div v-else class="stage-picker">
              <button
                v-for="entry in stageEntries" :key="entry.key"
                :class="['sp-btn', { active: editForm.stage === entry.key }]"
                :style="editForm.stage === entry.key ? { borderColor: entry.color, background: entry.bg, color: entry.color } : {}"
                @click="editForm.stage = entry.key"
              >
                {{ entry.icon }} {{ entry.label }}
              </button>
            </div>
          </div>

          <div class="em-row">
            <label>名称</label>
            <input v-model="editForm.name" class="em-input" placeholder="如: 都市文标准生成模板" />
          </div>

          <div class="em-row">
            <label>描述 <span class="label-hint">可选</span></label>
            <input v-model="editForm.description" class="em-input" placeholder="简要说明此模板的用途和适用场景" />
          </div>

          <div class="em-row">
            <label>
              提示词内容
              <span class="label-hint">支持 {novel_title} {chapter_number} {synopsis} 等变量</span>
            </label>
            <textarea
              v-model="editForm.content" class="em-textarea" rows="14"
              placeholder="在此编写提示词模板..."
            ></textarea>
          </div>

          <div class="em-row inline">
            <label>启用状态</label>
            <div class="toggle-switch" :class="{ on: editForm.is_active }" @click="editForm.is_active = !editForm.is_active">
              <div class="toggle-thumb"></div>
            </div>
            <span class="toggle-label">{{ editForm.is_active ? '已启用' : '已停用' }}</span>
          </div>
        </div>

        <div class="em-footer">
          <button class="btn btn-ghost" @click="showEditor = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="savePrompt">
            {{ saving ? '保存中...' : editMode === 'create' ? '创建' : '保存修改' }}
          </button>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<style scoped>
.pg{max-width:1000px}

/* Header */
.pg-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:24px}
.pg-title{font-size:22px;font-weight:800;color:var(--gray-900);letter-spacing:-.3px}
.pg-desc{font-size:13px;color:var(--gray-400);margin-top:6px}

/* Sections */
.pg-section{background:#fff;border:1px solid var(--gray-200);border-radius:16px;padding:22px;margin-bottom:16px;
  animation:fadeIn .2s}
@keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.section-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px}
.section-left{display:flex;align-items:center;gap:8px}
.section-title{font-size:15px;font-weight:600;color:var(--gray-800)}
.section-count{font-size:11px;color:var(--gray-400);background:var(--gray-100);padding:2px 8px;border-radius:10px;font-weight:500}
.clear-filter{font-size:11px;color:var(--primary);background:none;border:none;cursor:pointer;padding:2px 6px;
  border-radius:4px;transition:background .12s}
.clear-filter:hover{background:var(--primary-light)}

/* Search */
.search-wrap{display:flex;align-items:center;gap:6px;background:var(--gray-50);border:1px solid var(--gray-200);
  border-radius:10px;padding:7px 14px;min-width:200px;transition:all .15s}
.search-wrap:focus-within{box-shadow:0 0 0 3px rgba(99,102,241,.1)}
.search-wrap:focus-within{border-color:var(--primary)}
.search-icon{font-size:12px;color:var(--gray-400);flex-shrink:0}
.search-input{border:none;background:none;outline:none;font-size:13px;color:var(--gray-700);width:100%}
.search-input::placeholder{color:var(--gray-300)}

/* Stage cards grid */
.stage-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:10px}
.stage-card{position:relative;padding:18px;border:2px solid var(--gray-100);border-radius:14px;
  cursor:pointer;transition:all .18s;user-select:none}
.stage-card:hover{border-color:var(--gray-300);transform:translateY(-2px);box-shadow:0 4px 16px rgba(0,0,0,.06)}
.stage-card.active{border-color:var(--primary);background:var(--primary-light)}
.sc-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.sc-icon{width:42px;height:42px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:18px}
.sc-count{width:22px;height:22px;border-radius:50%;background:var(--gray-100);color:var(--gray-400);
  display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600}
.sc-count.has-items{background:var(--primary-light);color:var(--primary)}
.sc-name{font-size:13px;font-weight:600;color:var(--gray-700);margin-bottom:2px}
.sc-sub{font-size:11px;color:var(--gray-400)}

/* Loading skeleton */
.loading-placeholder{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:10px}
.skeleton-card{height:100px;border-radius:14px;background:var(--gray-100);animation:shimmer 1.5s infinite}
@keyframes shimmer{0%,100%{opacity:.6}50%{opacity:1}}

/* Empty state */
.empty-state{text-align:center;padding:56px 20px}
.empty-visual{font-size:40px;margin-bottom:12px}
.empty-title{font-size:15px;font-weight:600;color:var(--gray-500);margin-bottom:4px}
.empty-desc{font-size:13px;color:var(--gray-400);margin-bottom:16px;line-height:1.5}
.btn-sm{padding:6px 16px;font-size:12px}

/* Prompt list */
.prompt-list{display:flex;flex-direction:column;gap:1px;background:var(--gray-100);border-radius:12px;overflow:hidden}
.pl-row{display:flex;align-items:center;gap:14px;padding:14px 16px;background:#fff;transition:background .12s}
.pl-row:hover{background:var(--gray-50)}

.pl-icon-col{flex-shrink:0}
.pl-badge{width:38px;height:38px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:17px}

.pl-main{flex:1;min-width:0}
.pl-title-row{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.pl-name{font-size:14px;font-weight:600;color:var(--gray-800)}
.pl-version{font-size:10px;color:var(--primary);background:var(--primary-light);padding:1px 7px;
  border-radius:10px;font-weight:600;letter-spacing:.3px}
.pl-status{font-size:10px;padding:1px 7px;border-radius:10px;font-weight:500}
.pl-status.on{color:#16a34a;background:#dcfce7}
.pl-status.off{color:var(--gray-400);background:var(--gray-100)}
.pl-desc{font-size:12px;color:var(--gray-500);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pl-content-preview{font-size:12px;color:var(--gray-400);margin-top:3px;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;font-style:italic}

.pl-stage-col{flex-shrink:0}
.pl-stage-tag{font-size:11px;padding:3px 10px;border-radius:10px;font-weight:500;white-space:nowrap}

.pl-date-col{flex-shrink:0;min-width:80px;text-align:right}
.pl-date{font-size:12px;color:var(--gray-300)}

.pl-actions{display:flex;gap:2px;flex-shrink:0;opacity:0;transition:opacity .15s}
.pl-row:hover .pl-actions{opacity:1}
.act-btn{width:30px;height:30px;border:none;background:none;border-radius:var(--radius-xs);
  cursor:pointer;font-size:13px;display:flex;align-items:center;justify-content:center;transition:all .12s}
.act-btn:hover{background:var(--gray-100)}
.act-btn.danger:hover{background:#fee2e2}

/* ── Editor Modal ────────────────────────────────────────── */
.editor-modal{background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.15)}
.em-header{display:flex;align-items:center;justify-content:space-between;padding:20px 24px;
  border-bottom:1px solid var(--gray-200)}
.em-header h3{font-size:16px;font-weight:700;color:var(--gray-800)}
.em-close{width:32px;height:32px;border:none;background:none;border-radius:var(--radius-xs);
  cursor:pointer;font-size:16px;color:var(--gray-400);display:flex;align-items:center;justify-content:center;
  transition:all .12s}
.em-close:hover{background:var(--gray-100);color:var(--gray-700)}

.em-body{padding:24px;display:flex;flex-direction:column;gap:18px;max-height:70vh;overflow-y:auto}
.em-row{display:flex;flex-direction:column;gap:6px}
.em-row label{font-size:12px;font-weight:600;color:var(--gray-500);text-transform:uppercase;letter-spacing:.3px;
  display:flex;align-items:center;gap:6px}
.label-hint{font-weight:400;text-transform:none;letter-spacing:0;color:var(--gray-300);font-size:11px}
.em-row.inline{flex-direction:row;align-items:center;gap:12px}

.em-input{padding:10px 14px;border:1px solid var(--gray-200);border-radius:var(--radius-xs);
  font-size:13px;color:var(--gray-700);outline:none;background:#fff;transition:border-color .15s;width:100%}
.em-input:focus{border-color:var(--primary)}
.em-input::placeholder{color:var(--gray-300)}

.em-textarea{padding:12px 14px;border:1px solid var(--gray-200);border-radius:var(--radius-xs);
  font-size:13px;color:var(--gray-700);outline:none;resize:vertical;font-family:ui-monospace,SFMono-Regular,
  "SF Mono",Menlo,Consolas,monospace;line-height:1.6;background:var(--gray-50);transition:border-color .15s;width:100%}
.em-textarea:focus{border-color:var(--primary);background:#fff}
.em-textarea::placeholder{color:var(--gray-300)}

.em-readonly{padding:8px 0}
.em-stage-badge{font-size:13px;padding:4px 12px;border-radius:var(--radius-xs);font-weight:500;display:inline-flex;
  align-items:center;gap:4px}

/* Stage picker */
.stage-picker{display:flex;flex-wrap:wrap;gap:6px}
.sp-btn{padding:6px 12px;border:1.5px solid var(--gray-200);border-radius:var(--radius-xs);
  background:#fff;font-size:12px;cursor:pointer;transition:all .12s;color:var(--gray-500);white-space:nowrap}
.sp-btn:hover{border-color:var(--gray-300);background:var(--gray-50)}
.sp-btn.active{font-weight:600}

/* Toggle switch */
.toggle-switch{width:40px;height:22px;border-radius:11px;background:var(--gray-200);position:relative;
  cursor:pointer;transition:background .2s;flex-shrink:0}
.toggle-switch.on{background:var(--primary)}
.toggle-thumb{width:18px;height:18px;border-radius:50%;background:#fff;position:absolute;top:2px;left:2px;
  transition:transform .2s;box-shadow:0 1px 3px rgba(0,0,0,.15)}
.toggle-switch.on .toggle-thumb{transform:translateX(18px)}
.toggle-label{font-size:12px;color:var(--gray-500)}

/* Footer */
.em-footer{display:flex;justify-content:flex-end;gap:8px;padding:16px 24px;border-top:1px solid var(--gray-200);
  background:var(--gray-50)}

@media (max-width:700px) {
  .stage-grid{grid-template-columns:repeat(2,1fr)}
  .pl-stage-col,.pl-date-col{display:none}
  .pl-actions{opacity:1}
}
</style>
