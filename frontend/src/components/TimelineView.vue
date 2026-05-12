<script setup lang="ts">
import { ref, computed } from 'vue'

export interface TimelineEvent {
  id: string
  title: string
  description?: string
  chapter?: number
  timestamp?: string      // 故事内时间
  storyline?: string      // 所属故事线
  type?: 'major' | 'minor' | 'turning_point'
}

const props = withDefaults(defineProps<{
  events: TimelineEvent[]
  storylines?: string[]
}>(), {
  events: () => [],
  storylines: () => [],
})

const emit = defineEmits<{
  (e: 'eventClick', event: TimelineEvent): void
}>()

// 排序方式
type SortMode = 'chapter' | 'time'
const sortMode = ref<SortMode>('chapter')
const filterLine = ref<string>('')

const storylineColors: Record<string, string> = {
  '主线': '#3b82f6',
  '副线A': '#22c55e',
  '副线B': '#f59e0b',
  '副线C': '#8b5cf6',
  '副线D': '#ec4899',
}

const defaultColors = ['#6366f1', '#14b8a6', '#f97316', '#06b6d4', '#84cc16']

function getLineColor(line: string): string {
  if (storylineColors[line]) return storylineColors[line]
  const idx = (props.storylines || []).indexOf(line)
  return defaultColors[idx % defaultColors.length] || '#6366f1'
}

const sortedEvents = computed(() => {
  let list = [...props.events]
  if (filterLine.value) {
    list = list.filter(e => e.storyline === filterLine.value)
  }
  if (sortMode.value === 'chapter') {
    list.sort((a, b) => (a.chapter || 0) - (b.chapter || 0))
  } else {
    list.sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''))
  }
  return list
})

const allStorylines = computed(() => {
  if (props.storylines.length) return props.storylines
  const set = new Set(props.events.map(e => e.storyline).filter(Boolean) as string[])
  return Array.from(set)
})

function getTypeIcon(type?: string): string {
  switch (type) {
    case 'turning_point': return '⚡'
    case 'major': return '🔸'
    default: return '•'
  }
}

const selectedEvent = ref<TimelineEvent | null>(null)
function selectEvent(ev: TimelineEvent) {
  selectedEvent.value = ev
  emit('eventClick', ev)
}
</script>

<template>
  <div class="tl-wrap">
    <!-- Toolbar -->
    <div class="tl-toolbar">
      <div class="tl-sort">
        <button :class="['btn-tab', { active: sortMode === 'chapter' }]" @click="sortMode = 'chapter'">按章节</button>
        <button :class="['btn-tab', { active: sortMode === 'time' }]" @click="sortMode = 'time'">按时间</button>
      </div>
      <div class="tl-filters">
        <button
          :class="['btn-filter', { active: !filterLine }]"
          @click="filterLine = ''"
        >全部</button>
        <button
          v-for="line in allStorylines"
          :key="line"
          :class="['btn-filter', { active: filterLine === line }]"
          :style="filterLine === line ? { background: getLineColor(line) + '22', color: getLineColor(line), borderColor: getLineColor(line) } : {}"
          @click="filterLine = line"
        >{{ line }}</button>
      </div>
    </div>

    <!-- Timeline -->
    <div class="tl-body">
      <div class="tl-line"></div>
      <div
        v-for="(ev, idx) in sortedEvents"
        :key="ev.id"
        class="tl-item"
        :class="{ selected: selectedEvent?.id === ev.id }"
        @click="selectEvent(ev)"
      >
        <div class="tl-dot" :style="{ background: getLineColor(ev.storyline || '主线') }">
          <span class="tl-icon">{{ getTypeIcon(ev.type) }}</span>
        </div>
        <div class="tl-card">
          <div class="tl-card-head">
            <span class="tl-chapter" v-if="ev.chapter">第{{ ev.chapter }}章</span>
            <span class="tl-time" v-if="ev.timestamp">{{ ev.timestamp }}</span>
            <span class="tl-line-badge" :style="{ color: getLineColor(ev.storyline || '主线') }">
              {{ ev.storyline || '主线' }}
            </span>
          </div>
          <div class="tl-title">{{ ev.title }}</div>
          <div class="tl-desc" v-if="ev.description">{{ ev.description }}</div>
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="sortedEvents.length === 0" class="tl-empty">
        <div class="tl-empty-icon">⏳</div>
        <div class="tl-empty-title">暂无事件</div>
        <div class="tl-empty-desc">分析小说后，故事事件将自动填充到时间线</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tl-wrap{display:flex;flex-direction:column;height:100%;overflow:hidden}

.tl-toolbar{display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid var(--gray-200);flex-shrink:0;flex-wrap:wrap}
.tl-sort{display:flex;gap:4px}
.btn-tab{padding:5px 12px;border:1px solid var(--gray-200);border-radius:var(--radius-xs);
  font-size:12px;cursor:pointer;background:#fff;color:var(--gray-600);transition:all .15s}
.btn-tab.active{background:var(--primary);color:#fff;border-color:var(--primary)}
.tl-filters{display:flex;gap:4px;flex-wrap:wrap}
.btn-filter{padding:4px 10px;border:1px solid var(--gray-200);border-radius:12px;
  font-size:11px;cursor:pointer;background:#fff;color:var(--gray-500);transition:all .15s}
.btn-filter.active{border-color:var(--primary);color:var(--primary);background:var(--primary-light)}

.tl-body{flex:1;overflow-y:auto;padding:20px 0 20px 30px;position:relative}
.tl-line{position:absolute;left:42px;top:0;bottom:0;width:2px;background:var(--gray-200)}

.tl-item{display:flex;align-items:flex-start;gap:16px;margin-bottom:20px;position:relative;cursor:pointer}
.tl-item.selected .tl-card{border-color:var(--primary);box-shadow:0 0 0 2px var(--primary-light)}
.tl-dot{width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  flex-shrink:0;position:relative;z-index:1;border:3px solid #fff;box-shadow:var(--shadow-sm)}
.tl-icon{font-size:10px;color:#fff}
.tl-card{flex:1;background:#fff;border:1px solid var(--gray-200);border-radius:var(--radius-sm);
  padding:12px 16px;transition:all .15s}
.tl-card:hover{box-shadow:var(--shadow-sm);border-color:var(--gray-300)}
.tl-card-head{display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap}
.tl-chapter{font-size:11px;background:var(--gray-100);color:var(--gray-600);padding:1px 8px;border-radius:8px}
.tl-time{font-size:11px;color:var(--gray-400)}
.tl-line-badge{font-size:11px;font-weight:500;margin-left:auto}
.tl-title{font-size:14px;font-weight:600;color:var(--gray-800);margin-bottom:4px}
.tl-desc{font-size:12px;color:var(--gray-500);line-height:1.5}

.tl-empty{text-align:center;padding:60px 20px;color:var(--gray-400)}
.tl-empty-icon{font-size:40px;margin-bottom:12px}
.tl-empty-title{font-size:15px;font-weight:600;color:var(--gray-600);margin-bottom:6px}
.tl-empty-desc{font-size:13px}
</style>
