<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

export interface MapLocation {
  id: string
  name: string
  x: number           // 0-100 百分比坐标
  y: number
  type?: 'city' | 'village' | 'mountain' | 'river' | 'forest' | 'castle' | 'other'
  description?: string
  connections?: string[] // 连接到的其他地点 id
}

const props = withDefaults(defineProps<{
  locations: MapLocation[]
  title?: string
}>(), {
  locations: () => [],
  title: '世界地图',
})

const emit = defineEmits<{
  (e: 'locationClick', loc: MapLocation): void
  (e: 'addLocation', loc: { x: number; y: number }): void
}>()

const svgRef = ref<SVGSVGElement>()
const selectedLoc = ref<MapLocation | null>(null)
const isAdding = ref(false)
const hoveredId = ref<string>('')
const scale = ref(1)
const panX = ref(0)
const panY = ref(0)

const typeIcons: Record<string, string> = {
  city: '🏙️',
  village: '🏘️',
  mountain: '⛰️',
  river: '🌊',
  forest: '🌲',
  castle: '🏰',
  other: '📍',
}

const typeColors: Record<string, string> = {
  city: '#3b82f6',
  village: '#22c55e',
  mountain: '#78716c',
  river: '#06b6d4',
  forest: '#16a34a',
  castle: '#8b5cf6',
  other: '#6366f1',
}

function getColor(type?: string): string {
  return typeColors[type || 'other'] || typeColors.other
}

// Connections between locations
const connectionLines = computed(() => {
  const locMap = new Map(props.locations.map(l => [l.id, l]))
  const lines: Array<{ x1: number; y1: number; x2: number; y2: number; label?: string }> = []
  const lineSet = new Set<string>()
  for (const loc of props.locations) {
    if (loc.connections) {
      for (const targetId of loc.connections) {
        const target = locMap.get(targetId)
        if (target) {
          const key = [loc.id, targetId].sort().join('|')
          if (!lineSet.has(key)) {
            lineSet.add(key)
            lines.push({ x1: loc.x, y1: loc.y, x2: target.x, y2: target.y })
          }
        }
      }
    }
  }
  // Auto-connect nearby locations if no explicit connections exist
  if (lines.length === 0 && props.locations.length >= 2) {
    const locs = [...props.locations]
    for (let i = 0; i < locs.length; i++) {
      const nearest: { dist: number; idx: number }[] = []
      for (let j = 0; j < locs.length; j++) {
        if (i === j) continue
        const dx = locs[i].x - locs[j].x
        const dy = locs[i].y - locs[j].y
        nearest.push({ dist: Math.sqrt(dx * dx + dy * dy), idx: j })
      }
      nearest.sort((a, b) => a.dist - b.dist)
      const connectCount = Math.min(2, nearest.length)
      for (let k = 0; k < connectCount; k++) {
        if (nearest[k].dist > 40) continue
        const key = [locs[i].id, locs[nearest[k].idx].id].sort().join('|')
        if (!lineSet.has(key)) {
          lineSet.add(key)
          lines.push({
            x1: locs[i].x, y1: locs[i].y,
            x2: locs[nearest[k].idx].x, y2: locs[nearest[k].idx].y,
          })
        }
      }
    }
  }
  return lines
})

// Region color areas based on types
const regionAreas = computed(() => {
  return props.locations.filter(l => l.type === 'forest' || l.type === 'river' || l.type === 'mountain').map(loc => ({
    cx: loc.x, cy: loc.y,
    r: loc.type === 'river' ? 6 : loc.type === 'forest' ? 8 : 10,
    color: getColor(loc.type),
    type: loc.type,
  }))
})

function handleSvgClick(event: MouseEvent) {
  if (!isAdding.value || !svgRef.value) return
  const rect = svgRef.value.getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width) * 100
  const y = ((event.clientY - rect.top) / rect.height) * 100
  emit('addLocation', { x, y })
  isAdding.value = false
}

function selectLocation(loc: MapLocation) {
  selectedLoc.value = loc
  emit('locationClick', loc)
}

function zoomIn() { scale.value = Math.min(3, scale.value + 0.3) }
function zoomOut() { scale.value = Math.max(0.5, scale.value - 0.3) }
function resetView() { scale.value = 1; panX.value = 0; panY.value = 0 }

// Drag pan
let isDragging = false
let startX = 0, startY = 0
function startPan(e: MouseEvent) {
  if (isAdding.value) return
  isDragging = true
  startX = e.clientX - panX.value
  startY = e.clientY - panY.value
}
function doPan(e: MouseEvent) {
  if (!isDragging) return
  panX.value = e.clientX - startX
  panY.value = e.clientY - startY
}
function endPan() { isDragging = false }
function handleWheel(e: WheelEvent) {
  e.preventDefault()
  if (e.deltaY < 0) zoomIn()
  else zoomOut()
}
</script>

<template>
  <div class="wm-wrap">
    <!-- Toolbar -->
    <div class="wm-toolbar">
      <span class="wm-title">🗺️ {{ title }}</span>
      <div class="wm-toolbar-right">
        <div class="wm-zoom-group">
          <button class="wm-zoom-btn" @click="zoomOut" title="缩小">−</button>
          <span class="wm-zoom-val">{{ (scale * 100).toFixed(0) }}%</span>
          <button class="wm-zoom-btn" @click="zoomIn" title="放大">+</button>
          <button class="wm-zoom-btn" @click="resetView" title="重置">⟲</button>
        </div>
        <button
          :class="['btn-add', { active: isAdding }]"
          @click="isAdding = !isAdding"
        >
          {{ isAdding ? '✕ 取消' : '+ 添加地点' }}
        </button>
      </div>
    </div>
    <span v-if="isAdding" class="wm-hint">点击地图上任意位置添加标注</span>

    <!-- SVG Map Canvas -->
    <div
      class="wm-canvas"
      @mousedown="startPan"
      @mousemove="doPan"
      @mouseup="endPan"
      @mouseleave="endPan"
      @wheel.prevent="handleWheel"
    >
      <svg
        ref="svgRef"
        viewBox="0 0 100 100"
        preserveAspectRatio="xMidYMid meet"
        class="wm-svg"
        :class="{ adding: isAdding }"
        :style="{ transform: `scale(${scale}) translate(${panX / scale}px, ${panY / scale}px)` }"
        @click="handleSvgClick"
      >
        <!-- Gradient & filter defs -->
        <defs>
          <pattern id="wm-grid" width="10" height="10" patternUnits="userSpaceOnUse">
            <path d="M 10 0 L 0 0 0 10" fill="none" stroke="#e2e8f0" stroke-width="0.15"/>
          </pattern>
          <radialGradient id="wm-terrain-green" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#bbf7d0" stop-opacity="0.5"/>
            <stop offset="100%" stop-color="#bbf7d0" stop-opacity="0"/>
          </radialGradient>
          <radialGradient id="wm-terrain-blue" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#bae6fd" stop-opacity="0.4"/>
            <stop offset="100%" stop-color="#bae6fd" stop-opacity="0"/>
          </radialGradient>
          <radialGradient id="wm-terrain-brown" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#e7e5e4" stop-opacity="0.4"/>
            <stop offset="100%" stop-color="#e7e5e4" stop-opacity="0"/>
          </radialGradient>
          <filter id="wm-glow">
            <feGaussianBlur in="SourceGraphic" stdDeviation="0.8" result="blur"/>
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
        </defs>

        <!-- Map background -->
        <rect width="100" height="100" fill="#f8fafc" rx="1"/>
        <rect width="100" height="100" fill="url(#wm-grid)" rx="1"/>

        <!-- Terrain regions -->
        <circle
          v-for="(area, i) in regionAreas" :key="'region-'+i"
          :cx="area.cx" :cy="area.cy" :r="area.r"
          :fill="area.type === 'forest' ? 'url(#wm-terrain-green)' : area.type === 'river' ? 'url(#wm-terrain-blue)' : 'url(#wm-terrain-brown)'"
        />

        <!-- Road connections -->
        <g class="wm-roads">
          <line
            v-for="(line, i) in connectionLines"
            :key="'road-'+i"
            :x1="line.x1" :y1="line.y1"
            :x2="line.x2" :y2="line.y2"
            stroke="#94a3b8"
            stroke-width="0.25"
            stroke-dasharray="1.2,0.6"
            stroke-linecap="round"
            opacity="0.6"
          />
        </g>

        <!-- Location markers -->
        <g
          v-for="loc in locations"
          :key="loc.id"
          :transform="`translate(${loc.x}, ${loc.y})`"
          class="wm-marker"
          @click.stop="selectLocation(loc)"
          @mouseenter="hoveredId = loc.id"
          @mouseleave="hoveredId = ''"
        >
          <!-- Hover glow ring -->
          <circle
            class="marker-glow"
            :r="hoveredId === loc.id ? 5 : 0"
            :fill="getColor(loc.type)"
            :opacity="hoveredId === loc.id ? 0.2 : 0"
          />
          <!-- Shadow -->
          <circle
            :r="loc.type === 'city' || loc.type === 'castle' ? 2.8 : 2"
            fill="rgba(0,0,0,.12)"
            :cy="0.4"
          />
          <!-- Main marker -->
          <circle
            class="marker-dot"
            :r="loc.type === 'city' || loc.type === 'castle' ? 2.8 : 2"
            :fill="getColor(loc.type)"
            :stroke="selectedLoc?.id === loc.id ? '#fff' : 'rgba(255,255,255,.6)'"
            :stroke-width="selectedLoc?.id === loc.id ? 0.6 : 0.3"
            :filter="hoveredId === loc.id || selectedLoc?.id === loc.id ? 'url(#wm-glow)' : ''"
          />
          <!-- Selected pulse ring -->
          <circle
            v-if="selectedLoc?.id === loc.id"
            class="marker-pulse"
            :r="4"
            fill="none"
            :stroke="getColor(loc.type)"
            stroke-width="0.3"
          />
          <!-- Type icon -->
          <text
            y="-3.8"
            text-anchor="middle"
            :font-size="loc.type === 'city' || loc.type === 'castle' ? '3.5' : '2.8'"
            class="marker-icon"
          >{{ typeIcons[loc.type || 'other'] }}</text>
          <!-- Name label -->
          <text
            :y="loc.type === 'city' || loc.type === 'castle' ? 5.5 : 4.8"
            text-anchor="middle"
            :font-size="loc.type === 'city' || loc.type === 'castle' ? '2.6' : '2.2'"
            font-weight="600"
            :fill="getColor(loc.type)"
            class="marker-label"
          >{{ loc.name }}</text>
        </g>
      </svg>
    </div>

    <!-- Detail panel -->
    <Transition name="slide">
      <div v-if="selectedLoc" class="wm-detail">
        <div class="wm-detail-head">
          <span class="wm-detail-icon">{{ typeIcons[selectedLoc.type || 'other'] }}</span>
          <div>
            <div class="wm-detail-name">{{ selectedLoc.name }}</div>
            <div class="wm-detail-type">{{ selectedLoc.type || '地点' }}</div>
          </div>
          <button class="wm-detail-close" @click="selectedLoc = null">✕</button>
        </div>
        <p class="wm-detail-desc" v-if="selectedLoc.description">{{ selectedLoc.description }}</p>
        <p class="wm-detail-desc" v-else style="color:var(--gray-400)">暂无描述</p>
        <div class="wm-detail-coord">
          坐标: ({{ selectedLoc.x.toFixed(1) }}, {{ selectedLoc.y.toFixed(1) }})
        </div>
      </div>
    </Transition>

    <!-- Empty state -->
    <div v-if="locations.length === 0 && !isAdding" class="wm-empty">
      <div class="wm-empty-icon">🗺️</div>
      <div class="wm-empty-title">地图上暂无标注</div>
      <div class="wm-empty-desc">点击"添加地点"开始构建你的世界</div>
    </div>

    <!-- Legend -->
    <div v-if="locations.length > 0" class="wm-legend">
      <span v-for="(icon, type) in typeIcons" :key="type" class="wm-legend-item">
        <i class="wm-legend-dot" :style="{ background: typeColors[type] }"></i>
        <span class="wm-legend-icon">{{ icon }}</span>
        {{ type === 'city' ? '城市' : type === 'village' ? '村庄' : type === 'mountain' ? '山脉' : type === 'river' ? '水域' : type === 'forest' ? '森林' : type === 'castle' ? '城堡' : '地点' }}
      </span>
    </div>

    <!-- Stats -->
    <div v-if="locations.length > 0" class="wm-stats">
      {{ locations.length }} 个地点 · {{ connectionLines.length }} 条路径
    </div>
  </div>
</template>

<style scoped>
.wm-wrap{position:relative;display:flex;flex-direction:column;height:100%;min-height:450px}

.wm-toolbar{display:flex;align-items:center;gap:12px;padding:10px 16px;flex-shrink:0}
.wm-toolbar-right{display:flex;align-items:center;gap:10px}
.wm-title{font-size:15px;font-weight:700;color:var(--gray-800);margin-right:auto}
.btn-add{padding:6px 16px;border:1.5px solid var(--gray-200);border-radius:8px;
  font-size:12px;cursor:pointer;background:#fff;color:var(--gray-600);transition:all .15s;font-weight:500}
.btn-add.active{background:var(--danger);color:#fff;border-color:var(--danger)}
.btn-add:hover:not(.active){background:var(--gray-50);border-color:var(--gray-300)}
.wm-hint{font-size:11px;color:var(--warning);animation:pulse 1.5s infinite;padding:0 16px}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}

.wm-zoom-group{display:flex;align-items:center;gap:2px;background:var(--gray-100);border-radius:8px;padding:2px}
.wm-zoom-btn{width:28px;height:28px;display:flex;align-items:center;justify-content:center;
  border:none;background:transparent;cursor:pointer;font-size:14px;color:var(--gray-600);
  border-radius:6px;transition:all .12s}
.wm-zoom-btn:hover{background:#fff;color:var(--gray-900);box-shadow:0 1px 3px rgba(0,0,0,.08)}
.wm-zoom-val{font-size:11px;color:var(--gray-500);min-width:36px;text-align:center;font-weight:500}

.wm-canvas{flex:1;border:1px solid var(--gray-200);border-radius:12px;overflow:hidden;
  background:linear-gradient(135deg,#f0f9ff,#f8fafc,#f0fdf4);cursor:grab;position:relative}
.wm-canvas:active{cursor:grabbing}
.wm-svg{width:100%;height:100%;display:block;transition:transform .1s ease-out;transform-origin:center center}
.wm-svg.adding{cursor:crosshair}
.wm-marker{cursor:pointer}
.marker-dot{transition:all .15s ease}
.marker-glow{transition:r .2s ease, opacity .2s ease;pointer-events:none}
.marker-icon{pointer-events:none}
.marker-label{pointer-events:none;text-shadow:0 0 3px rgba(255,255,255,.9)}
.marker-pulse{animation:markerPulse 2s infinite ease-out}
@keyframes markerPulse{0%{r:3.5;opacity:.8}100%{r:6;opacity:0}}

.wm-detail{position:absolute;top:60px;right:12px;width:240px;background:#fff;
  border:1px solid var(--gray-200);border-radius:12px;padding:16px;
  box-shadow:0 8px 30px rgba(0,0,0,.1);z-index:5}
.wm-detail-head{display:flex;align-items:center;gap:10px;margin-bottom:12px;position:relative}
.wm-detail-icon{font-size:26px}
.wm-detail-name{font-size:15px;font-weight:700;color:var(--gray-800)}
.wm-detail-type{font-size:11px;color:var(--gray-400);text-transform:capitalize;margin-top:1px}
.wm-detail-close{position:absolute;top:0;right:0;background:none;border:none;cursor:pointer;
  color:var(--gray-400);font-size:14px;width:24px;height:24px;border-radius:6px;
  display:flex;align-items:center;justify-content:center}
.wm-detail-close:hover{background:var(--gray-100);color:var(--gray-700)}
.wm-detail-desc{font-size:12px;color:var(--gray-600);line-height:1.6;margin-bottom:10px}
.wm-detail-coord{font-size:11px;color:var(--gray-400);font-family:monospace;
  background:var(--gray-50);padding:4px 8px;border-radius:6px;display:inline-block}

.wm-empty{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;pointer-events:none}
.wm-empty-icon{font-size:48px;margin-bottom:12px}
.wm-empty-title{font-size:16px;font-weight:600;color:var(--gray-600);margin-bottom:4px}
.wm-empty-desc{font-size:13px;color:var(--gray-400)}

.wm-legend{position:absolute;bottom:12px;left:12px;display:flex;gap:12px;flex-wrap:wrap;
  background:rgba(255,255,255,.95);padding:8px 14px;border-radius:10px;
  border:1px solid var(--gray-200);font-size:11px;color:var(--gray-600);
  backdrop-filter:blur(4px);box-shadow:0 2px 8px rgba(0,0,0,.04)}
.wm-legend-item{display:flex;align-items:center;gap:4px;font-weight:500}
.wm-legend-dot{width:8px;height:8px;border-radius:50%;display:inline-block;flex-shrink:0}
.wm-legend-icon{font-size:12px}

.wm-stats{position:absolute;bottom:12px;right:12px;font-size:11px;color:var(--gray-400);
  background:rgba(255,255,255,.9);padding:4px 10px;border-radius:6px;border:1px solid var(--gray-200)}

.slide-enter-active,.slide-leave-active{transition:all .2s}
.slide-enter-from,.slide-leave-to{opacity:0;transform:translateX(10px)}
</style>
