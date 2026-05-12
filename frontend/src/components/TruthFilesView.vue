<script setup lang="ts">
import { ref, watch, computed } from 'vue'

const props = defineProps<{
  novelId: string
}>()

interface TruthFile {
  id: string
  novel_id: string
  file_key: string
  content: string
  data_json: Record<string, any>
  version: number
  last_chapter: number
  updated_at: string | null
}

const files = ref<TruthFile[]>([])
const loading = ref(false)
const activeKey = ref('current_state')
const editing = ref(false)
const editContent = ref('')
const saving = ref(false)

const FILE_META: Record<string, { icon: string; label: string; color: string }> = {
  current_state:     { icon: '🌍', label: '世界状态',     color: '#6366f1' },
  particle_ledger:   { icon: '💰', label: '资源账本',     color: '#f59e0b' },
  pending_hooks:     { icon: '🪝', label: '伏笔追踪',     color: '#ec4899' },
  chapter_summaries: { icon: '📋', label: '章节摘要',     color: '#22c55e' },
  subplot_board:     { icon: '🧩', label: '支线进度板',   color: '#8b5cf6' },
  emotional_arcs:    { icon: '💗', label: '情感弧线',     color: '#ef4444' },
  character_matrix:  { icon: '👥', label: '角色矩阵',     color: '#0ea5e9' },
}

const activeFile = computed(() => files.value.find(f => f.file_key === activeKey.value))
const activeMeta = computed(() => FILE_META[activeKey.value] || { icon: '📄', label: activeKey.value, color: '#64748b' })

async function loadFiles() {
  if (!props.novelId) return
  loading.value = true
  try {
    const resp = await fetch(`/api/v1/novels/${props.novelId}/truth`)
    if (resp.ok) files.value = await resp.json()
  } catch (e) {
    console.error('加载真相文件失败', e)
  } finally {
    loading.value = false
  }
}

function startEdit() {
  if (!activeFile.value) return
  editContent.value = activeFile.value.content
  editing.value = true
}

function cancelEdit() {
  editing.value = false
  editContent.value = ''
}

async function saveEdit() {
  if (!activeFile.value) return
  saving.value = true
  try {
    const resp = await fetch(`/api/v1/novels/${props.novelId}/truth/${activeKey.value}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: editContent.value }),
    })
    if (resp.ok) {
      const updated = await resp.json()
      const idx = files.value.findIndex(f => f.file_key === activeKey.value)
      if (idx >= 0) files.value[idx] = updated
      editing.value = false
    }
  } catch (e) {
    console.error('保存失败', e)
  } finally {
    saving.value = false
  }
}

function formatTime(iso: string | null) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

watch(() => props.novelId, loadFiles, { immediate: true })
</script>

<template>
  <div class="tf-root">
    <!-- Sidebar: file list -->
    <div class="tf-sidebar">
      <div class="tf-sidebar-head">
        <span class="tf-sidebar-icon">📚</span>
        <span class="tf-sidebar-title">真相文件</span>
      </div>
      <div
        v-for="key in Object.keys(FILE_META)"
        :key="key"
        :class="['tf-item', { active: activeKey === key }]"
        @click="activeKey = key; editing = false"
      >
        <span class="tf-item-icon">{{ FILE_META[key].icon }}</span>
        <div class="tf-item-info">
          <span class="tf-item-label">{{ FILE_META[key].label }}</span>
          <span class="tf-item-meta" v-if="files.find(f => f.file_key === key)">
            v{{ files.find(f => f.file_key === key)?.version || 0 }}
            · ch{{ files.find(f => f.file_key === key)?.last_chapter || 0 }}
          </span>
        </div>
        <span
          class="tf-item-dot"
          :style="{ background: FILE_META[key].color }"
          v-if="(files.find(f => f.file_key === key)?.last_chapter || 0) > 0"
        ></span>
      </div>

      <div class="tf-sidebar-hint" v-if="loading">加载中...</div>
      <div class="tf-sidebar-hint" v-else-if="!props.novelId">请先选择小说</div>
    </div>

    <!-- Main content -->
    <div class="tf-main">
      <!-- Header -->
      <div class="tf-header" v-if="activeFile">
        <div class="tf-header-left">
          <span class="tf-h-icon" :style="{ background: activeMeta.color + '18', color: activeMeta.color }">
            {{ activeMeta.icon }}
          </span>
          <div>
            <h3 class="tf-h-title">{{ activeMeta.label }}</h3>
            <span class="tf-h-meta">
              版本 {{ activeFile.version }} · 最后更新于第 {{ activeFile.last_chapter }} 章
              <template v-if="activeFile.updated_at"> · {{ formatTime(activeFile.updated_at) }}</template>
            </span>
          </div>
        </div>
        <div class="tf-header-actions">
          <button v-if="!editing" class="tf-btn tf-btn-edit" @click="startEdit">编辑</button>
          <template v-else>
            <button class="tf-btn tf-btn-cancel" @click="cancelEdit">取消</button>
            <button class="tf-btn tf-btn-save" :disabled="saving" @click="saveEdit">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </template>
        </div>
      </div>

      <!-- Content: read mode -->
      <div class="tf-body" v-if="activeFile && !editing">
        <div class="tf-content-md" v-html="renderMarkdown(activeFile.content)"></div>
      </div>

      <!-- Content: edit mode -->
      <div class="tf-body tf-body-edit" v-else-if="activeFile && editing">
        <textarea
          class="tf-editor"
          v-model="editContent"
          placeholder="编辑真相文件内容 (Markdown)"
        ></textarea>
      </div>

      <!-- Empty state -->
      <div class="tf-empty" v-else-if="!loading">
        <div class="tf-empty-icon">📭</div>
        <p>暂无数据</p>
        <p class="tf-empty-hint">写完第一章后，章后管线将自动提取真相文件</p>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
function renderMarkdown(md: string): string {
  if (!md) return '<p style="color:#94a3b8">暂无内容</p>'
  return md
    .replace(/^### (.+)$/gm, '<h4 class="tf-md-h3">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 class="tf-md-h2">$1</h3>')
    .replace(/^# (.+)$/gm, '<h2 class="tf-md-h1">$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul class="tf-md-ul">${m}</ul>`)
    .replace(/^> (.+)$/gm, '<blockquote class="tf-md-bq">$1</blockquote>')
    .replace(/\n{2,}/g, '<br><br>')
    .replace(/\n/g, '<br>')
}
</script>

<style scoped>
.tf-root{display:flex;height:100%;overflow:hidden}

/* Sidebar */
.tf-sidebar{width:220px;border-right:1px solid #e2e8f0;display:flex;flex-direction:column;
  background:#fafbfc;flex-shrink:0;overflow-y:auto}
.tf-sidebar-head{display:flex;align-items:center;gap:8px;padding:16px 16px 12px;
  border-bottom:1px solid #f1f5f9}
.tf-sidebar-icon{font-size:18px}
.tf-sidebar-title{font-size:14px;font-weight:700;color:#1e293b}
.tf-item{display:flex;align-items:center;gap:10px;padding:10px 16px;cursor:pointer;
  transition:all .15s;border-left:3px solid transparent}
.tf-item:hover{background:#f1f5f9}
.tf-item.active{background:#eef2ff;border-left-color:#6366f1}
.tf-item-icon{font-size:16px;flex-shrink:0}
.tf-item-info{display:flex;flex-direction:column;flex:1;min-width:0}
.tf-item-label{font-size:13px;font-weight:500;color:#334155}
.tf-item.active .tf-item-label{color:#4f46e5;font-weight:600}
.tf-item-meta{font-size:10px;color:#94a3b8}
.tf-item-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.tf-sidebar-hint{padding:16px;font-size:12px;color:#94a3b8;text-align:center}

/* Main */
.tf-main{flex:1;display:flex;flex-direction:column;min-width:0;overflow:hidden}
.tf-header{display:flex;align-items:center;justify-content:space-between;
  padding:16px 24px;border-bottom:1px solid #f1f5f9;flex-shrink:0}
.tf-header-left{display:flex;align-items:center;gap:12px}
.tf-h-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;
  justify-content:center;font-size:20px;flex-shrink:0}
.tf-h-title{font-size:16px;font-weight:700;color:#1e293b;margin:0}
.tf-h-meta{font-size:11px;color:#94a3b8}
.tf-header-actions{display:flex;gap:8px}
.tf-btn{padding:6px 14px;border-radius:8px;font-size:12px;font-weight:500;
  cursor:pointer;border:1px solid #e2e8f0;background:#fff;color:#475569;
  transition:all .15s}
.tf-btn:hover{background:#f8fafc}
.tf-btn-edit{color:#6366f1;border-color:#c7d2fe}
.tf-btn-edit:hover{background:#eef2ff}
.tf-btn-save{background:#6366f1;color:#fff;border-color:#6366f1}
.tf-btn-save:hover{background:#4f46e5}
.tf-btn-save:disabled{opacity:.5;cursor:not-allowed}
.tf-btn-cancel{color:#64748b}

/* Body */
.tf-body{flex:1;overflow-y:auto;padding:20px 24px}
.tf-body-edit{padding:16px}
.tf-editor{width:100%;height:100%;min-height:300px;border:1px solid #e2e8f0;border-radius:10px;
  padding:16px;font-family:'JetBrains Mono',monospace;font-size:13px;line-height:1.7;
  color:#334155;resize:none;outline:none;background:#fafbfc}
.tf-editor:focus{border-color:#6366f1;box-shadow:0 0 0 3px rgba(99,102,241,.1)}

/* Markdown rendering */
:deep(.tf-md-h1){font-size:18px;font-weight:800;color:#0f172a;margin:16px 0 8px;
  padding-bottom:6px;border-bottom:2px solid #e2e8f0}
:deep(.tf-md-h2){font-size:15px;font-weight:700;color:#1e293b;margin:14px 0 6px}
:deep(.tf-md-h3){font-size:13px;font-weight:600;color:#334155;margin:10px 0 4px}
:deep(.tf-md-ul){padding-left:20px;margin:4px 0}
:deep(.tf-md-ul li){font-size:13px;color:#475569;line-height:1.8;margin:2px 0}
:deep(.tf-md-ul li strong){color:#1e293b}
:deep(.tf-md-bq){border-left:3px solid #e2e8f0;padding:4px 12px;margin:8px 0;
  color:#64748b;font-size:13px;background:#f8fafc;border-radius:0 6px 6px 0}

/* Empty */
.tf-empty{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;
  color:#94a3b8}
.tf-empty-icon{font-size:48px;margin-bottom:12px}
.tf-empty p{margin:4px 0;font-size:14px}
.tf-empty-hint{font-size:12px;color:#cbd5e1}
</style>
