<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useNovelsStore } from '@/stores/novels'

const router = useRouter()
const store = useNovelsStore()

// ── Steps ──
const steps = [
  { key: 'base', num: 1, label: '基础赛道' },
  { key: 'character', num: 2, label: '角色与动力' },
  { key: 'world', num: 3, label: '世界与对抗' },
  { key: 'plot', num: 4, label: '剧情与导航' },
  { key: 'confirm', num: 5, label: '确认' },
]
const currentStep = ref(1)

// ── Form data ──
const form = reactive({
  // Step 1
  title: '',
  synopsis: '',
  mcName: '',
  hook: '',
  channel: '男频' as '男频' | '女频',
  genre: '',
  subGenre: [] as string[],
  lengthTier: 'long' as 'short' | 'mid' | 'long' | 'ultra',
  // Step 2
  mcPersonality: '',
  mcMotivation: '',
  goldenFinger: '',
  antagonistType: '',
  // Step 3
  worldPreset: '',
  powerSystem: '',
  coreConflict: '',
  // Step 4
  openingHook: '',
  pacingStyle: '',
  plotNotes: '',
})

// ── Options ──
const channelOptions = [
  { label: '男频', value: '男频', desc: '主流男性向力作，侧重打怪升级、逆袭爽感爽感的创作路线' },
  { label: '女频', value: '女频', desc: '更强调关系角力、情感交叉、细腻流淌的创作路线' },
]

const genreMap: Record<string, { label: string; value: string }[]> = {
  '男频': [
    { label: '玄幻', value: '玄幻' }, { label: '仙侠', value: '仙侠' },
    { label: '武侠', value: '武侠' }, { label: '东方玄幻', value: '东方玄幻' },
    { label: '异世大陆', value: '异世大陆' }, { label: '高武世界', value: '高武世界' },
    { label: '都市', value: '都市' }, { label: '科幻', value: '科幻' },
    { label: '奇幻', value: '奇幻' }, { label: '军事', value: '军事' },
    { label: '游戏', value: '游戏' }, { label: '历史', value: '历史' },
    { label: '悬疑', value: '悬疑' }, { label: '末世', value: '末世' },
  ],
  '女频': [
    { label: '古代言情', value: '古代言情' }, { label: '现代言情', value: '现代言情' },
    { label: '仙侠奇缘', value: '仙侠奇缘' }, { label: '宫斗权谋', value: '宫斗权谋' },
    { label: '穿越重生', value: '穿越重生' }, { label: '甜宠', value: '甜宠' },
    { label: '豪门总裁', value: '豪门总裁' }, { label: '校园青春', value: '校园青春' },
    { label: '种田基建', value: '种田基建' }, { label: '星际', value: '星际' },
  ],
}
const genreOptions = computed(() => genreMap[form.channel] || genreMap['男频'])

const subGenreOptions = [
  '重生', '穿越', '系统', '无敌流', '升级流', '退婚流', '赘婿', '战神', '医神', '鉴宝',
  '甜宠', '虐恋', '豪门', '总裁', '校园', '宫斗', '种田', '星际', '修仙', '妖族',
  '炼丹', '阵法', '神豪', '黑科技', '诸天', '无限流', '直播', '电竞', '热血', '搞笑',
  '治愈', '暗黑', '悬疑推理', '商战', '娱乐圈', '体育', '美食',
].map(t => ({ label: t, value: t }))

const lengthTiers = [
  { value: 'short', title: '短篇', range: '10~20章', words: '3~10万字' },
  { value: 'mid', title: '中篇', range: '30~100章', words: '10~30万字' },
  { value: 'long', title: '长篇', range: '100~300章', words: '30~100万字' },
  { value: 'ultra', title: '超长篇', range: '300+章', words: '100万字以上' },
]
const lengthConfig: Record<string, { chapters: number; wpc: number }> = {
  short: { chapters: 15, wpc: 3000 },
  mid: { chapters: 60, wpc: 2500 },
  long: { chapters: 200, wpc: 2000 },
  ultra: { chapters: 500, wpc: 2000 },
}

const worldPresets = [
  '东方玄幻大陆', '九州仙侠世界', '现代都市异能', '末世废土', '星际文明',
  '古代架空王朝', '西方魔法大陆', '赛博朋克', '武侠江湖', '洪荒神话',
  '灵气复苏现代', '副本/无限流', '游戏世界', '自定义',
]

const personalityOptions = [
  '隐忍坚韧型', '热血冲动型', '腹黑算计型', '佛系随缘型', '冷酷无情型',
  '痞气幽默型', '温柔治愈型', '疯批偏执型',
]

const motivationOptions = [
  '复仇/报恩', '守护家人', '追求极致力量', '探索世界真相', '称霸天下',
  '回到过去', '活下去', '寻找失踪之人', '证明自我价值',
]

const goldenFingerOptions = [
  '系统', '空间', '重生记忆', '特殊体质', '神秘传承', '签到', '模拟器',
  '时间回溯', '复制能力', '无',
]

const antagonistOptions = [
  '同辈天才', '腐朽家族', '邪恶组织', '远古存在', '人心险恶', '天道/规则',
  '内心魔障', '末世怪物',
]

const pacingOptions = [
  { label: '爽文节奏', desc: '快速升级、密集爽点、一路碾压' },
  { label: '稳扎稳打', desc: '逻辑严密、步步为营、张弛有度' },
  { label: '慢热渐进', desc: '前期铺垫、中期爆发、后期收割' },
  { label: '悬疑推进', desc: '层层谜团、反转不断、烧脑剧情' },
]

// ── Navigation ──
function nextStep() { if (currentStep.value < 5) currentStep.value++ }
function prevStep() { if (currentStep.value > 1) currentStep.value-- }

// ── Computed ──
const estimatedWords = computed(() => {
  const c = lengthConfig[form.lengthTier]
  return ((c?.chapters || 200) * (c?.wpc || 2000)).toLocaleString()
})

const summaryItems = computed(() => {
  const items: { label: string; value: string }[] = []
  if (form.title) items.push({ label: '书名', value: form.title })
  items.push({ label: '频道', value: form.channel })
  if (form.genre) items.push({ label: '类型', value: form.genre })
  if (form.subGenre.length) items.push({ label: '流派', value: form.subGenre.join('、') })
  const lt = lengthTiers.find(t => t.value === form.lengthTier)
  if (lt) items.push({ label: '篇幅', value: `${lt.title} ${lt.words}` })
  if (form.mcName) items.push({ label: '主角', value: form.mcName })
  if (form.hook) items.push({ label: '卖点', value: form.hook })
  if (form.mcPersonality) items.push({ label: '性格', value: form.mcPersonality })
  if (form.mcMotivation) items.push({ label: '动机', value: form.mcMotivation })
  if (form.goldenFinger) items.push({ label: '金手指', value: form.goldenFinger })
  if (form.antagonistType) items.push({ label: '对抗', value: form.antagonistType })
  if (form.worldPreset) items.push({ label: '世界观', value: form.worldPreset })
  if (form.powerSystem) items.push({ label: '力量体系', value: form.powerSystem })
  if (form.pacingStyle) items.push({ label: '节奏', value: form.pacingStyle })
  return items
})

// ── Create ──
const creating = ref(false)
const createError = ref('')
const bootstrapping = ref(false)
const bootstrapDone = ref(false)
const bootstrapNovelId = ref('')
const bootstrapStages = ref<{ key: string; label: string; status: string; detail: string }[]>([])
let bootstrapSSE: EventSource | null = null

function buildPremise(): string {
  const parts: string[] = []
  if (form.hook) parts.push(`【核心卖点】${form.hook}`)
  if (form.mcName) parts.push(`【主角】${form.mcName}`)
  if (form.mcPersonality) parts.push(`【性格】${form.mcPersonality}`)
  if (form.mcMotivation) parts.push(`【动机】${form.mcMotivation}`)
  if (form.goldenFinger && form.goldenFinger !== '无') parts.push(`【金手指】${form.goldenFinger}`)
  if (form.antagonistType) parts.push(`【对抗力量】${form.antagonistType}`)
  if (form.coreConflict) parts.push(`【核心冲突】${form.coreConflict}`)
  if (form.openingHook) parts.push(`【开篇钩子】${form.openingHook}`)
  if (form.pacingStyle) parts.push(`【节奏风格】${form.pacingStyle}`)
  if (form.plotNotes) parts.push(`【剧情备注】${form.plotNotes}`)
  return parts.join('\n')
}

function buildWorldSetting(): string {
  const parts: string[] = []
  if (form.worldPreset) parts.push(`世界观基调：${form.worldPreset}`)
  if (form.powerSystem) parts.push(`力量体系：${form.powerSystem}`)
  return parts.join('\n')
}

async function handleCreate() {
  if (!form.title.trim()) { createError.value = '请输入书名'; return }
  creating.value = true
  createError.value = ''
  try {
    const cfg = lengthConfig[form.lengthTier]
    const novel = await store.createNovel({
      title: form.title.trim(),
      genre: form.genre,
      tags: form.subGenre,
      synopsis: form.synopsis,
      premise: buildPremise(),
      world_setting: buildWorldSetting(),
      target_chapter_count: cfg.chapters,
      words_per_chapter: cfg.wpc,
      target_word_count: cfg.chapters * cfg.wpc,
    })
    bootstrapNovelId.value = novel.id
    bootstrapStages.value = [
      { key: 'world', label: '世界观设定', status: 'pending', detail: '' },
      { key: 'characters', label: '核心人物', status: 'pending', detail: '' },
      { key: 'outline', label: '宏观大纲', status: 'pending', detail: '' },
    ]
    bootstrapping.value = true
    startBootstrap(novel.id)
  } catch (e: any) {
    createError.value = e.message || '创建失败'
  } finally {
    creating.value = false
  }
}

function setStage(key: string, status: string, detail = '') {
  const s = bootstrapStages.value.find(s => s.key === key)
  if (s) { s.status = status; if (detail) s.detail = detail }
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
        return
      }
      if (d.status === 'start') setStage(d.stage, 'running', '生成中…')
      else if (d.status === 'done') {
        const count = d.saved_count ? `${d.saved_count}条` : '✓'
        setStage(d.stage, 'done', count)
      } else if (d.status === 'error') setStage(d.stage, 'error', d.message || '失败')
    } catch { /* ignore */ }
  }
  bootstrapSSE.onerror = () => { bootstrapSSE?.close(); bootstrapDone.value = true }
}

function goStudio() {
  if (bootstrapNovelId.value) {
    router.push({ path: '/studio', query: { novelId: bootstrapNovelId.value } })
  }
}

function goBack() { router.push('/dashboard') }
</script>

<template>
  <div class="wiz-page">
    <!-- Header -->
    <div class="wiz-header">
      <button class="wiz-back" @click="goBack">← 返回</button>
      <h1 class="wiz-title">创建新作品</h1>
    </div>

    <!-- Steps Bar -->
    <div class="wiz-steps">
      <div
        v-for="s in steps" :key="s.num"
        class="wiz-step"
        :class="{ active: currentStep === s.num, done: currentStep > s.num }"
        @click="s.num < currentStep ? currentStep = s.num : null"
      >
        <span class="step-num" v-if="currentStep <= s.num">{{ s.num }}</span>
        <span class="step-check" v-else>✓</span>
        <span class="step-label">{{ s.label }}</span>
      </div>
    </div>

    <div class="wiz-body" v-if="!bootstrapping">
      <div class="wiz-main">

        <!-- ═══ Step 1: 基础赛道 ═══ -->
        <div v-if="currentStep === 1" class="step-content">
          <h2 class="sec-title">基础赛道</h2>
          <p class="sec-desc">选择作品的市场定位与类型</p>

          <div class="field">
            <label>书名（可选，留空由 AI 生成）</label>
            <input v-model="form.title" placeholder="有明确书名直接填写，留空则由 AI 生成" class="input-dark" />
          </div>

          <div class="field">
            <label>简介（可选，留空由 AI 生成）</label>
            <textarea v-model="form.synopsis" placeholder="有明确主线构思直接填写，留空则由 AI 生成" class="input-dark textarea" rows="3" />
          </div>

          <div class="field-row">
            <div class="field half">
              <label>主角名字（可选，留空由 AI 生成）</label>
              <input v-model="form.mcName" placeholder="有明确角色名直接填写" class="input-dark" />
            </div>
            <div class="field half">
              <label>一句话卖点（可选，留空由 AI 生成）</label>
              <input v-model="form.hook" placeholder="有明确卖点直接填写，留空则由 AI 生成" class="input-dark" />
            </div>
          </div>

          <div class="field">
            <label>频道分类 *</label>
            <div class="channel-cards">
              <div
                v-for="ch in channelOptions" :key="ch.value"
                class="channel-card"
                :class="{ active: form.channel === ch.value }"
                @click="form.channel = ch.value as any; form.genre = ''; form.subGenre = []"
              >
                <strong>{{ ch.label }}</strong>
                <p>{{ ch.desc }}</p>
              </div>
            </div>
          </div>

          <div class="field">
            <label>一级类目 *</label>
            <div class="tag-grid">
              <button
                v-for="g in genreOptions" :key="g.value"
                class="tag-btn" :class="{ active: form.genre === g.value }"
                @click="form.genre = g.value"
              >{{ g.label }}</button>
            </div>
          </div>

          <div class="field">
            <label>辅分流派</label>
            <div class="tag-grid">
              <button
                v-for="sg in subGenreOptions" :key="sg.value"
                class="tag-btn sm" :class="{ active: form.subGenre.includes(sg.value) }"
                @click="form.subGenre.includes(sg.value) ? form.subGenre = form.subGenre.filter(x => x !== sg.value) : form.subGenre.length < 5 && form.subGenre.push(sg.value)"
              >{{ sg.label }}</button>
            </div>
          </div>

          <div class="field">
            <label>篇幅预估</label>
            <div class="length-cards">
              <div
                v-for="lt in lengthTiers" :key="lt.value"
                class="length-card" :class="{ active: form.lengthTier === lt.value }"
                @click="form.lengthTier = lt.value as any"
              >
                <div class="lc-title">{{ lt.title }}</div>
                <div class="lc-range">{{ lt.range }}</div>
                <div class="lc-words">{{ lt.words }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- ═══ Step 2: 角色与动力 ═══ -->
        <div v-if="currentStep === 2" class="step-content">
          <h2 class="sec-title">角色与动力</h2>
          <p class="sec-desc">设定主角的内核和故事驱动力</p>

          <div class="field">
            <label>主角性格类型</label>
            <div class="tag-grid">
              <button
                v-for="p in personalityOptions" :key="p"
                class="tag-btn" :class="{ active: form.mcPersonality === p }"
                @click="form.mcPersonality = form.mcPersonality === p ? '' : p"
              >{{ p }}</button>
            </div>
          </div>

          <div class="field">
            <label>核心动机</label>
            <div class="tag-grid">
              <button
                v-for="m in motivationOptions" :key="m"
                class="tag-btn" :class="{ active: form.mcMotivation === m }"
                @click="form.mcMotivation = form.mcMotivation === m ? '' : m"
              >{{ m }}</button>
            </div>
          </div>

          <div class="field">
            <label>金手指 / 外挂设定</label>
            <div class="tag-grid">
              <button
                v-for="g in goldenFingerOptions" :key="g"
                class="tag-btn" :class="{ active: form.goldenFinger === g }"
                @click="form.goldenFinger = form.goldenFinger === g ? '' : g"
              >{{ g }}</button>
            </div>
          </div>

          <div class="field">
            <label>主要对抗力量</label>
            <div class="tag-grid">
              <button
                v-for="a in antagonistOptions" :key="a"
                class="tag-btn" :class="{ active: form.antagonistType === a }"
                @click="form.antagonistType = form.antagonistType === a ? '' : a"
              >{{ a }}</button>
            </div>
          </div>
        </div>

        <!-- ═══ Step 3: 世界与对抗 ═══ -->
        <div v-if="currentStep === 3" class="step-content">
          <h2 class="sec-title">世界与对抗</h2>
          <p class="sec-desc">构建故事发生的舞台</p>

          <div class="field">
            <label>世界观模板</label>
            <div class="tag-grid">
              <button
                v-for="w in worldPresets" :key="w"
                class="tag-btn" :class="{ active: form.worldPreset === w }"
                @click="form.worldPreset = form.worldPreset === w ? '' : w"
              >{{ w }}</button>
            </div>
          </div>

          <div class="field">
            <label>力量体系描述（可选）</label>
            <textarea v-model="form.powerSystem" class="input-dark textarea" rows="3"
              placeholder="如：灵气修炼体系，分炼气、筑基、金丹、元婴四大境界，每个境界分初中后期…" />
          </div>

          <div class="field">
            <label>核心冲突（可选）</label>
            <textarea v-model="form.coreConflict" class="input-dark textarea" rows="3"
              placeholder="故事最根本的矛盾是什么？如：主角的恩赐者身份是被世界排斥的存在…" />
          </div>
        </div>

        <!-- ═══ Step 4: 剧情与导航 ═══ -->
        <div v-if="currentStep === 4" class="step-content">
          <h2 class="sec-title">剧情与导航</h2>
          <p class="sec-desc">设定故事的开篇和节奏风格</p>

          <div class="field">
            <label>开篇钩子（可选）</label>
            <textarea v-model="form.openingHook" class="input-dark textarea" rows="3"
              placeholder="第一章要抓住读者的场景或悬念，如：主角在万人面前被宣布为废物，却意外觉醒了…" />
          </div>

          <div class="field">
            <label>节奏风格</label>
            <div class="pacing-cards">
              <div
                v-for="p in pacingOptions" :key="p.label"
                class="pacing-card" :class="{ active: form.pacingStyle === p.label }"
                @click="form.pacingStyle = form.pacingStyle === p.label ? '' : p.label"
              >
                <strong>{{ p.label }}</strong>
                <p>{{ p.desc }}</p>
              </div>
            </div>
          </div>

          <div class="field">
            <label>其他剧情备注（可选）</label>
            <textarea v-model="form.plotNotes" class="input-dark textarea" rows="4"
              placeholder="任何你想告诉 AI 的额外信息：特殊设定、必须出现的桥段、风格偏好等…" />
          </div>
        </div>

        <!-- ═══ Step 5: 确认 ═══ -->
        <div v-if="currentStep === 5" class="step-content">
          <h2 class="sec-title">确认创建</h2>
          <p class="sec-desc">检查设定，一键开始创作</p>

          <div class="confirm-grid">
            <div v-for="item in summaryItems" :key="item.label" class="confirm-item">
              <span class="ci-label">{{ item.label }}</span>
              <span class="ci-value">{{ item.value }}</span>
            </div>
            <div class="confirm-item highlight">
              <span class="ci-label">预计总字数</span>
              <span class="ci-value">{{ estimatedWords }} 字</span>
            </div>
          </div>

          <div v-if="createError" class="wiz-error">{{ createError }}</div>

          <div class="confirm-tip">
            点击「开始创作」后，AI 将自动生成世界观、人物和大纲，你可以随时在创作台修改。
          </div>
        </div>

        <!-- Footer -->
        <div class="wiz-footer">
          <button v-if="currentStep > 1" class="btn-ghost-dark" @click="prevStep">上一步</button>
          <div class="flex-grow"></div>
          <button v-if="currentStep < 5" class="btn-primary-dark" @click="nextStep">
            下一步 →
          </button>
          <button v-if="currentStep === 5" class="btn-primary-dark create-btn" :disabled="creating" @click="handleCreate">
            {{ creating ? '创建中…' : '开始创作' }}
          </button>
        </div>
      </div>

      <!-- ═══ Right Sidebar: Config Summary ═══ -->
      <div class="wiz-sidebar">
        <div class="sidebar-card">
          <h3 class="sb-title">配置摘要</h3>
          <div class="sb-badges">
            <span class="sb-badge" :class="form.channel === '男频' ? 'male' : 'female'">{{ form.channel }}</span>
            <span v-if="form.genre" class="sb-badge genre">{{ form.genre }}</span>
            <span v-for="sg in form.subGenre" :key="sg" class="sb-badge sub">{{ sg }}</span>
          </div>
          <div class="sb-list">
            <div class="sb-row" v-if="form.title"><span class="sb-k">书名</span><span class="sb-v">{{ form.title }}</span></div>
            <div class="sb-row" v-if="form.mcName"><span class="sb-k">主角</span><span class="sb-v">{{ form.mcName }}</span></div>
            <div class="sb-row" v-if="form.hook"><span class="sb-k">卖点</span><span class="sb-v line-clamp">{{ form.hook }}</span></div>
            <div class="sb-row"><span class="sb-k">篇幅</span><span class="sb-v">{{ lengthTiers.find(t => t.value === form.lengthTier)?.title }} {{ lengthTiers.find(t => t.value === form.lengthTier)?.words }}</span></div>
            <div class="sb-row" v-if="form.mcPersonality"><span class="sb-k">性格</span><span class="sb-v">{{ form.mcPersonality }}</span></div>
            <div class="sb-row" v-if="form.mcMotivation"><span class="sb-k">动机</span><span class="sb-v">{{ form.mcMotivation }}</span></div>
            <div class="sb-row" v-if="form.goldenFinger"><span class="sb-k">金手指</span><span class="sb-v">{{ form.goldenFinger }}</span></div>
            <div class="sb-row" v-if="form.antagonistType"><span class="sb-k">对抗</span><span class="sb-v">{{ form.antagonistType }}</span></div>
            <div class="sb-row" v-if="form.worldPreset"><span class="sb-k">世界观</span><span class="sb-v">{{ form.worldPreset }}</span></div>
            <div class="sb-row" v-if="form.powerSystem"><span class="sb-k">体系</span><span class="sb-v line-clamp">{{ form.powerSystem }}</span></div>
            <div class="sb-row" v-if="form.pacingStyle"><span class="sb-k">节奏</span><span class="sb-v">{{ form.pacingStyle }}</span></div>
          </div>
          <div class="sb-footer">
            <div class="sb-est">约 {{ estimatedWords }} 字</div>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ Bootstrap Overlay ═══ -->
    <div v-if="bootstrapping" class="wiz-bootstrap">
      <div class="bs-panel">
        <div class="bs-icon">{{ bootstrapDone ? '✅' : '🚀' }}</div>
        <h3>{{ bootstrapDone ? '初始化完成' : '正在初始化作品…' }}</h3>
        <p class="bs-novel">《{{ form.title || '新作品' }}》</p>

        <div class="bs-stages">
          <div v-for="s in bootstrapStages" :key="s.key" class="bs-stage" :class="s.status">
            <span class="bs-dot">
              <span v-if="s.status === 'done'" class="dot-ok">✓</span>
              <span v-else-if="s.status === 'running'" class="dot-spin"></span>
              <span v-else-if="s.status === 'error'" class="dot-err">!</span>
              <span v-else class="dot-num">·</span>
            </span>
            <span class="bs-label">{{ s.label }}</span>
            <span v-if="s.detail" class="bs-detail" :class="s.status">{{ s.detail }}</span>
          </div>
        </div>

        <div v-if="bootstrapDone" class="bs-actions">
          <button class="btn-ghost-dark" @click="goBack">返回仪表盘</button>
          <button class="btn-primary-dark" @click="goStudio">进入创作台 →</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wiz-page{
  min-height:100vh;background:#0c0e14;color:#c8ccd4;
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans SC",sans-serif;
}

/* ── Header ── */
.wiz-header{display:flex;align-items:center;gap:16px;padding:20px 32px 0}
.wiz-back{background:none;border:1px solid #2a2e38;border-radius:8px;padding:6px 14px;
  color:#8b8f9a;font-size:13px;cursor:pointer;transition:all .15s}
.wiz-back:hover{border-color:#4f46e5;color:#a5b4fc}
.wiz-title{font-size:20px;font-weight:700;color:#e2e4e9}

/* ── Steps ── */
.wiz-steps{display:flex;align-items:center;gap:8px;padding:20px 32px;justify-content:center}
.wiz-step{display:flex;align-items:center;gap:8px;padding:8px 20px;border-radius:20px;
  background:#181a22;border:1px solid #2a2e38;cursor:default;transition:all .2s;font-size:13px}
.wiz-step.active{background:#1e1b4b;border-color:#4f46e5;color:#a5b4fc}
.wiz-step.done{border-color:#22c55e44;color:#4ade80;cursor:pointer}
.step-num{width:22px;height:22px;border-radius:50%;background:#2a2e38;display:flex;
  align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#8b8f9a}
.wiz-step.active .step-num{background:#4f46e5;color:#fff}
.step-check{color:#4ade80;font-weight:700;font-size:14px}
.step-label{font-weight:500}

/* ── Body layout ── */
.wiz-body{display:flex;gap:24px;padding:0 32px 32px;max-width:1200px;margin:0 auto}
.wiz-main{flex:1;min-width:0}
.wiz-sidebar{width:280px;flex-shrink:0}

/* ── Section titles ── */
.sec-title{font-size:18px;font-weight:700;color:#e2e4e9;margin-bottom:4px}
.sec-desc{font-size:13px;color:#6b7080;margin-bottom:20px}

/* ── Fields ── */
.field{margin-bottom:18px}
.field label{display:block;font-size:13px;font-weight:500;color:#8b8f9a;margin-bottom:6px}
.field-row{display:flex;gap:16px}
.field.half{flex:1}
.input-dark{width:100%;background:#181a22;border:1px solid #2a2e38;border-radius:8px;
  padding:10px 14px;color:#e2e4e9;font-size:14px;outline:none;transition:border-color .15s}
.input-dark:focus{border-color:#4f46e5}
.input-dark::placeholder{color:#4a4e5a}
.textarea{resize:vertical;font-family:inherit;min-height:60px}

/* ── Channel cards ── */
.channel-cards{display:flex;gap:12px}
.channel-card{flex:1;padding:14px 18px;background:#181a22;border:1px solid #2a2e38;border-radius:10px;
  cursor:pointer;transition:all .15s}
.channel-card:hover{border-color:#4f46e5}
.channel-card.active{border-color:#4f46e5;background:#1e1b4b}
.channel-card strong{color:#e2e4e9;font-size:14px;display:block;margin-bottom:4px}
.channel-card p{color:#6b7080;font-size:12px;margin:0;line-height:1.5}

/* ── Tag grid ── */
.tag-grid{display:flex;flex-wrap:wrap;gap:8px}
.tag-btn{padding:6px 16px;border-radius:8px;border:1px solid #2a2e38;background:#181a22;
  color:#8b8f9a;font-size:13px;cursor:pointer;transition:all .15s;white-space:nowrap}
.tag-btn:hover{border-color:#4f46e5;color:#a5b4fc}
.tag-btn.active{border-color:#4f46e5;background:#1e1b4b;color:#a5b4fc}
.tag-btn.sm{padding:4px 12px;font-size:12px}

/* ── Length cards ── */
.length-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.length-card{padding:16px;background:#181a22;border:1px solid #2a2e38;border-radius:10px;
  cursor:pointer;transition:all .15s;text-align:center}
.length-card:hover{border-color:#4f46e5}
.length-card.active{border-color:#4f46e5;background:#1e1b4b}
.lc-title{font-size:15px;font-weight:700;color:#e2e4e9;margin-bottom:4px}
.lc-range{font-size:12px;color:#6b7080}
.lc-words{font-size:11px;color:#4f46e5;margin-top:2px}

/* ── Pacing cards ── */
.pacing-cards{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.pacing-card{padding:14px 18px;background:#181a22;border:1px solid #2a2e38;border-radius:10px;
  cursor:pointer;transition:all .15s}
.pacing-card:hover{border-color:#4f46e5}
.pacing-card.active{border-color:#4f46e5;background:#1e1b4b}
.pacing-card strong{color:#e2e4e9;font-size:13px;display:block;margin-bottom:4px}
.pacing-card p{color:#6b7080;font-size:12px;margin:0;line-height:1.5}

/* ── Confirm ── */
.confirm-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px}
.confirm-item{display:flex;justify-content:space-between;padding:10px 14px;
  background:#181a22;border:1px solid #2a2e38;border-radius:8px}
.confirm-item.highlight{grid-column:span 2;border-color:#4f46e5;background:#1e1b4b}
.ci-label{font-size:12px;color:#6b7080}
.ci-value{font-size:13px;color:#e2e4e9;font-weight:500;text-align:right;max-width:60%;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.confirm-item.highlight .ci-value{color:#a5b4fc;font-weight:700}
.confirm-tip{font-size:12px;color:#6b7080;padding:12px;background:#181a22;border-radius:8px;
  line-height:1.7;border:1px dashed #2a2e38}
.wiz-error{color:#ef4444;font-size:13px;padding:8px 12px;background:#1c1012;border:1px solid #7f1d1d;
  border-radius:8px;margin-bottom:12px}

/* ── Footer ── */
.wiz-footer{display:flex;align-items:center;gap:12px;padding:20px 0;margin-top:8px;
  border-top:1px solid #1e2028}
.flex-grow{flex:1}
.btn-ghost-dark{padding:10px 24px;border-radius:8px;border:1px solid #2a2e38;background:none;
  color:#8b8f9a;font-size:13px;cursor:pointer;transition:all .15s;font-weight:500}
.btn-ghost-dark:hover{border-color:#4f46e5;color:#a5b4fc}
.btn-primary-dark{padding:10px 28px;border-radius:8px;border:none;
  background:linear-gradient(135deg,#818cf8,#4f46e5);color:#fff;font-size:13px;
  cursor:pointer;transition:all .2s;font-weight:600;box-shadow:0 4px 14px rgba(79,70,229,.3)}
.btn-primary-dark:hover{transform:translateY(-1px);box-shadow:0 6px 20px rgba(79,70,229,.4)}
.btn-primary-dark:disabled{opacity:.5;cursor:not-allowed;transform:none}
.create-btn{padding:12px 36px;font-size:14px}

/* ── Sidebar ── */
.sidebar-card{background:#181a22;border:1px solid #2a2e38;border-radius:12px;padding:18px;
  position:sticky;top:24px}
.sb-title{font-size:14px;font-weight:600;color:#e2e4e9;margin-bottom:12px}
.sb-badges{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}
.sb-badge{padding:3px 10px;border-radius:6px;font-size:11px;font-weight:600}
.sb-badge.male{background:#1e3a5f;color:#60a5fa}
.sb-badge.female{background:#4a1942;color:#f472b6}
.sb-badge.genre{background:#1e1b4b;color:#a5b4fc}
.sb-badge.sub{background:#1a2e1a;color:#4ade80}
.sb-list{display:flex;flex-direction:column;gap:8px}
.sb-row{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.sb-k{font-size:11px;color:#6b7080;flex-shrink:0}
.sb-v{font-size:12px;color:#c8ccd4;text-align:right;min-width:0}
.sb-v.line-clamp{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sb-footer{margin-top:14px;padding-top:12px;border-top:1px solid #2a2e38}
.sb-est{font-size:14px;font-weight:700;color:#a5b4fc;text-align:center}

/* ── Bootstrap ── */
.wiz-bootstrap{display:flex;align-items:center;justify-content:center;padding:60px 32px}
.bs-panel{background:#181a22;border:1px solid #2a2e38;border-radius:16px;padding:40px;
  text-align:center;max-width:480px;width:100%;animation:fadeUp .3s ease-out}
@keyframes fadeUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
.bs-icon{font-size:40px;margin-bottom:12px}
.bs-panel h3{font-size:18px;font-weight:700;color:#e2e4e9;margin-bottom:4px}
.bs-novel{color:#a5b4fc;font-size:14px;margin-bottom:24px}
.bs-stages{text-align:left;margin-bottom:24px}
.bs-stage{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #1e2028}
.bs-stage:last-child{border-bottom:none}
.bs-dot{width:24px;height:24px;border-radius:50%;border:2px solid #2a2e38;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:11px}
.bs-stage.done .bs-dot{background:#4f46e5;border-color:#4f46e5}
.bs-stage.running .bs-dot{border-color:#4f46e5}
.bs-stage.error .bs-dot{border-color:#ef4444}
.dot-ok{color:#fff;font-weight:700}
.dot-err{color:#ef4444;font-weight:700}
.dot-spin{width:10px;height:10px;border:2px solid #a5b4fc44;border-top-color:#a5b4fc;
  border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.dot-num{color:#6b7080}
.bs-label{font-size:14px;color:#c8ccd4;font-weight:500}
.bs-detail{margin-left:auto;font-size:11px;padding:2px 8px;border-radius:6px;font-weight:500}
.bs-detail.done{background:#1a2e1a;color:#4ade80}
.bs-detail.running{background:#1e1b4b;color:#a5b4fc}
.bs-detail.error{background:#2d1215;color:#f87171}
.bs-actions{display:flex;gap:12px;justify-content:center}

/* ── Responsive ── */
@media(max-width:900px){
  .wiz-body{flex-direction:column}
  .wiz-sidebar{width:100%}
  .length-cards{grid-template-columns:repeat(2,1fr)}
  .wiz-steps{flex-wrap:wrap}
}
</style>
