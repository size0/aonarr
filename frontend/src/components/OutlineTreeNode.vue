<script setup lang="ts">
import type { OutlineNodeDTO } from '@/api/outline'

const levelConfig: Record<string, { icon: string; label: string; color: string }> = {
  volume: { icon: '📚', label: '卷', color: '#8b5cf6' },
  act: { icon: '🎬', label: '幕', color: '#3b82f6' },
  chapter: { icon: '📄', label: '章', color: '#22c55e' },
  scene: { icon: '🎭', label: '场景', color: '#f59e0b' },
  beat: { icon: '🎵', label: '节拍', color: '#ec4899' },
}

const props = defineProps<{
  node: OutlineNodeDTO
  depth: number
  editingId: string
  collapsedSet: Set<string>
  selectedId: string
}>()

const emit = defineEmits<{
  (e: 'contextmenu', event: MouseEvent, node: OutlineNodeDTO): void
  (e: 'select', id: string): void
  (e: 'toggleCollapse', id: string): void
  (e: 'startEdit', node: OutlineNodeDTO): void
  (e: 'dragStart', event: DragEvent, node: OutlineNodeDTO): void
  (e: 'drop', event: DragEvent, node: OutlineNodeDTO): void
  (e: 'dragOver', event: DragEvent): void
}>()

function getCfg(level: string) {
  return levelConfig[level] || { icon: '📝', label: '节点', color: '#6b7280' }
}
</script>

<template>
  <div class="tree-node-wrap">
    <div
      :class="['tree-node', { selected: selectedId === node.id }]"
      :style="{ paddingLeft: (depth * 24 + 12) + 'px' }"
      draggable="true"
      @contextmenu.prevent="emit('contextmenu', $event, node)"
      @click="emit('select', node.id)"
      @dblclick="emit('startEdit', node)"
      @dragstart="emit('dragStart', $event, node)"
      @drop="emit('drop', $event, node)"
      @dragover="emit('dragOver', $event)"
    >
      <span
        v-if="node.children?.length"
        class="tree-toggle"
        @click.stop="emit('toggleCollapse', node.id)"
      >{{ collapsedSet.has(node.id) ? '▸' : '▾' }}</span>
      <span v-else class="tree-toggle-placeholder"></span>
      <span class="tree-dot" :style="{ background: getCfg(node.level).color }"></span>
      <span class="tree-level">{{ getCfg(node.level).icon }}</span>
      <span class="tree-title">{{ node.title || '未命名' }}</span>
      <span class="tree-summary" v-if="node.summary">{{ node.summary.slice(0, 40) }}</span>
    </div>
    <template v-if="node.children?.length && !collapsedSet.has(node.id)">
      <OutlineTreeNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :depth="depth + 1"
        :editing-id="editingId"
        :collapsed-set="collapsedSet"
        :selected-id="selectedId"
        @contextmenu="(e, n) => emit('contextmenu', e, n)"
        @select="(id) => emit('select', id)"
        @toggle-collapse="(id) => emit('toggleCollapse', id)"
        @start-edit="(n) => emit('startEdit', n)"
        @drag-start="(e, n) => emit('dragStart', e, n)"
        @drop="(e, n) => emit('drop', e, n)"
        @drag-over="(e) => emit('dragOver', e)"
      />
    </template>
  </div>
</template>

<style scoped>
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
</style>
