<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import { NButton, NSpin, NTag, NEmpty } from 'naive-ui'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, MarkLineComponent, VisualMapComponent, DataZoomComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, VisualMapComponent, DataZoomComponent, CanvasRenderer])

const props = defineProps<{ novelId: string }>()

interface TensionPoint {
  chapter: number; title: string; tension: number;
  words: number; level: string; summary: string;
  estimated?: boolean
}
interface ECGData {
  novel_title: string; chapter_count: number
  points: TensionPoint[]
  stats: { avg_tension: number; max_tension: number; min_tension: number; climax_ratio: number; pacing_grade: string }
  warnings: string[]; suggestions: string[]
}

const loading = ref(false)
const ecg = ref<ECGData | null>(null)
const error = ref('')
const chartRef = ref<HTMLDivElement | null>(null)
let chartInstance: echarts.ECharts | null = null

async function loadECG() {
  if (!props.novelId) return
  loading.value = true; error.value = ''
  try {
    const resp = await fetch(`/api/v1/audit/${props.novelId}/tension-ecg`)
    if (!resp.ok) throw new Error(await resp.text())
    ecg.value = await resp.json()
    await nextTick()
    renderChart()
  } catch (e: any) { error.value = e.message || '加载失败' }
  finally { loading.value = false }
}

function renderChart() {
  if (!ecg.value || !chartRef.value) return
  if (chartInstance) chartInstance.dispose()
  chartInstance = echarts.init(chartRef.value)

  const pts = ecg.value.points
  const xData = pts.map(p => `${p.chapter}`)
  const yData = pts.map(p => p.tension)

  chartInstance.setOption({
    tooltip: {
      trigger: 'axis',
      formatter(params: any) {
        const d = params[0]
        const p = pts[d.dataIndex]
        const estTag = p.estimated ? ' <span style="color:#f59e0b">[估]</span>' : ''
        return `<b>第${p.chapter}章</b> ${p.title}<br/>张力: <b>${p.tension}</b>${estTag} (${levelLabel[p.level] || p.level})<br/>字数: ${p.words.toLocaleString()}<br/>${p.summary}`
      }
    },
    grid: { left: 36, right: 16, top: 16, bottom: 60 },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 10, color: '#94a3b8' }, name: '章', nameGap: 4 },
    yAxis: { type: 'value', min: 0, max: 10, splitNumber: 5, axisLabel: { fontSize: 10, color: '#94a3b8' } },
    dataZoom: pts.length > 30 ? [{ type: 'slider', height: 20, bottom: 4 }] : [],
    visualMap: {
      show: false, min: 0, max: 10, dimension: 1,
      inRange: { color: ['#94a3b8', '#3b82f6', '#f59e0b', '#ef4444'] }
    },
    series: [{
      type: 'line', data: yData, smooth: 0.3, symbol: 'circle', symbolSize: 6,
      lineStyle: { width: 2 },
      areaStyle: { opacity: 0.08 },
      markLine: {
        silent: true, symbol: 'none',
        data: [
          { yAxis: 7, lineStyle: { color: '#ef444466', type: 'dashed' }, label: { formatter: '高潮线', fontSize: 9, color: '#ef4444' } },
          { yAxis: 5, lineStyle: { color: '#f59e0b66', type: 'dashed' }, label: { formatter: '紧张线', fontSize: 9, color: '#f59e0b' } },
          { yAxis: 3, lineStyle: { color: '#94a3b866', type: 'dashed' }, label: { formatter: '低潮线', fontSize: 9, color: '#94a3b8' } },
        ]
      }
    }]
  })
}

onMounted(loadECG)
watch(() => props.novelId, loadECG)

const gradeColor: Record<string, string> = {
  S: '#22c55e', A: '#6366f1', B: '#3b82f6', C: '#f59e0b', D: '#ef4444'
}
const levelColor: Record<string, string> = {
  climax: '#ef4444', high: '#f59e0b', normal: '#3b82f6', low: '#94a3b8'
}
const levelLabel: Record<string, string> = {
  climax: '高潮', high: '紧张', normal: '平稳', low: '低潮'
}
</script>

<template>
  <div class="audit-dash">
    <div v-if="loading" class="ad-loading"><n-spin size="large" /><span>加载审核数据…</span></div>
    <div v-else-if="error" class="ad-error">{{ error }}<n-button size="small" @click="loadECG">重试</n-button></div>
    <div v-else-if="!ecg || ecg.chapter_count === 0">
      <n-empty description="暂无章节数据，请先创作至少1章" />
    </div>
    <template v-else>
      <!-- Stats Row -->
      <div class="ad-stats">
        <div class="ad-stat">
          <div class="ads-label">节奏评级</div>
          <div class="ads-value ads-grade" :style="{ color: gradeColor[ecg.stats.pacing_grade] || '#64748b' }">
            {{ ecg.stats.pacing_grade }}
          </div>
        </div>
        <div class="ad-stat">
          <div class="ads-label">平均张力</div>
          <div class="ads-value">{{ ecg.stats.avg_tension }}</div>
        </div>
        <div class="ad-stat">
          <div class="ads-label">最高张力</div>
          <div class="ads-value" style="color:#ef4444">{{ ecg.stats.max_tension }}</div>
        </div>
        <div class="ad-stat">
          <div class="ads-label">高潮占比</div>
          <div class="ads-value">{{ (ecg.stats.climax_ratio * 100).toFixed(0) }}%</div>
        </div>
        <div class="ad-stat">
          <div class="ads-label">总章数</div>
          <div class="ads-value">{{ ecg.chapter_count }}</div>
        </div>
      </div>

      <!-- Tension ECG Chart (ECharts) -->
      <div class="ad-section">
        <h3 class="ad-sec-title">张力心电图</h3>
        <div ref="chartRef" class="ecg-echarts"></div>
        <div class="ecg-legend">
          <span v-for="(label, key) in levelLabel" :key="key" class="ecg-leg-item">
            <span class="ecg-leg-dot" :style="{ background: levelColor[key] }"></span>{{ label }}
          </span>
        </div>
      </div>

      <!-- Warnings -->
      <div v-if="ecg.warnings.length" class="ad-section">
        <h3 class="ad-sec-title">⚠️ 节奏预警</h3>
        <div class="ad-list warn">
          <div v-for="(w, i) in ecg.warnings" :key="i" class="ad-list-item">{{ w }}</div>
        </div>
      </div>

      <!-- Suggestions -->
      <div v-if="ecg.suggestions.length" class="ad-section">
        <h3 class="ad-sec-title">💡 优化建议</h3>
        <div class="ad-list suggest">
          <div v-for="(s, i) in ecg.suggestions" :key="i" class="ad-list-item">{{ s }}</div>
        </div>
      </div>

      <!-- Chapter Detail Table -->
      <div class="ad-section">
        <h3 class="ad-sec-title">章节详情</h3>
        <div class="ad-table-wrap">
          <table class="ad-table">
            <thead><tr><th>章</th><th>标题</th><th>张力</th><th>级别</th><th>字数</th><th>摘要</th></tr></thead>
            <tbody>
              <tr v-for="p in ecg.points" :key="p.chapter">
                <td class="at-ch">{{ p.chapter }}</td>
                <td class="at-title">{{ p.title }}</td>
                <td><span class="at-tension" :style="{ color: levelColor[p.level] }">{{ p.tension }}</span><span v-if="p.estimated" class="at-est-tag"> 估</span></td>
                <td><n-tag :bordered="false" size="small" :color="{ color: levelColor[p.level] + '22', textColor: levelColor[p.level] }">{{ levelLabel[p.level] || p.level }}</n-tag></td>
                <td class="at-words">{{ p.words.toLocaleString() }}</td>
                <td class="at-summary">{{ p.summary }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="ad-footer">
        <n-button @click="loadECG" size="small">🔄 刷新</n-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.audit-dash { padding: 4px; }
.ad-loading { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 60px 0; color: #64748b; }
.ad-error { text-align: center; padding: 40px; color: #ef4444; display: flex; flex-direction: column; align-items: center; gap: 12px; }

.ad-stats { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
.ad-stat { flex: 1; min-width: 100px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px; text-align: center; }
.ads-label { font-size: 11px; color: #94a3b8; margin-bottom: 4px; }
.ads-value { font-size: 22px; font-weight: 800; color: #1e293b; }
.ads-grade { font-size: 32px; }

.ad-section { margin-bottom: 20px; }
.ad-sec-title { font-size: 14px; font-weight: 600; color: #334155; margin-bottom: 10px; }

/* ECG Chart */
.ecg-echarts { width: 100%; height: 220px; background: #fafbfc; border: 1px solid #e2e8f0; border-radius: 10px; }

.ecg-legend { display: flex; gap: 14px; margin-top: 8px; justify-content: center; }
.ecg-leg-item { display: flex; align-items: center; gap: 4px; font-size: 11px; color: #64748b; }
.ecg-leg-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }

/* Warnings & Suggestions */
.ad-list { display: flex; flex-direction: column; gap: 6px; }
.ad-list-item { font-size: 12px; padding: 8px 12px; border-radius: 8px; line-height: 1.5; }
.ad-list.warn .ad-list-item { background: #fef3c7; color: #92400e; border-left: 3px solid #f59e0b; }
.ad-list.suggest .ad-list-item { background: #eef2ff; color: #3730a3; border-left: 3px solid #6366f1; }

/* Table */
.ad-table-wrap { overflow-x: auto; border: 1px solid #e2e8f0; border-radius: 10px; }
.ad-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.ad-table th { background: #f8fafc; color: #64748b; font-weight: 600; text-align: left; padding: 8px 10px; border-bottom: 1px solid #e2e8f0; white-space: nowrap; }
.ad-table td { padding: 7px 10px; border-bottom: 1px solid #f1f5f9; }
.at-ch { font-weight: 600; color: #6366f1; width: 40px; }
.at-title { font-weight: 500; color: #1e293b; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.at-tension { font-weight: 700; }
.at-est-tag { font-size: 10px; color: #f59e0b; font-weight: 500; }
.at-words { color: #64748b; }
.at-summary { color: #94a3b8; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.ad-footer { text-align: center; padding: 12px 0; }
</style>
