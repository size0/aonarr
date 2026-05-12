<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as d3 from 'd3'

export interface CharacterNode {
  id: string
  name: string
  role?: string          // 主角 / 配角 / 反派
  appearances?: number   // 出场次数 → 决定节点大小
  color?: string
}

export interface CharacterRelation {
  source: string
  target: string
  label?: string         // 关系类型: 师徒/恋人/敌对 等
  strength?: number      // 0-1 关系强度
}

const props = withDefaults(defineProps<{
  characters: CharacterNode[]
  relations: CharacterRelation[]
}>(), {
  characters: () => [],
  relations: () => [],
})

const emit = defineEmits<{
  (e: 'nodeClick', node: CharacterNode): void
}>()

const container = ref<HTMLDivElement>()
let simulation: d3.Simulation<any, any> | null = null
let resizeObserver: ResizeObserver | null = null

const selectedNode = ref<CharacterNode | null>(null)

// 角色颜色
const roleColors: Record<string, string> = {
  '主角': '#3b82f6',
  '配角': '#22c55e',
  '反派': '#ef4444',
  '路人': '#9ca3af',
}

function getColor(node: CharacterNode): string {
  if (node.color) return node.color
  return roleColors[node.role || '路人'] || '#6366f1'
}

function getRadius(node: CharacterNode): number {
  const base = 20
  const extra = Math.min((node.appearances || 1) / 5, 15)
  return base + extra
}

function render() {
  if (!container.value) return
  const el = container.value
  el.innerHTML = ''

  const width = el.clientWidth || 600
  const height = el.clientHeight || 450

  const svg = d3.select(el)
    .append('svg')
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', `0 0 ${width} ${height}`)

  // Defs for arrow marker
  svg.append('defs').append('marker')
    .attr('id', 'arrowhead')
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 28)
    .attr('refY', 0)
    .attr('markerWidth', 6)
    .attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-5L10,0L0,5')
    .attr('fill', '#9ca3af')

  // Prepare data
  const nodes = props.characters.map(c => ({ ...c }))
  const nodeMap = new Map(nodes.map(n => [n.id, n]))
  const links = props.relations
    .filter(r => nodeMap.has(r.source) && nodeMap.has(r.target))
    .map(r => ({ ...r, source: r.source, target: r.target }))

  // Force simulation
  simulation = d3.forceSimulation(nodes as any)
    .force('link', d3.forceLink(links as any).id((d: any) => d.id).distance(120))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius((d: any) => getRadius(d) + 5))

  // Link lines
  const link = svg.append('g')
    .selectAll('line')
    .data(links)
    .enter().append('line')
    .attr('stroke', '#d1d5db')
    .attr('stroke-width', (d: any) => Math.max(1, (d.strength || 0.5) * 3))
    .attr('marker-end', 'url(#arrowhead)')

  // Link labels
  const linkLabel = svg.append('g')
    .selectAll('text')
    .data(links)
    .enter().append('text')
    .attr('font-size', '11px')
    .attr('fill', '#6b7280')
    .attr('text-anchor', 'middle')
    .text((d: any) => d.label || '')

  // Node groups
  const node = svg.append('g')
    .selectAll('g')
    .data(nodes)
    .enter().append('g')
    .attr('cursor', 'pointer')
    .call(d3.drag<any, any>()
      .on('start', dragStarted)
      .on('drag', dragged)
      .on('end', dragEnded)
    )
    .on('click', (_event: any, d: any) => {
      selectedNode.value = d
      emit('nodeClick', d)
    })

  // Node circles
  node.append('circle')
    .attr('r', (d: any) => getRadius(d))
    .attr('fill', (d: any) => getColor(d))
    .attr('stroke', '#fff')
    .attr('stroke-width', 2.5)
    .attr('opacity', 0.9)

  // Node labels
  node.append('text')
    .attr('text-anchor', 'middle')
    .attr('dy', (d: any) => getRadius(d) + 16)
    .attr('font-size', '12px')
    .attr('font-weight', '500')
    .attr('fill', '#374151')
    .text((d: any) => d.name)

  // Appearance count inside circle
  node.append('text')
    .attr('text-anchor', 'middle')
    .attr('dy', '4px')
    .attr('font-size', '11px')
    .attr('font-weight', '600')
    .attr('fill', '#fff')
    .text((d: any) => d.appearances ? `${d.appearances}` : '')

  // Tick
  simulation.on('tick', () => {
    link
      .attr('x1', (d: any) => d.source.x)
      .attr('y1', (d: any) => d.source.y)
      .attr('x2', (d: any) => d.target.x)
      .attr('y2', (d: any) => d.target.y)

    linkLabel
      .attr('x', (d: any) => (d.source.x + d.target.x) / 2)
      .attr('y', (d: any) => (d.source.y + d.target.y) / 2 - 6)

    node.attr('transform', (d: any) => `translate(${d.x},${d.y})`)
  })

  function dragStarted(event: any, d: any) {
    if (!event.active) simulation!.alphaTarget(0.3).restart()
    d.fx = d.x
    d.fy = d.y
  }
  function dragged(event: any, d: any) {
    d.fx = event.x
    d.fy = event.y
  }
  function dragEnded(event: any, d: any) {
    if (!event.active) simulation!.alphaTarget(0)
    d.fx = null
    d.fy = null
  }
}

onMounted(() => {
  nextTick(render)
  resizeObserver = new ResizeObserver(() => render())
  if (container.value) resizeObserver.observe(container.value)
})

onUnmounted(() => {
  if (simulation) simulation.stop()
  if (resizeObserver) resizeObserver.disconnect()
})

watch(() => [props.characters, props.relations], () => nextTick(render), { deep: true })
</script>

<template>
  <div class="cg-wrap">
    <div ref="container" class="cg-canvas"></div>
    <!-- Detail Panel -->
    <Transition name="fade">
      <div v-if="selectedNode" class="cg-detail">
        <div class="cg-detail-head">
          <div class="cg-avatar" :style="{ background: getColor(selectedNode) }">
            {{ selectedNode.name[0] }}
          </div>
          <div>
            <div class="cg-name">{{ selectedNode.name }}</div>
            <div class="cg-role">{{ selectedNode.role || '未分类' }}</div>
          </div>
          <button class="cg-close" @click="selectedNode = null">✕</button>
        </div>
        <div class="cg-stat">
          <span>出场次数</span>
          <strong>{{ selectedNode.appearances || 0 }}</strong>
        </div>
        <div class="cg-stat">
          <span>相关关系</span>
          <strong>{{ relations.filter(r => r.source === selectedNode!.id || r.target === selectedNode!.id).length }}</strong>
        </div>
      </div>
    </Transition>
    <!-- Legend -->
    <div class="cg-legend">
      <span v-for="(color, role) in roleColors" :key="role" class="legend-item">
        <i :style="{ background: color }"></i>{{ role }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.cg-wrap{position:relative;width:100%;height:100%;min-height:450px}
.cg-canvas{width:100%;height:100%;min-height:450px}
.cg-legend{position:absolute;bottom:12px;left:12px;display:flex;gap:12px;
  background:rgba(255,255,255,.9);padding:6px 12px;border-radius:var(--radius-sm);
  border:1px solid var(--gray-200);font-size:12px;color:var(--gray-600)}
.legend-item{display:flex;align-items:center;gap:4px}
.legend-item i{width:10px;height:10px;border-radius:50%;display:inline-block}

.cg-detail{position:absolute;top:12px;right:12px;width:220px;background:#fff;
  border:1px solid var(--gray-200);border-radius:var(--radius);padding:16px;
  box-shadow:var(--shadow-md)}
.cg-detail-head{display:flex;align-items:center;gap:10px;margin-bottom:12px;position:relative}
.cg-avatar{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;color:#fff;font-weight:600;font-size:14px}
.cg-name{font-size:14px;font-weight:600;color:var(--gray-800)}
.cg-role{font-size:12px;color:var(--gray-400)}
.cg-close{position:absolute;top:0;right:0;background:none;border:none;cursor:pointer;
  font-size:14px;color:var(--gray-400)}
.cg-stat{display:flex;justify-content:space-between;padding:8px 0;
  border-top:1px solid var(--gray-100);font-size:13px;color:var(--gray-600)}
.cg-stat strong{color:var(--gray-800)}

.fade-enter-active,.fade-leave-active{transition:opacity .2s}
.fade-enter-from,.fade-leave-to{opacity:0}
</style>
