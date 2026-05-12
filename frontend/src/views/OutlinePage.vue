<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useOutlineStore } from '@/stores/outline'
import { useNovelsStore } from '@/stores/novels'
import OutlineTreeNode from '@/components/OutlineTreeNode.vue'
import type { OutlineNodeDTO } from '@/api/outline'

const outlineStore = useOutlineStore()
const novelsStore = useNovelsStore()

// Novel selector
const selectedNovelId = ref('')

onMounted(async () => {
  if (!novelsStore.novels.length) await novelsStore.loadNovels()
  if (novelsStore.novels.length) {
    selectedNovelId.value = novelsStore.novels[0].id
  }
})

watch(selectedNovelId, (id) => {
  if (id) outlineStore.loadOutline(id)
})

// Level config
const levelConfig: Record<string, { icon: string; label: string; color: string }> = {
  volume: { icon: '📚', label: '卷', color: '#8b5cf6' },
  act: { icon: '🎬', label: '幕', color: '#3b82f6' },
  chapter: { icon: '📄', label: '章', color: '#22c55e' },
  scene: { icon: '🎭', label: '场景', color: '#f59e0b' },
  beat: { icon: '🎵', label: '节拍', color: '#ec4899' },
}

const levelOrder = ['volume', 'act', 'chapter', 'scene', 'beat']

function getChildLevel(parentLevel: string): string {
  const idx = levelOrder.indexOf(parentLevel)
  return idx < levelOrder.length - 1 ? levelOrder[idx + 1] : 'beat'
}

// Context menu
const contextMenu = ref<{ show: boolean; x: number; y: number; node: OutlineNodeDTO | null }>({
  show: false, x: 0, y: 0, node: null
})

function showContextMenu(e: MouseEvent, node: OutlineNodeDTO) {
  e.preventDefault()
  contextMenu.value = { show: true, x: e.clientX, y: e.clientY, node }
}

function hideContextMenu() {
  contextMenu.value.show = false
}

// Editing
const editingNodeId = ref('')
const editTitle = ref('')
const editSummary = ref('')

function startEdit(node: OutlineNodeDTO) {
  editingNodeId.value = node.id
  editTitle.value = node.title
  editSummary.value = node.summary
  outlineStore.selectNode(node.id)
  hideContextMenu()
}

async function saveEdit() {
  if (!editingNodeId.value) return
  await outlineStore.updateNode(editingNodeId.value, {
    title: editTitle.value,
    summary: editSummary.value,
  })
  editingNodeId.value = ''
}

function cancelEdit() {
  editingNodeId.value = ''
}

// Add node
async function addChild(parentNode: OutlineNodeDTO | null) {
  hideContextMenu()
  const parentId = parentNode?.id || null
  const level = parentNode ? getChildLevel(parentNode.level) : 'volume'
  await outlineStore.addNode({
    parent_id: parentId,
    level,
    title: `新${levelConfig[level]?.label || '节点'}`,
    summary: '',
  })
}

async function addSibling(node: OutlineNodeDTO) {
  hideContextMenu()
  await outlineStore.addNode({
    parent_id: node.parent_id,
    level: node.level,
    title: `新${levelConfig[node.level]?.label || '节点'}`,
    sort_order: node.sort_order + 1,
  })
}

// Delete
async function deleteNode(node: OutlineNodeDTO) {
  hideContextMenu()
  if (confirm(`确定删除"${node.title || '未命名'}"及其所有子节点？`)) {
    await outlineStore.deleteNode(node.id)
  }
}

// Move up/down
async function moveUp(node: OutlineNodeDTO) {
  hideContextMenu()
  if (node.sort_order <= 0) return
  await outlineStore.updateNode(node.id, { sort_order: node.sort_order - 1 })
}

async function moveDown(node: OutlineNodeDTO) {
  hideContextMenu()
  await outlineStore.updateNode(node.id, { sort_order: node.sort_order + 1 })
}

// Drag and drop
const dragNodeId = ref('')

function onDragStart(e: DragEvent, node: OutlineNodeDTO) {
  dragNodeId.value = node.id
  e.dataTransfer?.setData('text/plain', node.id)
}

function onDrop(e: DragEvent, targetNode: OutlineNodeDTO) {
  e.preventDefault()
  const sourceId = dragNodeId.value
  if (!sourceId || sourceId === targetNode.id) return
  // Move source under target
  outlineStore.updateNode(sourceId, { parent_id: targetNode.id })
  dragNodeId.value = ''
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
}

// Collapse state
const collapsed = ref<Set<string>>(new Set())

function toggleCollapse(nodeId: string) {
  if (collapsed.value.has(nodeId)) {
    collapsed.value.delete(nodeId)
  } else {
    collapsed.value.add(nodeId)
  }
}

// AI generate outline
const aiGenerating = ref(false)
async function aiGenerateOutline() {
  if (!selectedNovelId.value) return
  const novel = novelsStore.novels.find(n => n.id === selectedNovelId.value)
  if (!novel) return
  aiGenerating.value = true
  try {
    const { default: apiClient } = await import('@/api/client')
    await apiClient.post(`/creation/${selectedNovelId.value}/outline`, {
      premise: novel.premise || novel.synopsis || novel.title,
      genre: novel.genre || '玄幻',
      synopsis: novel.synopsis || '',
      world_setting: novel.world_setting || '',
      target_chapters: novel.target_chapter_count || 200,
    })
    await outlineStore.loadOutline(selectedNovelId.value)
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    const msg = typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : e.message
    alert('AI大纲生成失败: ' + msg)
  } finally {
    aiGenerating.value = false
  }
}

// Click outside context menu
function onPageClick() {
  if (contextMenu.value.show) hideContextMenu()
}
</script>

<template>
  <div class="page-outline" @click="onPageClick">
    <!-- Header -->
    <div class="ol-header">
      <div>
        <h1 class="page-title">🗂️ 大纲规划</h1>
        <p class="page-desc">卷 → 幕 → 章 → 场景 → 节拍，从宏观到微观规划你的故事</p>
      </div>
      <div class="ol-actions">
        <select v-model="selectedNovelId" class="ol-select">
          <option value="" disabled>选择作品</option>
          <option v-for="n in novelsStore.novels" :key="n.id" :value="n.id">{{ n.title }}</option>
        </select>
        <button class="btn btn-ghost" @click="addChild(null)">+ 添加根节点</button>
        <button class="btn btn-primary" :disabled="aiGenerating || !selectedNovelId" @click="aiGenerateOutline">
          {{ aiGenerating ? '⏳ 生成中...' : '🤖 AI 生成大纲' }}
        </button>
      </div>
    </div>


    <!-- Level legend -->
    <div class="ol-legend">
      <span v-for="(cfg, key) in levelConfig" :key="key" class="legend-item">
        <span class="legend-dot" :style="{ background: cfg.color }"></span>
        {{ cfg.icon }} {{ cfg.label }}
      </span>
    </div>

    <!-- Tree -->
    <div class="ol-body" v-if="selectedNovelId">
      <div v-if="outlineStore.loading" class="ol-loading">加载中...</div>
      <div v-else-if="outlineStore.tree.length === 0" class="ol-empty">
        <div class="ol-empty-icon">🏗️</div>
        <div class="ol-empty-title">暂无大纲节点</div>
        <div class="ol-empty-desc">点击"添加根节点"或"AI 生成大纲"开始</div>
      </div>
      <div v-else class="ol-tree">
        <template v-for="node in outlineStore.tree" :key="node.id">
          <OutlineTreeNode
            :node="node"
            :depth="0"
            :editing-id="editingNodeId"
            :collapsed-set="collapsed"
            :selected-id="outlineStore.selectedNodeId"
            @contextmenu="showContextMenu"
            @select="outlineStore.selectNode"
            @toggle-collapse="toggleCollapse"
            @start-edit="startEdit"
            @drag-start="onDragStart"
            @drop="onDrop"
            @drag-over="onDragOver"
          />
        </template>
      </div>
    </div>
    <div v-else class="ol-empty">
      <div class="ol-empty-icon">📖</div>
      <div class="ol-empty-title">请先选择一部作品</div>
    </div>

    <!-- Edit panel (right side) -->
    <Transition name="slide">
      <div v-if="editingNodeId" class="ol-edit-panel">
        <div class="edit-head">
          <span>编辑节点</span>
          <button class="edit-close" @click="cancelEdit">✕</button>
        </div>
        <div class="edit-field">
          <label>标题</label>
          <input v-model="editTitle" class="edit-input" @keydown.enter="saveEdit" />
        </div>
        <div class="edit-field">
          <label>摘要</label>
          <textarea v-model="editSummary" class="edit-textarea" rows="5"></textarea>
        </div>
        <div class="edit-actions">
          <button class="btn btn-ghost" @click="cancelEdit">取消</button>
          <button class="btn btn-primary" @click="saveEdit">保存</button>
        </div>
      </div>
    </Transition>

    <!-- Context menu -->
    <Teleport to="body">
      <div
        v-if="contextMenu.show"
        class="ctx-menu"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      >
        <div class="ctx-item" @click="startEdit(contextMenu.node!)">✏️ 编辑</div>
        <div class="ctx-item" @click="addChild(contextMenu.node!)">➕ 添加子节点</div>
        <div class="ctx-item" @click="addSibling(contextMenu.node!)">↕️ 添加同级</div>
        <div class="ctx-sep"></div>
        <div class="ctx-item" @click="moveUp(contextMenu.node!)">⬆️ 上移</div>
        <div class="ctx-item" @click="moveDown(contextMenu.node!)">⬇️ 下移</div>
        <div class="ctx-sep"></div>
        <div class="ctx-item ctx-danger" @click="deleteNode(contextMenu.node!)">🗑️ 删除</div>
      </div>
    </Teleport>
  </div>
</template>


<style scoped>
.page-outline{display:flex;flex-direction:column;height:calc(100vh - 80px);max-width:1100px;position:relative}

.ol-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:18px;flex-shrink:0;gap:16px;flex-wrap:wrap}
.page-title{font-size:22px;font-weight:800;color:var(--gray-900);letter-spacing:-.3px}
.page-desc{font-size:13px;color:var(--gray-400);margin-top:6px}
.ol-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.ol-select{padding:8px 14px;border:1px solid var(--gray-200);border-radius:10px;
  font-size:13px;color:var(--gray-700);background:#fff;min-width:180px;outline:none;transition:all .15s}
.ol-select:focus{border-color:var(--primary);box-shadow:0 0 0 3px rgba(99,102,241,.1)}

.ol-legend{display:flex;gap:14px;margin-bottom:14px;flex-shrink:0;padding:8px 14px;background:var(--gray-50);border-radius:10px}
.legend-item{display:flex;align-items:center;gap:5px;font-size:12px;color:var(--gray-500)}
.legend-dot{width:8px;height:8px;border-radius:50%}

.ol-body{flex:1;overflow-y:auto;background:#fff;border:1px solid var(--gray-200);border-radius:16px;padding:8px 0;box-shadow:0 4px 24px rgba(0,0,0,.06)}
.ol-loading{padding:40px;text-align:center;color:var(--gray-400);font-size:13px}
.ol-empty{text-align:center;padding:60px 20px}
.ol-empty-icon{font-size:36px;margin-bottom:10px}
.ol-empty-title{font-size:15px;font-weight:600;color:var(--gray-600);margin-bottom:4px}
.ol-empty-desc{font-size:12px;color:var(--gray-400)}

/* Tree nodes */
.ol-tree{padding:4px 0}
.tree-node-wrap{}
.tree-node{display:flex;align-items:center;gap:6px;padding:7px 12px;cursor:pointer;
  border-left:3px solid transparent;transition:all .12s;user-select:none}
.tree-node:hover{background:var(--gray-50)}
.tree-node.selected{background:var(--primary-light);border-left-color:var(--primary)}
.tree-toggle{width:16px;font-size:12px;color:var(--gray-400);cursor:pointer;text-align:center;flex-shrink:0}
.tree-toggle:hover{color:var(--gray-700)}
.tree-toggle-placeholder{width:16px;flex-shrink:0}
.tree-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.tree-level{font-size:14px;flex-shrink:0}
.tree-title{font-size:13px;font-weight:500;color:var(--gray-800);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tree-summary{font-size:11px;color:var(--gray-400);margin-left:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px}

/* Edit panel */
.ol-edit-panel{position:absolute;top:60px;right:0;width:340px;background:#fff;
  border:1px solid var(--gray-200);border-radius:16px;padding:22px;
  box-shadow:0 8px 30px rgba(0,0,0,.12);z-index:10}
.edit-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;
  font-size:14px;font-weight:600;color:var(--gray-800)}
.edit-close{background:none;border:none;cursor:pointer;font-size:16px;color:var(--gray-400)}
.edit-field{margin-bottom:12px}
.edit-field label{display:block;font-size:12px;font-weight:500;color:var(--gray-500);margin-bottom:4px}
.edit-input{width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:var(--radius-xs);
  font-size:13px;outline:none}
.edit-input:focus{border-color:var(--primary)}
.edit-textarea{width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:var(--radius-xs);
  font-size:13px;outline:none;resize:vertical;line-height:1.5}
.edit-textarea:focus{border-color:var(--primary)}
.edit-actions{display:flex;justify-content:flex-end;gap:8px}

/* Context menu */
.ctx-menu{position:fixed;z-index:9999;background:#fff;border:1px solid var(--gray-200);
  border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.15);padding:6px 0;min-width:180px}
.ctx-item{padding:8px 14px;font-size:13px;cursor:pointer;color:var(--gray-700);display:flex;align-items:center;gap:8px;
  transition:all .1s}
.ctx-item:hover{background:var(--primary-light);color:var(--primary)}
.ctx-danger{color:var(--danger)}
.ctx-danger:hover{background:#fef2f2;color:var(--danger)}
.ctx-sep{height:1px;background:var(--gray-100);margin:4px 0}

/* Transitions */
.slide-enter-active,.slide-leave-active{transition:all .2s}
.slide-enter-from,.slide-leave-to{opacity:0;transform:translateX(10px)}
</style>
