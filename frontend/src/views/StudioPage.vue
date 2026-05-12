<script setup lang="ts">
import {
  NButton, NSpace, NSelect, NModal, NForm, NFormItem,
  NInput, NInputNumber, useMessage,
} from 'naive-ui'
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useCreationStore } from '@/stores/creation'
import { useNovelsStore } from '@/stores/novels'
import { creationApi } from '@/api/creation'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { novelApi, type ChapterDTO, type CharacterDTO } from '@/api/novels'
import * as echarts from 'echarts'

const route = useRoute()
const message = useMessage()
const store = useCreationStore()
const novelsStore = useNovelsStore()

// ── Novel selector ────────────────────────────────────────────
const novelOptions = computed(() =>
  novelsStore.novels.map(n => ({ label: n.title, value: n.id }))
)
const selectedNovelId = ref<string | null>(null)

// 大纲节点（当没有章节时作为目录展示）
const outlineNodes = ref<any[]>([])

watch(selectedNovelId, async (id) => {
  if (id) {
    await store.selectNovel(id)
    await loadOutlineForSidebar(id)
    loadCreativeData(id)
    // 自动检查是否有运行中的托管任务
    try {
      const status = await creationApi.autopilotStatus(id)
      autopilotStatus.value = status
      if (status.state === 'running' || status.state === 'paused') {
        // 同步已完成章节数，避免首次轮询重复刷新
        _lastKnownChaptersDone = status.chapters_completed || 0
        startAutopilotPolling()
        // 连接 SSE 流式输出
        if (status.state === 'running') connectAutopilotSSE()
        // 自动选中最新章节
        if (store.sortedChapters.length > 0 && !store.currentChapter) {
          store.selectChapter(store.sortedChapters[store.sortedChapters.length - 1])
        }
      }
    } catch { /* ignore */ }
  }
})

async function loadOutlineForSidebar(novelId: string) {
  try {
    const resp = await fetch(`/api/v1/novels/${novelId}/outline`)
    if (resp.ok) outlineNodes.value = await resp.json()
    else outlineNodes.value = []
  } catch { outlineNodes.value = [] }
}

/** 纯文本 → Tiptap HTML：\n\n 分段，单 \n 换行 */
function textToHtml(text: string): string {
  if (!text) return ''
  if (text.startsWith('<p>') || text.startsWith('<h')) return text
  return text
    .split(/\n{2,}/)
    .map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`)
    .join('')
}

// ── Tiptap Editor ─────────────────────────────────────────────
const editor = useEditor({
  extensions: [StarterKit],
  content: '<p>选择章节开始创作...</p>',
  editorProps: {
    attributes: {
      style: 'min-height: 500px; outline: none; padding: 16px; font-size: 15px; line-height: 1.8; font-family: "PingFang SC", "Noto Sans SC", sans-serif;',
    },
  },
})

watch(() => store.currentChapter, (ch) => {
  if (ch && editor.value) {
    editor.value.commands.setContent(textToHtml(ch.content) || '<p></p>')
  }
})

// ── Chapter actions ───────────────────────────────────────────
function selectChapter(ch: ChapterDTO) {
  store.selectChapter(ch)
}

function chapterDisplayTitle(ch: ChapterDTO): string {
  if (!ch.title) return '未命名'
  // 如果标题就是 "第N章" 格式，显示为空（避免重复）
  if (/^第\d+章$/.test(ch.title)) return ''
  return ch.title
}

// ── Characters & creative panel data ──────────────────────────
const characters = ref<CharacterDTO[]>([])
const activeForeshadows = ref<any[]>([])
const collapsedVols = ref<Set<string>>(new Set())

function toggleVol(volId: string) {
  if (collapsedVols.value.has(volId)) collapsedVols.value.delete(volId)
  else collapsedVols.value.add(volId)
}

// 按卷分组章节（如果有大纲卷节点就用卷，否则单组）
const volumeGroupedChapters = computed(() => {
  const chapters = store.sortedChapters
  if (!chapters.length) return []
  if (outlineNodes.value.length > 0) {
    return outlineNodes.value.map((vol: any, vi: number) => {
      const childCount = vol.children?.length || 10
      const startNum = vi === 0 ? 1 : outlineNodes.value.slice(0, vi).reduce((s: number, v: any) => s + (v.children?.length || 10), 0) + 1
      const endNum = startNum + childCount - 1
      return {
        id: vol.id || `vol-${vi}`,
        title: vol.title || `第${vi + 1}卷`,
        chapters: chapters.filter(c => c.number >= startNum && c.number <= endNum),
        outlineChildren: vol.children || [],
      }
    })
  }
  // 无大纲：单卷
  return [{ id: 'default', title: '全部章节', chapters, outlineChildren: [] }]
})

// 写作统计
const writingStats = computed(() => {
  const chs = store.sortedChapters
  const totalWords = chs.reduce((s, c) => s + (c.word_count || 0), 0)
  const totalChs = chs.length
  const targetChs = store.currentNovel?.target_chapter_count || 100
  const pct = targetChs > 0 ? Math.min(100, Math.round(totalChs / targetChs * 100)) : 0
  const currentCh = store.currentChapter
  return {
    totalWords,
    totalChapters: totalChs,
    targetChapters: targetChs,
    completionPct: pct,
    currentChapterWords: currentCh?.word_count || 0,
  }
})

// 加载角色和伏笔
async function loadCreativeData(novelId: string) {
  try {
    characters.value = await novelApi.listCharacters(novelId)
  } catch { characters.value = [] }
  try {
    const resp = await fetch(`/api/v1/audit/${novelId}/foreshadows`)
    if (resp.ok) {
      const data = await resp.json()
      activeForeshadows.value = data.active || []
    } else activeForeshadows.value = []
  } catch { activeForeshadows.value = [] }
}

// AI 快速指令输入
const aiQuickInput = ref('')

const showNewChapter = ref(false)
const newChapterForm = ref({ number: 1, title: '' })

async function createChapter() {
  if (!newChapterForm.value.title.trim()) { message.warning('请输入章节标题'); return }
  try {
    await store.addChapter({
      number: newChapterForm.value.number,
      title: newChapterForm.value.title,
      content: '',
    })
    showNewChapter.value = false
    newChapterForm.value = { number: (store.sortedChapters.length || 0) + 2, title: '' }
    message.success('章节创建成功')
  } catch (e: any) {
    message.error(e.message || '创建失败')
  }
}

// ── SSE streaming ─────────────────────────────────────────────
let eventSource: EventSource | null = null
const streaming = ref(false)
const sseBeatTotal = ref(0)
const sseBeatCurrent = ref(0)
const sseBeatSummary = ref('')
const sseStatus = ref('')  // 'chapter_start' | 'beat_start' | 'beat_done' | 'chapter_saved'
const streamingContent = ref('')  // PlotPilot 风格：纯文本累积
const streamingChapterNum = ref(0)
const streamingContentEl = ref<HTMLElement | null>(null)

// 流式内容自动滚动到底部
watch(streamingContent, () => {
  nextTick(() => {
    if (streamingContentEl.value) {
      streamingContentEl.value.scrollTop = streamingContentEl.value.scrollHeight
    }
  })
})

function resetSSEState() {
  sseBeatTotal.value = 0
  sseBeatCurrent.value = 0
  sseBeatSummary.value = ''
  sseStatus.value = ''
  streamingContent.value = ''
  streamingChapterNum.value = 0
}

function startSSE() {
  if (!store.currentNovel || !store.currentChapter) {
    message.warning('请先选择作品和章节')
    return
  }
  if (streaming.value) return

  resetSSEState()
  const url = creationApi.getStreamUrl(store.currentNovel.id, store.currentChapter.number)
  eventSource = new EventSource(url)
  streaming.value = true
  store.sseStreaming = true

  eventSource.onmessage = (event) => {
    if (!editor.value) return
    const raw = event.data
    if (raw === '{"type":"done"}') {
      stopSSE()
      message.success('AI 续写完成')
      return
    }
    try {
      const parsed = JSON.parse(raw)
      switch (parsed.type) {
        case 'chapter_start':
          sseBeatTotal.value = parsed.beat_total || 0
          sseBeatCurrent.value = 0
          sseStatus.value = 'chapter_start'
          editor.value.commands.clearContent()
          break
        case 'beat_start':
          sseBeatCurrent.value = parsed.beat_index || 0
          sseBeatSummary.value = parsed.beat_summary || ''
          sseStatus.value = 'beat_start'
          break
        case 'chapter_chunk': {
          const t = parsed.text || ''
          if (t.includes('\n')) {
            editor.value.commands.insertContent(textToHtml(t), { parseOptions: { preserveWhitespace: false } })
          } else {
            editor.value.commands.insertContent(t)
          }
          break
        }
        case 'beat_done':
          sseStatus.value = 'beat_done'
          break
        case 'chapter_saved':
          sseStatus.value = 'chapter_saved'
          stopSSE()
          message.success(`章节已保存，共 ${(parsed.total_words || 0).toLocaleString()} 字`)
          store.refreshChapters()
          break
        case 'error':
          message.error(parsed.message || '生成出错')
          stopSSE()
          break
        default:
          if (parsed.text || parsed.content) {
            const t = parsed.text || parsed.content
            editor.value.commands.insertContent(t.includes('\n') ? textToHtml(t) : t)
          }
      }
    } catch {
      editor.value.commands.insertContent(raw.includes('\n') ? textToHtml(raw) : raw)
    }
  }

  eventSource.onerror = () => {
    stopSSE()
    message.error('SSE 连接中断')
  }
}

function stopSSE() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  streaming.value = false
  store.sseStreaming = false
}

// ── Autopilot ────────────────────────────────────────────────
const showAutopilot = ref(false)
const autopilotForm = ref({ start_chapter: 1, end_chapter: 10, auto_beats: true })
const autopilotStatus = ref<import('@/api/creation').AutopilotStatus | null>(null)
const autopilotPolling = ref<ReturnType<typeof setInterval> | null>(null)

async function startAutopilot() {
  if (!store.currentNovel) { message.warning('请先选择作品'); return }
  try {
    const status = await creationApi.autopilotStart(store.currentNovel.id, autopilotForm.value)
    autopilotStatus.value = status
    showAutopilot.value = false
    message.success('全托管写作已启动')
    startAutopilotPolling()
    connectAutopilotSSE()
  } catch (e: any) {
    message.error(e.response?.data?.detail || e.message || '启动失败')
  }
}

// ── Autopilot SSE 流式 ───────────────────────────────────────
let autopilotES: EventSource | null = null
const autopilotStreaming = ref(false)

function connectAutopilotSSE() {
  if (!store.currentNovel || autopilotES) return
  const url = creationApi.getAutopilotStreamUrl(store.currentNovel.id)
  autopilotES = new EventSource(url)
  autopilotStreaming.value = true
  streaming.value = true
  store.sseStreaming = true

  autopilotES.onmessage = (event) => {
    try {
      const parsed = JSON.parse(event.data)
      switch (parsed.type) {
        case 'chapter_start':
          sseBeatTotal.value = parsed.beat_total || 0
          sseBeatCurrent.value = 0
          sseStatus.value = 'chapter_start'
          streamingContent.value = ''
          streamingChapterNum.value = parsed.chapter_number || 0
          break
        case 'beat_start':
          sseBeatCurrent.value = parsed.beat_index || 0
          sseBeatSummary.value = parsed.beat_summary || ''
          sseStatus.value = 'beat_start'
          break
        case 'chapter_chunk': {
          // PlotPilot 风格：逐字累积，不依赖 TipTap
          const t = parsed.text || ''
          streamingContent.value += t
          break
        }
        case 'beat_done':
          sseStatus.value = 'beat_done'
          break
        case 'chapter_saved':
          sseStatus.value = 'chapter_saved'
          message.success(`第${parsed.chapter_number || '?'}章已保存 (${(parsed.total_words || 0).toLocaleString()}字)`)
          store.refreshChapters()
          // 短暂保留内容后清空准备下一章
          setTimeout(() => {
            streamingContent.value = ''
            streamingChapterNum.value = 0
          }, 800)
          break
        case 'autopilot_done':
          disconnectAutopilotSSE()
          message.success(`全托管完成！共${parsed.chapters_completed}章`)
          store.refreshChapters()
          break
        case 'heartbeat':
          break
        default:
          if (parsed.text) {
            streamingContent.value += parsed.text
          }
      }
    } catch {
      // 纯文本 fallback
    }
  }

  autopilotES.onerror = () => {
    // 不立刻断开，EventSource 会自动重连
    console.warn('Autopilot SSE error, will auto-reconnect')
  }
}

function disconnectAutopilotSSE() {
  if (autopilotES) {
    autopilotES.close()
    autopilotES = null
  }
  autopilotStreaming.value = false
  streaming.value = false
  store.sseStreaming = false
  resetSSEState()
}

async function controlAutopilot(action: 'stop' | 'pause' | 'resume') {
  if (!store.currentNovel) return
  try {
    const fn = action === 'stop' ? creationApi.autopilotStop
      : action === 'pause' ? creationApi.autopilotPause
      : creationApi.autopilotResume
    const status = await fn(store.currentNovel.id)
    autopilotStatus.value = status
    if (action === 'stop') {
      stopAutopilotPolling()
      disconnectAutopilotSSE()
    }
  } catch (e: any) {
    message.error(e.response?.data?.detail || '操作失败')
  }
}

let _lastKnownChaptersDone = 0

function startAutopilotPolling() {
  stopAutopilotPolling()
  _lastKnownChaptersDone = 0
  autopilotPolling.value = setInterval(async () => {
    if (!store.currentNovel) return
    try {
      const status = await creationApi.autopilotStatus(store.currentNovel.id)
      autopilotStatus.value = status

      // 检测是否有新章节完成 → 刷新列表 + 自动选中
      const done = status.chapters_completed || 0
      if (done > _lastKnownChaptersDone) {
        _lastKnownChaptersDone = done
        await store.refreshChapters()
        // 自动选中最新章节
        const latest = store.sortedChapters[store.sortedChapters.length - 1]
        if (latest) store.selectChapter(latest)
      }

      if (status.state === 'completed' || status.state === 'idle' || status.state === 'failed') {
        stopAutopilotPolling()
        await store.refreshChapters()
        if (status.state === 'completed') message.success('全托管写作已完成！')
      }
    } catch { /* ignore */ }
  }, 3000)
}

function stopAutopilotPolling() {
  if (autopilotPolling.value) {
    clearInterval(autopilotPolling.value)
    autopilotPolling.value = null
  }
}

// ── Chapter Intent / Plan ────────────────────────────────────
const showIntentPanel = ref(false)
const intentForm = ref({ author_intent: '', current_focus: '' })
const chapterPlan = ref<any>(null)
const planning = ref(false)

const focusOptions = [
  { label: '主线推进', value: '主线推进' },
  { label: '支线展开', value: '支线展开' },
  { label: '情感深化', value: '情感深化' },
  { label: '世界扩展', value: '世界扩展' },
  { label: '战斗/高潮', value: '战斗/高潮' },
  { label: '过渡/铺垫', value: '过渡/铺垫' },
]

async function generatePlan() {
  if (!store.currentNovel || !store.currentChapter) {
    message.warning('请先选择作品和章节'); return
  }
  planning.value = true
  try {
    const resp = await fetch(`/api/v1/creation/${store.currentNovel.id}/chapter/${store.currentChapter.number}/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(intentForm.value),
    })
    if (!resp.ok) throw new Error(await resp.text())
    const data = await resp.json()
    chapterPlan.value = data.plan
    message.success('写作计划已生成')
  } catch (e: any) {
    message.error('计划生成失败: ' + (e.message || ''))
  } finally {
    planning.value = false
  }
}

function startSSEv2() {
  if (!store.currentNovel || !store.currentChapter) {
    message.warning('请先选择作品和章节'); return
  }
  if (streaming.value) return

  resetSSEState()
  const params = new URLSearchParams({
    author_intent: intentForm.value.author_intent,
    current_focus: intentForm.value.current_focus,
  })
  // Use v2 generate endpoint via POST fetch + SSE reading
  const novelId = store.currentNovel.id
  const chNum = store.currentChapter.number

  streaming.value = true
  store.sseStreaming = true

  fetch(`/api/v1/creation/${novelId}/chapter/${chNum}/generate-v2`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      author_intent: intentForm.value.author_intent,
      current_focus: intentForm.value.current_focus,
      mode: 'creative',
      enable_settlement: true,
      use_planner: true,
    }),
  }).then(async (resp) => {
    if (!resp.ok || !resp.body) {
      stopSSE(); message.error('SSE v2 连接失败'); return
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (!raw) continue
        processSSEEvent(raw)
      }
    }
    stopSSE()
    message.success('AI 续写完成')
  }).catch(() => {
    stopSSE(); message.error('SSE v2 连接中断')
  })
}

function processSSEEvent(raw: string) {
  if (!editor.value) return
  if (raw === '{"type":"done"}') return
  try {
    const parsed = JSON.parse(raw)
    switch (parsed.type) {
      case 'plan_start':
        sseStatus.value = 'planning'
        break
      case 'plan_done':
        sseStatus.value = 'plan_done'
        break
      case 'settlement_start':
        sseStatus.value = 'settlement'
        break
      case 'settlement_done':
        sseStatus.value = 'settlement_done'
        break
      case 'chapter_start':
        sseBeatTotal.value = parsed.beat_total || 0
        sseBeatCurrent.value = 0
        sseStatus.value = 'chapter_start'
        editor.value.commands.clearContent()
        break
      case 'beat_start':
        sseBeatCurrent.value = parsed.beat_index || 0
        sseBeatSummary.value = parsed.beat_summary || ''
        sseStatus.value = 'beat_start'
        break
      case 'chapter_chunk': {
        const t = parsed.text || ''
        if (t.includes('\n')) {
          editor.value.commands.insertContent(textToHtml(t), { parseOptions: { preserveWhitespace: false } })
        } else {
          editor.value.commands.insertContent(t)
        }
        break
      }
      case 'beat_done':
        sseStatus.value = 'beat_done'
        break
      case 'chapter_saved':
        sseStatus.value = 'chapter_saved'
        message.success(`章节已保存，共 ${(parsed.total_words || 0).toLocaleString()} 字`)
        store.refreshChapters()
        break
      case 'error':
        message.error(parsed.message || '生成出错')
        break
    }
  } catch {
    if (editor.value) {
      editor.value.commands.insertContent(raw.includes('\n') ? textToHtml(raw) : raw)
    }
  }
}

// ── Post-pipeline trigger ────────────────────────────────────
const runningPipeline = ref(false)
async function triggerPostPipeline() {
  if (!store.currentNovel || !store.currentChapter) return
  runningPipeline.value = true
  try {
    await creationApi.runPostPipeline(store.currentNovel.id, store.currentChapter.number)
    message.success('章后管线已完成')
    store.refreshChapters()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '管线执行失败')
  } finally {
    runningPipeline.value = false
  }
}

// ── Save ──────────────────────────────────────────────────────
const saving = ref(false)
async function saveContent() {
  if (!store.currentNovel || !store.currentChapter || !editor.value) return
  saving.value = true
  try {
    const text = editor.value.getText({ blockSeparator: '\n\n' })
    await creationApi.saveChapter(store.currentNovel.id, store.currentChapter.id, { content: text })
    message.success('已保存')
  } catch (e: any) {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

// ── Audit panel (quality radar + issues + actions) ──────────────
const radarRef = ref<HTMLDivElement>()
let radarChart: ReturnType<typeof echarts.init> | null = null

interface AuditScores {
  naturalness: number; reading_power: number; pacing: number; dialogue: number
  foreshadowing: number; continuity: number; ai_detect: number; vocab_diversity: number
  emotion_arc: number; sentence_variety: number; overall: number; passed: boolean
  issues: Array<{ dimension: string; severity: string; message: string }>
}
const auditScores = ref<AuditScores | null>(null)
const auditing = ref(false)
const antiDetecting = ref(false)
const revisionLooping = ref(false)
const revisionResult = ref<any>(null)

function updateRadar(scores: AuditScores) {
  if (!radarRef.value) return
  if (!radarChart) radarChart = echarts.init(radarRef.value)
  radarChart.setOption({
    radar: {
      indicator: [
        { name: '自然度', max: 100 }, { name: '吸引力', max: 100 },
        { name: '节奏', max: 100 }, { name: '对话', max: 100 },
        { name: '伏笔', max: 100 }, { name: '连贯', max: 100 },
        { name: '反AI', max: 100 }, { name: '词汇', max: 100 },
        { name: '情感', max: 100 }, { name: '句式', max: 100 },
      ],
      radius: 65,
      axisName: { color: '#6b7280', fontSize: 10 },
    },
    series: [{
      type: 'radar',
      data: [{
        value: [
          scores.naturalness, scores.reading_power, scores.pacing,
          scores.dialogue, scores.foreshadowing, scores.continuity,
          scores.ai_detect, scores.vocab_diversity, scores.emotion_arc,
          scores.sentence_variety,
        ],
        name: '质量评分',
      }],
      areaStyle: { color: scores.passed ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)' },
      lineStyle: { color: scores.passed ? '#22c55e' : '#ef4444' },
      itemStyle: { color: scores.passed ? '#22c55e' : '#ef4444' },
    }],
  })
}

async function runFullAudit() {
  if (!store.currentNovel || !store.currentChapter) return
  auditing.value = true
  try {
    const resp = await fetch(`/api/v1/audit/${store.currentNovel.id}/chapters/${store.currentChapter.number}/full-audit`, { method: 'POST' })
    if (!resp.ok) { message.error('审计失败'); return }
    const data = await resp.json()
    auditScores.value = data.scores as AuditScores
    await nextTick()
    updateRadar(auditScores.value)
    message.success(`审计完成: ${data.scores.overall.toFixed(1)}分 ${data.scores.passed ? '✅ 通过' : '❌ 未通过'}`)
  } catch (e: any) {
    message.error('审计请求失败')
  } finally {
    auditing.value = false
  }
}

async function runAntiDetect() {
  if (!store.currentNovel || !store.currentChapter) return
  antiDetecting.value = true
  try {
    const resp = await fetch(`/api/v1/audit/${store.currentNovel.id}/chapters/${store.currentChapter.number}/anti-detect`, { method: 'POST' })
    if (!resp.ok) { message.error('去AI味失败'); return }
    const data = await resp.json()
    message.success(data.message || '去AI味完成')
    store.refreshChapters()
    // 重新审计
    await runFullAudit()
  } catch {
    message.error('去AI味请求失败')
  } finally {
    antiDetecting.value = false
  }
}

async function runRevisionLoop() {
  if (!store.currentNovel || !store.currentChapter) return
  revisionLooping.value = true
  revisionResult.value = null
  try {
    const resp = await fetch(`/api/v1/audit/${store.currentNovel.id}/chapters/${store.currentChapter.number}/revision-loop`, { method: 'POST' })
    if (!resp.ok) { message.error('修订循环失败'); return }
    const data = await resp.json()
    revisionResult.value = data
    message.success(`修订完成: ${data.initial_score} → ${data.final_score} (${data.rounds}轮)`)
    store.refreshChapters()
    await runFullAudit()
  } catch {
    message.error('修订循环请求失败')
  } finally {
    revisionLooping.value = false
  }
}

function severityColor(sev: string) {
  return sev === 'critical' ? '#ef4444' : sev === 'warning' ? '#f59e0b' : '#6b7280'
}

const wordCount = computed(() => {
  if (!editor.value) return 0
  return editor.value.storage?.characterCount?.characters?.() || editor.value.getText().length
})

onMounted(async () => {
  await novelsStore.loadNovels()
  const qid = route.query.novelId as string
  if (qid) {
    selectedNovelId.value = qid
  }
  newChapterForm.value.number = (store.sortedChapters.length || 0) + 1
})

onBeforeUnmount(() => {
  stopSSE()
  stopAutopilotPolling()
  disconnectAutopilotSSE()
})
</script>

<template>
  <div class="studio-wrap">
    <!-- Top bar: novel + breadcrumb + actions -->
    <div class="studio-header">
      <n-select v-model:value="selectedNovelId" :options="novelOptions" placeholder="选择作品" style="width:220px" filterable size="small" />
      <!-- Breadcrumb -->
      <div v-if="store.currentChapter" class="header-breadcrumb">
        <span class="bc-sep">&rarr;</span>
        <span class="bc-item active">第{{ store.currentChapter.number }}章：{{ store.currentChapter.title || '未命名' }}</span>
      </div>
      <div class="header-actions">
        <button class="btn btn-ghost" :disabled="!store.currentChapter || saving" @click="saveContent">💾 保存</button>
        <button class="btn btn-ghost" :disabled="!store.currentChapter || runningPipeline" @click="triggerPostPipeline">🔍 章后管线</button>
        <button class="btn btn-ghost" :disabled="!store.currentChapter" @click="showIntentPanel = !showIntentPanel">🎯 意图</button>
        <button class="btn" :class="streaming ? 'btn-danger' : 'btn-primary'" :disabled="!store.currentChapter" @click="streaming ? stopSSE() : startSSE()">
          {{ streaming ? '⏹ 停止' : '✨ AI续写' }}
        </button>
        <button class="btn btn-accent-alt" :disabled="!store.currentChapter || streaming" @click="startSSEv2()">🧠 智能续写</button>
        <button class="btn btn-accent" :disabled="!store.currentNovel" @click="showAutopilot = true">🚀 全托管</button>
      </div>
    </div>

    <!-- Autopilot status bar -->
    <div v-if="autopilotStatus && (autopilotStatus.state === 'running' || autopilotStatus.state === 'paused')" class="autopilot-bar">
      <span class="ap-indicator" :class="autopilotStatus.state"></span>
      <span class="ap-label">{{ autopilotStatus.state === 'running' ? '🚀 全托管写作中' : '⏸️ 已暂停' }}</span>
      <span class="ap-detail">
        第{{ autopilotStatus.current_chapter || '?' }}章
        <template v-if="autopilotStatus.target_end_chapter"> / {{ autopilotStatus.target_end_chapter }}章</template>
        · {{ autopilotStatus.total_words_written.toLocaleString() }}字
      </span>
      <div class="ap-actions">
        <button v-if="autopilotStatus.state === 'running'" class="btn-sm btn-warn" @click="controlAutopilot('pause')">⏸ 暂停</button>
        <button v-if="autopilotStatus.state === 'paused'" class="btn-sm btn-primary-sm" @click="controlAutopilot('resume')">▶ 继续</button>
        <button class="btn-sm btn-danger-sm" @click="controlAutopilot('stop')">⏹ 停止</button>
      </div>
    </div>

    <div class="studio-body">
      <!-- ═══ Left: Chapter sidebar ═══ -->
      <div class="chapter-sidebar">
        <div class="sidebar-head">
          <span class="sidebar-title">📚 章节目录</span>
          <button class="add-ch-btn" @click="showNewChapter = true" :disabled="!store.currentNovel">+ 新章节</button>
        </div>
        <div class="chapter-list">
          <div v-if="!store.currentNovel" class="empty-hint">请先选择作品</div>
          <div v-else-if="store.sortedChapters.length === 0 && outlineNodes.length === 0" class="empty-hint">
            暂无章节<br><span class="hint-link" @click="showNewChapter = true">+ 创建第一章</span>
          </div>

          <!-- 卷/章分组 -->
          <template v-for="vol in volumeGroupedChapters" :key="vol.id">
            <div class="vol-header" @click="toggleVol(vol.id)">
              <span class="vol-arrow" :class="{ collapsed: collapsedVols.has(vol.id) }">▾</span>
              <span class="vol-title">{{ vol.title }}</span>
              <span class="vol-count">{{ vol.chapters.length }}章</span>
            </div>
            <template v-if="!collapsedVols.has(vol.id)">
              <div v-for="ch in vol.chapters" :key="ch.id"
                class="chapter-item" :class="{ active: store.currentChapter?.id === ch.id }"
                @click="selectChapter(ch)">
                <div class="ch-dot" :class="{ written: ch.status === 'reviewed', current: store.currentChapter?.id === ch.id }"></div>
                <div class="ch-info">
                  <div class="ch-number">第{{ ch.number }}章<template v-if="chapterDisplayTitle(ch)">：{{ chapterDisplayTitle(ch) }}</template></div>
                  <div class="ch-meta">{{ ch.word_count || 0 }}字</div>
                </div>
              </div>
              <!-- 大纲中还没写的章节 -->
              <div v-for="oc in vol.outlineChildren.filter((_: any, i: number) => !vol.chapters.some((c: any) => c.number === i + 1))" :key="oc.id" class="chapter-item outline-pending">
                <div class="ch-dot outline"></div>
                <div class="ch-info">
                  <div class="ch-number">{{ oc.title || '待写' }}</div>
                  <div class="ch-meta">未开始</div>
                </div>
              </div>
            </template>
          </template>

          <!-- 无卷时：纯大纲目录 -->
          <template v-if="store.sortedChapters.length === 0 && outlineNodes.length > 0">
            <div class="outline-sidebar-hint">📐 大纲目录（尚未开始写作）</div>
            <template v-for="vol in outlineNodes" :key="vol.id">
              <div class="vol-header">
                <span class="vol-title">{{ vol.title || '未命名卷' }}</span>
              </div>
              <div v-for="(ch, idx) in (vol.children || [])" :key="ch.id" class="chapter-item outline-pending">
                <div class="ch-dot outline"></div>
                <div class="ch-info">
                  <div class="ch-number">{{ ch.title || `第${idx + 1}章` }}</div>
                  <div class="ch-meta">{{ ch.summary?.slice(0, 30) || '' }}</div>
                </div>
              </div>
            </template>
          </template>
        </div>

        <!-- 底部：作品信息 -->
        <div v-if="store.currentNovel" class="sidebar-footer">
          <div class="novel-info-card">
            <div class="novel-info-title">{{ store.currentNovel.title }}</div>
            <div class="novel-info-meta">状态：{{ store.currentNovel.status }}</div>
          </div>
          <div class="sidebar-total-words">
            <span class="total-label">全书字数 / 编辑</span>
            <span class="total-num">{{ writingStats.totalWords.toLocaleString() }}</span>
            <span class="total-unit">字</span>
          </div>
        </div>
      </div>

      <!-- ═══ Center: Editor ═══ -->
      <div class="editor-area">
        <div v-if="!store.currentChapter" class="editor-empty">
          <div class="editor-empty-icon">✍️</div>
          <div class="editor-empty-title">选择章节开始创作</div>
          <div class="editor-empty-sub">从左侧选择一个章节，或创建新章节</div>
        </div>
        <template v-else>
          <!-- Editor header with chapter info -->
          <div class="editor-header">
            <span class="editor-ch-title">第{{ store.currentChapter.number }}章：{{ store.currentChapter.title || '未命名' }}</span>
            <div class="editor-header-meta">
              <span class="editor-meta-item">字数 <b>{{ wordCount.toLocaleString() }}</b></span>
              <span class="editor-meta-item" v-if="store.currentChapter.tension_score">张力 <b>{{ store.currentChapter.tension_score.toFixed(1) }}</b></span>
              <span class="editor-status" :class="{ streaming: streaming || autopilotStreaming }">
                {{ streaming || autopilotStreaming ? '✨ AI写作中...' : '编辑中' }}
              </span>
              <span v-if="store.currentChapter.model_used" class="editor-model">{{ store.currentChapter.model_used }}</span>
            </div>
          </div>
          <!-- Beat progress bar -->
          <div v-if="(streaming || autopilotStreaming) && sseBeatTotal > 0" class="beat-progress">
            <div class="beat-bar">
              <div class="beat-fill" :style="{ width: `${(sseBeatCurrent / sseBeatTotal) * 100}%` }"></div>
            </div>
            <span class="beat-info">节拍 {{ sseBeatCurrent }}/{{ sseBeatTotal }}{{ sseBeatSummary ? ` — ${sseBeatSummary}` : '' }}</span>
          </div>
          <!-- Intent Panel -->
          <div v-if="showIntentPanel" class="intent-panel">
            <div class="intent-head">
              <span class="intent-icon">🎯</span>
              <span class="intent-title">本章意图</span>
              <button class="intent-close" @click="showIntentPanel = false">&times;</button>
            </div>
            <div class="intent-body">
              <div class="intent-row">
                <label class="intent-label">写作焦点</label>
                <n-select v-model:value="intentForm.current_focus" :options="focusOptions" placeholder="选择焦点" size="small" style="flex:1" />
              </div>
              <div class="intent-row">
                <label class="intent-label">作者意图</label>
                <n-input v-model:value="intentForm.author_intent" type="textarea" placeholder="描述本章要实现的目标..." :rows="2" size="small" style="flex:1" />
              </div>
              <div class="intent-actions">
                <button class="btn btn-ghost btn-xs" :disabled="planning" @click="generatePlan">
                  {{ planning ? '规划中...' : '📋 生成计划' }}
                </button>
              </div>
              <div v-if="chapterPlan" class="intent-plan">
                <div class="plan-intent">{{ chapterPlan.chapter_intent }}</div>
                <div class="plan-meta">
                  <span v-if="chapterPlan.pov">👤 {{ chapterPlan.pov }}</span>
                  <span v-if="chapterPlan.location">📍 {{ chapterPlan.location }}</span>
                  <span v-if="chapterPlan.tone">🎭 {{ chapterPlan.tone }}</span>
                </div>
                <div v-if="chapterPlan.beats_suggestion?.length" class="plan-beats">
                  <div v-for="(b, i) in chapterPlan.beats_suggestion" :key="i" class="plan-beat">
                    <span class="beat-type">{{ b.type }}</span>
                    <span class="beat-sum">{{ b.summary }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <!-- Editor body: autopilot streaming or normal editor -->
          <div v-if="autopilotStreaming && streamingContent" class="editor-body streaming-body">
            <div class="streaming-header">
              <span class="streaming-ch">✍️ 正在写作：第{{ streamingChapterNum }}章</span>
              <span class="streaming-wc">{{ streamingContent.length.toLocaleString() }}字</span>
            </div>
            <div class="streaming-content" ref="streamingContentEl">{{ streamingContent }}</div>
          </div>
          <div v-else class="editor-body">
            <editor-content :editor="editor" />
          </div>
          <!-- Bottom: AI input bar -->
          <div class="ai-input-bar">
            <div class="ai-bar-inner">
              <input v-model="aiQuickInput" class="ai-input" placeholder="输入人类指令，如：描写主角的内心独白，或推进剧情发展..." @keydown.enter="startSSEv2" />
              <div class="ai-bar-controls">
                <span class="ai-bar-label">模型：创作模式</span>
                <span class="ai-bar-counter">{{ aiQuickInput.length }}/1000</span>
                <button class="btn btn-primary btn-bar" :disabled="streaming || !store.currentChapter" @click="startSSEv2">▶ 开始续写</button>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- ═══ Right: Creative panel ═══ -->
      <div class="creative-panel">
        <div class="cp-head">
          <span class="cp-head-title">章情画板</span>
          <div class="cp-tabs">
            <button class="cp-tab active">一键展开</button>
            <button class="cp-tab">全收起</button>
          </div>
        </div>
        <div class="cp-content">
          <!-- 章情重点 -->
          <div v-if="store.currentChapter?.summary" class="cp-section">
            <div class="cp-label">📋 章情重点</div>
            <div class="cp-card">{{ store.currentChapter.summary }}</div>
          </div>

          <!-- 角色列表 -->
          <div class="cp-section">
            <div class="cp-label">👥 角色列表</div>
            <div v-if="characters.length === 0" class="cp-empty">暂无角色信息</div>
            <div v-for="char in characters.slice(0, 6)" :key="char.id" class="char-card">
              <div class="char-avatar">{{ char.name[0] }}</div>
              <div class="char-info">
                <div class="char-name">{{ char.name }}</div>
                <div class="char-role">{{ char.role === 'protagonist' ? '主角' : char.role === 'antagonist' ? '反派' : '配角' }}</div>
                <div class="char-desc">{{ char.description?.slice(0, 40) || '' }}</div>
              </div>
            </div>
          </div>

          <!-- 情节建议 / 伏笔 -->
          <div class="cp-section">
            <div class="cp-label">🧩 情节建议</div>
            <div v-if="activeForeshadows.length === 0" class="cp-empty">暂无活跃伏笔</div>
            <div v-for="(fs, i) in activeForeshadows.slice(0, 5)" :key="i" class="fs-card">
              <div class="fs-dot" :style="{ background: fs.resolved ? '#22c55e' : '#6366f1' }"></div>
              <span class="fs-text">{{ fs.description || fs.name || fs }}</span>
            </div>
            <button class="btn btn-ghost btn-xs cp-gen-btn" :disabled="!store.currentChapter">+ 生成多章节建议</button>
          </div>

          <!-- 审核面板 -->
          <div class="cp-section">
            <div class="cp-label">🔍 审核面板</div>
            <div class="audit-actions">
              <button class="btn btn-ghost btn-xs" :disabled="!store.currentChapter || auditing" @click="runFullAudit">
                {{ auditing ? '审计中...' : '📊 一键审计' }}
              </button>
              <button class="btn btn-ghost btn-xs" :disabled="!store.currentChapter || antiDetecting" @click="runAntiDetect">
                {{ antiDetecting ? '处理中...' : '🧹 去AI味' }}
              </button>
              <button class="btn btn-ghost btn-xs" :disabled="!store.currentChapter || revisionLooping" @click="runRevisionLoop">
                {{ revisionLooping ? '修订中...' : '🔄 自动修订' }}
              </button>
            </div>
            <div ref="radarRef" style="height:180px"></div>
            <div v-if="auditScores" class="audit-score" :class="{ 'score-pass': auditScores.passed, 'score-fail': !auditScores.passed }">
              综合评分 <span class="score-num">{{ auditScores.overall.toFixed(1) }}</span>/100
              <span class="score-badge">{{ auditScores.passed ? '✅ 通过' : '❌ 未通过' }}</span>
            </div>
            <!-- Issues -->
            <div v-if="auditScores?.issues?.length" class="issues-list" style="margin-top:8px">
              <div v-for="(issue, i) in auditScores.issues.slice(0, 5)" :key="i" class="issue-item">
                <span class="issue-dot" :style="{ background: severityColor(issue.severity) }"></span>
                <span class="issue-msg">{{ issue.message }}</span>
              </div>
            </div>
            <!-- Dimension bars -->
            <div v-if="auditScores" class="dim-list" style="margin-top:8px">
              <div class="dim-row" v-for="dim in [
                { label: '自然度', key: 'naturalness' }, { label: '吸引力', key: 'reading_power' },
                { label: '节奏', key: 'pacing' }, { label: '对话', key: 'dialogue' },
                { label: '伏笔', key: 'foreshadowing' }, { label: '连贯', key: 'continuity' },
                { label: '反AI', key: 'ai_detect' }, { label: '词汇', key: 'vocab_diversity' },
                { label: '情感', key: 'emotion_arc' }, { label: '句式', key: 'sentence_variety' },
              ]" :key="dim.key">
                <span class="dim-label">{{ dim.label }}</span>
                <div class="dim-bar-bg">
                  <div class="dim-bar-fill" :style="{ width: `${(auditScores as any)[dim.key]}%`, background: (auditScores as any)[dim.key] >= 60 ? '#22c55e' : (auditScores as any)[dim.key] >= 40 ? '#f59e0b' : '#ef4444' }"></div>
                </div>
                <span class="dim-score">{{ ((auditScores as any)[dim.key] as number).toFixed(0) }}</span>
              </div>
            </div>
            <!-- Revision result -->
            <div v-if="revisionResult" class="revision-card" style="margin-top:8px">
              <div class="rev-stats">
                <span>{{ revisionResult.rounds }}轮</span>
                <span>{{ revisionResult.initial_score }} → {{ revisionResult.final_score }}</span>
                <span :style="{ color: revisionResult.passed ? '#22c55e' : '#ef4444' }">
                  {{ revisionResult.passed ? '✅' : '❌' }}
                </span>
              </div>
            </div>
          </div>

          <!-- 写作统计 -->
          <div class="cp-section">
            <div class="cp-label">📊 写作统计</div>
            <div class="stats-grid">
              <div class="stat-item"><span class="stat-val">{{ writingStats.currentChapterWords.toLocaleString() }}</span><span class="stat-key">本章字数</span></div>
              <div class="stat-item"><span class="stat-val">{{ writingStats.totalChapters }}</span><span class="stat-key">已写章节</span></div>
              <div class="stat-item"><span class="stat-val">{{ writingStats.totalWords.toLocaleString() }}</span><span class="stat-key">全书字数</span></div>
              <div class="stat-item"><span class="stat-val">{{ writingStats.completionPct }}%</span><span class="stat-key">完成率</span></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- New chapter modal -->
    <n-modal v-model:show="showNewChapter" preset="card" style="width: 460px; border-radius: 16px" :bordered="false">
      <template #header>
        <div style="display:flex;align-items:center;gap:8px">
          <span style="font-size:20px">📝</span>
          <span style="font-size:16px;font-weight:600">新建章节</span>
        </div>
      </template>
      <n-form label-placement="left" label-width="70" style="padding:8px 0">
        <n-form-item label="章节号">
          <n-input-number v-model:value="newChapterForm.number" :min="1" style="width: 100%" />
        </n-form-item>
        <n-form-item label="标题">
          <n-input v-model:value="newChapterForm.title" placeholder="输入章节标题，如：星陨之夜" />
        </n-form-item>
      </n-form>
      <template #action>
        <n-space justify="end">
          <n-button @click="showNewChapter = false">取消</n-button>
          <n-button type="primary" @click="createChapter">创建章节</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Autopilot modal -->
    <n-modal v-model:show="showAutopilot" preset="card" style="width: 480px; border-radius: 16px" :bordered="false">
      <template #header>
        <div style="display:flex;align-items:center;gap:8px">
          <span style="font-size:20px">🚀</span>
          <div>
            <div style="font-size:16px;font-weight:600">全托管写作</div>
            <div style="font-size:12px;color:var(--gray-400);font-weight:400;margin-top:2px">AI 自动生成节拍并逐章写作</div>
          </div>
        </div>
      </template>
      <n-form label-placement="left" label-width="90" style="padding:8px 0">
        <n-form-item label="起始章节">
          <n-input-number v-model:value="autopilotForm.start_chapter" :min="1" style="width:100%" />
        </n-form-item>
        <n-form-item label="结束章节">
          <n-input-number v-model:value="autopilotForm.end_chapter" :min="autopilotForm.start_chapter" style="width:100%" />
        </n-form-item>
        <n-form-item label="自动节拍">
          <div style="display:flex;align-items:center;gap:8px">
            <input type="checkbox" v-model="autopilotForm.auto_beats" />
            <span style="font-size:13px;color:var(--gray-500)">自动为每章生成节拍（推荐）</span>
          </div>
        </n-form-item>
      </n-form>
      <div style="background:var(--gray-50);border-radius:8px;padding:12px;font-size:12px;color:var(--gray-500);line-height:1.6">
        💡 全托管模式将自动循环执行：生成节拍 → 写章节 → 章后管线。<br>
        写作过程中可随时暂停/停止。每章约 2000-3000 字。
      </div>
      <template #action>
        <n-space justify="end">
          <n-button @click="showAutopilot = false">取消</n-button>
          <n-button type="primary" @click="startAutopilot">开始全托管</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
/* ═══ Layout ═══ */
.studio-wrap{display:flex;flex-direction:column;height:calc(100vh - 64px);max-width:100%}
.studio-header{display:flex;align-items:center;gap:12px;padding:10px 16px;background:#fff;border-bottom:1px solid var(--gray-200)}
.header-breadcrumb{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--gray-500)}
.bc-sep{color:var(--gray-300);font-size:12px}
.bc-item{color:var(--gray-600);font-weight:500}.bc-item.active{color:var(--primary);font-weight:700}
.header-actions{display:flex;gap:6px;margin-left:auto}
.btn-danger{background:#ef4444;color:#fff;border:none;border-radius:10px}.btn-danger:hover{background:#dc2626}
.studio-body{flex:1;display:flex;gap:0;overflow:hidden;background:#fff}

/* ═══ Autopilot Bar ═══ */
.autopilot-bar{display:flex;align-items:center;gap:10px;padding:8px 16px;
  background:linear-gradient(90deg,#eef2ff,#faf5ff);border-bottom:1px solid rgba(99,102,241,.15)}
.ap-indicator{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.ap-indicator.running{background:#22c55e;box-shadow:0 0 6px #22c55e;animation:pulse 1.5s infinite}
.ap-indicator.paused{background:#f59e0b}
.ap-label{font-size:13px;font-weight:700;color:var(--gray-800)}
.ap-detail{font-size:12px;color:var(--gray-500);flex:1}
.ap-actions{display:flex;gap:6px}
.btn-sm{font-size:11px;padding:4px 10px;border-radius:6px;border:none;cursor:pointer;font-weight:600;transition:all .15s}
.btn-warn{background:#fef3c7;color:#d97706}.btn-warn:hover{background:#fde68a}
.btn-primary-sm{background:rgba(99,102,241,.1);color:var(--primary)}.btn-primary-sm:hover{background:var(--primary);color:#fff}
.btn-danger-sm{background:rgba(239,68,68,.1);color:#ef4444}.btn-danger-sm:hover{background:#ef4444;color:#fff}

/* ═══ Sidebar ═══ */
.chapter-sidebar{width:260px;border-right:1px solid var(--gray-200);display:flex;flex-direction:column;background:#f8f9fc}
.sidebar-head{padding:12px 16px;border-bottom:1px solid var(--gray-200);display:flex;align-items:center;justify-content:space-between;
  background:linear-gradient(135deg,#eef2ff,#f5f3ff)}
.sidebar-title{font-size:13px;font-weight:700;color:var(--gray-700)}
.add-ch-btn{font-size:11px;padding:4px 10px;border-radius:6px;border:1px solid rgba(99,102,241,.3);
  background:rgba(99,102,241,.08);color:var(--primary);cursor:pointer;font-weight:600;transition:all .15s}
.add-ch-btn:hover{background:var(--primary);color:#fff;border-color:var(--primary)}
.add-ch-btn:disabled{opacity:.4;cursor:not-allowed}
.chapter-list{flex:1;overflow-y:auto;padding:4px 0}
.empty-hint{padding:24px 16px;color:var(--gray-400);font-size:13px;text-align:center;line-height:1.8}
.hint-link{color:var(--primary);cursor:pointer;font-weight:500}.hint-link:hover{text-decoration:underline}

/* Volume headers */
.vol-header{display:flex;align-items:center;gap:6px;padding:8px 14px;cursor:pointer;user-select:none;
  border-bottom:1px solid var(--gray-100);background:rgba(99,102,241,.03)}
.vol-header:hover{background:rgba(99,102,241,.06)}
.vol-arrow{font-size:11px;color:var(--gray-400);transition:transform .15s;width:14px;text-align:center}
.vol-arrow.collapsed{transform:rotate(-90deg)}
.vol-title{font-size:12px;font-weight:700;color:var(--gray-700);flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.vol-count{font-size:10px;color:var(--gray-400);font-weight:500}

/* Chapter items */
.chapter-item{display:flex;align-items:center;gap:10px;padding:8px 14px 8px 20px;cursor:pointer;transition:all .12s}
.chapter-item:hover{background:rgba(99,102,241,.05)}
.chapter-item.active{background:rgba(99,102,241,.1)}
.chapter-item.outline-pending{opacity:.5}
.ch-dot{width:8px;height:8px;border-radius:50%;background:var(--gray-300);flex-shrink:0;transition:all .15s}
.ch-dot.current{background:var(--primary);box-shadow:0 0 0 3px rgba(99,102,241,.2)}
.ch-dot.written{background:#22c55e}
.ch-dot.outline{background:var(--gray-200);border:1px dashed var(--gray-300)}
.ch-info{flex:1;min-width:0}
.ch-number{font-size:12px;font-weight:600;color:var(--gray-700);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chapter-item.active .ch-number{color:var(--primary)}
.ch-meta{font-size:10px;color:var(--gray-400);margin-top:1px}

/* Sidebar footer */
.sidebar-footer{border-top:1px solid var(--gray-200);padding:12px 14px;background:linear-gradient(135deg,#f5f3ff,#eef2ff)}
.novel-info-card{margin-bottom:8px}
.novel-info-title{font-size:12px;font-weight:700;color:var(--gray-800);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.novel-info-meta{font-size:10px;color:var(--gray-400);margin-top:2px}
.sidebar-total-words{display:flex;align-items:baseline;gap:4px}
.total-label{font-size:10px;color:var(--gray-400)}
.total-num{font-size:24px;font-weight:800;color:var(--primary)}
.total-unit{font-size:12px;color:var(--gray-400)}

/* Outline fallback */
.outline-sidebar-hint{padding:10px 16px;font-size:12px;color:var(--primary);font-weight:600;border-bottom:1px solid var(--gray-100)}

/* ═══ Editor ═══ */
.editor-area{flex:1;display:flex;flex-direction:column;min-width:0;border-left:1px solid var(--gray-100);border-right:1px solid var(--gray-100)}
.editor-empty{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--gray-400)}
.editor-empty-icon{font-size:56px;margin-bottom:16px}
.editor-empty-title{font-size:17px;font-weight:600;color:var(--gray-500);margin-bottom:6px}
.editor-empty-sub{font-size:13px;color:var(--gray-400)}
.editor-header{padding:10px 24px;border-bottom:1px solid var(--gray-100);display:flex;align-items:center;gap:16px;flex-shrink:0;background:#fafbfc}
.editor-ch-title{font-size:15px;font-weight:700;color:var(--gray-800);white-space:nowrap}
.editor-header-meta{display:flex;align-items:center;gap:12px;margin-left:auto}
.editor-meta-item{font-size:11px;color:var(--gray-400)}
.editor-meta-item b{color:var(--gray-700);font-weight:700}
.editor-status{font-size:11px;padding:3px 10px;border-radius:10px;background:var(--gray-100);color:var(--gray-500);font-weight:500}
.editor-status.streaming{background:#fef3c7;color:#d97706;animation:pulse 1.5s infinite}
.editor-model{font-size:10px;padding:1px 6px;border-radius:4px;background:var(--gray-100);color:var(--gray-400);font-family:monospace}
.editor-body{flex:1;overflow-y:auto}

/* Streaming display (PlotPilot-style) */
.streaming-body{display:flex;flex-direction:column}
.streaming-header{display:flex;align-items:center;justify-content:space-between;padding:8px 24px;
  background:linear-gradient(90deg,#fef3c7,#fffbeb);border-bottom:1px solid rgba(217,119,6,.15)}
.streaming-ch{font-size:13px;font-weight:700;color:#92400e}
.streaming-wc{font-size:12px;color:#d97706;font-weight:600}
.streaming-content{flex:1;overflow-y:auto;padding:20px 28px;font-size:15px;line-height:1.9;
  font-family:"PingFang SC","Noto Sans SC",sans-serif;color:var(--gray-800);white-space:pre-wrap;word-break:break-all}

/* AI input bar */
.ai-input-bar{border-top:1px solid var(--gray-200);padding:10px 20px;background:#f8f9fc;flex-shrink:0}
.ai-bar-inner{display:flex;flex-direction:column;gap:6px}
.ai-input{width:100%;padding:8px 12px;border:1px solid var(--gray-200);border-radius:8px;font-size:13px;outline:none;
  background:#fff;transition:border-color .15s}
.ai-input:focus{border-color:var(--primary)}
.ai-bar-controls{display:flex;align-items:center;gap:12px}
.ai-bar-label{font-size:11px;color:var(--gray-400);font-weight:500}
.ai-bar-counter{font-size:10px;color:var(--gray-300);margin-left:auto}
.btn-bar{padding:5px 16px!important;font-size:12px!important;border-radius:8px!important}

/* ═══ Creative Panel ═══ */
.creative-panel{width:280px;display:flex;flex-direction:column;background:#f8f9fc}
.cp-head{padding:12px 16px;border-bottom:1px solid var(--gray-200);display:flex;align-items:center;justify-content:space-between;
  background:linear-gradient(135deg,#eef2ff,#f5f3ff)}
.cp-head-title{font-size:13px;font-weight:700;color:var(--gray-700)}
.cp-tabs{display:flex;gap:4px}
.cp-tab{font-size:10px;padding:2px 8px;border-radius:4px;border:1px solid var(--gray-200);background:#fff;color:var(--gray-500);
  cursor:pointer;font-weight:500;transition:all .12s}
.cp-tab.active{background:var(--primary);color:#fff;border-color:var(--primary)}
.cp-content{flex:1;overflow-y:auto;padding:12px 14px}
.cp-section{margin-bottom:16px}
.cp-label{font-size:12px;font-weight:700;color:var(--gray-600);margin-bottom:8px}
.cp-card{font-size:12px;color:var(--gray-600);line-height:1.6;padding:8px 10px;background:#fff;border:1px solid var(--gray-200);border-radius:8px}
.cp-empty{font-size:11px;color:var(--gray-400);padding:6px 0}
.cp-gen-btn{margin-top:6px;width:100%}

/* Character cards */
.char-card{display:flex;align-items:center;gap:10px;padding:8px 10px;background:#fff;border:1px solid var(--gray-200);
  border-radius:8px;margin-bottom:6px;transition:all .12s}
.char-card:hover{border-color:var(--primary);box-shadow:0 2px 8px rgba(99,102,241,.08)}
.char-avatar{width:32px;height:32px;border-radius:50%;background:var(--primary-gradient);color:#fff;
  font-size:14px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.char-info{flex:1;min-width:0}
.char-name{font-size:12px;font-weight:700;color:var(--gray-800)}
.char-role{font-size:10px;color:var(--primary);font-weight:500}
.char-desc{font-size:10px;color:var(--gray-400);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px}

/* Foreshadow cards */
.fs-card{display:flex;align-items:center;gap:8px;font-size:11px;color:var(--gray-600);padding:6px 10px;
  background:#fff;border:1px solid var(--gray-200);border-radius:6px;margin-bottom:4px}
.fs-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.fs-text{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* Stats grid */
.stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.stat-item{background:#fff;border:1px solid var(--gray-200);border-radius:8px;padding:8px 10px;text-align:center}
.stat-val{display:block;font-size:16px;font-weight:800;color:var(--primary)}
.stat-key{display:block;font-size:10px;color:var(--gray-400);margin-top:2px}

/* ═══ Audit (inside creative panel) ═══ */
.audit-actions{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px}
.audit-score{text-align:center;font-size:12px;color:var(--gray-500);margin-top:4px}
.score-num{font-size:18px;font-weight:800;color:var(--primary)}
.score-pass .score-num{color:#22c55e}
.score-fail .score-num{color:#ef4444}
.score-badge{display:inline-block;margin-left:6px;font-size:11px}
.issues-list{display:flex;flex-direction:column;gap:4px}
.issue-item{display:flex;align-items:flex-start;gap:6px;font-size:11px;padding:5px 8px;background:#fff;border:1px solid var(--gray-200);border-radius:6px;line-height:1.4}
.issue-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0;margin-top:4px}
.issue-msg{color:var(--gray-600);flex:1}
.dim-list{display:flex;flex-direction:column;gap:5px}
.dim-row{display:flex;align-items:center;gap:6px}
.dim-label{font-size:10px;color:var(--gray-500);width:32px;flex-shrink:0;text-align:right}
.dim-bar-bg{flex:1;height:5px;background:var(--gray-200);border-radius:3px;overflow:hidden}
.dim-bar-fill{height:100%;border-radius:3px;transition:width .4s ease}
.dim-score{font-size:10px;font-weight:700;color:var(--gray-600);width:20px;text-align:right}
.revision-card{background:#fff;border:1px solid var(--gray-200);border-radius:8px;padding:8px 10px;font-size:11px}
.rev-stats{display:flex;flex-wrap:wrap;gap:8px;color:var(--gray-600);font-weight:500}

/* ═══ Beat progress ═══ */
.beat-progress{padding:8px 24px;border-bottom:1px solid var(--gray-100);display:flex;align-items:center;gap:12px;flex-shrink:0;
  background:linear-gradient(90deg,#fefce8,#fffbeb)}
.beat-bar{flex:1;height:6px;background:var(--gray-200);border-radius:3px;overflow:hidden}
.beat-fill{height:100%;background:var(--primary-gradient);border-radius:3px;transition:width .3s ease}
.beat-info{font-size:11px;color:#92400e;white-space:nowrap;flex-shrink:0;font-weight:500}

/* ═══ Buttons ═══ */
.btn-accent{background:var(--primary-gradient);color:#fff;border:none;border-radius:10px}
.btn-accent:hover{background:linear-gradient(135deg,#4f46e5,#7c3aed);box-shadow:0 4px 14px rgba(99,102,241,.3)}
.btn-accent-alt{background:linear-gradient(135deg,#06b6d4,#0891b2);color:#fff;border:none;border-radius:10px}
.btn-accent-alt:hover{background:linear-gradient(135deg,#0891b2,#0e7490);box-shadow:0 4px 14px rgba(6,182,212,.3)}
.btn-accent-alt:disabled{opacity:.5;cursor:not-allowed;box-shadow:none}
.btn-xs{padding:2px 8px!important;font-size:11px!important;height:24px!important;min-width:auto!important}

/* ═══ Intent Panel ═══ */
.intent-panel{border-bottom:1px solid var(--gray-100);background:linear-gradient(135deg,#f0fdfa,#f0f9ff);animation:intentSlide .2s ease-out}
@keyframes intentSlide{from{max-height:0;opacity:0}to{max-height:500px;opacity:1}}
.intent-head{display:flex;align-items:center;gap:8px;padding:10px 24px;border-bottom:1px solid rgba(99,102,241,.1)}
.intent-icon{font-size:15px}
.intent-title{font-size:13px;font-weight:700;color:var(--gray-700)}
.intent-close{margin-left:auto;background:none;border:none;font-size:18px;color:var(--gray-400);cursor:pointer;
  width:24px;height:24px;display:flex;align-items:center;justify-content:center;border-radius:6px;transition:all .15s}
.intent-close:hover{background:var(--gray-200);color:var(--gray-600)}
.intent-body{padding:12px 24px}
.intent-row{display:flex;align-items:flex-start;gap:10px;margin-bottom:10px}
.intent-label{font-size:12px;font-weight:600;color:var(--gray-600);width:60px;flex-shrink:0;padding-top:5px}
.intent-actions{display:flex;gap:8px;margin-bottom:10px}
.intent-plan{background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:12px 14px;animation:intentSlide .2s}
.plan-intent{font-size:13px;font-weight:600;color:var(--gray-800);margin-bottom:8px}
.plan-meta{display:flex;gap:12px;font-size:11px;color:var(--gray-500);margin-bottom:8px;flex-wrap:wrap}
.plan-meta span{display:flex;align-items:center;gap:2px}
.plan-beats{display:flex;flex-direction:column;gap:4px;margin-bottom:8px}
.plan-beat{display:flex;align-items:center;gap:8px;font-size:11px;padding:3px 0}
.beat-type{font-size:10px;padding:1px 6px;border-radius:4px;background:var(--primary-light);color:var(--primary);font-weight:600;min-width:50px;text-align:center}
.beat-sum{color:var(--gray-600)}

@keyframes pulse{0%,100%{opacity:1}50%{opacity:.6}}

:deep(.tiptap){min-height:400px;padding:20px 28px;font-size:15px;line-height:1.9;
  font-family:"PingFang SC","Noto Sans SC",sans-serif;outline:none;color:var(--gray-800)}
:deep(.tiptap p){margin:.5em 0}
</style>
