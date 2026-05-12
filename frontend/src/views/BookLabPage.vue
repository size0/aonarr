<script setup lang="ts">
import {
  NCard, NButton, NTabs, NTabPane, NProgress, NTag, NSpace,
  NEmpty, NSpin, NDataTable, NUploadDragger, NUpload, NIcon,
  NPopconfirm, useMessage,
} from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { analysisApi, type AnalysisJob } from '@/api/analysis'
import * as echarts from 'echarts'

const message = useMessage()
const jobs = ref<AnalysisJob[]>([])
const loading = ref(false)
const selectedJob = ref<AnalysisJob | null>(null)
const chapterResults = ref<any[]>([])
const uploading = ref(false)

// ── Upload ────────────────────────────────────────────────────
async function handleUpload({ file }: { file: UploadFileInfo }) {
  if (!file.file) return
  uploading.value = true
  try {
    const job = await analysisApi.upload(file.file)
    jobs.value.unshift(job)
    message.success(`任务已创建: ${job.novel_title}`)
    startPolling()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

// ── Job list ──────────────────────────────────────────────────
async function loadJobs() {
  loading.value = true
  try {
    jobs.value = await analysisApi.listJobs()
  } finally {
    loading.value = false
  }
}

async function deleteJob(id: string) {
  await analysisApi.deleteJob(id)
  jobs.value = jobs.value.filter(j => j.id !== id)
  if (selectedJob.value?.id === id) {
    selectedJob.value = null
    chapterResults.value = []
  }
  message.success('已删除')
}

async function selectJob(job: AnalysisJob) {
  selectedJob.value = job
  if (job.status === 'done') {
    chapterResults.value = await analysisApi.getJobChapters(job.id)
  }
}

// ── Polling for in-progress jobs ──────────────────────────────
let pollTimer: number | null = null

function startPolling() {
  if (pollTimer) return
  pollTimer = window.setInterval(async () => {
    const active = jobs.value.filter(j => !['done', 'failed'].includes(j.status))
    if (active.length === 0) { stopPolling(); return }
    for (const j of active) {
      try {
        const updated = await analysisApi.getJob(j.id)
        const idx = jobs.value.findIndex(x => x.id === j.id)
        if (idx >= 0) jobs.value[idx] = updated
        if (selectedJob.value?.id === j.id) {
          selectedJob.value = updated
          if (updated.status === 'done') {
            chapterResults.value = await analysisApi.getJobChapters(j.id)
          }
        }
      } catch {}
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

const statusMap: Record<string, { type: 'default' | 'info' | 'warning' | 'success' | 'error'; label: string }> = {
  pending: { type: 'default', label: '等待中' },
  scanning: { type: 'info', label: '扫描中' },
  extracting: { type: 'warning', label: '提取中' },
  aggregating: { type: 'warning', label: '聚合中' },
  done: { type: 'success', label: '已完成' },
  failed: { type: 'error', label: '失败' },
}

// ── Result rendering ──────────────────────────────────────────
const resultSummary = computed(() => selectedJob.value?.result_summary || {})
const aggregation = computed(() => resultSummary.value?.aggregation || {})
const styleFingerprint = computed(() => resultSummary.value?.style_fingerprint || {})

// ── Character graph (ECharts) ─────────────────────────────────
const graphRef = ref<HTMLDivElement>()
function initGraph() {
  if (!graphRef.value || chapterResults.value.length === 0) return
  const chart = echarts.init(graphRef.value)
  const charMap = new Map<string, { count: number }>()
  const links: { source: string; target: string }[] = []

  for (const ch of chapterResults.value) {
    for (const c of (ch.characters || [])) {
      const name = c.name || c
      charMap.set(name, { count: (charMap.get(name)?.count || 0) + 1 })
    }
    for (const r of (ch.relationships || [])) {
      if (r.from && r.to) links.push({ source: r.from, target: r.to })
    }
  }

  const nodes = Array.from(charMap.entries()).map(([name, d]) => ({
    name, symbolSize: Math.min(50, 15 + d.count * 3),
    label: { show: true, fontSize: 11 },
  }))

  chart.setOption({
    tooltip: {},
    series: [{
      type: 'graph', layout: 'force', roam: true,
      data: nodes, links,
      force: { repulsion: 200, edgeLength: 100 },
      lineStyle: { color: '#ddd', width: 1 },
      emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
    }],
  })
}

onMounted(async () => {
  await loadJobs()
  const hasActive = jobs.value.some(j => !['done', 'failed'].includes(j.status))
  if (hasActive) startPolling()
})

onBeforeUnmount(() => stopPolling())
</script>

<template>
  <div class="page-booklab">
    <div class="page-head-row">
      <div>
        <h1 class="page-title">📖 拆书实验室</h1>
        <p class="page-desc">上传小说文件，AI 自动提取大纲、人物、时间线和文风指纹</p>
      </div>
    </div>

    <!-- Upload -->
    <div class="upload-zone" @click="($refs.uploadInput as HTMLInputElement)?.click()">
      <n-upload
        :custom-request="({ file }) => handleUpload({ file })"
        accept=".txt,.epub,.docx"
        :show-file-list="false"
        :max="1"
      >
        <n-upload-dragger style="border:none;background:none">
          <div class="upload-inner">
            <div class="upload-icon">📁</div>
            <div class="upload-text">拖拽文件到此处，或<span class="upload-link">点击上传</span></div>
            <div class="upload-hint">支持 .txt / .epub / .docx 格式</div>
          </div>
        </n-upload-dragger>
      </n-upload>
    </div>

    <!-- Job list -->
    <div class="section-head"><h2>分析任务</h2></div>
    <n-spin :show="loading">
      <div v-if="jobs.length === 0 && !loading" class="empty-block">
        <div class="empty-icon">📂</div>
        <div>暂无分析任务，上传文件开始拆书</div>
      </div>
      <div v-else class="job-list">
        <div
          v-for="job in jobs" :key="job.id"
          class="job-card" :class="{ selected: selectedJob?.id === job.id }"
          @click="selectJob(job)"
        >
          <div class="job-row">
            <span class="job-title">{{ job.novel_title }}</span>
            <n-tag size="small" :type="(statusMap[job.status] || statusMap.pending).type">
              {{ (statusMap[job.status] || statusMap.pending).label }}
            </n-tag>
            <span class="job-meta">{{ job.chapter_count || 0 }} 章</span>
            <n-popconfirm @positive-click="deleteJob(job.id)">
              <template #trigger>
                <button class="btn-tiny-del" @click.stop>删除</button>
              </template>
              确认删除此任务？
            </n-popconfirm>
          </div>
          <n-progress
            v-if="job.status !== 'done' && job.status !== 'failed'"
            type="line" :percentage="Math.round((job.progress || 0) * 100)"
            :show-indicator="false" style="margin-top:8px"
          />
          <div v-if="job.error_message" class="job-error">{{ job.error_message }}</div>
        </div>
      </div>
    </n-spin>

    <!-- Results -->
    <div v-if="selectedJob?.status === 'done'" class="results-section">
      <div class="section-head"><h2>分析结果 — {{ selectedJob.novel_title }}</h2></div>
      <n-tabs type="line" animated>
        <n-tab-pane name="outline" tab="逆向大纲">
          <div v-if="chapterResults.length === 0" class="empty-block">无数据</div>
          <div v-else class="result-list">
            <div v-for="ch in chapterResults" :key="ch.id" class="result-card">
              <div class="result-head">
                <span>第{{ ch.chapter_number }}章 {{ ch.chapter_title }}</span>
                <n-tag size="tiny">{{ ch.word_count }} 字</n-tag>
              </div>
              <div class="result-body">{{ ch.summary || '暂无摘要' }}</div>
              <div v-if="ch.events?.length" class="result-tags">
                <n-tag v-for="(ev, i) in ch.events.slice(0, 5)" :key="i" size="tiny" type="info" style="margin:2px">
                  {{ typeof ev === 'string' ? ev : ev.description || ev.event || JSON.stringify(ev) }}
                </n-tag>
              </div>
            </div>
          </div>
        </n-tab-pane>

        <n-tab-pane name="graph" tab="人物图谱">
          <button class="btn btn-ghost" style="margin-bottom:12px" @click="initGraph">刷新图谱</button>
          <div ref="graphRef" class="graph-box"></div>
        </n-tab-pane>

        <n-tab-pane name="timeline" tab="时间线">
          <div class="timeline-wrap">
            <div v-for="ch in chapterResults" :key="ch.id" class="tl-item">
              <div class="tl-dot-col"><div class="tl-dot"></div><div class="tl-line"></div></div>
              <div class="tl-content">
                <div class="tl-title">第{{ ch.chapter_number }}章 {{ ch.chapter_title }}</div>
                <div class="tl-desc">{{ ch.summary || '' }}</div>
              </div>
            </div>
          </div>
        </n-tab-pane>

        <n-tab-pane name="style" tab="文风指纹">
          <div v-if="Object.keys(styleFingerprint).length > 0" class="fp-grid">
            <div v-for="(val, key) in styleFingerprint" :key="key" class="fp-item">
              <div class="fp-label">{{ key }}</div>
              <div class="fp-value">{{ typeof val === 'object' ? JSON.stringify(val) : val }}</div>
            </div>
          </div>
          <div v-else class="empty-block">暂无文风数据</div>
        </n-tab-pane>

        <n-tab-pane name="wiki" tab="百科">
          <div v-if="aggregation.characters?.length" class="wiki-grid">
            <div v-for="c in aggregation.characters" :key="c.name || c" class="wiki-card">
              <div class="wiki-name">{{ c.name || c }}</div>
              <div class="wiki-desc">{{ c.description || c.role || '暂无描述' }}</div>
            </div>
          </div>
          <div v-else class="empty-block">暂无百科数据</div>
        </n-tab-pane>
      </n-tabs>
    </div>
  </div>
</template>

<style scoped>
.page-booklab{max-width:1000px}
.page-head-row{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:22px}
.page-title{font-size:22px;font-weight:800;color:var(--gray-900);letter-spacing:-.3px}
.page-desc{font-size:13px;color:var(--gray-400);margin-top:6px}

.upload-zone{background:linear-gradient(135deg,#fafafe,#f5f3ff);border:2px dashed var(--gray-200);border-radius:16px;
  margin-bottom:24px;transition:all .2s;cursor:pointer}
.upload-zone:hover{border-color:var(--primary);background:var(--primary-light);box-shadow:0 4px 20px rgba(99,102,241,.1)}
.upload-inner{text-align:center;padding:36px}
.upload-icon{font-size:42px;margin-bottom:10px}
.upload-text{font-size:14px;color:var(--gray-600);font-weight:500}
.upload-link{color:var(--primary);font-weight:600}
.upload-hint{font-size:12px;color:var(--gray-400);margin-top:6px}

.section-head{margin-bottom:14px}
.section-head h2{font-size:15px;font-weight:600;color:var(--gray-700)}

.empty-block{text-align:center;padding:40px;color:var(--gray-400);font-size:13px;
  background:#fff;border:1px solid var(--gray-200);border-radius:14px}
.empty-icon{font-size:28px;margin-bottom:8px}

.job-list{display:flex;flex-direction:column;gap:10px;margin-bottom:24px}
.job-card{padding:16px 18px;background:#fff;border:1px solid var(--gray-200);border-radius:14px;
  cursor:pointer;transition:all .18s}
.job-card:hover{box-shadow:0 4px 16px rgba(0,0,0,.06);transform:translateY(-1px)}
.job-card.selected{border-color:var(--primary);box-shadow:0 0 0 3px rgba(99,102,241,.12)}
.job-row{display:flex;align-items:center;gap:12px}
.job-title{font-weight:600;flex:1;font-size:14px;color:var(--gray-800)}
.job-meta{font-size:12px;color:var(--gray-400)}
.job-error{font-size:12px;color:var(--danger);margin-top:4px}
.btn-tiny-del{border:none;background:none;color:var(--danger);font-size:12px;cursor:pointer;padding:2px 6px;border-radius:4px}
.btn-tiny-del:hover{background:#fef2f2}

.results-section{margin-top:8px}
.result-list{display:flex;flex-direction:column;gap:12px;padding:12px 0}
.result-card{padding:16px 18px;background:#fff;border:1px solid var(--gray-200);border-radius:12px;transition:all .15s}
.result-card:hover{border-color:var(--gray-300);box-shadow:0 2px 10px rgba(0,0,0,.04)}
.result-head{font-size:13px;font-weight:600;color:var(--gray-700);display:flex;align-items:center;gap:8px;margin-bottom:8px}
.result-body{font-size:13px;color:var(--gray-500);line-height:1.7}
.result-tags{margin-top:8px}

.graph-box{height:450px;border:1px solid var(--gray-200);border-radius:14px;background:#fff}

.timeline-wrap{padding:16px 0}
.tl-item{display:flex;gap:16px;margin-bottom:16px}
.tl-dot-col{width:20px;flex-shrink:0;display:flex;flex-direction:column;align-items:center}
.tl-dot{width:10px;height:10px;border-radius:50%;background:var(--primary);margin-top:4px}
.tl-line{width:2px;flex:1;background:var(--gray-200);margin-top:4px}
.tl-content{flex:1;padding-bottom:4px}
.tl-title{font-size:13px;font-weight:600;color:var(--gray-700)}
.tl-desc{font-size:12px;color:var(--gray-500);margin-top:4px;line-height:1.6}

.fp-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:16px;background:#fff;border:1px solid var(--gray-200);border-radius:14px}
.fp-item{padding:8px}
.fp-label{font-size:12px;color:var(--gray-400);margin-bottom:4px}
.fp-value{font-size:14px;font-weight:500;color:var(--gray-700)}

.wiki-grid{display:flex;flex-wrap:wrap;gap:12px;padding:12px 0}
.wiki-card{width:200px;padding:16px;background:#fff;border:1px solid var(--gray-200);border-radius:12px;transition:all .15s}
.wiki-card:hover{border-color:var(--gray-300);box-shadow:0 2px 10px rgba(0,0,0,.04)}
.wiki-name{font-size:14px;font-weight:600;color:var(--gray-800);margin-bottom:6px}
.wiki-desc{font-size:12px;color:var(--gray-500);line-height:1.5}
</style>
