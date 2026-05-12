<script setup lang="ts">
import { ref, computed } from 'vue'

export interface WikiEntry {
  id: string
  name: string
  category: 'character' | 'location' | 'item' | 'faction' | 'lore'
  description?: string
  tags?: string[]
  properties?: Record<string, string>  // 自定义属性
  relatedIds?: string[]
}

const props = withDefaults(defineProps<{
  entries: WikiEntry[]
}>(), {
  entries: () => [],
})

const emit = defineEmits<{
  (e: 'entryClick', entry: WikiEntry): void
}>()

// 分类配置
const categories = [
  { key: 'character', label: '人物', icon: '👥', color: '#3b82f6' },
  { key: 'location', label: '地点', icon: '📍', color: '#22c55e' },
  { key: 'item', label: '物品', icon: '💎', color: '#f59e0b' },
  { key: 'faction', label: '势力', icon: '🏛️', color: '#8b5cf6' },
  { key: 'lore', label: '设定', icon: '📜', color: '#ec4899' },
]

const activeCategory = ref<string>('character')
const searchQuery = ref('')
const selectedEntry = ref<WikiEntry | null>(null)

const filteredEntries = computed(() => {
  let list = props.entries.filter(e => e.category === activeCategory.value)
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(e =>
      e.name.toLowerCase().includes(q) ||
      (e.description || '').toLowerCase().includes(q) ||
      (e.tags || []).some(t => t.toLowerCase().includes(q))
    )
  }
  return list
})

const categoryCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const cat of categories) {
    counts[cat.key] = props.entries.filter(e => e.category === cat.key).length
  }
  return counts
})

function selectEntry(entry: WikiEntry) {
  selectedEntry.value = entry
  emit('entryClick', entry)
}

function getRelatedEntries(entry: WikiEntry): WikiEntry[] {
  if (!entry.relatedIds) return []
  return props.entries.filter(e => entry.relatedIds!.includes(e.id))
}

function getCategoryMeta(cat: string) {
  return categories.find(c => c.key === cat) || categories[0]
}
</script>

<template>
  <div class="wiki-wrap">
    <!-- Left: Categories & List -->
    <div class="wiki-left">
      <!-- Search -->
      <div class="wiki-search">
        <span class="search-icon">🔍</span>
        <input
          v-model="searchQuery"
          placeholder="搜索条目..."
          class="search-input"
        />
      </div>

      <!-- Category tabs -->
      <div class="wiki-cats">
        <div
          v-for="cat in categories"
          :key="cat.key"
          :class="['wiki-cat', { active: activeCategory === cat.key }]"
          :style="activeCategory === cat.key ? { borderColor: cat.color, color: cat.color } : {}"
          @click="activeCategory = cat.key"
        >
          <span class="cat-icon">{{ cat.icon }}</span>
          <span class="cat-label">{{ cat.label }}</span>
          <span class="cat-count">{{ categoryCounts[cat.key] || 0 }}</span>
        </div>
      </div>

      <!-- Entry list -->
      <div class="wiki-list">
        <div
          v-for="entry in filteredEntries"
          :key="entry.id"
          :class="['wiki-item', { active: selectedEntry?.id === entry.id }]"
          @click="selectEntry(entry)"
        >
          <div class="wiki-item-name">{{ entry.name }}</div>
          <div class="wiki-item-tags" v-if="entry.tags?.length">
            <span v-for="tag in entry.tags.slice(0, 3)" :key="tag" class="tag">{{ tag }}</span>
          </div>
        </div>

        <!-- Empty -->
        <div v-if="filteredEntries.length === 0" class="wiki-empty">
          <div class="wiki-empty-icon">{{ getCategoryMeta(activeCategory).icon }}</div>
          <div class="wiki-empty-text">暂无{{ getCategoryMeta(activeCategory).label }}条目</div>
        </div>
      </div>
    </div>

    <!-- Right: Detail -->
    <div class="wiki-right">
      <template v-if="selectedEntry">
        <div class="wiki-detail-head">
          <span class="detail-cat-icon" :style="{ background: getCategoryMeta(selectedEntry.category).color + '20', color: getCategoryMeta(selectedEntry.category).color }">
            {{ getCategoryMeta(selectedEntry.category).icon }}
          </span>
          <div>
            <h3 class="detail-name">{{ selectedEntry.name }}</h3>
            <span class="detail-cat">{{ getCategoryMeta(selectedEntry.category).label }}</span>
          </div>
        </div>

        <!-- Description -->
        <div class="detail-section">
          <div class="detail-section-title">描述</div>
          <p class="detail-desc">{{ selectedEntry.description || '暂无描述' }}</p>
        </div>

        <!-- Properties -->
        <div class="detail-section" v-if="selectedEntry.properties && Object.keys(selectedEntry.properties).length">
          <div class="detail-section-title">属性</div>
          <div class="detail-props">
            <div v-for="(val, key) in selectedEntry.properties" :key="key" class="prop-row">
              <span class="prop-key">{{ key }}</span>
              <span class="prop-val">{{ val }}</span>
            </div>
          </div>
        </div>

        <!-- Tags -->
        <div class="detail-section" v-if="selectedEntry.tags?.length">
          <div class="detail-section-title">标签</div>
          <div class="detail-tags">
            <span v-for="tag in selectedEntry.tags" :key="tag" class="tag-lg">{{ tag }}</span>
          </div>
        </div>

        <!-- Related -->
        <div class="detail-section" v-if="getRelatedEntries(selectedEntry).length">
          <div class="detail-section-title">关联条目</div>
          <div class="detail-related">
            <div
              v-for="rel in getRelatedEntries(selectedEntry)"
              :key="rel.id"
              class="related-item"
              @click="selectEntry(rel)"
            >
              <span>{{ getCategoryMeta(rel.category).icon }}</span>
              {{ rel.name }}
            </div>
          </div>
        </div>
      </template>

      <!-- No selection state -->
      <div v-else class="wiki-no-select">
        <div class="wiki-no-icon">📖</div>
        <div class="wiki-no-title">选择一个条目查看详情</div>
        <div class="wiki-no-desc">从左侧列表中选择，或使用搜索功能</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wiki-wrap{display:flex;height:100%;min-height:450px;gap:0;border:1px solid var(--gray-200);border-radius:var(--radius);overflow:hidden;background:#fff}

/* Left panel */
.wiki-left{width:280px;border-right:1px solid var(--gray-200);display:flex;flex-direction:column;flex-shrink:0}

.wiki-search{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--gray-100)}
.search-icon{font-size:14px;color:var(--gray-400)}
.search-input{border:none;outline:none;background:none;font-size:13px;width:100%;color:var(--gray-700)}
.search-input::placeholder{color:var(--gray-400)}

.wiki-cats{display:flex;overflow-x:auto;padding:8px 8px 0;gap:4px;flex-shrink:0}
.wiki-cat{display:flex;align-items:center;gap:4px;padding:6px 10px;border-radius:var(--radius-xs);
  cursor:pointer;font-size:12px;color:var(--gray-500);border:1px solid transparent;transition:all .15s;white-space:nowrap}
.wiki-cat:hover{background:var(--gray-50)}
.wiki-cat.active{background:#fff;border-color:var(--primary);font-weight:500}
.cat-icon{font-size:14px}
.cat-count{font-size:10px;background:var(--gray-100);color:var(--gray-500);padding:0 5px;border-radius:8px;min-width:18px;text-align:center}

.wiki-list{flex:1;overflow-y:auto;padding:8px}
.wiki-item{padding:10px 12px;border-radius:var(--radius-xs);cursor:pointer;transition:all .12s;margin-bottom:2px}
.wiki-item:hover{background:var(--gray-50)}
.wiki-item.active{background:var(--primary-light);border-left:3px solid var(--primary)}
.wiki-item-name{font-size:13px;font-weight:500;color:var(--gray-700);margin-bottom:3px}
.wiki-item-tags{display:flex;gap:4px;flex-wrap:wrap}
.tag{font-size:10px;padding:1px 6px;border-radius:6px;background:var(--gray-100);color:var(--gray-500)}

.wiki-empty{padding:30px 16px;text-align:center}
.wiki-empty-icon{font-size:28px;margin-bottom:8px}
.wiki-empty-text{font-size:12px;color:var(--gray-400)}

/* Right panel */
.wiki-right{flex:1;overflow-y:auto;padding:20px 24px}

.wiki-detail-head{display:flex;align-items:center;gap:12px;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid var(--gray-100)}
.detail-cat-icon{width:42px;height:42px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px}
.detail-name{font-size:18px;font-weight:700;color:var(--gray-800)}
.detail-cat{font-size:12px;color:var(--gray-400)}

.detail-section{margin-bottom:18px}
.detail-section-title{font-size:12px;font-weight:600;color:var(--gray-500);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px}
.detail-desc{font-size:13px;color:var(--gray-700);line-height:1.7}

.detail-props{background:var(--gray-50);border-radius:var(--radius-xs);padding:10px 12px}
.prop-row{display:flex;justify-content:space-between;padding:5px 0;font-size:13px;
  border-bottom:1px solid var(--gray-100)}
.prop-row:last-child{border-bottom:none}
.prop-key{color:var(--gray-500);font-weight:500}
.prop-val{color:var(--gray-800)}

.detail-tags{display:flex;gap:6px;flex-wrap:wrap}
.tag-lg{font-size:11px;padding:3px 10px;border-radius:10px;background:var(--gray-100);color:var(--gray-600)}

.detail-related{display:flex;flex-direction:column;gap:4px}
.related-item{display:flex;align-items:center;gap:6px;padding:6px 10px;border-radius:var(--radius-xs);
  cursor:pointer;font-size:13px;color:var(--gray-600);transition:background .12s}
.related-item:hover{background:var(--gray-50)}

.wiki-no-select{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;text-align:center}
.wiki-no-icon{font-size:40px;margin-bottom:12px}
.wiki-no-title{font-size:15px;font-weight:600;color:var(--gray-600);margin-bottom:4px}
.wiki-no-desc{font-size:12px;color:var(--gray-400)}
</style>
