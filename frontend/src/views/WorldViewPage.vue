<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useNovelsStore } from '@/stores/novels'
import CharacterGraph from '@/components/CharacterGraph.vue'
import TimelineView from '@/components/TimelineView.vue'
import WorldMap from '@/components/WorldMap.vue'
import WikiBrowser from '@/components/WikiBrowser.vue'
import TruthFilesView from '@/components/TruthFilesView.vue'
import AuditDashboard from '@/components/AuditDashboard.vue'

const store = useNovelsStore()

// ── Novel selector ──────────────────────────────────────────
const selectedNovelId = ref('')
const currentNovelId = computed(() => selectedNovelId.value)

// Active tab
type TabKey = 'truth' | 'audit' | 'graph' | 'timeline' | 'map' | 'wiki'
const activeTab = ref<TabKey>('truth')

const tabs = [
  { key: 'truth' as TabKey, icon: '📚', label: '真相文件', color: '#6366f1' },
  { key: 'audit' as TabKey, icon: '📈', label: '张力心电图', color: '#ef4444' },
  { key: 'graph' as TabKey, icon: '👥', label: '人物关系', color: '#8b5cf6' },
  { key: 'timeline' as TabKey, icon: '⏳', label: '时间线', color: '#f59e0b' },
  { key: 'map' as TabKey, icon: '🗺️', label: '世界地图', color: '#22c55e' },
  { key: 'wiki' as TabKey, icon: '📖', label: '百科全书', color: '#ec4899' },
]

// ── Real data state ─────────────────────────────────────────
const loading = ref(false)

const roleMap: Record<string, string> = {
  protagonist: '主角', antagonist: '反派', supporting: '配角',
  mentor: '师长', love_interest: '红颜',
}

// Characters → CharacterGraph
const characterNodes = ref<any[]>([])
const characterRelations = ref<any[]>([])

// Outline / Chapters → Timeline
const timelineEvents = ref<any[]>([])
const timelineStorylines = ref<string[]>([])

// World items (location) → WorldMap
const mapLocations = ref<any[]>([])
const mapTitle = ref('世界地图')

// World items + Characters → WikiBrowser
const wikiEntries = ref<any[]>([])

// ── Data loading ────────────────────────────────────────────
async function loadAllData(novelId: string) {
  if (!novelId) return
  loading.value = true
  try {
    await Promise.all([
      loadCharacters(novelId),
      loadWorldItems(novelId),
      loadTimeline(novelId),
    ])
    buildWikiEntries()
  } catch (e) {
    console.error('加载世界观数据失败', e)
  } finally {
    loading.value = false
  }
}

async function loadCharacters(novelId: string) {
  try {
    const resp = await fetch(`/api/v1/novels/${novelId}/characters`)
    if (!resp.ok) return
    const chars: any[] = await resp.json()

    characterNodes.value = chars.map(c => ({
      id: c.id,
      name: c.name,
      role: roleMap[c.role] || c.role || '配角',
      appearances: c.first_appearance || 0,
    }))

    // 从 relationships 字段提取关系边
    const rels: any[] = []
    for (const c of chars) {
      const relationships = Array.isArray(c.relationships) ? c.relationships : []
      for (const r of relationships) {
        const targetChar = chars.find(t =>
          t.name === r.target || t.name === r.name || t.id === r.target_id
        )
        if (targetChar) {
          rels.push({
            source: c.id,
            target: targetChar.id,
            label: r.type || r.label || r.relationship || '关联',
            strength: r.strength ?? 0.6,
          })
        }
      }
    }
    characterRelations.value = rels
  } catch (e) {
    console.error('加载角色失败', e)
  }
}

async function loadWorldItems(novelId: string) {
  try {
    const resp = await fetch(`/api/v1/novels/${novelId}/world`)
    if (!resp.ok) return
    const items: any[] = await resp.json()

    // 类型映射: world item category → MapLocation type
    const typeMap: Record<string, string> = {
      location: 'city', mountain: 'mountain', river: 'river',
      forest: 'forest', castle: 'castle', village: 'village',
    }

    // 从 location 类型的 world items 提取地图数据
    const locationItems = items.filter(i =>
      i.category === 'location' || i.category === 'mountain' ||
      i.category === 'river' || i.category === 'forest' ||
      i.category === 'castle' || i.category === 'village'
    )

    // 为地点分配坐标（若 properties 中有就用，否则自动散布）
    mapLocations.value = locationItems.map((item, idx) => {
      const props = item.properties || {}
      return {
        id: item.id,
        name: item.name,
        x: props.x ?? (15 + ((idx * 37 + 13) % 70)),
        y: props.y ?? (15 + ((idx * 53 + 7) % 70)),
        type: typeMap[item.category] || 'city',
        description: item.description || '',
      }
    })

    // 更新地图标题
    const novel = store.novels.find(n => n.id === novelId)
    if (novel) mapTitle.value = `${novel.title} — 世界地图`
  } catch (e) {
    console.error('加载世界观条目失败', e)
  }
}

async function loadTimeline(novelId: string) {
  try {
    // 从大纲获取结构化事件
    const outlineResp = await fetch(`/api/v1/novels/${novelId}/outline`)
    const outlineNodes: any[] = outlineResp.ok ? await outlineResp.json() : []

    // 从章节摘要获取事件
    const chapterResp = await fetch(`/api/v1/novels/${novelId}/chapters`)
    const chapters: any[] = chapterResp.ok ? await chapterResp.json() : []

    const events: any[] = []
    const storylines = new Set<string>()

    // 从大纲节点提取（卷/章级别）
    function flattenOutline(nodes: any[], storyline: string) {
      for (const node of nodes) {
        if (node.title || node.summary) {
          const isVolume = node.level === 'volume' || node.level === 'act'
          events.push({
            id: node.id,
            title: node.title || '未命名',
            description: node.summary || '',
            chapter: node.sort_order ?? events.length + 1,
            timestamp: isVolume ? `卷${node.sort_order ?? ''}` : `第${node.sort_order ?? events.length + 1}章`,
            storyline,
            type: isVolume ? 'turning_point' : 'major',
          })
          storylines.add(storyline)
        }
        if (node.children?.length) {
          flattenOutline(node.children, storyline)
        }
      }
    }
    flattenOutline(outlineNodes, '主线')

    // 从章节摘要补充（若大纲为空）
    if (events.length === 0 && chapters.length > 0) {
      for (const ch of chapters) {
        if (ch.summary || ch.title) {
          events.push({
            id: ch.id,
            title: ch.title || `第${ch.number}章`,
            description: ch.summary || '',
            chapter: ch.number,
            timestamp: `第${ch.number}章`,
            storyline: '主线',
            type: ch.tension_score > 70 ? 'turning_point' : ch.tension_score > 40 ? 'major' : 'minor',
          })
          storylines.add('主线')
        }
      }
    }

    timelineEvents.value = events
    timelineStorylines.value = [...storylines]
  } catch (e) {
    console.error('加载时间线失败', e)
  }
}

function buildWikiEntries() {
  const entries: any[] = []

  // 角色 → wiki
  for (const c of characterNodes.value) {
    entries.push({
      id: `char-${c.id}`,
      name: c.name,
      category: 'character' as const,
      description: c.description || `${c.role}`,
      tags: [c.role].filter(Boolean),
    })
  }

  // 世界条目 → wiki (从 mapLocations + 其他 world items)
  // 单独再拉一次所有 world items（已在内存中可以直接用 fetch 结果）
  // 简化: 使用 mapLocations 作为 location 类条目
  for (const loc of mapLocations.value) {
    entries.push({
      id: `loc-${loc.id}`,
      name: loc.name,
      category: 'location' as const,
      description: loc.description || '',
      tags: [loc.type].filter(Boolean),
    })
  }

  wikiEntries.value = entries
}

// ── 完整 wiki 加载（包含所有 world item 类别）──
async function loadFullWiki(novelId: string) {
  try {
    const [charResp, worldResp] = await Promise.all([
      fetch(`/api/v1/novels/${novelId}/characters`),
      fetch(`/api/v1/novels/${novelId}/world`),
    ])
    const chars: any[] = charResp.ok ? await charResp.json() : []
    const worldItems: any[] = worldResp.ok ? await worldResp.json() : []

    const catMap: Record<string, string> = {
      location: 'location', faction: 'faction', item: 'item',
      rule: 'lore', history: 'lore', power_system: 'lore',
      race: 'faction', geography: 'location',
    }
    const catLabel: Record<string, string> = {
      location: '地点', faction: '势力', item: '物品', rule: '规则', history: '历史',
      power_system: '力量体系', race: '种族', geography: '地理',
      mountain: '山脉', river: '河流', forest: '森林', castle: '城堡', village: '村落',
    }

    const entries: any[] = []

    for (const c of chars) {
      const traits = Array.isArray(c.traits) ? c.traits : []
      entries.push({
        id: c.id,
        name: c.name,
        category: 'character' as const,
        description: c.description || '',
        tags: [roleMap[c.role] || c.role, ...traits].filter(Boolean),
        properties: { '类型': roleMap[c.role] || c.role },
      })
    }

    for (const item of worldItems) {
      entries.push({
        id: item.id,
        name: item.name,
        category: (catMap[item.category] || 'lore') as any,
        description: item.description || '',
        tags: [catLabel[item.category] || item.category].filter(Boolean),
        properties: item.properties || {},
      })
    }

    wikiEntries.value = entries
  } catch (e) {
    console.error('加载百科全书失败', e)
  }
}

// ── Watchers & init ─────────────────────────────────────────
watch(selectedNovelId, async (id) => {
  if (id) {
    await loadAllData(id)
    await loadFullWiki(id)
  }
})

onMounted(async () => {
  await store.loadNovels()
  if (store.novels.length > 0) {
    selectedNovelId.value = store.novels[0].id
  }
})

function handleNodeClick(node: any) {
  console.log('Character clicked:', node)
}

function handleEventClick(event: any) {
  console.log('Event clicked:', event)
}

function handleLocationClick(loc: any) {
  console.log('Location clicked:', loc)
}

function handleAddLocation(pos: { x: number; y: number }) {
  console.log('Add location at:', pos)
}

function handleEntryClick(entry: any) {
  console.log('Wiki entry clicked:', entry)
}
</script>

<template>
  <div class="page-wv">
    <!-- Header -->
    <div class="page-head">
      <div class="page-head-row">
        <div>
          <h1 class="page-title">🌍 世界观设定</h1>
          <p class="page-desc">人物关系、时间线、地图标注、百科全书 — 构建你的小说宇宙</p>
        </div>
        <select class="novel-select" v-model="selectedNovelId">
          <option value="" disabled>选择作品</option>
          <option v-for="n in store.novels" :key="n.id" :value="n.id">{{ n.title }}</option>
        </select>
      </div>
      <div v-if="loading" class="page-loading">⏳ 加载中...</div>
    </div>

    <!-- Tabs -->
    <div class="wv-tabs">
      <div
        v-for="tab in tabs"
        :key="tab.key"
        :class="['wv-tab', { active: activeTab === tab.key }]"
        :style="activeTab === tab.key ? { '--tab-color': tab.color } : {}"
        @click="activeTab = tab.key"
      >
        <span class="tab-icon">{{ tab.icon }}</span>
        <span class="tab-label">{{ tab.label }}</span>
      </div>
    </div>

    <!-- Tab content -->
    <div class="wv-content">
      <div v-show="activeTab === 'truth'" class="wv-panel">
        <TruthFilesView :novel-id="currentNovelId" />
      </div>

      <div v-show="activeTab === 'audit'" class="wv-panel" style="overflow:auto;padding:16px">
        <AuditDashboard :novel-id="currentNovelId" />
      </div>

      <div v-show="activeTab === 'graph'" class="wv-panel">
        <CharacterGraph
          :characters="characterNodes"
          :relations="characterRelations"
          @node-click="handleNodeClick"
        />
      </div>

      <div v-show="activeTab === 'timeline'" class="wv-panel">
        <TimelineView
          :events="timelineEvents"
          :storylines="timelineStorylines"
          @event-click="handleEventClick"
        />
      </div>

      <div v-show="activeTab === 'map'" class="wv-panel">
        <WorldMap
          :locations="mapLocations"
          :title="mapTitle"
          @location-click="handleLocationClick"
          @add-location="handleAddLocation"
        />
      </div>

      <div v-show="activeTab === 'wiki'" class="wv-panel wv-panel-wiki">
        <WikiBrowser
          :entries="wikiEntries"
          @entry-click="handleEntryClick"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-wv{display:flex;flex-direction:column;height:calc(100vh - 80px);max-width:1200px}
.page-head{margin-bottom:20px;flex-shrink:0}
.page-head-row{display:flex;align-items:center;justify-content:space-between;gap:16px}
.page-title{font-size:22px;font-weight:800;color:var(--gray-900);letter-spacing:-.3px}
.page-desc{font-size:13px;color:var(--gray-400);margin-top:6px}
.novel-select{padding:8px 14px;border:1px solid var(--gray-200);border-radius:10px;font-size:13px;
  color:var(--gray-700);background:#fff;cursor:pointer;min-width:180px;transition:all .15s}
.novel-select:hover{border-color:var(--primary)}
.novel-select:focus{outline:none;border-color:var(--primary);box-shadow:0 0 0 3px rgba(99,102,241,.12)}
.page-loading{font-size:12px;color:var(--primary);margin-top:8px}

/* Tabs */
.wv-tabs{display:flex;gap:6px;padding:4px;background:var(--gray-100);border-radius:12px;flex-shrink:0;margin-bottom:16px}
.wv-tab{display:flex;align-items:center;gap:6px;padding:10px 20px;cursor:pointer;
  border:none;color:var(--gray-500);font-size:13px;border-radius:10px;
  transition:all .18s;background:transparent}
.wv-tab:hover{color:var(--gray-700);background:rgba(255,255,255,.6)}
.wv-tab.active{color:var(--tab-color, var(--primary));background:#fff;font-weight:600;
  box-shadow:0 1px 3px rgba(0,0,0,.08)}
.tab-icon{font-size:16px}
.tab-label{font-size:13px}

/* Content */
.wv-content{flex:1;overflow:hidden;min-height:0;background:#fff;border:1px solid var(--gray-200);
  border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.06)}
.wv-panel{height:100%;overflow:hidden}
.wv-panel-wiki{overflow:visible}
</style>
