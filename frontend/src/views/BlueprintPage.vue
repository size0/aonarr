<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useOutlineStore } from '@/stores/outline'
import { useNovelsStore } from '@/stores/novels'
import OutlineTreeNode from '@/components/OutlineTreeNode.vue'
import CharacterGraph from '@/components/CharacterGraph.vue'
import TimelineView from '@/components/TimelineView.vue'
import WorldMap from '@/components/WorldMap.vue'
import WikiBrowser from '@/components/WikiBrowser.vue'
import TruthFilesView from '@/components/TruthFilesView.vue'
import AuditDashboard from '@/components/AuditDashboard.vue'
import type { OutlineNodeDTO } from '@/api/outline'

const outlineStore = useOutlineStore()
const novelsStore = useNovelsStore()

// ── Novel selector ─────────────────────────────────────────
const selectedNovelId = ref('')

onMounted(async () => {
  if (!novelsStore.novels.length) await novelsStore.loadNovels()
  if (novelsStore.novels.length) {
    selectedNovelId.value = novelsStore.novels[0].id
  }
})

watch(selectedNovelId, (id) => {
  if (id) {
    outlineStore.loadOutline(id)
    loadWorldData(id)
  }
})

const currentNovel = computed(() => novelsStore.novels.find(n => n.id === selectedNovelId.value))

// ── Tab ────────────────────────────────────────────────────
type TabKey = 'outline' | 'truth' | 'audit' | 'graph' | 'timeline' | 'map' | 'wiki' | 'knowledge'
const activeTab = ref<TabKey>('outline')

const tabs: { key: TabKey; icon: string; label: string; color: string }[] = [
  { key: 'outline', icon: '🗂️', label: '大纲规划', color: '#6366f1' },
  { key: 'truth', icon: '📚', label: '真相文件', color: '#8b5cf6' },
  { key: 'audit', icon: '📈', label: '张力心电图', color: '#ef4444' },
  { key: 'graph', icon: '👥', label: '人物关系', color: '#3b82f6' },
  { key: 'knowledge', icon: '🔗', label: '知识图谱', color: '#0ea5e9' },
  { key: 'timeline', icon: '⏳', label: '时间线', color: '#f59e0b' },
  { key: 'map', icon: '🗺️', label: '世界地图', color: '#22c55e' },
  { key: 'wiki', icon: '📖', label: '百科全书', color: '#ec4899' },
]

// ═══ OUTLINE LOGIC ═══════════════════════════════════════════

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
  show: false, x: 0, y: 0, node: null,
})
function showContextMenu(e: MouseEvent, node: OutlineNodeDTO) {
  e.preventDefault()
  contextMenu.value = { show: true, x: e.clientX, y: e.clientY, node }
}
function hideContextMenu() { contextMenu.value.show = false }

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
  await outlineStore.updateNode(editingNodeId.value, { title: editTitle.value, summary: editSummary.value })
  editingNodeId.value = ''
}
function cancelEdit() { editingNodeId.value = '' }

// Add/Delete/Move
async function addChild(parentNode: OutlineNodeDTO | null) {
  hideContextMenu()
  const parentId = parentNode?.id || null
  const level = parentNode ? getChildLevel(parentNode.level) : 'volume'
  await outlineStore.addNode({ parent_id: parentId, level, title: `新${levelConfig[level]?.label || '节点'}`, summary: '' })
}
async function addSibling(node: OutlineNodeDTO) {
  hideContextMenu()
  await outlineStore.addNode({ parent_id: node.parent_id, level: node.level, title: `新${levelConfig[node.level]?.label || '节点'}`, sort_order: node.sort_order + 1 })
}
async function deleteNode(node: OutlineNodeDTO) {
  hideContextMenu()
  if (confirm(`确定删除"${node.title || '未命名'}"及其所有子节点？`)) await outlineStore.deleteNode(node.id)
}
async function moveUp(node: OutlineNodeDTO) {
  hideContextMenu()
  if (node.sort_order <= 0) return
  await outlineStore.updateNode(node.id, { sort_order: node.sort_order - 1 })
}
async function moveDown(node: OutlineNodeDTO) {
  hideContextMenu()
  await outlineStore.updateNode(node.id, { sort_order: node.sort_order + 1 })
}

// Drag
const dragNodeId = ref('')
function onDragStart(e: DragEvent, node: OutlineNodeDTO) {
  dragNodeId.value = node.id
  e.dataTransfer?.setData('text/plain', node.id)
}
function onDrop(e: DragEvent, targetNode: OutlineNodeDTO) {
  e.preventDefault()
  const sourceId = dragNodeId.value
  if (!sourceId || sourceId === targetNode.id) return
  outlineStore.updateNode(sourceId, { parent_id: targetNode.id })
  dragNodeId.value = ''
}
function onDragOver(e: DragEvent) { e.preventDefault() }

// Collapse
const collapsed = ref<Set<string>>(new Set())
function toggleCollapse(nodeId: string) {
  if (collapsed.value.has(nodeId)) collapsed.value.delete(nodeId)
  else collapsed.value.add(nodeId)
}

// AI outline
const aiGenerating = ref(false)
async function aiGenerateOutline() {
  if (!selectedNovelId.value) return
  const novel = currentNovel.value
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
    alert('AI大纲生成失败: ' + (typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : e.message))
  } finally {
    aiGenerating.value = false
  }
}

function onPageClick() { if (contextMenu.value.show) hideContextMenu() }

// ═══ REAL DATA STATE ════════════════════════════════════════

const roleMap: Record<string, string> = {
  protagonist: '主角', antagonist: '反派', supporting: '配角',
  mentor: '师长', love_interest: '红颜',
}

const characterNodes = ref<any[]>([])
const characterRelations = ref<any[]>([])
const timelineEvents = ref<any[]>([])
const timelineStorylines = ref<string[]>([])
const mapLocations = ref<any[]>([])
const mapTitle = ref('世界地图')
const wikiEntries = ref<any[]>([])
const kgTriples = ref<any[]>([])
const kgStats = ref<any>(null)
const kgLoading = ref(false)
const kgRebuilding = ref(false)
const kgSearch = ref('')
const worldDataLoading = ref(false)

async function loadWorldData(novelId: string) {
  if (!novelId) return
  worldDataLoading.value = true
  try {
    await Promise.all([
      loadCharacters(novelId),
      loadWorldItems(novelId),
      loadTimeline(novelId),
      loadWiki(novelId),
      loadKnowledgeGraph(novelId),
    ])
  } catch (e) {
    console.error('加载世界观数据失败', e)
  } finally {
    worldDataLoading.value = false
  }
}

async function loadCharacters(novelId: string) {
  try {
    const [charResp, kgResp] = await Promise.all([
      fetch(`/api/v1/novels/${novelId}/characters`),
      fetch(`/api/v1/novels/${novelId}/knowledge-graph`),
    ])
    const chars: any[] = charResp.ok ? await charResp.json() : []
    const triples: any[] = kgResp.ok ? await kgResp.json() : []

    characterNodes.value = chars.map(c => ({
      id: c.id, name: c.name,
      role: roleMap[c.role] || c.role || '配角',
      appearances: c.first_appearance || 0,
    }))

    const rels: any[] = []
    const relSet = new Set<string>()

    // 1. 从 characters 表的 relationships 字段
    for (const c of chars) {
      for (const r of (Array.isArray(c.relationships) ? c.relationships : [])) {
        const target = chars.find(t => t.name === r.target || t.name === r.name || t.id === r.target_id)
        if (target) {
          const key = [c.id, target.id].sort().join('|')
          if (!relSet.has(key)) {
            relSet.add(key)
            rels.push({ source: c.id, target: target.id, label: r.type || r.label || r.relationship || '关联', strength: r.strength ?? 0.6 })
          }
        }
      }
    }

    // 2. 从知识图谱三元组补充角色间关系（如角色不在 characters 表中则动态添加节点）
    const charTriples = triples.filter((t: any) => t.subject_type === 'character' && t.object_type === 'character')
    const nodeNameMap = new Map(characterNodes.value.map(n => [n.name, n.id]))

    function ensureNode(name: string): string {
      if (nodeNameMap.has(name)) return nodeNameMap.get(name)!
      const id = 'kg_' + name
      characterNodes.value.push({ id, name, role: '配角', appearances: 0 })
      nodeNameMap.set(name, id)
      return id
    }

    for (const t of charTriples) {
      const srcId = ensureNode(t.subject_id)
      const tgtId = ensureNode(t.object_id)
      if (srcId === tgtId) continue
      const key = [srcId, tgtId].sort().join('|')
      if (!relSet.has(key)) {
        relSet.add(key)
        rels.push({ source: srcId, target: tgtId, label: t.predicate || '关联', strength: t.confidence ?? 0.7 })
      }
    }

    characterRelations.value = rels
  } catch (e) { console.error('加载角色失败', e) }
}

async function loadWorldItems(novelId: string) {
  try {
    const [worldResp, kgResp] = await Promise.all([
      fetch(`/api/v1/novels/${novelId}/world`),
      fetch(`/api/v1/novels/${novelId}/knowledge-graph`),
    ])
    const items: any[] = worldResp.ok ? await worldResp.json() : []
    const triples: any[] = kgResp.ok ? await kgResp.json() : []

    const typeMap: Record<string, string> = { location: 'city', mountain: 'mountain', river: 'river', forest: 'forest', castle: 'castle', village: 'village' }
    const locItems = items.filter(i => ['location','mountain','river','forest','castle','village'].includes(i.category))

    // 使用圆形布局让地点分布更均匀
    function circleLayout(idx: number, total: number): { x: number; y: number } {
      if (total <= 1) return { x: 50, y: 50 }
      const angle = (idx / total) * Math.PI * 2 - Math.PI / 2
      const radius = 25 + (idx % 3) * 8
      return { x: 50 + radius * Math.cos(angle), y: 50 + radius * Math.sin(angle) }
    }

    const locations: any[] = locItems.map((item, idx) => {
      const props = item.properties || {}
      const pos = circleLayout(idx, locItems.length)
      return {
        id: item.id, name: item.name,
        x: props.x ?? pos.x, y: props.y ?? pos.y,
        type: typeMap[item.category] || 'city',
        description: item.description || '',
        connections: [],
      }
    })

    // 从知识图谱补充地点（如果 world 表中没有的话）
    const existingNames = new Set(locations.map(l => l.name))
    const locTriples = triples.filter((t: any) =>
      (t.subject_type === 'location' || t.object_type === 'location') && t.is_active
    )
    const kgLocNames = new Set<string>()
    for (const t of locTriples) {
      if (t.subject_type === 'location') kgLocNames.add(t.subject_id)
      if (t.object_type === 'location') kgLocNames.add(t.object_id)
    }
    let extraIdx = locations.length
    for (const name of kgLocNames) {
      if (!existingNames.has(name)) {
        const pos = circleLayout(extraIdx, locations.length + kgLocNames.size)
        locations.push({
          id: 'kg_loc_' + name, name,
          x: pos.x, y: pos.y,
          type: 'city', description: '',
          connections: [],
        })
        existingNames.add(name)
        extraIdx++
      }
    }

    // 从知识图谱中构建地点间连接（角色"出现在"不同地点 → 这些地点有联系）
    const charLocMap = new Map<string, Set<string>>()
    for (const t of locTriples) {
      if (t.predicate === '出现在' && t.subject_type === 'character' && t.object_type === 'location') {
        if (!charLocMap.has(t.subject_id)) charLocMap.set(t.subject_id, new Set())
        charLocMap.get(t.subject_id)!.add(t.object_id)
      }
    }
    // 如果同一角色出现在多个地点，这些地点之间有路径
    const locNameToId = new Map(locations.map(l => [l.name, l.id]))
    const connSet = new Set<string>()
    for (const [_char, locs] of charLocMap) {
      const locArr = [...locs]
      for (let i = 0; i < locArr.length - 1; i++) {
        for (let j = i + 1; j < locArr.length; j++) {
          const id1 = locNameToId.get(locArr[i])
          const id2 = locNameToId.get(locArr[j])
          if (id1 && id2) {
            const key = [id1, id2].sort().join('|')
            if (!connSet.has(key)) {
              connSet.add(key)
              const loc1 = locations.find(l => l.id === id1)
              if (loc1) loc1.connections.push(id2)
            }
          }
        }
      }
    }

    mapLocations.value = locations
    const novel = novelsStore.novels.find(n => n.id === novelId)
    if (novel) mapTitle.value = `${novel.title} — 世界地图`
  } catch (e) { console.error('加载世界条目失败', e) }
}

async function loadTimeline(novelId: string) {
  try {
    const outlineResp = await fetch(`/api/v1/novels/${novelId}/outline`)
    const outlineNodes: any[] = outlineResp.ok ? await outlineResp.json() : []
    const chapterResp = await fetch(`/api/v1/novels/${novelId}/chapters`)
    const chapters: any[] = chapterResp.ok ? await chapterResp.json() : []
    const events: any[] = []
    const storylines = new Set<string>()
    function flattenOutline(nodes: any[], storyline: string) {
      for (const node of nodes) {
        if (node.title || node.summary) {
          const isVol = node.level === 'volume' || node.level === 'act'
          events.push({ id: node.id, title: node.title || '未命名', description: node.summary || '', chapter: node.sort_order ?? events.length + 1, timestamp: isVol ? `卷${node.sort_order ?? ''}` : `第${node.sort_order ?? events.length + 1}章`, storyline, type: isVol ? 'turning_point' : 'major' })
          storylines.add(storyline)
        }
        if (node.children?.length) flattenOutline(node.children, storyline)
      }
    }
    flattenOutline(outlineNodes, '主线')
    if (events.length === 0 && chapters.length > 0) {
      for (const ch of chapters) {
        if (ch.summary || ch.title) {
          events.push({ id: ch.id, title: ch.title || `第${ch.number}章`, description: ch.summary || '', chapter: ch.number, timestamp: `第${ch.number}章`, storyline: '主线', type: ch.tension_score > 70 ? 'turning_point' : ch.tension_score > 40 ? 'major' : 'minor' })
          storylines.add('主线')
        }
      }
    }
    timelineEvents.value = events
    timelineStorylines.value = [...storylines]
  } catch (e) { console.error('加载时间线失败', e) }
}

async function loadWiki(novelId: string) {
  try {
    const [charResp, worldResp] = await Promise.all([
      fetch(`/api/v1/novels/${novelId}/characters`),
      fetch(`/api/v1/novels/${novelId}/world`),
    ])
    const chars: any[] = charResp.ok ? await charResp.json() : []
    const worldItems: any[] = worldResp.ok ? await worldResp.json() : []
    const catMap: Record<string, string> = { location: 'location', faction: 'faction', item: 'item', rule: 'lore', history: 'lore', power_system: 'lore', race: 'faction', geography: 'location' }
    const catLabel: Record<string, string> = { location: '地点', faction: '势力', item: '物品', rule: '规则', history: '历史', power_system: '力量体系', race: '种族', geography: '地理', mountain: '山脉', river: '河流', forest: '森林', castle: '城堡', village: '村落' }
    const entries: any[] = []
    for (const c of chars) {
      const traits = Array.isArray(c.traits) ? c.traits : []
      entries.push({ id: c.id, name: c.name, category: 'character', description: c.description || '', tags: [roleMap[c.role] || c.role, ...traits].filter(Boolean), properties: { '类型': roleMap[c.role] || c.role } })
    }
    for (const item of worldItems) {
      entries.push({ id: item.id, name: item.name, category: catMap[item.category] || 'lore', description: item.description || '', tags: [catLabel[item.category] || item.category].filter(Boolean), properties: item.properties || {} })
    }
    wikiEntries.value = entries
  } catch (e) { console.error('加载百科全书失败', e) }
}

// ═══ KNOWLEDGE GRAPH ════════════════════════════════════════
async function loadKnowledgeGraph(novelId: string) {
  kgLoading.value = true
  try {
    const [triplesResp, statsResp] = await Promise.all([
      fetch(`/api/v1/novels/${novelId}/knowledge-graph`),
      fetch(`/api/v1/novels/${novelId}/knowledge-graph/stats`),
    ])
    kgTriples.value = triplesResp.ok ? await triplesResp.json() : []
    kgStats.value = statsResp.ok ? await statsResp.json() : null
  } catch (e) { console.error('加载知识图谱失败', e) }
  finally { kgLoading.value = false }
}

const filteredTriples = computed(() => {
  if (!kgSearch.value.trim()) return kgTriples.value
  const q = kgSearch.value.trim().toLowerCase()
  return kgTriples.value.filter((t: any) =>
    t.subject_id?.toLowerCase().includes(q) ||
    t.object_id?.toLowerCase().includes(q) ||
    t.predicate?.toLowerCase().includes(q) ||
    t.description?.toLowerCase().includes(q)
  )
})

async function rebuildKG() {
  if (!selectedNovelId.value) return
  kgRebuilding.value = true
  try {
    const resp = await fetch(`/api/v1/novels/${selectedNovelId.value}/knowledge-graph/rebuild`, { method: 'POST' })
    if (resp.ok) {
      const result = await resp.json()
      alert(`重建完成：提取 ${result.rebuilt} 条三元组，处理 ${result.chapters_processed} 个章节`)
      await loadKnowledgeGraph(selectedNovelId.value)
    }
  } catch (e: any) { alert('重建失败: ' + e.message) }
  finally { kgRebuilding.value = false }
}

async function deleteTriple(tripleId: string) {
  if (!selectedNovelId.value) return
  await fetch(`/api/v1/novels/${selectedNovelId.value}/knowledge-graph/${tripleId}`, { method: 'DELETE' })
  kgTriples.value = kgTriples.value.filter((t: any) => t.id !== tripleId)
}

const typeColors: Record<string, string> = {
  character: '#3b82f6', location: '#22c55e', item: '#f59e0b',
  faction: '#8b5cf6', event: '#ef4444', concept: '#0ea5e9',
}
const typeLabels: Record<string, string> = {
  character: '角色', location: '地点', item: '物品',
  faction: '势力', event: '事件', concept: '概念',
}

function handleNodeClick(node: any) { console.log('Character:', node) }
function handleEventClick(event: any) { console.log('Event:', event) }
function handleLocationClick(loc: any) { console.log('Location:', loc) }
function handleAddLocation(pos: { x: number; y: number }) { console.log('Add location:', pos) }
function handleEntryClick(entry: any) { console.log('Wiki entry:', entry) }
</script>

<template>
  <div class="bp-page" @click="onPageClick">
    <!-- Header -->
    <div class="bp-header">
      <div class="bp-header-left">
        <h1 class="bp-title">📐 作品蓝图</h1>
        <p class="bp-sub">大纲规划 + 世界观设定 — 一处管理你的小说架构</p>
      </div>
      <div class="bp-header-right">
        <select v-model="selectedNovelId" class="bp-select">
          <option value="" disabled>选择作品</option>
          <option v-for="n in novelsStore.novels" :key="n.id" :value="n.id">{{ n.title }}</option>
        </select>
        <span v-if="currentNovel" class="bp-novel-info">
          {{ currentNovel.genre || '' }} · {{ (currentNovel.current_word_count || 0).toLocaleString() }}字
        </span>
      </div>
    </div>

    <!-- No novel selected -->
    <div v-if="!selectedNovelId" class="bp-empty">
      <div class="bp-empty-icon">📖</div>
      <div class="bp-empty-title">请先选择一部作品</div>
      <div class="bp-empty-desc">选择后可查看和编辑该作品的大纲与世界观</div>
    </div>

    <template v-else>
      <!-- Tabs -->
      <div class="bp-tabs">
        <div
          v-for="tab in tabs" :key="tab.key"
          :class="['bp-tab', { active: activeTab === tab.key }]"
          :style="activeTab === tab.key ? { '--tab-color': tab.color } : {}"
          @click="activeTab = tab.key"
        >
          <span class="tab-icon">{{ tab.icon }}</span>
          <span class="tab-label">{{ tab.label }}</span>
        </div>
      </div>

      <!-- Tab content -->
      <div class="bp-content">
        <!-- ═══ OUTLINE TAB ═══ -->
        <div v-show="activeTab === 'outline'" class="bp-panel outline-panel">
          <div class="outline-toolbar">
            <div class="ol-legend">
              <span v-for="(cfg, key) in levelConfig" :key="key" class="legend-item">
                <span class="legend-dot" :style="{ background: cfg.color }"></span>
                {{ cfg.icon }} {{ cfg.label }}
              </span>
            </div>
            <div class="ol-btns">
              <button class="btn btn-ghost" @click="addChild(null)">+ 根节点</button>
              <button class="btn btn-primary" :disabled="aiGenerating" @click="aiGenerateOutline">
                {{ aiGenerating ? '⏳ 生成中...' : '🤖 AI 生成大纲' }}
              </button>
            </div>
          </div>

          <div v-if="outlineStore.loading" class="bp-loading">加载中...</div>
          <div v-else-if="outlineStore.tree.length === 0" class="bp-empty-inner">
            <div class="bp-empty-icon">🏗️</div>
            <div class="bp-empty-title">暂无大纲节点</div>
            <div class="bp-empty-desc">点击「+ 根节点」或「AI 生成大纲」开始规划</div>
          </div>
          <div v-else class="ol-tree">
            <template v-for="node in outlineStore.tree" :key="node.id">
              <OutlineTreeNode
                :node="node" :depth="0" :editing-id="editingNodeId"
                :collapsed-set="collapsed" :selected-id="outlineStore.selectedNodeId"
                @contextmenu="showContextMenu" @select="outlineStore.selectNode"
                @toggle-collapse="toggleCollapse" @start-edit="startEdit"
                @drag-start="onDragStart" @drop="onDrop" @drag-over="onDragOver"
              />
            </template>
          </div>

          <!-- Edit panel -->
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
        </div>

        <!-- ═══ WORLDVIEW TABS ═══ -->
        <div v-show="activeTab === 'truth'" class="bp-panel">
          <TruthFilesView :novel-id="selectedNovelId" />
        </div>
        <div v-show="activeTab === 'audit'" class="bp-panel" style="overflow:auto;padding:16px">
          <AuditDashboard :novel-id="selectedNovelId" />
        </div>
        <div v-show="activeTab === 'graph'" class="bp-panel">
          <CharacterGraph :characters="characterNodes" :relations="characterRelations" @node-click="handleNodeClick" />
        </div>
        <div v-show="activeTab === 'timeline'" class="bp-panel">
          <TimelineView :events="timelineEvents" :storylines="timelineStorylines" @event-click="handleEventClick" />
        </div>
        <div v-show="activeTab === 'map'" class="bp-panel">
          <WorldMap :locations="mapLocations" :title="mapTitle" @location-click="handleLocationClick" @add-location="handleAddLocation" />
        </div>
        <div v-show="activeTab === 'wiki'" class="bp-panel" style="overflow:visible">
          <WikiBrowser :entries="wikiEntries" @entry-click="handleEntryClick" />
        </div>

        <!-- ═══ KNOWLEDGE GRAPH TAB ═══ -->
        <div v-show="activeTab === 'knowledge'" class="bp-panel" style="overflow:auto;padding:20px">
          <!-- KG Header -->
          <div class="kg-header">
            <div class="kg-header-left">
              <h3 class="kg-title">🔗 知识图谱三元组</h3>
              <span v-if="kgStats" class="kg-count">{{ kgStats.total_active || 0 }} 条活跃三元组</span>
            </div>
            <div class="kg-header-right">
              <input v-model="kgSearch" class="kg-search" placeholder="搜索实体/关系…" />
              <button class="btn btn-ghost" :disabled="kgRebuilding" @click="rebuildKG">
                {{ kgRebuilding ? '重建中…' : '🔄 重建' }}
              </button>
            </div>
          </div>

          <!-- KG Stats cards -->
          <div v-if="kgStats" class="kg-stats">
            <div class="kg-stat-card">
              <div class="ksc-val">{{ kgStats.total_active || 0 }}</div>
              <div class="ksc-label">活跃三元组</div>
            </div>
            <div class="kg-stat-card">
              <div class="ksc-val">{{ kgStats.unique_subjects || 0 }}</div>
              <div class="ksc-label">主语实体</div>
            </div>
            <div class="kg-stat-card">
              <div class="ksc-val">{{ kgStats.unique_predicates || 0 }}</div>
              <div class="ksc-label">关系类型</div>
            </div>
            <div class="kg-stat-card">
              <div class="ksc-val">{{ kgStats.chapters_covered || 0 }}</div>
              <div class="ksc-label">覆盖章节</div>
            </div>
          </div>

          <!-- KG Table -->
          <div v-if="kgLoading" class="bp-loading">加载中…</div>
          <div v-else-if="filteredTriples.length === 0" class="bp-empty-inner">
            <div class="bp-empty-icon">🔗</div>
            <div class="bp-empty-title">暂无知识三元组</div>
            <div class="bp-empty-desc">续写章节后将自动从 Observer 事实中提取，或点击「重建」批量生成</div>
          </div>
          <div v-else class="kg-table-wrap">
            <table class="kg-table">
              <thead>
                <tr>
                  <th>主语</th>
                  <th>关系</th>
                  <th>宾语</th>
                  <th>描述</th>
                  <th>置信度</th>
                  <th>来源章节</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="t in filteredTriples" :key="t.id">
                  <td>
                    <span class="kg-entity" :style="{ borderColor: typeColors[t.subject_type] || '#94a3b8' }">
                      {{ t.subject_id }}
                    </span>
                    <span class="kg-type-badge" :style="{ background: typeColors[t.subject_type] || '#94a3b8' }">
                      {{ typeLabels[t.subject_type] || t.subject_type }}
                    </span>
                  </td>
                  <td><span class="kg-predicate">{{ t.predicate }}</span></td>
                  <td>
                    <span class="kg-entity" :style="{ borderColor: typeColors[t.object_type] || '#94a3b8' }">
                      {{ t.object_id }}
                    </span>
                    <span class="kg-type-badge" :style="{ background: typeColors[t.object_type] || '#94a3b8' }">
                      {{ typeLabels[t.object_type] || t.object_type }}
                    </span>
                  </td>
                  <td class="kg-desc">{{ t.description || '-' }}</td>
                  <td>
                    <div class="kg-conf">
                      <div class="kg-conf-bar"><div class="kg-conf-fill" :style="{ width: (t.confidence * 100) + '%' }"></div></div>
                      <span class="kg-conf-num">{{ (t.confidence * 100).toFixed(0) }}%</span>
                    </div>
                  </td>
                  <td class="kg-chapter">{{ t.source_chapter ? '第' + t.source_chapter + '章' : '-' }}</td>
                  <td>
                    <button class="kg-del-btn" @click="deleteTriple(t.id)" title="删除">🗑</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </template>

    <!-- Context menu (outline) -->
    <Teleport to="body">
      <div v-if="contextMenu.show" class="ctx-menu" :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }">
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
.bp-page{display:flex;flex-direction:column;height:100%;overflow:hidden;position:relative}

/* Header */
.bp-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-shrink:0;flex-wrap:wrap;gap:12px}
.bp-header-left{min-width:0}
.bp-title{font-size:22px;font-weight:800;color:var(--gray-900);letter-spacing:-.3px;margin:0}
.bp-sub{font-size:13px;color:var(--gray-400);margin:4px 0 0}
.bp-header-right{display:flex;align-items:center;gap:10px}
.bp-select{padding:8px 14px;border:1px solid var(--gray-200);border-radius:10px;font-size:13px;color:var(--gray-700);background:#fff;min-width:180px;outline:none;transition:all .15s}
.bp-select:focus{border-color:var(--primary);box-shadow:0 0 0 3px rgba(99,102,241,.1)}
.bp-novel-info{font-size:12px;color:var(--gray-400);white-space:nowrap}

/* Empty */
.bp-empty{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
.bp-empty-inner{padding:40px;text-align:center}
.bp-empty-icon{font-size:36px;margin-bottom:10px}
.bp-empty-title{font-size:15px;font-weight:600;color:var(--gray-600);margin-bottom:4px}
.bp-empty-desc{font-size:12px;color:var(--gray-400)}

/* Tabs */
.bp-tabs{display:flex;gap:4px;padding:4px;background:var(--gray-100);border-radius:12px;flex-shrink:0;margin-bottom:14px;overflow-x:auto}
.bp-tab{display:flex;align-items:center;gap:5px;padding:9px 16px;cursor:pointer;color:var(--gray-500);font-size:13px;border-radius:10px;transition:all .18s;background:transparent;white-space:nowrap;border:none}
.bp-tab:hover{color:var(--gray-700);background:rgba(255,255,255,.6)}
.bp-tab.active{color:var(--tab-color, var(--primary));background:#fff;font-weight:600;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.tab-icon{font-size:15px}
.tab-label{font-size:13px}

/* Content */
.bp-content{flex:1;overflow:hidden;min-height:0;background:#fff;border:1px solid var(--gray-200);border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.06)}
.bp-panel{height:100%;overflow:hidden}
.bp-loading{padding:40px;text-align:center;color:var(--gray-400);font-size:13px}

/* ── Outline tab ── */
.outline-panel{display:flex;flex-direction:column;position:relative}
.outline-toolbar{display:flex;align-items:center;justify-content:space-between;padding:10px 16px;border-bottom:1px solid var(--gray-100);flex-shrink:0;gap:12px;flex-wrap:wrap}
.ol-legend{display:flex;gap:12px;flex-wrap:wrap}
.legend-item{display:flex;align-items:center;gap:4px;font-size:12px;color:var(--gray-500)}
.legend-dot{width:8px;height:8px;border-radius:50%}
.ol-btns{display:flex;gap:6px}
.ol-tree{flex:1;overflow-y:auto;padding:4px 0}

/* Edit panel */
.ol-edit-panel{position:absolute;top:50px;right:12px;width:320px;background:#fff;border:1px solid var(--gray-200);border-radius:14px;padding:18px;box-shadow:0 8px 30px rgba(0,0,0,.12);z-index:10}
.edit-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;font-size:14px;font-weight:600;color:var(--gray-800)}
.edit-close{background:none;border:none;cursor:pointer;font-size:16px;color:var(--gray-400)}
.edit-field{margin-bottom:10px}
.edit-field label{display:block;font-size:12px;font-weight:500;color:var(--gray-500);margin-bottom:4px}
.edit-input{width:100%;padding:7px 10px;border:1px solid var(--gray-200);border-radius:8px;font-size:13px;outline:none}
.edit-input:focus{border-color:var(--primary)}
.edit-textarea{width:100%;padding:7px 10px;border:1px solid var(--gray-200);border-radius:8px;font-size:13px;outline:none;resize:vertical;line-height:1.5}
.edit-textarea:focus{border-color:var(--primary)}
.edit-actions{display:flex;justify-content:flex-end;gap:6px}

/* Context menu */
.ctx-menu{position:fixed;z-index:9999;background:#fff;border:1px solid var(--gray-200);border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.15);padding:6px 0;min-width:180px}
.ctx-item{padding:8px 14px;font-size:13px;cursor:pointer;color:var(--gray-700);display:flex;align-items:center;gap:8px;transition:all .1s}
.ctx-item:hover{background:var(--primary-light);color:var(--primary)}
.ctx-danger{color:var(--danger)}
.ctx-danger:hover{background:#fef2f2;color:var(--danger)}
.ctx-sep{height:1px;background:var(--gray-100);margin:4px 0}

/* Transitions */
.slide-enter-active,.slide-leave-active{transition:all .2s}
.slide-enter-from,.slide-leave-to{opacity:0;transform:translateX(10px)}

/* ── Knowledge Graph ── */
.kg-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:12px}
.kg-header-left{display:flex;align-items:center;gap:12px}
.kg-header-right{display:flex;align-items:center;gap:8px}
.kg-title{font-size:16px;font-weight:700;color:var(--gray-800);margin:0}
.kg-count{font-size:12px;color:var(--gray-400);background:var(--gray-100);padding:3px 10px;border-radius:10px}
.kg-search{padding:7px 14px;border:1px solid var(--gray-200);border-radius:8px;font-size:13px;outline:none;width:200px;transition:all .15s}
.kg-search:focus{border-color:var(--primary);box-shadow:0 0 0 3px rgba(99,102,241,.1)}

.kg-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}
.kg-stat-card{background:var(--gray-50,#f8fafc);border:1px solid var(--gray-200);border-radius:12px;padding:14px 16px;text-align:center}
.ksc-val{font-size:24px;font-weight:800;color:var(--primary);letter-spacing:-.5px}
.ksc-label{font-size:11px;color:var(--gray-400);margin-top:2px}

.kg-table-wrap{overflow-x:auto}
.kg-table{width:100%;border-collapse:collapse;font-size:13px}
.kg-table th{text-align:left;padding:10px 12px;font-size:11px;font-weight:600;color:var(--gray-400);
  text-transform:uppercase;letter-spacing:.5px;border-bottom:2px solid var(--gray-100);white-space:nowrap}
.kg-table td{padding:10px 12px;border-bottom:1px solid var(--gray-100);vertical-align:middle}
.kg-table tr:hover{background:var(--gray-50,#f8fafc)}
.kg-entity{font-weight:600;color:var(--gray-800);padding:2px 8px;border-radius:6px;border:1.5px solid;
  display:inline-block;font-size:12px;margin-right:4px}
.kg-type-badge{display:inline-block;font-size:10px;color:#fff;padding:1px 6px;border-radius:4px;font-weight:500;vertical-align:middle}
.kg-predicate{background:#eef2ff;color:#6366f1;padding:3px 10px;border-radius:6px;font-weight:600;font-size:12px;white-space:nowrap}
.kg-desc{max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--gray-500);font-size:12px}
.kg-conf{display:flex;align-items:center;gap:6px}
.kg-conf-bar{width:48px;height:5px;background:var(--gray-100);border-radius:3px;overflow:hidden}
.kg-conf-fill{height:100%;background:var(--primary);border-radius:3px}
.kg-conf-num{font-size:11px;color:var(--gray-500);font-weight:500}
.kg-chapter{font-size:11px;color:var(--gray-400);white-space:nowrap}
.kg-del-btn{background:none;border:none;cursor:pointer;font-size:14px;padding:4px;border-radius:6px;color:var(--gray-400);transition:all .15s}
.kg-del-btn:hover{background:#fee2e2;color:#dc2626}

@media(max-width:900px){
  .kg-stats{grid-template-columns:repeat(2,1fr)}
}
</style>
