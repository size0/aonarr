<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { NSpin, NSelect, NModal, useMessage } from 'naive-ui'
import {
  learningApi,
  type LearningStats,
  type KnowledgeEntry,
  type HotNovel,
  type HotNovelChapter,
  type ChapterContent,
  type OptimizationLog,
  type TutorialScanResult,
} from '@/api/learning'

const message = useMessage()
const loading = ref(false)
const stats = ref<LearningStats>({ knowledge_count: 0, hot_novel_count: 0, chapter_count: 0, opt_log_count: 0, crawling_count: 0, done_count: 0, last_crawl_at: null })
const knowledge = ref<KnowledgeEntry[]>([])
const hotNovels = ref<HotNovel[]>([])
const optLogs = ref<OptimizationLog[]>([])
const triggering = ref<Record<string, boolean>>({ crawl: false, learn: false, optimize: false, covers: false })

// Tutorial import
const tutorialDir = ref('D:\\mCloudDownload\\小说写作教程')
const tutorialScanResult = ref<TutorialScanResult | null>(null)
const tutorialImporting = ref(false)
const tutorialScanning = ref(false)
const tutorialMaxFiles = ref(100)
const tutorialUseLlm = ref(true)

type TabKey = 'knowledge' | 'hot' | 'trends' | 'logs'
const activeTab = ref<TabKey>('hot')
const knowledgeFilter = ref<string | null>(null)

// Chapter viewer
const selectedNovel = ref<HotNovel | null>(null)
const novelChapters = ref<HotNovelChapter[]>([])
const selectedChapter = ref<ChapterContent | null>(null)
const loadingChapters = ref(false)
const loadingContent = ref(false)

// Polling
let pollTimer: ReturnType<typeof setInterval> | null = null

// Activity log
const activityLogs = ref<{ ts: string; level: string; msg: string }[]>([])
const showLogPanel = ref(false)
let logPollTimer: ReturnType<typeof setInterval> | null = null

function startLogPoll() {
  stopLogPoll()
  logPollTimer = setInterval(async () => {
    try {
      const res = await learningApi.getActivityLog(0)
      activityLogs.value = res.logs
    } catch { /* ignore */ }
  }, 2000)
}
function stopLogPoll() { if (logPollTimer) { clearInterval(logPollTimer); logPollTimer = null } }

// 番茄登录状态（复用发布中心）
const fanqieLoggedIn = ref(false)

async function checkFanqieLogin() {
  try {
    const res = await learningApi.fanqieLoginStatus()
    fanqieLoggedIn.value = res.logged_in
  } catch { /* ignore */ }
}

const filteredKnowledge = computed(() => {
  if (!knowledgeFilter.value) return knowledge.value
  return knowledge.value.filter(k => k.category === knowledgeFilter.value)
})

const genreTrends = computed(() => {
  const map: Record<string, number> = {}
  hotNovels.value.forEach(n => { if (n.genre) map[n.genre] = (map[n.genre] || 0) + 1 })
  return Object.entries(map).sort((a, b) => b[1] - a[1]).slice(0, 12)
})

const categoryOptions = [
  { label: '全部', value: null as any },
  { label: '开篇套路', value: 'opening_pattern' },
  { label: '爽点分布', value: 'thrill_distribution' },
  { label: '人物模板', value: 'character_template' },
  { label: '对话风格', value: 'dialogue_style' },
  { label: '伏笔技巧', value: 'foreshadow_technique' },
  { label: '题材结构', value: 'genre_formula' },
  { label: '写作基础', value: 'writing_basics' },
  { label: '进阶技巧', value: 'writing_advanced' },
  { label: '大纲技巧', value: 'outline_technique' },
  { label: '世界观设定', value: 'worldbuilding' },
  { label: '节奏控制', value: 'pacing_technique' },
  { label: '写作技巧', value: 'writing_technique' },
  { label: '参考资料', value: 'reference_material' },
  { label: '网文流程', value: 'webnovel_workflow' },
  { label: '网文培训', value: 'webnovel_training' },
  { label: '心理学', value: 'psychology' },
  { label: '通用', value: 'writing_general' },
]

const categoryLabel: Record<string, string> = {
  opening_pattern: '开篇套路',
  thrill_distribution: '爽点分布',
  character_template: '人物模板',
  dialogue_style: '对话风格',
  foreshadow_technique: '伏笔技巧',
  genre_formula: '题材结构',
  writing_basics: '写作基础',
  writing_advanced: '进阶技巧',
  outline_technique: '大纲技巧',
  worldbuilding: '世界观设定',
  pacing_technique: '节奏控制',
  writing_technique: '写作技巧',
  reference_material: '参考资料',
  webnovel_workflow: '网文流程',
  webnovel_training: '网文培训',
  psychology: '心理学',
  writing_general: '通用',
  vocabulary: '描写词汇',
  plot_strategy: '计谋篇',
  eastern_worldbuilding: '东方世界观',
  western_worldbuilding: '西方世界观',
  urban_genre: '都市类',
  isekai_genre: '穿越类',
  game_genre: '网游类',
  cultivation_genre: '修真类',
  fantasy_genre: '玄幻类',
  weapons_reference: '兵器篇',
  combat_reference: '格斗技巧',
  naming_reference: '名字篇',
  taoism_reference: '道家篇',
  buddhism_reference: '佛家篇',
  story_structure: '故事结构',
  writing_material: '写作素材',
  writing_updates: '更新教程',
}

const statusLabel: Record<string, { text: string; cls: string }> = {
  meta: { text: '待采集', cls: 'st-meta' },
  crawling: { text: '采集中…', cls: 'st-crawling' },
  done: { text: '已完成', cls: 'st-done' },
  failed: { text: '失败', cls: 'st-failed' },
}

async function loadAll() {
  loading.value = true
  try {
    const [s, k, h, o] = await Promise.all([
      learningApi.getStats(),
      learningApi.listKnowledge(),
      learningApi.listHotNovels(),
      learningApi.listOptLogs(),
    ])
    stats.value = s
    knowledge.value = k
    hotNovels.value = h
    optLogs.value = o
  } catch { /* empty */ } finally { loading.value = false }
}

function startPoll() {
  stopPoll()
  pollTimer = setInterval(async () => {
    try {
      const [s, h] = await Promise.all([learningApi.getStats(), learningApi.listHotNovels()])
      stats.value = s
      hotNovels.value = h
      if (s.crawling_count === 0) stopPoll()
    } catch { /* ignore */ }
  }, 5000)
}
function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null } }

onMounted(() => { loadAll(); startLogPoll(); checkFanqieLogin() })
onBeforeUnmount(() => { stopPoll(); stopLogPoll() })

function coverSrc(url: string): string {
  if (!url) return ''
  if (url.startsWith('/api/')) return url
  return `/api/v1/learning/cover-proxy?url=${encodeURIComponent(url)}`
}
function onCoverError(e: Event) {
  const img = e.target as HTMLImageElement
  img.style.display = 'none'
  if (img.parentElement) img.parentElement.classList.add('nc-placeholder')
  if (img.parentElement) img.parentElement.textContent = '📕'
}

async function trigger(type: 'crawl' | 'learn' | 'optimize' | 'covers') {
  triggering.value[type] = true
  try {
    const fn = { crawl: learningApi.triggerCrawl, learn: learningApi.triggerLearn, optimize: learningApi.triggerOptimize, covers: learningApi.triggerCoverDownload }[type]
    const res = await fn()
    message.success(res.message)
    if (type === 'crawl') startPoll()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '触发失败')
  } finally {
    triggering.value[type] = false
    setTimeout(loadAll, 3000)
  }
}

async function scanTutorials() {
  if (!tutorialDir.value) { message.warning('请输入教程目录'); return }
  tutorialScanning.value = true
  try {
    tutorialScanResult.value = await learningApi.scanTutorials(tutorialDir.value)
    message.success(`扫描完成: ${tutorialScanResult.value.total} 个文件`)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '扫描失败')
  } finally { tutorialScanning.value = false }
}

async function importTutorials() {
  if (!tutorialDir.value) return
  tutorialImporting.value = true
  try {
    const res = await learningApi.importTutorials(tutorialDir.value, tutorialUseLlm.value, tutorialMaxFiles.value)
    message.success(res.message)
    setTimeout(loadAll, 5000)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '导入失败')
  } finally { tutorialImporting.value = false }
}

async function openNovel(novel: HotNovel) {
  selectedNovel.value = novel
  selectedChapter.value = null
  novelChapters.value = []
  if (novel.status === 'done') {
    loadingChapters.value = true
    try { novelChapters.value = await learningApi.listNovelChapters(novel.id) }
    catch { /* empty */ } finally { loadingChapters.value = false }
  }
}

async function readChapter(ch: HotNovelChapter) {
  if (!selectedNovel.value) return
  loadingContent.value = true
  try { selectedChapter.value = await learningApi.getChapterContent(selectedNovel.value.id, ch.id) }
  catch { message.error('加载章节失败') } finally { loadingContent.value = false }
}

async function applyLog(log: OptimizationLog) {
  try { await learningApi.applyOptLog(log.id); log.applied = true; message.success('已应用') }
  catch { message.error('应用失败') }
}

async function deleteKnowledge(id: string) {
  if (!confirm('确定删除该知识条目?')) return
  try { await learningApi.deleteKnowledge(id); knowledge.value = knowledge.value.filter(k => k.id !== id); message.success('已删除') }
  catch { message.error('删除失败') }
}

function fmtWords(n: number) { return n >= 10000 ? (n / 10000).toFixed(1) + '万' : n.toLocaleString() }

const tabs: { key: TabKey; icon: string; label: string }[] = [
  { key: 'hot', icon: '\uD83D\uDD25', label: '热门小说' },
  { key: 'knowledge', icon: '\uD83D\uDCD6', label: '知识库' },
  { key: 'trends', icon: '\uD83D\uDCC8', label: '题材趋势' },
  { key: 'logs', icon: '\uD83D\uDCDD', label: '优化日志' },
]
</script>

<template>
  <div class="page-learn">
    <div class="page-head-row">
      <div>
        <h1 class="page-title">🤖 学习中心</h1>
        <p class="page-desc">采集番茄热门 → AI 拆书学习 → 自动优化提示词</p>
      </div>
      <span v-if="stats.last_crawl_at" class="last-crawl">上次采集: {{ stats.last_crawl_at?.slice(0, 10) }}</span>
    </div>

    <!-- Stats -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="sc-icon" style="background:#eef2ff;color:#6366f1">📚</div>
        <div>
          <div class="sc-val">{{ stats.knowledge_count }}</div>
          <div class="sc-label">知识条目</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="sc-icon" style="background:#fef3c7;color:#f59e0b">🔥</div>
        <div>
          <div class="sc-val">{{ stats.hot_novel_count }}</div>
          <div class="sc-label">采集书目</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="sc-icon" style="background:#dbeafe;color:#3b82f6">📄</div>
        <div>
          <div class="sc-val">{{ stats.chapter_count }}</div>
          <div class="sc-label">采集章节</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="sc-icon" style="background:#dcfce7;color:#22c55e">⚡</div>
        <div>
          <div class="sc-val">{{ stats.opt_log_count }}</div>
          <div class="sc-label">优化次数</div>
        </div>
      </div>
    </div>

    <!-- Action buttons -->
    <div class="action-bar">
      <button class="btn btn-primary" :disabled="triggering.crawl" @click="trigger('crawl')">
        {{ triggering.crawl ? '⏳ 采集中...' : '📡 触发采集' }}
      </button>
      <button class="btn btn-ghost" :disabled="triggering.learn" @click="trigger('learn')">
        {{ triggering.learn ? '⏳ 学习中...' : '🧠 触发学习' }}
      </button>
      <button class="btn btn-ghost" :disabled="triggering.optimize" @click="trigger('optimize')">
        {{ triggering.optimize ? '⏳ 优化中...' : '⚡ 触发优化' }}
      </button>
      <!-- 番茄登录状态 -->
      <span v-if="fanqieLoggedIn" class="btn btn-ghost fanqie-logged" title="发布中心已登录，章节正文可获取">
        🍅 已登录
      </span>
      <span v-else class="btn btn-ghost fanqie-login-btn" title="请在发布中心配置番茄登录">
        🍅 未登录
      </span>
      <button class="btn btn-ghost" @click="loadAll" style="margin-left:auto">🔄 刷新</button>
      <button class="btn" :class="showLogPanel ? 'btn-primary' : 'btn-ghost'" @click="showLogPanel = !showLogPanel">📋 日志 <span v-if="activityLogs.length" class="log-badge">{{ activityLogs.length }}</span></button>
    </div>

    <!-- Crawling banner -->
    <div v-if="stats.crawling_count > 0" class="crawl-banner">
      <span class="crawl-dot"></span>
      正在采集中… {{ stats.crawling_count }} 本书正在抓取章节
    </div>

    <!-- Tabs -->
    <div class="tab-bar">
      <div v-for="t in tabs" :key="t.key"
        :class="['tab-item', { active: activeTab === t.key }]"
        @click="activeTab = t.key"
      >{{ t.icon }} {{ t.label }}</div>
    </div>

    <n-spin :show="loading">
      <!-- ═══ Hot Novels Tab ═══ -->
      <div v-if="activeTab === 'hot'" class="tab-content">
        <div v-if="!hotNovels.length" class="empty-state">
          <div class="empty-icon">&#x1F525;</div>
          <div>暂无热门小说数据</div>
          <div class="empty-sub">点击「触发采集」从番茄书库抓取</div>
        </div>
        <div v-else class="novel-grid">
          <div v-for="n in hotNovels" :key="n.id" class="novel-card" @click="openNovel(n)">
            <div class="nc-cover" v-if="n.cover_url">
              <img :src="coverSrc(n.cover_url)" :alt="n.title" loading="lazy" @error="onCoverError" />
            </div>
            <div class="nc-cover nc-placeholder" v-else>📕</div>
            <div class="nc-body">
              <div class="nc-title">{{ n.title }}</div>
              <div class="nc-author">{{ n.author }}</div>
              <div class="nc-meta">
                <span v-if="n.genre" class="nc-genre">{{ n.genre }}</span>
                <span>{{ fmtWords(n.word_count) }}字</span>
                <span v-if="n.chapter_count">{{ n.chapter_count }}章</span>
              </div>
              <div class="nc-status" :class="statusLabel[n.status]?.cls || ''">
                {{ statusLabel[n.status]?.text || n.status }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ Knowledge Tab ═══ -->
      <div v-if="activeTab === 'knowledge'" class="tab-content">
        <!-- Tutorial import panel -->
        <div class="tutorial-panel">
          <div class="tp-title">📂 教程导入</div>
          <div class="tp-row">
            <input v-model="tutorialDir" class="tp-input" placeholder="教程目录绝对路径" />
            <button class="btn btn-ghost btn-sm" :disabled="tutorialScanning" @click="scanTutorials">
              {{ tutorialScanning ? '⏳ 扫描中...' : '🔍 扫描' }}
            </button>
            <label class="tp-label"><input type="checkbox" v-model="tutorialUseLlm" /> LLM 提取</label>
            <input v-model.number="tutorialMaxFiles" type="number" class="tp-num" min="1" max="2000" title="最大文件数" />
            <button class="btn btn-primary btn-sm" :disabled="tutorialImporting || !tutorialDir" @click="importTutorials">
              {{ tutorialImporting ? '⏳ 导入中...' : '📥 导入' }}
            </button>
          </div>
          <div v-if="tutorialScanResult" class="tp-result">
            <span>共 {{ tutorialScanResult.total }} 个文件</span>
            <span v-for="(count, cat) in tutorialScanResult.by_category" :key="cat" class="tp-cat-badge">
              {{ categoryLabel[cat as string] || cat }}: {{ count }}
            </span>
          </div>
        </div>

        <div class="filter-bar">
          <n-select v-model:value="knowledgeFilter" :options="categoryOptions" placeholder="筛选分类" clearable style="width:180px" size="small" />
          <span class="filter-count">{{ filteredKnowledge.length }} 条</span>
        </div>
        <div v-if="!filteredKnowledge.length" class="empty-state">
          <div class="empty-icon">&#x1F4D6;</div>
          <div>知识库为空</div>
          <div class="empty-sub">点击「触发采集」→「触发学习」或使用上方教程导入</div>
        </div>
        <div v-else class="item-list">
          <div v-for="k in filteredKnowledge" :key="k.id" class="k-item">
            <div class="k-head">
              <span class="k-category">{{ categoryLabel[k.category] || k.category }}</span>
              <span v-if="k.source_file" class="k-source">📂 教程</span>
              <span v-else-if="k.source_novel_id" class="k-source k-source-novel">📚 拆书</span>
              <span class="k-title">{{ k.title }}</span>
              <span class="k-score">⭐ {{ k.quality_score?.toFixed(1) || '—' }}</span>
            </div>
            <div v-if="k.content?.pattern" class="k-pattern">💡 {{ k.content.pattern }}</div>
            <div v-if="k.content?.insights?.length" class="k-insights">
              <span v-for="(ins, i) in k.content.insights.slice(0, 3)" :key="i" class="k-insight">{{ ins }}</span>
            </div>
            <div class="k-tags">
              <span v-for="tag in k.tags" :key="tag" class="k-tag">{{ tag }}</span>
            </div>
            <div class="k-foot">
              <span class="k-date">{{ k.created_at?.slice(0, 10) || '' }}</span>
              <span v-if="k.source_file" class="k-file" :title="k.source_file">{{ k.source_file.split('\\').pop()?.split('/').pop() }}</span>
              <button class="btn-icon danger" title="删除" @click.stop="deleteKnowledge(k.id)">🗑️</button>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ Trends Tab ═══ -->
      <div v-if="activeTab === 'trends'" class="tab-content">
        <div v-if="!genreTrends.length" class="empty-state">
          <div class="empty-icon">📈</div>
          <div>趋势图将在采集数据后自动生成</div>
        </div>
        <div v-else class="trends-chart">
          <div class="trends-title">热门题材分布 (Top {{ genreTrends.length }})</div>
          <div v-for="([genre, count]) in genreTrends" :key="genre" class="trend-bar">
            <div class="tb-label">{{ genre }}</div>
            <div class="tb-track">
              <div class="tb-fill" :style="{ width: (count / genreTrends[0][1] * 100) + '%' }"></div>
            </div>
            <div class="tb-count">{{ count }}</div>
          </div>
        </div>
      </div>

      <!-- ═══ Optimization Logs Tab ═══ -->
      <div v-if="activeTab === 'logs'" class="tab-content">
        <div v-if="!optLogs.length" class="empty-state">
          <div class="empty-icon">📝</div>
          <div>暂无优化记录</div>
          <div class="empty-sub">点击「触发优化」让 AI 自动优化提示词</div>
        </div>
        <div v-else class="item-list">
          <div v-for="log in optLogs" :key="log.id" class="log-item">
            <div class="log-head">
              <span class="log-target">{{ log.description || log.target }}</span>
              <span v-if="log.applied" class="log-applied">✅ 已应用</span>
              <button v-else class="btn btn-sm btn-ghost" @click="applyLog(log)">应用</button>
            </div>
            <div v-if="log.after_snapshot?.analysis" class="log-desc">{{ log.after_snapshot.analysis }}</div>
            <div class="log-foot">
              <span v-if="log.improvement_score" class="log-score">置信度 {{ (log.improvement_score * 100).toFixed(0) }}%</span>
              <span class="log-date">{{ log.created_at?.slice(0, 10) }}</span>
            </div>
          </div>
        </div>
      </div>
    </n-spin>

    <!-- ═══ Novel Detail Modal ═══ -->
    <n-modal :show="!!selectedNovel" :mask-closable="true" @update:show="v => { if (!v) { selectedNovel = null; selectedChapter = null } }">
      <div class="novel-modal" v-if="selectedNovel">
        <div class="nm-header">
          <div class="nm-info">
            <h3>{{ selectedNovel.title }}</h3>
            <div class="nm-meta">{{ selectedNovel.author }} · {{ selectedNovel.genre }} · {{ fmtWords(selectedNovel.word_count) }}字</div>
          </div>
          <button class="nm-close" @click="selectedNovel = null">✕</button>
        </div>
        <div v-if="selectedNovel.synopsis" class="nm-synopsis">{{ selectedNovel.synopsis }}</div>

        <div v-if="selectedNovel.status === 'done'" class="nm-body">
          <div class="nm-sidebar">
            <div class="nm-sidebar-title">章节目录 ({{ novelChapters.length }})</div>
            <n-spin :show="loadingChapters" size="small">
              <div class="nm-chapter-list">
                <div v-for="ch in novelChapters" :key="ch.id"
                  :class="['nm-ch', { active: selectedChapter?.id === ch.id }]"
                  @click="readChapter(ch)"
                >
                  <span class="nm-ch-num">{{ ch.chapter_number }}</span>
                  <span class="nm-ch-title">{{ ch.title }}</span>
                  <span class="nm-ch-words">{{ ch.word_count }}字</span>
                </div>
              </div>
            </n-spin>
          </div>
          <div class="nm-content">
            <n-spin :show="loadingContent" size="small">
              <div v-if="selectedChapter" class="nm-reader">
                <h4>{{ selectedChapter.title }}</h4>
                <div class="nm-text" v-html="selectedChapter.content.replace(/\n/g, '<br/>')"></div>
              </div>
              <div v-else class="nm-placeholder">← 选择章节阅读</div>
            </n-spin>
          </div>
        </div>
        <div v-else class="nm-status-info">
          <div class="nm-status-badge" :class="statusLabel[selectedNovel.status]?.cls || ''">
            {{ statusLabel[selectedNovel.status]?.text || selectedNovel.status }}
          </div>
          <p v-if="selectedNovel.status === 'meta'">此书尚未采集章节内容，点击「触发采集」开始</p>
          <p v-else-if="selectedNovel.status === 'crawling'">正在采集章节内容…</p>
          <p v-else-if="selectedNovel.status === 'failed'">采集失败，请重新触发采集</p>
        </div>
      </div>
    </n-modal>
    <!-- Activity Log Panel -->
    <Transition name="slide">
      <div v-if="showLogPanel" class="log-panel">
        <div class="lp-header">
          <span class="lp-title">📋 活动日志</span>
          <button class="lp-close" @click="showLogPanel = false">✕</button>
        </div>
        <div class="lp-body">
          <div v-if="!activityLogs.length" class="lp-empty">暂无活动</div>
          <div v-for="(log, i) in [...activityLogs].reverse()" :key="i" :class="['lp-line', 'lp-' + log.level]">
            <span class="lp-ts">{{ log.ts }}</span>
            <span class="lp-msg">{{ log.msg }}</span>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.page-learn{max-width:1100px}
.page-head-row{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:22px}
.page-title{font-size:22px;font-weight:800;color:var(--gray-900);letter-spacing:-.3px}
.page-desc{font-size:13px;color:var(--gray-400);margin-top:6px}
.last-crawl{font-size:11px;color:var(--gray-400);padding:4px 10px;background:var(--gray-100);border-radius:8px}

/* Stats */
.stats-row{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}
.stat-card{display:flex;align-items:center;gap:14px;padding:18px;background:#fff;border:1px solid var(--gray-200);border-radius:14px;transition:all .18s}
.stat-card:hover{box-shadow:0 4px 16px rgba(0,0,0,.06);transform:translateY(-2px)}
.sc-icon{width:44px;height:44px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0}
.sc-val{font-size:22px;font-weight:700;color:var(--gray-800)}
.sc-label{font-size:12px;color:var(--gray-400);margin-top:2px}

/* Action bar */
.action-bar{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}

/* Crawl banner */
.crawl-banner{display:flex;align-items:center;gap:8px;padding:12px 18px;margin-bottom:16px;
  background:linear-gradient(90deg,#eef2ff,#f5f3ff);border:1px solid #e0e7ff;border-radius:12px;
  font-size:13px;color:#6366f1;font-weight:500}
.crawl-dot{width:8px;height:8px;border-radius:50%;background:#6366f1;animation:blink 1.2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}

/* Tabs */
.tab-bar{display:flex;gap:6px;padding:4px;background:var(--gray-100);border-radius:12px;margin-bottom:16px}
.tab-item{padding:8px 16px;cursor:pointer;font-size:13px;color:var(--gray-500);border-radius:10px;transition:all .18s;background:transparent}
.tab-item:hover{color:var(--gray-700);background:rgba(255,255,255,.5)}
.tab-item.active{color:var(--primary);background:#fff;font-weight:600;box-shadow:0 1px 3px rgba(0,0,0,.08)}

/* Tab content */
.tab-content{min-height:200px}
.filter-bar{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.filter-count{font-size:12px;color:var(--gray-400)}

/* Empty */
.empty-state{text-align:center;padding:48px 20px;background:#fff;border:2px dashed var(--gray-200);border-radius:16px;color:var(--gray-400);font-size:14px}
.empty-state .empty-icon{font-size:32px;margin-bottom:8px}
.empty-state .empty-sub{font-size:12px;margin-top:4px}

/* Item list */
.item-list{display:flex;flex-direction:column;gap:8px}

/* ─ Novel grid ─ */
.novel-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.novel-card{display:flex;gap:14px;background:#fff;border:1px solid var(--gray-200);border-radius:14px;
  padding:16px;cursor:pointer;transition:all .18s}
.novel-card:hover{box-shadow:0 4px 16px rgba(0,0,0,.06);transform:translateY(-2px)}
.nc-cover{width:56px;height:76px;border-radius:6px;overflow:hidden;flex-shrink:0;background:var(--gray-100)}
.nc-cover img{width:100%;height:100%;object-fit:cover}
.nc-placeholder{display:flex;align-items:center;justify-content:center;font-size:24px}
.nc-body{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}
.nc-title{font-size:14px;font-weight:600;color:var(--gray-800);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nc-author{font-size:12px;color:var(--gray-400)}
.nc-meta{font-size:11px;color:var(--gray-400);display:flex;gap:6px;flex-wrap:wrap;margin-top:auto}
.nc-genre{color:var(--primary);font-weight:500}
.nc-status{font-size:10px;padding:1px 8px;border-radius:10px;font-weight:600;width:fit-content;margin-top:4px}
.st-meta{background:var(--gray-100);color:var(--gray-500)}
.st-crawling{background:#fef3c7;color:#d97706}
.st-done{background:#dcfce7;color:#16a34a}
.st-failed{background:#fee2e2;color:#dc2626}

/* ─ Knowledge items ─ */
.k-item{background:#fff;border:1px solid var(--gray-200);border-radius:14px;padding:16px 18px;transition:all .15s}
.k-item:hover{box-shadow:0 2px 10px rgba(0,0,0,.04)}
.k-item:hover{border-color:var(--gray-300)}
.k-head{display:flex;align-items:center;gap:8px}
.k-category{font-size:11px;padding:1px 8px;border-radius:4px;background:var(--primary-light,#eef2ff);color:var(--primary);font-weight:500;flex-shrink:0}
.k-title{font-size:14px;font-weight:600;color:var(--gray-800);flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.k-score{font-size:12px;color:var(--gray-500);flex-shrink:0}
.k-pattern{font-size:12px;color:var(--gray-600);margin-top:6px;line-height:1.5;padding:8px 10px;background:var(--gray-50);border-radius:var(--radius-xs)}
.k-tags{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.k-tag{font-size:11px;padding:1px 6px;border-radius:4px;background:var(--gray-100);color:var(--gray-500)}
.k-foot{display:flex;align-items:center;justify-content:space-between;margin-top:6px}
.k-date{font-size:11px;color:var(--gray-300)}

/* ─ Trends ─ */
.trends-chart{background:#fff;border:1px solid var(--gray-200);border-radius:16px;padding:22px}
.trends-title{font-size:14px;font-weight:600;color:var(--gray-700);margin-bottom:14px}
.trend-bar{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.tb-label{width:80px;font-size:13px;color:var(--gray-600);text-align:right;flex-shrink:0}
.tb-track{flex:1;height:22px;background:var(--gray-100);border-radius:4px;overflow:hidden}
.tb-fill{height:100%;background:var(--primary-gradient);border-radius:4px;transition:width .3s}
.tb-count{width:30px;font-size:13px;font-weight:600;color:var(--gray-700)}

/* ─ Log items ─ */
.log-item{background:#fff;border:1px solid var(--gray-200);border-radius:14px;padding:16px 18px;transition:all .15s}
.log-item:hover{box-shadow:0 2px 10px rgba(0,0,0,.04)}
.log-item:hover{border-color:var(--gray-300)}
.log-head{display:flex;align-items:center;gap:8px}
.log-target{font-size:14px;font-weight:600;color:var(--gray-800);flex:1}
.log-applied{font-size:12px;color:#22c55e}
.log-desc{font-size:12px;color:var(--gray-500);margin-top:6px;line-height:1.5;padding:8px 10px;background:var(--gray-50);border-radius:var(--radius-xs)}
.log-foot{display:flex;gap:10px;margin-top:6px;font-size:12px}
.log-score{color:var(--primary);font-weight:600}
.log-date{color:var(--gray-300)}

/* ─ Novel Modal ─ */
.novel-modal{width:900px;max-width:95vw;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.15)}
.nm-header{display:flex;align-items:flex-start;justify-content:space-between;padding:20px 24px;border-bottom:1px solid var(--gray-200)}
.nm-info h3{font-size:16px;font-weight:700;color:var(--gray-900);margin:0}
.nm-meta{font-size:12px;color:var(--gray-400);margin-top:4px}
.nm-close{background:none;border:none;cursor:pointer;font-size:16px;color:var(--gray-400);padding:4px}
.nm-close:hover{color:var(--gray-700)}
.nm-synopsis{padding:12px 24px;font-size:13px;color:var(--gray-500);line-height:1.6;border-bottom:1px solid var(--gray-100);background:var(--gray-50)}

.nm-body{display:flex;height:500px}
.nm-sidebar{width:240px;border-right:1px solid var(--gray-200);display:flex;flex-direction:column;flex-shrink:0}
.nm-sidebar-title{padding:12px 16px;font-size:13px;font-weight:600;color:var(--gray-700);border-bottom:1px solid var(--gray-100)}
.nm-chapter-list{flex:1;overflow-y:auto}
.nm-ch{display:flex;align-items:center;gap:8px;padding:8px 16px;cursor:pointer;font-size:12px;transition:background .12s}
.nm-ch:hover{background:var(--gray-50)}
.nm-ch.active{background:var(--primary-light);color:var(--primary)}
.nm-ch-num{width:22px;flex-shrink:0;color:var(--gray-400);text-align:center;font-size:11px}
.nm-ch-title{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--gray-700)}
.nm-ch.active .nm-ch-title{color:var(--primary);font-weight:500}
.nm-ch-words{font-size:10px;color:var(--gray-300);flex-shrink:0}

.nm-content{flex:1;overflow-y:auto}
.nm-reader{padding:20px 24px}
.nm-reader h4{font-size:15px;font-weight:700;color:var(--gray-800);margin:0 0 16px}
.nm-text{font-size:14px;line-height:1.9;color:var(--gray-700)}
.nm-placeholder{display:flex;align-items:center;justify-content:center;height:100%;color:var(--gray-400);font-size:14px}

.nm-status-info{padding:40px;text-align:center}
.nm-status-badge{display:inline-block;font-size:13px;padding:4px 16px;border-radius:12px;font-weight:600;margin-bottom:12px}
.nm-status-info p{font-size:13px;color:var(--gray-400)}

/* ─ Tutorial import panel ─ */
.tutorial-panel{background:#fff;border:1px solid var(--gray-200);border-radius:14px;padding:16px 18px;margin-bottom:14px}
.tp-title{font-size:14px;font-weight:600;color:var(--gray-700);margin-bottom:10px}
.tp-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.tp-input{flex:1;min-width:200px;padding:6px 12px;border:1px solid var(--gray-200);border-radius:8px;font-size:13px;color:var(--gray-700);outline:none;transition:border .15s}
.tp-input:focus{border-color:var(--primary)}
.tp-label{display:flex;align-items:center;gap:4px;font-size:12px;color:var(--gray-500);cursor:pointer;white-space:nowrap}
.tp-num{width:70px;padding:6px 8px;border:1px solid var(--gray-200);border-radius:8px;font-size:12px;text-align:center}
.tp-result{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;font-size:12px;color:var(--gray-500)}
.tp-cat-badge{padding:1px 8px;background:var(--gray-100);border-radius:4px}

/* ─ Knowledge source badges ─ */
.k-source{font-size:10px;padding:1px 6px;border-radius:4px;background:#fef3c7;color:#d97706;flex-shrink:0}
.k-source-novel{background:#dbeafe;color:#3b82f6}
.k-insights{display:flex;flex-direction:column;gap:3px;margin-top:6px;font-size:12px;color:var(--gray-600)}
.k-insight{line-height:1.5;padding-left:10px;border-left:2px solid var(--gray-200)}
.k-file{font-size:10px;color:var(--gray-400);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* Misc */
.btn-icon{background:none;border:none;cursor:pointer;font-size:14px;padding:4px 6px;border-radius:4px;transition:background .15s}
.btn-icon:hover{background:var(--gray-100)}
.btn-icon.danger:hover{background:#fee2e2}
.btn-sm{font-size:12px;padding:2px 10px}

/* Log badge */
.log-badge{display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;padding:0 5px;border-radius:9px;background:#ef4444;color:#fff;font-size:10px;font-weight:700;margin-left:4px}

/* Activity Log Panel — right sidebar */
.log-panel{position:fixed;right:0;top:60px;bottom:0;width:420px;background:#fff;border-left:1px solid var(--gray-200);box-shadow:-4px 0 24px rgba(0,0,0,.06);z-index:100;display:flex;flex-direction:column}
.lp-header{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--gray-100);background:var(--gray-50)}
.lp-title{font-size:15px;font-weight:700;color:var(--gray-800)}
.lp-close{background:none;border:none;cursor:pointer;font-size:16px;color:var(--gray-400);padding:4px 8px;border-radius:6px}
.lp-close:hover{background:var(--gray-100);color:var(--gray-700)}
.lp-body{flex:1;overflow-y:auto;padding:12px 16px}
.lp-empty{text-align:center;color:var(--gray-400);font-size:14px;padding:40px 20px}
.lp-line{display:flex;gap:10px;padding:8px 10px;font-size:13px;line-height:1.6;border-bottom:1px solid var(--gray-50);border-radius:6px;transition:background .12s}
.lp-line:hover{background:var(--gray-50)}
.lp-ts{color:var(--gray-400);flex-shrink:0;font-family:monospace;font-size:12px;min-width:60px}
.lp-msg{color:var(--gray-700);word-break:break-all}
.lp-error .lp-msg{color:#dc2626;font-weight:500}
.lp-warning .lp-msg{color:#d97706}
.slide-enter-active,.slide-leave-active{transition:transform .25s ease}
.slide-enter-from,.slide-leave-to{transform:translateX(100%)}

/* 番茄登录状态 */
.fanqie-login-btn{color:#f97316!important;border-color:#fed7aa!important;background:#fffbeb!important;cursor:default!important}
.fanqie-logged{color:#16a34a!important;border-color:#bbf7d0!important;background:#f0fdf4!important;cursor:default!important}
</style>
