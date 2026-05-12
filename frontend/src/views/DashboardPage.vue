<script setup lang="ts">
import { NSelect, NInputNumber, NPopconfirm, useMessage } from 'naive-ui'
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useNovelsStore } from '@/stores/novels'
import type { NovelDTO } from '@/api/novels'

const router = useRouter()
const message = useMessage()
const store = useNovelsStore()

const totalWords = computed(() => store.novels.reduce((s, n) => s + (n.current_word_count || 0), 0))
const totalChapters = computed(() => store.novels.reduce((s, n) => s + (n.chapter_count || 0), 0))

const showCreate = ref(false)
const createForm = ref({ title: '', genre: '', tags: [] as string[], synopsis: '', target_chapter_count: 200, words_per_chapter: 2000 })
const creating = ref(false)

// ── Bootstrap state ─────────────────────────────────────────
interface BsStage {
  key: string; label: string; icon: string
  status: 'pending'|'running'|'done'|'error'
  detail: string; data: any
}
const bootstrapping = ref(false)
const bootstrapDone = ref(false)  // all stages finished
const bootstrapNovelId = ref('')
const bootstrapTitle = ref('')
const bootstrapStages = ref<BsStage[]>([])
let bootstrapSSE: EventSource | null = null

// ── Prediction state ─────────────────────────────────────────
const predictionResult = ref<any>(null)
const predicting = ref(false)

// ── Stage regeneration ───────────────────────────────────────
const regeneratingStage = ref<string | null>(null)

function initBootstrapStages() {
  bootstrapDone.value = false
  bootstrapStages.value = [
    { key: 'world', label: '世界观设定', icon: '🌍', status: 'pending', detail: '', data: null },
    { key: 'characters', label: '核心人物', icon: '👥', status: 'pending', detail: '', data: null },
    { key: 'outline', label: '宏观大纲', icon: '📑', status: 'pending', detail: '', data: null },
  ]
}

function setStageStatus(key: string, status: 'running'|'done'|'error', detail = '', data: any = null) {
  const s = bootstrapStages.value.find(s => s.key === key)
  if (s) { s.status = status; if (detail) s.detail = detail; if (data) s.data = data }
}

const roleLabel: Record<string, string> = {
  protagonist: '主角', antagonist: '反派', supporting: '配角',
  mentor: '师长', love_interest: '红颜'
}
const roleCls: Record<string, string> = {
  protagonist: 'role-protagonist', antagonist: 'role-antagonist',
  supporting: 'role-supporting', mentor: 'role-mentor', love_interest: 'role-love'
}
const genreOptions = ['玄幻','仙侠','都市','职场博弈','科幻','历史','悬疑','言情','奇幻','军事','游戏'].map(g => ({ label: g, value: g }))
const tagOptions = [
  '重生','穿越','系统','无敌流','升级流','退婚流','赘婿','战神','医神','鉴宝',
  '甜宠','虐恋','豪门','总裁','校园','古代','宫斗','种田','末世','星际',
  '修仙','妖族','炼丹','阵法','神豪','黑科技','诸天','无限流','直播','电竞',
  '热血','搞笑','治愈','暗黑','悬疑推理','商战','娱乐圈','体育','美食',
  '职场','规则流','博弈','短剧','打脸','逆袭','权谋',
].map(t => ({ label: t, value: t }))

async function handleCreate() {
  if (!createForm.value.title.trim()) { message.warning('请输入作品标题'); return }
  creating.value = true
  try {
    const payload = {
      ...createForm.value,
      target_word_count: (createForm.value.target_chapter_count || 200) * (createForm.value.words_per_chapter || 2000),
    }
    const novel = await store.createNovel(payload)
    message.success('作品创建成功，正在生成世界观/人物/大纲…')
    // 进入初始化引导
    editGuideMode.value = false
    bootstrapNovelId.value = novel.id
    bootstrapTitle.value = createForm.value.title
    predictionResult.value = null
    initBootstrapStages()
    bootstrapping.value = true
    showCreate.value = false
    startBootstrap(novel.id)
  } catch (e: any) { message.error(e.message || '创建失败') }
  finally { creating.value = false }
}

function startBootstrap(novelId: string) {
  if (bootstrapSSE) bootstrapSSE.close()
  bootstrapSSE = new EventSource(`/api/v1/creation/${novelId}/bootstrap`)

  bootstrapSSE.onmessage = (event) => {
    try {
      const d = JSON.parse(event.data)
      if (d.stage === 'done' || d.stage === 'complete') {
        bootstrapSSE?.close()
        bootstrapDone.value = true
        runPrediction()
        return
      }
      if (d.status === 'start') {
        setStageStatus(d.stage, 'running', '生成中…')
      } else if (d.status === 'done') {
        const count = d.saved_count ? `${d.saved_count}条` :
          Array.isArray(d.data) ? `${d.data.length}个` : '✓'
        setStageStatus(d.stage, 'done', count, d.data)
      } else if (d.status === 'error') {
        setStageStatus(d.stage, 'error', d.message || '生成失败')
      } else if (d.stage === 'error') {
        message.error(d.message || '初始化失败')
      }
    } catch { /* ignore */ }
  }

  bootstrapSSE.onerror = () => {
    bootstrapSSE?.close()
    bootstrapDone.value = true
    runPrediction()
  }
}

function confirmBootstrap() {
  bootstrapping.value = false
  if (bootstrapNovelId.value) {
    router.push({ path: '/studio', query: { novelId: bootstrapNovelId.value } })
  }
}

function skipBootstrap() {
  bootstrapSSE?.close()
  bootstrapping.value = false
  bootstrapDone.value = false
  editGuideMode.value = false
  predictionResult.value = null
}

async function regenerateStage(stageKey: string) {
  if (!bootstrapNovelId.value || regeneratingStage.value) return
  regeneratingStage.value = stageKey
  setStageStatus(stageKey, 'running', '重新生成中…')
  try {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 600000)
    const resp = await fetch(`/api/v1/creation/${bootstrapNovelId.value}/bootstrap/${stageKey}/regenerate`, { method: 'POST', signal: controller.signal })
    clearTimeout(timer)
    if (!resp.ok) throw new Error(await resp.text())
    const result = await resp.json()
    const count = result.saved_count ? `${result.saved_count}条` : '✓'
    setStageStatus(stageKey, 'done', count, result.data)
    message.success(`${stageKey === 'world' ? '世界观' : stageKey === 'characters' ? '人物' : '大纲'}已重新生成`)
    // 重新预测
    if (bootstrapDone.value) runPrediction()
  } catch (e: any) {
    setStageStatus(stageKey, 'error', e.message || '重新生成失败')
    message.error('重新生成失败')
  } finally {
    regeneratingStage.value = null
  }
}

async function runPrediction() {
  if (!bootstrapNovelId.value) return
  predicting.value = true
  try {
    const novel = store.novels.find(n => n.id === bootstrapNovelId.value)
    const resp = await fetch('/api/v1/prediction/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: novel?.title || bootstrapTitle.value,
        genre: novel?.genre || createForm.value.genre || '',
        synopsis: novel?.synopsis || createForm.value.synopsis || '',
        tags: novel?.tags || createForm.value.tags || [],
      }),
    })
    if (resp.ok) {
      predictionResult.value = await resp.json()
    }
  } catch (e) {
    console.error('预测失败', e)
  } finally {
    predicting.value = false
  }
}

function goStudio(novel?: NovelDTO) {
  router.push(novel ? { path: '/studio', query: { novelId: novel.id } } : '/studio')
}

async function handleDelete(novel: NovelDTO) {
  try {
    await store.deleteNovel(novel.id)
    message.success(`《${novel.title}》已删除`)
  } catch (e: any) {
    message.error(e?.message || '删除失败')
  }
}

// ── Edit Guide (open bootstrap overlay for existing novel) ──
const editGuideMode = ref(false)
const editGuideLoading = ref(false)

async function openEditGuide(novel: NovelDTO) {
  editGuideMode.value = true
  editGuideLoading.value = true
  bootstrapNovelId.value = novel.id
  bootstrapTitle.value = novel.title
  predictionResult.value = null
  initBootstrapStages()

  try {
    const resp = await fetch(`/api/v1/creation/${novel.id}/bootstrap/status`)
    if (resp.ok) {
      const status = await resp.json()
      const stages = status.stages || {}
      // World
      if (stages.world?.status === 'done') {
        setStageStatus('world', 'done', `${stages.world.count || 0}条`)
      }
      // Characters
      if (stages.characters?.status === 'done') {
        const charData = stages.characters.data
        setStageStatus('characters', 'done', `${stages.characters.count || 0}个`, charData)
      }
      // Outline
      if (stages.outline?.status === 'done') {
        setStageStatus('outline', 'done', `${stages.outline.count || 0}条`, stages.outline.data)
      }
      bootstrapDone.value = true
    }
  } catch (e) {
    console.error('获取初始化状态失败', e)
    // 全部标记为 pending，用户可以手动重新生成
    bootstrapDone.value = true
  } finally {
    editGuideLoading.value = false
  }
  bootstrapping.value = true
}

const statusLabel: Record<string, string> = { writing: '连载中', draft: '草稿', completed: '已完结', paused: '暂停' }

const quickActions = [
  { icon: '📖', label: '新建作品', sub: '向导式创建新小说', color: '#f5f3ff', fg: '#7c3aed', action: () => { showCreate.value = true } },
  { icon: '✍️', label: '创作台', sub: '沉浸式写作、续写创作', color: '#eef2ff', fg: '#6366f1', action: () => router.push('/studio') },
  { icon: '📑', label: '大纲管理', sub: '规划故事线路、管控全局', color: '#dcfce7', fg: '#22c55e', action: () => router.push('/outline') },
  { icon: '🌍', label: '世界观设定', sub: '构建特殊世界观、本篇设定室', color: '#fef3c7', fg: '#f59e0b', action: () => router.push('/worldview') },
  { icon: '📖', label: '拆书分析', sub: '多维度数据分析、作品表现', color: '#fce7f3', fg: '#ec4899', action: () => router.push('/booklab') },
  { icon: '📤', label: '发布中心', sub: '作品发布与管理', color: '#e0e7ff', fg: '#6366f1', action: () => router.push('/publish') },
  { icon: '📊', label: '数据看板', sub: '多维度数据分析', color: '#fff7ed', fg: '#f97316', action: () => router.push('/data') },
  { icon: '📈', label: '数据预测', sub: 'AI密度预测作品表现', color: '#faf5ff', fg: '#a855f7', action: () => router.push('/predict') },
  { icon: '🤖', label: '学习中心', sub: '写作课程与技巧学习', color: '#f0fdf4', fg: '#16a34a', action: () => router.push('/learn') },
]

const todayGoal = ref(3000)
const todayWords = computed(() => {
  return Math.min(totalWords.value, todayGoal.value)
})
const goalProgress = computed(() => Math.min(100, Math.round(todayWords.value / todayGoal.value * 100)))

// ── Title optimizer ─────────────────────────────────────────
const titleOptimizing = ref(false)
const titleOptResult = ref<any>(null)

async function optimizeTitle() {
  const t = createForm.value.title.trim()
  if (!t) { message.warning('请先输入书名'); return }
  titleOptimizing.value = true
  titleOptResult.value = null
  try {
    const resp = await fetch('/api/v1/creation/title/optimize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: t,
        genre: createForm.value.genre || '',
        synopsis: createForm.value.synopsis || '',
      }),
    })
    if (resp.ok) titleOptResult.value = await resp.json()
    else message.error('优化失败')
  } catch { message.error('网络错误') }
  finally { titleOptimizing.value = false }
}

function pickTitle(t: string) {
  createForm.value.title = t
  titleOptResult.value = null
  message.success(`已选用: ${t}`)
}

const streakDays = ref(7)
const weekGoal = ref(21000)
const weekWords = computed(() => Math.min(totalWords.value, weekGoal.value))
const weekProgress = computed(() => Math.min(100, Math.round(weekWords.value / weekGoal.value * 100)))
const monthGoalPct = ref(85)
const avgWordsPerDay = computed(() => {
  const days = Math.max(1, streakDays.value)
  return (totalWords.value / days).toFixed(1)
})

// Calendar mini
const now = new Date()
const calYear = ref(now.getFullYear())
const calMonth = ref(now.getMonth())
const calMonthLabel = computed(() => `${calYear.value}年${calMonth.value + 1}月`)
const calWeekLabels = ['一','二','三','四','五','六','日']
const calDays = computed(() => {
  const first = new Date(calYear.value, calMonth.value, 1)
  const last = new Date(calYear.value, calMonth.value + 1, 0)
  let startDay = first.getDay() - 1; if (startDay < 0) startDay = 6
  const days: { num: number; cur: boolean; today: boolean }[] = []
  const prevLast = new Date(calYear.value, calMonth.value, 0).getDate()
  for (let i = startDay - 1; i >= 0; i--) days.push({ num: prevLast - i, cur: false, today: false })
  for (let d = 1; d <= last.getDate(); d++) {
    const isToday = d === now.getDate() && calMonth.value === now.getMonth() && calYear.value === now.getFullYear()
    days.push({ num: d, cur: true, today: isToday })
  }
  const rem = 7 - (days.length % 7); if (rem < 7) for (let i = 1; i <= rem; i++) days.push({ num: i, cur: false, today: false })
  return days
})
function calPrev() { if (calMonth.value === 0) { calMonth.value = 11; calYear.value-- } else calMonth.value-- }
function calNext() { if (calMonth.value === 11) { calMonth.value = 0; calYear.value++ } else calMonth.value++ }

onMounted(() => store.loadNovels())
</script>

<template>
  <div class="dashboard-wrap">
    <div class="dashboard-main">
      <!-- Stats Row -->
      <div class="stats-row">
        <div class="stat-card">
          <div class="sc-icon" style="background:#eef2ff;color:#6366f1">📄</div>
          <div class="sc-body">
            <div class="sc-value">{{ totalWords.toLocaleString() }}</div>
            <div class="sc-label">创作总字数</div>
          </div>
          <div class="sc-delta up"><span class="delta-arrow">↑</span> 12.6% <span class="delta-vs">较上周</span></div>
        </div>
        <div class="stat-card">
          <div class="sc-icon" style="background:#dcfce7;color:#22c55e">�</div>
          <div class="sc-body">
            <div class="sc-value">{{ totalChapters }}</div>
            <div class="sc-label">总章节数</div>
          </div>
          <div class="sc-delta up"><span class="delta-arrow">↑</span> 9.1% <span class="delta-vs">较上周</span></div>
        </div>
        <div class="stat-card">
          <div class="sc-icon" style="background:#dcfce7;color:#16a34a">📅</div>
          <div class="sc-body">
            <div class="sc-value">{{ streakDays }}</div>
            <div class="sc-label">连续创作天数</div>
          </div>
          <div class="sc-delta up"><span class="delta-arrow">↑</span> 15.0% <span class="delta-vs">较上周</span></div>
        </div>
        <div class="stat-card">
          <div class="sc-icon" style="background:#fae8ff;color:#d946ef">👁</div>
          <div class="sc-body">
            <div class="sc-value">18,732</div>
            <div class="sc-label">累计阅读</div>
          </div>
          <div class="sc-delta up"><span class="delta-arrow">↑</span> 21.3% <span class="delta-vs">较上周</span></div>
        </div>
      </div>

      <!-- Today Goal + Stats in one row -->
      <div class="section-row">
        <div class="card-panel overview-card">
          <div class="card-head">
            <span class="card-title">创作概览</span>
            <span class="card-link" @click="$router.push('/data')">查看全部 ›</span>
          </div>
          <!-- mini stats inside -->
          <div class="ov-grid">
            <div class="ov-item">
              <div class="ov-icon" style="background:#eef2ff;color:#6366f1">✏️</div>
              <div>
                <div class="ov-val">{{ totalWords.toLocaleString() }}</div>
                <div class="ov-label">本月字数</div>
              </div>
            </div>
            <div class="ov-item">
              <div class="ov-icon" style="background:#dcfce7;color:#22c55e">�</div>
              <div>
                <div class="ov-val">{{ avgWordsPerDay }}</div>
                <div class="ov-label">日均字数</div>
              </div>
            </div>
            <div class="ov-item">
              <div class="ov-icon" style="background:#fef3c7;color:#f59e0b">�</div>
              <div>
                <div class="ov-val">{{ streakDays }}</div>
                <div class="ov-label">连续天数</div>
              </div>
            </div>
            <div class="ov-item">
              <div class="ov-icon" style="background:#fae8ff;color:#d946ef">🎯</div>
              <div>
                <div class="ov-val">{{ monthGoalPct }}%</div>
                <div class="ov-label">目标达成</div>
              </div>
            </div>
          </div>
        </div>

        <div class="card-panel goal-card">
          <div class="card-head">
            <span class="card-title">今日创作目标</span>
            <span class="card-link">编辑目标</span>
          </div>
          <div class="goal-number">{{ todayWords.toLocaleString() }} <span class="goal-of">/ {{ todayGoal.toLocaleString() }} 字</span></div>
          <div class="goal-bar-wrap">
            <div class="goal-bar"><div class="goal-fill" :style="{ width: goalProgress + '%' }"></div></div>
          </div>
          <div class="goal-hint">
            <span>⭐ 继续加油！距离今日目标还差 {{ (todayGoal - todayWords).toLocaleString() }} 字</span>
          </div>
        </div>
      </div>

      <!-- Quick Entry -->
      <div class="section">
        <div class="card-head" style="margin-bottom:14px">
          <span class="card-title">快速入口</span>
        </div>
        <div class="action-grid">
          <div v-for="a in quickActions" :key="a.label" class="action-btn" @click="a.action()">
            <div class="action-icon" :style="{ background: a.color, color: a.fg }">{{ a.icon }}</div>
            <div class="action-text">
              <div class="action-label">{{ a.label }}</div>
              <div class="action-sub">{{ a.sub }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Recent Works -->
      <div class="section">
        <div class="card-head" style="margin-bottom:14px">
          <span class="card-title">最近作品</span>
          <span class="card-link" @click="showCreate = true">新建作品 ›</span>
        </div>
        <div v-if="store.novels.length > 0" class="novels-grid">
          <div v-for="novel in store.novels.slice(0, 4)" :key="novel.id" class="novel-card">
            <div class="nc-cover" @click="goStudio(novel)">
              <span class="nc-letter">{{ novel.title?.charAt(0) || '书' }}</span>
              <div class="nc-genre" v-if="novel.genre">{{ novel.genre }}</div>
            </div>
            <div class="nc-info" @click="goStudio(novel)">
              <div class="nc-title">{{ novel.title }}</div>
              <div class="nc-meta">
                <span>更新时间: {{ novel.updated_at?.slice(0, 10) || '-' }}</span>
              </div>
              <div class="nc-stats">
                <span>字数: {{ (novel.current_word_count || 0).toLocaleString() }}</span>
              </div>
            </div>
            <div class="nc-actions">
              <button class="nc-guide-btn" @click.stop="openEditGuide(novel)" title="编辑向导">
                🧭 编辑向导
              </button>
              <n-popconfirm
                :positive-text="'确认删除'"
                :negative-text="'取消'"
                @positive-click="handleDelete(novel)"
              >
                <template #trigger>
                  <button class="nc-del-btn" @click.stop title="删除作品">🗑</button>
                </template>
                确定删除《{{ novel.title }}》吗？此操作不可恢复。
              </n-popconfirm>
            </div>
          </div>
          <!-- New novel card -->
          <div class="novel-card novel-card-new" @click="showCreate = true">
            <div class="nc-new-inner">
              <div class="nc-plus">+</div>
              <div class="nc-new-label">新建作品</div>
              <div class="nc-new-sub">开始创作新书</div>
            </div>
          </div>
        </div>
        <div v-else class="empty-block" @click="showCreate = true">
          <div class="empty-icon">📖</div>
          <div class="empty-title">还没有作品</div>
          <div class="empty-sub">点击创建你的第一部小说</div>
        </div>
      </div>
    </div>

    <!-- ========== Right Sidebar ========== -->
    <div class="dashboard-right">
      <!-- Calendar -->
      <div class="right-card">
        <div class="card-head">
          <span class="card-title">📅 创作日历</span>
        </div>
        <div class="cal-nav">
          <span class="cal-arrow" @click="calPrev">‹</span>
          <span class="cal-month">{{ calMonthLabel }}</span>
          <span class="cal-arrow" @click="calNext">›</span>
        </div>
        <div class="cal-grid">
          <div v-for="w in calWeekLabels" :key="w" class="cal-wk">{{ w }}</div>
          <div v-for="(d, i) in calDays" :key="i" :class="['cal-day', { cur: d.cur, today: d.today }]">
            {{ d.num }}
          </div>
        </div>
        <div class="cal-legend">
          <span class="cal-leg-item"><span class="cal-dot filled"></span> 创作日</span>
          <span class="cal-leg-item"><span class="cal-dot outline"></span> 达标日</span>
        </div>
      </div>

      <!-- Writing Streak -->
      <div class="right-card streak-card">
        <div class="card-head">
          <span class="card-title">🔥 连续创作</span>
        </div>
        <div class="streak-body">
          <div class="streak-num"><span class="streak-val">{{ streakDays }}</span> <span class="streak-unit">天</span></div>
          <div class="streak-flame">🔥</div>
        </div>
        <div class="streak-hint">继续保持！</div>
      </div>

      <!-- Goal This Week -->
      <div class="right-card">
        <div class="card-head">
          <span class="card-title">📊 本周目标</span>
        </div>
        <div class="week-goal-num">{{ weekWords.toLocaleString() }} <span class="week-goal-of">/ {{ weekGoal.toLocaleString() }}</span></div>
        <div class="week-goal-label">字数</div>
        <div class="week-bar-wrap">
          <div class="week-bar"><div class="week-fill" :style="{ width: weekProgress + '%' }"></div></div>
          <span class="week-pct">{{ weekProgress }}%</span>
        </div>
      </div>

      <!-- Latest Achievement -->
      <div class="right-card">
        <div class="card-head">
          <span class="card-title">🏆 最新成就</span>
        </div>
        <div class="achieve-row">
          <div class="achieve-badge">⭐</div>
          <div class="achieve-info">
            <div class="achieve-name">坚持写作者</div>
            <div class="achieve-desc">连续创作 7 天</div>
            <div class="achieve-xp">+150 XP</div>
          </div>
        </div>
      </div>

      <!-- Writing Tip -->
      <div class="right-card tip-card">
        <div class="card-head">
          <span class="card-title">💡 写作小贴士</span>
        </div>
        <p class="tip-text">强大的角色塑造是好故事的基石。赋予你的角色清晰的欲望、弱点和内心冲突，让读者产生共鸣。</p>
        <span class="tip-link" @click="$router.push('/learn')">了解更多 →</span>
      </div>
    </div>

    <!-- Create Modal — 白色卡片弹窗 -->
    <Teleport to="body">
      <div v-if="showCreate" class="create-overlay" @click.self="showCreate = false">
        <div class="create-card">
          <!-- Card Header -->
          <div class="cc-header">
            <div class="cc-header-left">
              <div class="cc-icon-wrap">
                <span class="cc-icon">✨</span>
              </div>
              <div>
                <div class="cc-title">创建新作品</div>
                <div class="cc-subtitle">填写基础信息，AI 自动生成世界观、人物和大纲</div>
              </div>
            </div>
            <button class="cc-close" @click="showCreate = false">&times;</button>
          </div>

          <!-- Card Body -->
          <div class="cc-body">
            <!-- 书名 -->
            <div class="cc-field">
              <label class="cc-label">作品名称 <span class="cc-required">*</span></label>
              <div class="cc-input-row">
                <input
                  v-model="createForm.title"
                  class="cc-input"
                  placeholder="给你的作品起个名字"
                  @input="titleOptResult = null"
                />
                <button class="cc-ai-btn" :disabled="titleOptimizing" @click="optimizeTitle">
                  {{ titleOptimizing ? '分析中…' : '✨ AI优化' }}
                </button>
              </div>
            </div>

            <!-- Title optimizer results -->
            <div v-if="titleOptResult" class="title-opt-box">
              <div class="to-diagnosis">
                <span class="to-score">{{ titleOptResult.original?.score || 0 }}/10</span>
                <span class="to-diag">{{ titleOptResult.original?.diagnosis || '' }}</span>
              </div>
              <div class="to-dims">
                <span :class="['to-dim', titleOptResult.original?.analysis?.background ? 'ok' : 'miss']">{{ titleOptResult.original?.analysis?.background ? '✅' : '❌' }} 背景</span>
                <span :class="['to-dim', titleOptResult.original?.analysis?.action ? 'ok' : 'miss']">{{ titleOptResult.original?.analysis?.action ? '✅' : '❌' }} 行为</span>
                <span :class="['to-dim', titleOptResult.original?.analysis?.expectation ? 'ok' : 'miss']">{{ titleOptResult.original?.analysis?.expectation ? '✅' : '❌' }} 期待</span>
                <span :class="['to-dim', titleOptResult.original?.analysis?.contrast ? 'ok' : 'miss']">{{ titleOptResult.original?.analysis?.contrast ? '✅' : '❌' }} 反差</span>
              </div>
              <div class="to-candidates">
                <div v-for="(c, i) in titleOptResult.candidates" :key="i" class="to-cand" @click="pickTitle(c.title)">
                  <div class="to-cand-head">
                    <span class="to-cand-title">{{ c.title }}</span>
                    <span class="to-cand-score">{{ c.score }}/10</span>
                  </div>
                  <div class="to-cand-reason">{{ c.reason }}</div>
                </div>
              </div>
            </div>

            <!-- 题材 + 标签 并排 -->
            <div class="cc-row">
              <div class="cc-field cc-half">
                <label class="cc-label">题材</label>
                <n-select v-model:value="createForm.genre" :options="genreOptions" placeholder="选择题材" clearable size="medium" />
              </div>
              <div class="cc-field cc-half">
                <label class="cc-label">标签</label>
                <n-select
                  v-model:value="createForm.tags"
                  :options="tagOptions"
                  placeholder="选择标签"
                  multiple filterable tag clearable
                  :max-tag-count="3"
                  size="medium"
                />
              </div>
            </div>

            <!-- 简介 -->
            <div class="cc-field">
              <label class="cc-label">故事简介</label>
              <textarea
                v-model="createForm.synopsis"
                class="cc-textarea"
                rows="3"
                placeholder="简要描述你的故事核心（选填，留空由 AI 根据题材自动生成）"
              />
            </div>

            <!-- 章节设定 -->
            <div class="cc-row">
              <div class="cc-field cc-half">
                <label class="cc-label">目标章数</label>
                <n-input-number v-model:value="createForm.target_chapter_count" :min="1" :max="5000" :step="10" placeholder="200" style="width:100%" size="medium" />
              </div>
              <div class="cc-field cc-half">
                <label class="cc-label">每章字数</label>
                <n-input-number v-model:value="createForm.words_per_chapter" :min="500" :max="10000" :step="100" placeholder="2000" style="width:100%" size="medium" />
              </div>
            </div>

            <!-- 预计字数 -->
            <div class="cc-estimate">
              <span class="cc-est-icon">📊</span>
              <span>预计总字数</span>
              <span class="cc-est-value">{{ ((createForm.target_chapter_count || 0) * (createForm.words_per_chapter || 0)).toLocaleString() }} 字</span>
            </div>
          </div>

          <!-- Card Footer -->
          <div class="cc-footer">
            <button class="cc-btn-cancel" @click="showCreate = false">取消</button>
            <button class="cc-btn-create" :disabled="creating" @click="handleCreate">
              {{ creating ? '创建中…' : '开始创作 →' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Bootstrap Progress & Results Overlay -->
    <Teleport to="body">
      <div v-if="bootstrapping" class="bootstrap-overlay">
        <div class="bootstrap-panel" :class="{ 'bp-wide': bootstrapDone }">

          <!-- Header -->
          <div class="bp-header">
            <button class="bp-close" @click="skipBootstrap" title="关闭">&times;</button>
            <div class="bp-icon-wrap">
              <div v-if="!bootstrapDone" class="bp-icon-pulse"></div>
              <span class="bp-icon">{{ bootstrapDone ? (editGuideMode ? '🧭' : '✅') : '🚀' }}</span>
            </div>
            <h3 class="bp-title">{{ bootstrapDone ? (editGuideMode ? '作品设定向导' : '初始化完成') : '正在初始化作品' }}</h3>
            <p class="bp-novel-name" v-if="bootstrapTitle">《{{ bootstrapTitle }}》</p>
            <p class="bp-sub">{{ bootstrapDone ? (editGuideMode ? '查看并管理世界观、人物、大纲，点击 🔄 可重新生成' : '请确认以下生成内容，然后进入创作台') : 'AI 正在为您生成世界观、人物和大纲…' }}</p>
          </div>

          <!-- Stage progress + content -->
          <div class="bp-body">
            <div v-for="(s, i) in bootstrapStages" :key="s.key" class="bp-section">
              <!-- Stage header -->
              <div class="bp-stage-row" :class="s.status">
                <div class="bp-stage-dot">
                  <span v-if="s.status === 'done'" class="dot-check">✓</span>
                  <span v-else-if="s.status === 'error'" class="dot-err">!</span>
                  <span v-else-if="s.status === 'running'" class="dot-spin"></span>
                  <span v-else class="dot-num">{{ i + 1 }}</span>
                </div>
                <span class="bp-stage-icon">{{ s.icon }}</span>
                <span class="bp-stage-label">{{ s.label }}</span>
                <span v-if="s.detail" class="bp-stage-detail" :class="s.status">{{ s.detail }}</span>
                <button
                  v-if="s.status === 'done' || s.status === 'error' || (editGuideMode && s.status === 'pending')"
                  class="bp-regen-btn"
                  :disabled="regeneratingStage !== null"
                  @click="regenerateStage(s.key)"
                  :title="s.status === 'pending' ? '生成' + s.label : '重新生成' + s.label"
                >
                  {{ s.status === 'pending' ? '✨' : '🔄' }}
                </button>
              </div>
              <!-- Progress bar -->
              <div v-if="s.status === 'running'" class="bp-stage-bar"><div class="bp-stage-bar-fill"></div></div>
              <!-- Error -->
              <div v-if="s.status === 'error'" class="bp-error">{{ s.detail }}</div>

              <!-- ═══ World items ═══ -->
              <div v-if="s.key === 'world' && s.status === 'done' && s.data" class="bp-result">
                <div class="bp-result-grid">
                  <div v-for="(item, idx) in (s.data.items || s.data.world_items || []).slice(0, 12)" :key="idx" class="bp-world-card">
                    <div class="bwc-cat">{{ item.category }}</div>
                    <div class="bwc-name">{{ item.name }}</div>
                    <div class="bwc-desc">{{ (item.description || '').slice(0, 80) }}</div>
                  </div>
                </div>
              </div>

              <!-- ═══ Characters ═══ -->
              <div v-if="s.key === 'characters' && s.status === 'done' && s.data" class="bp-result">
                <div class="bp-char-list">
                  <div v-for="(ch, idx) in (Array.isArray(s.data) ? s.data : s.data.characters || []).slice(0, 6)" :key="idx" class="bp-char-card">
                    <div class="bcc-top">
                      <span class="bcc-avatar">{{ (ch.name || '?')[0] }}</span>
                      <div class="bcc-info">
                        <span class="bcc-name">{{ ch.name }}</span>
                        <span class="bcc-role" :class="roleCls[ch.role] || ''">{{ roleLabel[ch.role] || ch.role }}</span>
                      </div>
                    </div>
                    <div class="bcc-desc">{{ (ch.description || '').slice(0, 60) }}</div>
                    <div v-if="ch.traits?.length" class="bcc-traits">
                      <span v-for="t in ch.traits.slice(0, 4)" :key="t" class="bcc-tag">{{ t }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- ═══ Outline ═══ -->
              <div v-if="s.key === 'outline' && s.status === 'done' && s.data" class="bp-result">
                <div class="bp-outline-tree">
                  <div v-for="(vol, vi) in (s.data.volumes || s.data.acts || []).slice(0, 5)" :key="vi" class="bp-vol">
                    <div class="bpv-head">
                      <span class="bpv-badge">卷{{ Number(vi) + 1 }}</span>
                      <span class="bpv-title">{{ vol.title }}</span>
                      <span v-if="vol.chapter_range" class="bpv-range">第{{ vol.chapter_range[0] }}-{{ vol.chapter_range[1] }}章</span>
                    </div>
                    <div v-if="vol.summary" class="bpv-summary">{{ vol.summary }}</div>
                    <div v-if="vol.chapters?.length" class="bpv-chapters">
                      <div v-for="(ch, ci) in vol.chapters.slice(0, 5)" :key="ci" class="bpv-ch">
                        <span class="bpv-ch-num">{{ Number(ci) + 1 }}.</span>
                        <span class="bpv-ch-title">{{ ch.title }}</span>
                        <span v-if="ch.summary" class="bpv-ch-sum">{{ ch.summary }}</span>
                      </div>
                      <div v-if="vol.chapters.length > 5" class="bpv-more">还有 {{ vol.chapters.length - 5 }} 个章节…</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Prediction Panel -->
          <div v-if="bootstrapDone" class="bp-predict">
            <div class="bp-predict-head">
              <span class="bp-predict-icon">📊</span>
              <span class="bp-predict-title">AI 写前预评估</span>
              <span v-if="predicting" class="bp-predict-loading">分析中…</span>
              <button v-else-if="predictionResult" class="bp-regen-btn" @click="runPrediction" title="重新预测">🔄</button>
            </div>
            <div v-if="predicting" class="bp-predict-skeleton">
              <div class="bp-skel-bar"></div>
              <div class="bp-skel-bar short"></div>
            </div>
            <div v-else-if="predictionResult" class="bp-predict-body">
              <div class="bp-predict-score-row">
                <div class="bp-predict-score" :class="{
                  high: predictionResult.overall_score >= 70,
                  mid: predictionResult.overall_score >= 40 && predictionResult.overall_score < 70,
                  low: predictionResult.overall_score < 40
                }">
                  <span class="bps-num">{{ predictionResult.overall_score }}</span>
                  <span class="bps-label">综合评分</span>
                </div>
                <div class="bp-predict-metrics">
                  <div class="bpm-item"><span class="bpm-label">预估日读</span><span class="bpm-val">{{ predictionResult.estimated_daily_reads }}</span></div>
                  <div class="bpm-item"><span class="bpm-label">追更率</span><span class="bpm-val">{{ predictionResult.follow_rate }}</span></div>
                  <div class="bpm-item"><span class="bpm-label">签约概率</span><span class="bpm-val">{{ predictionResult.signing_probability }}</span></div>
                  <div class="bpm-item"><span class="bpm-label">赛道热度</span><span class="bpm-val">{{ predictionResult.genre_heat?.split(' ')[0] || predictionResult.genre_heat }}</span></div>
                </div>
              </div>
              <div v-if="predictionResult.risk_warnings?.length" class="bp-predict-section">
                <div class="bps-title">⚠️ 风险提示</div>
                <ul class="bps-list warn">
                  <li v-for="(w, i) in predictionResult.risk_warnings" :key="i">{{ w }}</li>
                </ul>
              </div>
              <div v-if="predictionResult.optimization_suggestions?.length" class="bp-predict-section">
                <div class="bps-title">💡 优化建议</div>
                <ul class="bps-list suggest">
                  <li v-for="(s, i) in predictionResult.optimization_suggestions" :key="i">{{ s }}</li>
                </ul>
              </div>
              <div v-if="predictionResult.best_publish_time" class="bp-predict-hint">
                ⏰ {{ predictionResult.best_publish_time }}
              </div>
            </div>
          </div>

          <!-- Footer -->
          <div class="bp-footer">
            <button v-if="!bootstrapDone" class="btn-ghost-sm" @click="skipBootstrap">跳过，稍后再生成</button>
            <div v-else style="display:flex;align-items:center;gap:12px;justify-content:center">
              <button class="btn-ghost-sm" @click="skipBootstrap">返回仪表盘</button>
              <button class="btn-primary-lg" @click="confirmBootstrap">
                确认并进入创作台 →
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
/* ========== Layout ========== */
.dashboard-wrap{display:flex;gap:24px}
.dashboard-main{flex:1;min-width:0}
.dashboard-right{width:300px;flex-shrink:0}

/* ========== Stats Row ========== */
.stats-row{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:20px}
.stat-card{background:#fff;border:1px solid var(--gray-200);border-radius:14px;padding:20px 20px 32px;display:flex;align-items:center;gap:14px;position:relative;transition:all .18s}
.stat-card:hover{border-color:var(--primary);box-shadow:var(--shadow)}
.sc-icon{width:48px;height:48px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0}
.sc-body{flex:1;min-width:0}
.sc-value{font-size:22px;font-weight:800;color:var(--gray-800);letter-spacing:-.5px;line-height:1.2}
.sc-label{font-size:11px;color:var(--gray-400);margin-top:2px}
.sc-delta{font-size:10px;color:var(--gray-400);position:absolute;bottom:10px;left:20px;display:flex;align-items:center;gap:3px}
.sc-delta.up{color:#16a34a}
.sc-delta .delta-arrow{font-weight:700}
.sc-delta .delta-vs{color:var(--gray-300);margin-left:2px}

/* ========== Section Row (two cards) ========== */
.section-row{display:flex;gap:16px;margin-bottom:20px}
.card-panel{background:#fff;border:1px solid var(--gray-200);border-radius:14px;padding:20px;flex:1;transition:all .18s}
.card-panel:hover{border-color:var(--gray-300);box-shadow:0 2px 12px rgba(0,0,0,.04)}
.card-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
.card-title{font-size:14px;font-weight:600;color:var(--gray-800)}
.card-link{font-size:12px;color:var(--primary);cursor:pointer;font-weight:500}
.card-link:hover{text-decoration:underline}

/* Overview card */
.ov-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.ov-item{display:flex;align-items:center;gap:10px}
.ov-icon{width:38px;height:38px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0}
.ov-val{font-size:18px;font-weight:700;color:var(--gray-800);letter-spacing:-.3px}
.ov-label{font-size:11px;color:var(--gray-400);margin-top:1px}

/* Goal card */
.goal-card{max-width:380px}
.goal-number{font-size:32px;font-weight:800;color:var(--primary);letter-spacing:-.5px;margin-bottom:4px}
.goal-of{font-size:14px;color:var(--gray-400);font-weight:400}
.goal-bar-wrap{margin-bottom:10px}
.goal-bar{height:10px;background:var(--gray-100);border-radius:5px;overflow:hidden}
.goal-fill{height:100%;background:var(--primary-gradient);border-radius:5px;transition:width .4s ease}
.goal-hint{font-size:12px;color:var(--gray-400);display:flex;align-items:center;gap:4px}

/* ========== Quick Actions ========== */
.section{margin-bottom:20px}
.action-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.action-btn{display:flex;align-items:center;gap:12px;padding:16px 18px;
  background:#fff;border:1px solid var(--gray-200);border-radius:14px;
  cursor:pointer;transition:all .18s}
.action-btn:hover{border-color:var(--primary);box-shadow:var(--shadow);transform:translateY(-2px)}
.action-icon{width:44px;height:44px;border-radius:12px;display:flex;
  align-items:center;justify-content:center;font-size:20px;flex-shrink:0}
.action-text{min-width:0}
.action-label{font-size:13px;font-weight:600;color:var(--gray-800)}
.action-sub{font-size:11px;color:var(--gray-400);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* ========== Create Form Helpers ========== */
.create-row{display:flex;gap:16px}
.create-half{flex:1}
.create-calc{font-size:12px;color:var(--gray-500);text-align:right;padding:0 4px 4px;margin-top:-8px}
.create-calc b{color:var(--primary);font-size:14px}

/* ========== Recent Works ========== */
.novels-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px}
.novel-card{background:#fff;border:1px solid var(--gray-200);border-radius:16px;
  overflow:hidden;cursor:pointer;transition:all .18s}
.novel-card:hover{border-color:var(--primary);box-shadow:0 8px 30px rgba(99,102,241,.15);transform:translateY(-3px)}
.nc-cover{height:160px;background:linear-gradient(160deg,#1e1b4b 0%,#312e81 40%,#4f46e5 70%,#7c3aed 100%);
  display:flex;flex-direction:column;align-items:center;justify-content:center;position:relative;
  overflow:hidden}
.nc-cover::after{content:'';position:absolute;bottom:0;left:0;right:0;height:60px;
  background:linear-gradient(transparent,rgba(0,0,0,.25))}
.nc-letter{color:rgba(255,255,255,.45);font-size:52px;font-weight:800;position:relative;z-index:1}
.nc-genre{position:absolute;top:10px;left:10px;font-size:10px;padding:3px 10px;border-radius:6px;
  background:rgba(255,255,255,.2);color:rgba(255,255,255,.9);backdrop-filter:blur(6px);font-weight:500;z-index:1}
.nc-info{padding:14px}
.nc-title{font-size:14px;font-weight:600;color:var(--gray-800);margin-bottom:6px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nc-meta{font-size:11px;color:var(--gray-400);margin-bottom:3px}
.nc-stats{font-size:11px;color:var(--gray-400)}

.nc-actions{display:flex;align-items:center;justify-content:space-between;padding:6px 12px 10px;gap:6px}
.nc-guide-btn{font-size:11px;color:var(--primary);background:var(--primary-light,#eef2ff);border:1px solid #e0e7ff;
  border-radius:8px;padding:4px 10px;cursor:pointer;transition:all .15s;font-weight:500;white-space:nowrap}
.nc-guide-btn:hover{background:#dbeafe;border-color:#c7d2fe;transform:translateY(-1px);box-shadow:0 2px 8px rgba(99,102,241,.15)}
.nc-del-btn{background:none;border:none;font-size:14px;cursor:pointer;padding:4px 6px;
  border-radius:6px;color:var(--gray-400);transition:all .15s;margin-left:auto}
.nc-del-btn:hover{background:#fee2e2;color:#dc2626}

.novel-card-new{border:2px dashed var(--gray-200)}
.novel-card-new:hover{border-color:var(--primary);background:var(--primary-light)}
.nc-new-inner{display:flex;flex-direction:column;align-items:center;justify-content:center;
  height:100%;min-height:200px;padding:20px}
.nc-plus{width:48px;height:48px;border-radius:50%;background:var(--gray-100);display:flex;
  align-items:center;justify-content:center;font-size:28px;color:var(--gray-400);margin-bottom:10px}
.nc-new-label{font-size:14px;font-weight:600;color:var(--gray-600);margin-bottom:4px}
.nc-new-sub{font-size:12px;color:var(--gray-400)}

.empty-block{text-align:center;padding:48px;background:#fff;border:2px dashed var(--gray-200);
  border-radius:var(--radius);cursor:pointer;transition:all .15s}
.empty-block:hover{border-color:var(--primary);background:var(--primary-light)}
.empty-icon{font-size:36px;margin-bottom:10px}
.empty-title{font-size:15px;font-weight:600;color:var(--gray-600);margin-bottom:4px}
.empty-sub{font-size:13px;color:var(--gray-400)}

/* ========== Right Sidebar ========== */
.right-card{background:#fff;border-radius:14px;border:1px solid var(--gray-200);padding:18px;margin-bottom:14px;transition:all .18s}
.right-card:hover{border-color:var(--gray-300);box-shadow:0 2px 12px rgba(0,0,0,.04)}

/* Calendar */
.cal-nav{display:flex;align-items:center;justify-content:center;gap:14px;margin-bottom:10px}
.cal-arrow{cursor:pointer;font-size:16px;color:var(--gray-400);width:28px;height:28px;display:flex;
  align-items:center;justify-content:center;border-radius:6px;transition:all .12s;user-select:none}
.cal-arrow:hover{background:var(--gray-100);color:var(--gray-700)}
.cal-month{font-size:13px;font-weight:600;color:var(--gray-700);min-width:90px;text-align:center}
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;text-align:center}
.cal-wk{font-size:11px;color:var(--gray-400);padding:4px 0;font-weight:500}
.cal-day{font-size:12px;color:var(--gray-300);padding:5px 0;border-radius:50%;cursor:default;
  width:30px;height:30px;display:flex;align-items:center;justify-content:center;margin:0 auto}
.cal-day.cur{color:var(--gray-600)}
.cal-day.today{background:var(--primary);color:#fff;font-weight:600;border-radius:50%}
.cal-legend{display:flex;align-items:center;gap:14px;margin-top:10px;justify-content:center}
.cal-leg-item{font-size:11px;color:var(--gray-400);display:flex;align-items:center;gap:4px}
.cal-dot{width:8px;height:8px;border-radius:50%}
.cal-dot.filled{background:var(--primary)}
.cal-dot.outline{border:2px solid var(--primary);background:transparent}

/* Writing Streak */
.streak-card{overflow:hidden}
.streak-body{display:flex;align-items:center;justify-content:space-between;padding:4px 0}
.streak-num{display:flex;align-items:baseline;gap:4px}
.streak-val{font-size:36px;font-weight:800;color:var(--primary);letter-spacing:-1px}
.streak-unit{font-size:16px;font-weight:600;color:var(--gray-500)}
.streak-flame{font-size:48px;opacity:.85}
.streak-hint{font-size:12px;color:var(--gray-400);margin-top:2px}

/* Week Goal */
.week-goal-num{font-size:22px;font-weight:700;color:var(--primary);letter-spacing:-.3px}
.week-goal-of{font-size:13px;color:var(--gray-400);font-weight:400}
.week-goal-label{font-size:11px;color:var(--gray-400);margin-bottom:8px}
.week-bar-wrap{display:flex;align-items:center;gap:10px}
.week-bar{flex:1;height:8px;background:var(--gray-100);border-radius:4px;overflow:hidden}
.week-fill{height:100%;background:var(--primary-gradient);border-radius:4px;transition:width .4s ease}
.week-pct{font-size:12px;font-weight:600;color:var(--primary);flex-shrink:0}

/* Achievement */
.achieve-row{display:flex;align-items:center;gap:14px}
.achieve-badge{width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,#eef2ff,#e0e7ff);
  display:flex;align-items:center;justify-content:center;font-size:24px;flex-shrink:0}
.achieve-info{min-width:0}
.achieve-name{font-size:14px;font-weight:600;color:var(--gray-800)}
.achieve-desc{font-size:11px;color:var(--gray-400);margin-top:1px}
.achieve-xp{font-size:12px;font-weight:600;color:var(--primary);margin-top:3px}

/* Writing Tip */
.tip-card{background:linear-gradient(135deg,#faf5ff,#f5f3ff)}
.tip-text{font-size:12px;color:var(--gray-600);line-height:1.7;margin:0 0 10px}
.tip-link{font-size:12px;color:var(--primary);cursor:pointer;font-weight:500}
.tip-link:hover{text-decoration:underline}

/* ========== Responsive ========== */
@media(max-width:1100px){
  .action-grid{grid-template-columns:repeat(2,1fr)}
}
@media(max-width:960px){
  .dashboard-wrap{flex-direction:column}
  .dashboard-right{width:100%}
  .section-row{flex-direction:column}
  .goal-card{max-width:none}
  .novels-grid{grid-template-columns:repeat(2,1fr)}
  .stats-row{grid-template-columns:repeat(2,1fr)}
}
</style>

<style>
/* ═══ Create Card Overlay (non-scoped for Teleport) ═══ */
.create-overlay{position:fixed;inset:0;background:rgba(15,23,42,.45);backdrop-filter:blur(8px);
  z-index:9998;display:flex;align-items:center;justify-content:center;
  animation:ccFadeIn .2s ease-out;padding:24px}
@keyframes ccFadeIn{from{opacity:0}to{opacity:1}}

.create-card{background:#fff;border-radius:20px;width:560px;max-width:94vw;max-height:90vh;
  display:flex;flex-direction:column;overflow:hidden;
  box-shadow:0 25px 60px -12px rgba(0,0,0,.2),0 0 0 1px rgba(0,0,0,.04);
  animation:ccSlideUp .25s ease-out}
@keyframes ccSlideUp{from{opacity:0;transform:translateY(20px) scale(.98)}to{opacity:1;transform:none}}

/* Header */
.cc-header{display:flex;align-items:center;justify-content:space-between;padding:24px 28px 18px;
  border-bottom:1px solid #f1f5f9}
.cc-header-left{display:flex;align-items:center;gap:14px}
.cc-icon-wrap{width:46px;height:46px;border-radius:14px;
  background:linear-gradient(135deg,#eef2ff,#e0e7ff);
  display:flex;align-items:center;justify-content:center;flex-shrink:0}
.cc-icon{font-size:22px}
.cc-title{font-size:17px;font-weight:700;color:#0f172a;line-height:1.3}
.cc-subtitle{font-size:12px;color:#94a3b8;margin-top:2px}
.cc-close{background:none;border:none;font-size:24px;color:#94a3b8;cursor:pointer;
  width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;
  transition:all .15s;line-height:1;flex-shrink:0}
.cc-close:hover{background:#f1f5f9;color:#334155}

/* Body */
.cc-body{padding:22px 28px;overflow-y:auto;flex:1;min-height:0}
.cc-field{margin-bottom:16px}
.cc-label{display:block;font-size:13px;font-weight:600;color:#475569;margin-bottom:6px}
.cc-required{color:#ef4444;font-weight:400}
.cc-row{display:flex;gap:16px}
.cc-half{flex:1;min-width:0}

.cc-input-row{display:flex;gap:8px}
.cc-input{flex:1;height:40px;padding:0 14px;border:1.5px solid #e2e8f0;border-radius:10px;
  font-size:14px;color:#0f172a;background:#fff;outline:none;transition:all .15s;
  font-family:inherit}
.cc-input:focus{border-color:#818cf8;box-shadow:0 0 0 3px rgba(129,140,248,.15)}
.cc-input::placeholder{color:#cbd5e1}

.cc-ai-btn{flex-shrink:0;height:40px;padding:0 16px;border:1.5px solid #e0e7ff;border-radius:10px;
  background:linear-gradient(135deg,#f5f3ff,#eef2ff);color:#6366f1;font-size:13px;font-weight:600;
  cursor:pointer;transition:all .15s;white-space:nowrap;font-family:inherit}
.cc-ai-btn:hover{border-color:#c7d2fe;background:linear-gradient(135deg,#eef2ff,#e0e7ff);
  transform:translateY(-1px);box-shadow:0 2px 8px rgba(99,102,241,.12)}
.cc-ai-btn:disabled{opacity:.5;cursor:not-allowed;transform:none}

.cc-textarea{width:100%;padding:10px 14px;border:1.5px solid #e2e8f0;border-radius:10px;
  font-size:14px;color:#0f172a;background:#fff;outline:none;transition:all .15s;
  resize:vertical;font-family:inherit;min-height:72px;line-height:1.6}
.cc-textarea:focus{border-color:#818cf8;box-shadow:0 0 0 3px rgba(129,140,248,.15)}
.cc-textarea::placeholder{color:#cbd5e1}

.cc-estimate{display:flex;align-items:center;gap:8px;padding:12px 16px;
  background:linear-gradient(135deg,#f8fafc,#f1f5f9);border:1px solid #e2e8f0;
  border-radius:10px;font-size:13px;color:#64748b;margin-top:4px}
.cc-est-icon{font-size:16px}
.cc-est-value{margin-left:auto;font-size:15px;font-weight:700;color:#6366f1}

/* Footer */
.cc-footer{display:flex;align-items:center;justify-content:flex-end;gap:10px;
  padding:16px 28px 20px;border-top:1px solid #f1f5f9;background:#fafbfc}
.cc-btn-cancel{height:40px;padding:0 22px;border:1.5px solid #e2e8f0;border-radius:10px;
  background:#fff;color:#64748b;font-size:13px;font-weight:500;cursor:pointer;
  transition:all .15s;font-family:inherit}
.cc-btn-cancel:hover{border-color:#cbd5e1;color:#334155;background:#f8fafc}
.cc-btn-create{height:40px;padding:0 28px;border:none;border-radius:10px;
  background:linear-gradient(135deg,#818cf8,#6366f1);color:#fff;font-size:14px;
  font-weight:600;cursor:pointer;transition:all .2s;font-family:inherit;
  box-shadow:0 4px 14px rgba(99,102,241,.25)}
.cc-btn-create:hover{transform:translateY(-1px);box-shadow:0 6px 20px rgba(99,102,241,.35)}
.cc-btn-create:disabled{opacity:.5;cursor:not-allowed;transform:none}

/* Force Naive UI dropdown above the overlay */
.v-binder-follower-container{z-index:99999 !important}

@media(max-width:600px){
  .create-card{width:96vw;border-radius:16px}
  .cc-row{flex-direction:column;gap:0}
  .cc-header{padding:18px 20px 14px}
  .cc-body{padding:16px 20px}
  .cc-footer{padding:14px 20px 16px}
}

/* ═══ Bootstrap overlay (non-scoped for Teleport) ═══ */
.bootstrap-overlay{position:fixed;inset:0;background:rgba(15,23,42,.55);backdrop-filter:blur(6px);
  z-index:9999;display:flex;align-items:center;justify-content:center;animation:bsFadeIn .25s;
  overflow-y:auto;padding:24px}
@keyframes bsFadeIn{from{opacity:0}to{opacity:1}}

.bootstrap-panel{background:#fff;border-radius:20px;width:720px;max-width:94vw;
  box-shadow:0 25px 50px -12px rgba(0,0,0,.25);overflow:hidden;animation:bsSlideUp .3s ease-out;
  max-height:90vh;display:flex;flex-direction:column;transition:width .3s}
.bootstrap-panel.bp-wide{width:900px}
@keyframes bsSlideUp{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:none}}

.bp-header{text-align:center;padding:28px 24px 18px;background:linear-gradient(135deg,#eef2ff,#f5f3ff,#faf5ff);
  flex-shrink:0;position:relative}
.bp-close{position:absolute;top:12px;right:14px;background:none;border:none;font-size:22px;
  color:#94a3b8;cursor:pointer;width:32px;height:32px;border-radius:8px;display:flex;
  align-items:center;justify-content:center;transition:all .15s;line-height:1}
.bp-close:hover{background:#e2e8f0;color:#334155}
.bp-icon-wrap{position:relative;display:inline-flex;align-items:center;justify-content:center;margin-bottom:12px}
.bp-icon{font-size:36px;position:relative;z-index:1}
.bp-icon-pulse{position:absolute;width:58px;height:58px;border-radius:50%;background:#eef2ff;animation:bsPulse 2s infinite}
@keyframes bsPulse{0%{transform:scale(1);opacity:.6}50%{transform:scale(1.3);opacity:0}100%{transform:scale(1);opacity:0}}
.bp-title{font-size:17px;font-weight:700;color:#0f172a;margin:0 0 4px}
.bp-novel-name{font-size:14px;font-weight:600;color:#6366f1;margin:0 0 4px}
.bp-sub{font-size:12px;color:#64748b;margin:0}

/* Regen button */
.bp-regen-btn{background:none;border:1px solid #e2e8f0;border-radius:6px;width:28px;height:28px;
  display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:13px;
  transition:all .15s;flex-shrink:0;margin-left:6px}
.bp-regen-btn:hover{background:#eef2ff;border-color:#c7d2fe;transform:rotate(90deg)}
.bp-regen-btn:disabled{opacity:.4;cursor:not-allowed;transform:none}

/* Body - scrollable */
.bp-body{padding:16px 24px;overflow-y:auto;flex:1;min-height:0}
.bp-section{margin-bottom:16px}
.bp-section:last-child{margin-bottom:0}

/* Stage row */
.bp-stage-row{display:flex;align-items:center;gap:10px;padding:8px 0}
.bp-stage-dot{width:28px;height:28px;border-radius:50%;border:2px solid #e2e8f0;display:flex;
  align-items:center;justify-content:center;flex-shrink:0;background:#fff;transition:all .3s}
.bp-stage-row.done .bp-stage-dot{background:#6366f1;border-color:#6366f1}
.bp-stage-row.running .bp-stage-dot{border-color:#6366f1;background:#eef2ff}
.bp-stage-row.error .bp-stage-dot{border-color:#ef4444;background:#fef2f2}
.dot-check{color:#fff;font-size:13px;font-weight:700}
.dot-err{color:#ef4444;font-size:13px;font-weight:700}
.dot-num{font-size:11px;font-weight:600;color:#94a3b8}
.dot-spin{width:12px;height:12px;border:2px solid #c7d2fe;border-top-color:#6366f1;border-radius:50%;animation:bsSpin .8s linear infinite}
@keyframes bsSpin{to{transform:rotate(360deg)}}
.bp-stage-icon{font-size:15px}
.bp-stage-label{font-size:14px;font-weight:600;color:#334155}
.bp-stage-row.done .bp-stage-label{color:#6366f1}
.bp-stage-row.error .bp-stage-label{color:#ef4444}
.bp-stage-detail{font-size:11px;padding:2px 8px;border-radius:10px;font-weight:500;margin-left:auto}
.bp-stage-detail.done{background:#dcfce7;color:#16a34a}
.bp-stage-detail.running{background:#eef2ff;color:#6366f1}
.bp-stage-detail.error{background:#fee2e2;color:#dc2626}

.bp-stage-bar{height:3px;background:#f1f5f9;border-radius:2px;overflow:hidden;margin:4px 0 8px 38px}
.bp-stage-bar-fill{height:100%;width:60%;background:linear-gradient(90deg,#818cf8,#6366f1);border-radius:2px;
  animation:bsIndeterminate 1.5s ease-in-out infinite}
@keyframes bsIndeterminate{0%{width:10%;margin-left:0}50%{width:60%;margin-left:20%}100%{width:10%;margin-left:90%}}

.bp-error{margin:4px 0 8px 38px;font-size:12px;color:#dc2626;background:#fef2f2;padding:8px 12px;
  border-radius:8px;border:1px solid #fecaca}

/* ── Result containers ── */
.bp-result{margin:4px 0 0 38px;animation:bsFadeIn .3s}

/* World cards */
.bp-result-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}
.bp-world-card{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:10px 12px;
  transition:all .15s}
.bp-world-card:hover{border-color:#c7d2fe;background:#faf5ff}
.bwc-cat{font-size:10px;text-transform:uppercase;color:#94a3b8;font-weight:600;letter-spacing:.5px;margin-bottom:2px}
.bwc-name{font-size:13px;font-weight:600;color:#1e293b;margin-bottom:3px}
.bwc-desc{font-size:11px;color:#64748b;line-height:1.4;display:-webkit-box;-webkit-line-clamp:3;
  -webkit-box-orient:vertical;overflow:hidden}

/* Character cards */
.bp-char-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}
.bp-char-card{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:12px;
  transition:all .15s}
.bp-char-card:hover{border-color:#c7d2fe;background:#faf5ff}
.bcc-top{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.bcc-avatar{width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,#818cf8,#6366f1);
  color:#fff;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;flex-shrink:0}
.bcc-info{display:flex;flex-direction:column;gap:1px;min-width:0}
.bcc-name{font-size:14px;font-weight:600;color:#1e293b}
.bcc-role{font-size:10px;padding:1px 6px;border-radius:6px;font-weight:600;display:inline-block;width:fit-content}
.role-protagonist{background:#dbeafe;color:#2563eb}
.role-antagonist{background:#fee2e2;color:#dc2626}
.role-supporting{background:#f1f5f9;color:#64748b}
.role-mentor{background:#fef3c7;color:#d97706}
.role-love{background:#fce7f3;color:#db2777}
.bcc-desc{font-size:11px;color:#64748b;line-height:1.4;margin-bottom:6px}
.bcc-traits{display:flex;flex-wrap:wrap;gap:4px}
.bcc-tag{font-size:10px;padding:2px 7px;border-radius:6px;background:#eef2ff;color:#6366f1;font-weight:500}

/* Outline tree */
.bp-outline-tree{display:flex;flex-direction:column;gap:10px}
.bp-vol{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:12px 14px;
  transition:all .15s}
.bp-vol:hover{border-color:#c7d2fe}
.bpv-head{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.bpv-badge{font-size:10px;padding:2px 8px;border-radius:6px;background:#6366f1;color:#fff;font-weight:700}
.bpv-title{font-size:14px;font-weight:600;color:#1e293b}
.bpv-range{font-size:10px;color:#94a3b8;margin-left:auto}
.bpv-summary{font-size:11px;color:#64748b;line-height:1.4;margin-bottom:6px}
.bpv-chapters{display:flex;flex-direction:column;gap:3px}
.bpv-ch{display:flex;align-items:baseline;gap:6px;font-size:12px;padding:2px 0}
.bpv-ch-num{color:#94a3b8;font-weight:600;flex-shrink:0;width:20px}
.bpv-ch-title{color:#334155;font-weight:500}
.bpv-ch-sum{color:#94a3b8;font-size:11px;margin-left:4px;flex:1;min-width:0;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.bpv-more{font-size:11px;color:#94a3b8;padding:4px 0;font-style:italic}

/* Footer */
.bp-footer{padding:16px 24px 20px;text-align:center;flex-shrink:0;
  border-top:1px solid #f1f5f9;background:#fafbfc}
.btn-ghost-sm{font-size:12px;color:#94a3b8;background:none;border:1px solid #e2e8f0;border-radius:8px;
  padding:7px 18px;cursor:pointer;transition:all .15s}
.btn-ghost-sm:hover{background:#f8fafc;color:#64748b;border-color:#cbd5e1}
.btn-primary-lg{font-size:14px;font-weight:600;color:#fff;background:linear-gradient(135deg,#818cf8,#6366f1);
  border:none;border-radius:10px;padding:12px 32px;cursor:pointer;transition:all .2s;
  box-shadow:0 4px 14px rgba(99,102,241,.3)}
.btn-primary-lg:hover{transform:translateY(-1px);box-shadow:0 6px 20px rgba(99,102,241,.4)}

/* ── Prediction panel ── */
.bp-predict{padding:0 24px 16px;animation:bsFadeIn .3s}
.bp-predict-head{display:flex;align-items:center;gap:8px;margin-bottom:12px;padding:10px 14px;
  background:linear-gradient(135deg,#eef2ff,#f0fdf4);border-radius:10px;border:1px solid #e0e7ff}
.bp-predict-icon{font-size:18px}
.bp-predict-title{font-size:14px;font-weight:600;color:#1e293b}
.bp-predict-loading{font-size:11px;color:#6366f1;margin-left:auto;animation:bsPulse 1.5s infinite}
.bp-predict-skeleton{padding:0 14px}
.bp-skel-bar{height:10px;background:#f1f5f9;border-radius:5px;margin-bottom:8px;
  animation:bsSkelShimmer 1.2s infinite}
.bp-skel-bar.short{width:60%}
@keyframes bsSkelShimmer{0%{opacity:.6}50%{opacity:1}100%{opacity:.6}}

.bp-predict-body{padding:0 4px}
.bp-predict-score-row{display:flex;align-items:center;gap:16px;margin-bottom:12px}
.bp-predict-score{display:flex;flex-direction:column;align-items:center;justify-content:center;
  width:80px;height:80px;border-radius:50%;border:3px solid #e2e8f0;flex-shrink:0}
.bp-predict-score.high{border-color:#22c55e;background:#f0fdf4}
.bp-predict-score.mid{border-color:#f59e0b;background:#fffbeb}
.bp-predict-score.low{border-color:#ef4444;background:#fef2f2}
.bps-num{font-size:24px;font-weight:800;color:#1e293b;line-height:1}
.bp-predict-score.high .bps-num{color:#16a34a}
.bp-predict-score.mid .bps-num{color:#d97706}
.bp-predict-score.low .bps-num{color:#dc2626}
.bps-label{font-size:10px;color:#64748b;margin-top:2px}
.bp-predict-metrics{display:grid;grid-template-columns:1fr 1fr;gap:8px;flex:1}
.bpm-item{display:flex;flex-direction:column;padding:8px 12px;background:#f8fafc;
  border-radius:8px;border:1px solid #f1f5f9}
.bpm-label{font-size:10px;color:#94a3b8;margin-bottom:2px}
.bpm-val{font-size:13px;font-weight:600;color:#334155}

.bp-predict-section{margin-bottom:10px}
.bps-title{font-size:12px;font-weight:600;color:#475569;margin-bottom:4px}
.bps-list{margin:0;padding-left:18px;font-size:11px;line-height:1.7;color:#64748b}
.bps-list.warn li::marker{color:#f59e0b}
.bps-list.suggest li::marker{color:#6366f1}
.bp-predict-hint{font-size:11px;color:#64748b;padding:6px 10px;background:#f8fafc;border-radius:6px;
  border:1px solid #f1f5f9}

/* ── Title Optimizer ── */
.title-opt-box{margin:-8px 0 12px;padding:12px;background:#fefce8;border:1px solid #fde68a;
  border-radius:10px;animation:bsFadeIn .3s}
.to-diagnosis{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.to-score{font-size:18px;font-weight:800;color:#d97706;flex-shrink:0}
.to-diag{font-size:12px;color:#92400e;line-height:1.5}
.to-dims{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap}
.to-dim{font-size:11px;padding:3px 8px;border-radius:6px;font-weight:500}
.to-dim.ok{background:#dcfce7;color:#16a34a}
.to-dim.miss{background:#fee2e2;color:#dc2626}
.to-candidates{display:flex;flex-direction:column;gap:6px}
.to-cand{padding:8px 12px;background:#fff;border:1px solid #fde68a;border-radius:8px;
  cursor:pointer;transition:all .15s}
.to-cand:hover{border-color:#6366f1;background:#eef2ff;transform:translateX(2px)}
.to-cand-head{display:flex;align-items:center;justify-content:space-between}
.to-cand-title{font-size:13px;font-weight:600;color:#1e293b}
.to-cand-score{font-size:12px;font-weight:700;color:#6366f1;flex-shrink:0}
.to-cand-reason{font-size:11px;color:#64748b;margin-top:2px;line-height:1.4}

@media(max-width:600px){
  .bootstrap-panel{width:96vw}
  .bootstrap-panel.bp-wide{width:96vw}
  .bp-result-grid,.bp-char-list{grid-template-columns:1fr}
  .bp-predict-score-row{flex-direction:column;align-items:stretch}
  .bp-predict-metrics{grid-template-columns:1fr 1fr}
}
</style>
