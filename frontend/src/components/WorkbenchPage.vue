<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NIcon } from 'naive-ui'
import {
  AddOutline,
  ChevronBackOutline,
  ChevronForwardOutline,
  CopyOutline,
  CreateOutline,
  EllipsisHorizontalOutline,
  FileTrayFullOutline,
  FlameOutline,
  GlobeOutline,
  LibraryOutline,
  MapOutline,
  PeopleOutline,
  SearchOutline,
  SettingsOutline,
  ShieldCheckmarkOutline,
  SparklesOutline,
  TimeOutline,
} from '@vicons/ionicons5'
import type {
  createDefaultBibleForm,
  createDefaultProjectForm,
  createDefaultRunForm,
} from '../formDefaults'
import type { ChapterDraft, ChapterPlan, Project, Readiness, RunEvent, SerialRun } from '../types'
import {
  displayEventType,
  displayReadinessSection,
  displayStatus,
  type WorkbenchMainPanel,
  type WorkbenchSidePanel,
} from '../composables/useWorkspace'

type BibleForm = ReturnType<typeof createDefaultBibleForm>
type ProjectForm = ReturnType<typeof createDefaultProjectForm>
type RunForm = ReturnType<typeof createDefaultRunForm>
type DraftStatus = 'accepted' | 'needs_revision' | 'rejected'
type RunControlAction = 'pause' | 'resume' | 'cancel'
type ChapterFilter = 'all' | 'published' | 'draft'
type ChapterRow = {
  id: string
  chapter_number: number
  title: string
  summary: string
  word_count: number
  status: string
  version: number | null
  source: 'draft' | 'plan'
  draft?: ChapterDraft
}

const props = defineProps<{
  acceptedDrafts: ChapterDraft[]
  bibleForm: BibleForm
  busy: boolean
  drafts: ChapterDraft[]
  events: RunEvent[]
  notice: string
  plans: ChapterPlan[]
  projectForm: ProjectForm
  projects: Project[]
  readiness: Readiness | null
  runForm: RunForm
  runs: SerialRun[]
  selectedProject: Project | null
  selectedProjectId: string
  selectedRun: SerialRun | null
  selectedRunId: string
  workbenchMainPanel: WorkbenchMainPanel
  workbenchSidePanel: WorkbenchSidePanel
}>()

const emit = defineEmits<{
  exportMarkdown: []
  loadEvents: []
  loadProjectData: []
  navigateIndex: []
  openCreateProject: []
  openEventStream: []
  runAction: [action: RunControlAction]
  saveBible: []
  setDraftStatus: [draft: ChapterDraft, status: DraftStatus]
  setNotice: [message: string]
  startRun: []
  updateProjectSelection: []
  'update:selectedProjectId': [value: string]
  'update:selectedRunId': [value: string]
  'update:workbenchMainPanel': [value: WorkbenchMainPanel]
  'update:workbenchSidePanel': [value: WorkbenchSidePanel]
}>()

const selectedProjectIdModel = computed({
  get: () => props.selectedProjectId,
  set: (value: string) => emit('update:selectedProjectId', value),
})

const selectedRunIdModel = computed({
  get: () => props.selectedRunId,
  set: (value: string) => emit('update:selectedRunId', value),
})

const mainPanelModel = computed({
  get: () => props.workbenchMainPanel,
  set: (value: WorkbenchMainPanel) => emit('update:workbenchMainPanel', value),
})

const sidePanelModel = computed({
  get: () => props.workbenchSidePanel,
  set: (value: WorkbenchSidePanel) => emit('update:workbenchSidePanel', value),
})

const chapterFilter = ref<ChapterFilter>('all')
const chapterSearch = ref('')
const worldTabs = ['世界概览', '地理环境', '历史文明', '势力组织', '种族设定', '魔法体系', '科技体系', '规则设定']
const activeWorldTab = ref('世界概览')

const publishedDrafts = computed(() => props.drafts.filter((item) => item.status === 'accepted'))
const draftChapterCount = computed(() => props.drafts.filter((item) => item.status !== 'accepted').length)
const totalWords = computed(() => props.drafts.reduce((sum, item) => sum + item.word_count, 0))
const totalChapterCount = computed(() => Math.max(props.selectedProject?.target_chapter_count ?? 0, props.plans.length, props.drafts.length))
const chapterCoverText = computed(() => props.selectedProject?.title.slice(0, 2) || '作品')
const worldSettingCategories = computed(() => [
  { title: '地理环境', desc: '大陆、国家、城市、地形、气候和资源设定', count: 28, icon: MapOutline, tone: 'blue' },
  { title: '历史文明', desc: '历史事件、纪元划分、文化传承和文明兴衰', count: 35, icon: LibraryOutline, tone: 'purple' },
  { title: '势力组织', desc: '宗门、朝廷、家族、商会和敌对阵营', count: 42, icon: ShieldCheckmarkOutline, tone: 'orange' },
  { title: '种族设定', desc: '神族、妖族、外貌特征和文化习俗', count: 18, icon: PeopleOutline, tone: 'green' },
  { title: '魔法体系', desc: '灵法类型、元素属性、禁术和修炼路径', count: 15, icon: SparklesOutline, tone: 'violet' },
  { title: '科技体系', desc: '科技水平、发明创造、工艺技术和能源', count: 12, icon: GlobeOutline, tone: 'cyan' },
  { title: '规则设定', desc: '世界规则、物理法则、禁忌和特殊条件', count: 6, icon: FlameOutline, tone: 'red' },
  { title: '神话传说', desc: '神话故事、传说典故、宗教信仰和预言', count: 8, icon: FileTrayFullOutline, tone: 'amber' },
])
const worldTotalSettings = computed(() => worldSettingCategories.value.reduce((sum, item) => sum + item.count, 0))
const worldUpdateItems = computed(() => [
  { title: `${props.selectedProject?.genre ?? '主线'}世界观主日志表`, tag: '魔法体系', status: '重要设定', date: '2024-05-20 14:30' },
  { title: `${props.selectedProject?.title ?? '当前作品'}历史年表`, tag: '历史文明', status: '已公开', date: '2024-05-20 10:15' },
])

const chapterRows = computed<ChapterRow[]>(() => {
  if (props.drafts.length) {
    return [...props.drafts]
      .sort((left, right) => left.chapter_number - right.chapter_number)
      .map((draft) => ({
        id: draft.id,
        chapter_number: draft.chapter_number,
        title: draft.title,
        summary: draft.review_summary || draft.body,
        word_count: draft.word_count,
        status: draft.status,
        version: draft.version,
        source: 'draft',
        draft,
      }))
  }
  return [...props.plans]
    .sort((left, right) => left.chapter_number - right.chapter_number)
    .map((plan) => ({
      id: plan.id,
      chapter_number: plan.chapter_number,
      title: plan.title_hint,
      summary: [plan.goal, plan.conflict, plan.hook].filter(Boolean).join('，'),
      word_count: 0,
      status: plan.status,
      version: null,
      source: 'plan',
    }))
})

const filteredChapterRows = computed(() => {
  const keyword = chapterSearch.value.trim().toLowerCase()
  return chapterRows.value.filter((row) => {
    const matchesFilter =
      chapterFilter.value === 'all' ||
      (chapterFilter.value === 'published' ? row.status === 'accepted' : row.status !== 'accepted')
    const matchesSearch =
      !keyword ||
      row.title.toLowerCase().includes(keyword) ||
      row.summary.toLowerCase().includes(keyword) ||
      String(row.chapter_number).includes(keyword)
    return matchesFilter && matchesSearch
  })
})

function chapterSummary(summary: string) {
  return summary.length > 68 ? `${summary.slice(0, 68)}...` : summary
}

function openNewChapterFlow() {
  mainPanelModel.value = 'run'
  emit('setNotice', '请在生产驾驶舱启动运行生成新章节。')
}

function notifyChapterAction(message: string) {
  emit('setNotice', message)
}

function notifyWorldAction(message: string) {
  emit('setNotice', message)
}
</script>

<template>
  <section class="content workbench-content">
    <div class="workspace-breadcrumb">
      <button type="button" @click="emit('navigateIndex')">
        <n-icon :component="ChevronBackOutline" />
        返回工作台
      </button>
      <select v-if="projects.length" v-model="selectedProjectIdModel" @change="emit('updateProjectSelection')">
        <option v-for="project in projects" :key="project.id" :value="project.id">
          {{ project.title }} · {{ displayStatus(project.status) }}
        </option>
      </select>
      <n-button secondary type="primary" @click="emit('openCreateProject')">新建作品</n-button>
    </div>

    <div v-if="!selectedProject" class="empty-state panel">
      <h2>先选择或创建一个作品</h2>
      <p>生产工作台是单本书的生产空间，用来配置故事设定、启动自动连载、审阅草稿和查看运行日志。</p>
      <n-button type="primary" @click="emit('openCreateProject')">创建作品</n-button>
    </div>

    <section v-else-if="mainPanelModel === 'world'" class="world-setting-view">
      <header class="world-setting-header">
        <div>
          <h1>世界观设定</h1>
          <p>构建完整的世界观体系，让你的故事更加立体和真实</p>
        </div>
        <button class="chapter-primary-button" type="button" @click="notifyWorldAction('新建设定条目将在后续版本开放；当前可先编辑故事设定。')">
          <n-icon :component="AddOutline" />
          新建设定
        </button>
      </header>

      <nav class="world-tabs" aria-label="世界观分类">
        <button
          v-for="tab in worldTabs"
          :key="tab"
          :class="{ active: activeWorldTab === tab }"
          type="button"
          @click="activeWorldTab = tab"
        >
          {{ tab }}
        </button>
      </nav>

      <section class="world-setting-grid">
        <div class="world-main-column">
          <article class="world-card world-overview-card">
            <div class="world-card-head">
              <h2>世界概览</h2>
            </div>
            <div class="world-overview-body">
              <div class="world-hero-image"></div>
              <div class="world-overview-copy">
                <div>
                  <h3>{{ bibleForm.world_summary ? `${selectedProject.genre}世界` : `${selectedProject.title}世界观` }}</h3>
                  <span>主要世界</span>
                </div>
                <p>{{ bibleForm.world_summary || '在这里梳理大陆格局、时代背景、势力关系和核心规则，为后续章节生成提供统一参照。' }}</p>
                <div class="world-meta-grid">
                  <div>
                    <n-icon :component="TimeOutline" />
                    <span>创建时间</span>
                    <strong>2024-01-15</strong>
                  </div>
                  <div>
                    <n-icon :component="TimeOutline" />
                    <span>更新时间</span>
                    <strong>2024-05-20</strong>
                  </div>
                  <div>
                    <n-icon :component="PeopleOutline" />
                    <span>关联作品</span>
                    <strong>{{ selectedProject.title }}</strong>
                  </div>
                  <div>
                    <n-icon :component="FileTrayFullOutline" />
                    <span>设定条目</span>
                    <strong>{{ worldTotalSettings }} 项</strong>
                  </div>
                </div>
              </div>
            </div>
          </article>

          <article class="world-card">
            <div class="world-card-head">
              <h2>核心设定分类</h2>
            </div>
            <div class="world-category-grid">
              <button
                v-for="item in worldSettingCategories"
                :key="item.title"
                :class="['world-category-card', item.tone]"
                type="button"
                @click="activeWorldTab = item.title"
              >
                <n-icon :component="item.icon" />
                <span>
                  <strong>{{ item.title }}</strong>
                  <em>{{ item.desc }}</em>
                  <small>{{ item.count }} 项设定</small>
                </span>
              </button>
            </div>
          </article>

          <article class="world-card">
            <div class="world-card-head">
              <h2>最近更新</h2>
              <button type="button" @click="notifyWorldAction('完整更新记录将在后续版本开放。')">
                查看全部
                <n-icon :component="ChevronForwardOutline" />
              </button>
            </div>
            <div class="world-update-list">
              <div v-for="item in worldUpdateItems" :key="item.title" class="world-update-row">
                <n-icon :component="FileTrayFullOutline" />
                <div>
                  <strong>{{ item.title }}</strong>
                  <p>{{ bibleForm.premise || '根据当前故事前提持续沉淀世界观资料。' }}</p>
                </div>
                <span>{{ item.tag }}</span>
                <em>{{ item.status }}</em>
                <small>{{ item.date }}</small>
              </div>
            </div>
          </article>
        </div>

        <aside class="world-side-column">
          <article class="world-card">
            <div class="world-card-head">
              <h2>设定统计</h2>
              <button type="button" @click="notifyWorldAction('设定统计详情将在后续版本开放。')">查看详情</button>
            </div>
            <div class="world-stat-card">
              <div class="world-donut">
                <span>{{ worldTotalSettings }}</span>
                <em>总设定数</em>
              </div>
              <div class="world-stat-legend">
                <div v-for="item in worldSettingCategories.slice(0, 6)" :key="item.title">
                  <span :class="item.tone"></span>
                  <strong>{{ item.title }}</strong>
                  <em>{{ item.count }}</em>
                </div>
              </div>
            </div>
          </article>

          <article class="world-card">
            <div class="world-card-head">
              <h2>世界地图</h2>
              <button type="button" @click="notifyWorldAction('世界地图编辑将在后续版本开放。')">
                查看详情
                <n-icon :component="ChevronForwardOutline" />
              </button>
            </div>
            <div class="world-map-card">
              <span class="pin pin-blue">北境之地</span>
              <span class="pin pin-red">中央帝国</span>
              <span class="pin pin-green">精灵森林</span>
              <span class="pin pin-orange">沙海王国</span>
              <span class="pin pin-purple">海洋领地</span>
            </div>
          </article>

          <article class="world-card">
            <div class="world-card-head">
              <h2>快速操作</h2>
            </div>
            <div class="world-quick-actions">
              <button type="button" @click="notifyWorldAction('新建设定条目将在后续版本开放。')">
                <n-icon :component="FileTrayFullOutline" />
                <span><strong>新建设定条目</strong><em>创建新的世界观设定</em></span>
              </button>
              <button type="button" @click="notifyWorldAction('批量导入设定将在后续版本开放。')">
                <n-icon :component="AddOutline" />
                <span><strong>批量导入设定</strong><em>从文件批量导入设定条目</em></span>
              </button>
              <button type="button" @click="notifyWorldAction('设定关系图谱将在后续版本开放。')">
                <n-icon :component="SparklesOutline" />
                <span><strong>设定关系图谱</strong><em>查看设定之间的关联关系</em></span>
              </button>
              <button type="button" @click="notifyWorldAction('世界观设定导出备份将在后续版本开放。')">
                <n-icon :component="ChevronForwardOutline" />
                <span><strong>设定导出备份</strong><em>导出世界观设定数据</em></span>
              </button>
            </div>
          </article>
        </aside>
      </section>
    </section>

    <section v-else-if="mainPanelModel === 'drafts'" class="chapter-manager-view">
      <header class="chapter-manager-header">
        <div>
          <h1>章节管理</h1>
          <p>管理作品章节，调整章节顺序和内容</p>
        </div>
        <div class="chapter-manager-actions">
          <button class="chapter-primary-button" type="button" @click="openNewChapterFlow">
            <n-icon :component="AddOutline" />
            新建章节
          </button>
          <button class="chapter-icon-button" type="button" aria-label="更多操作" @click="notifyChapterAction('更多章节操作将在后续版本开放。')">
            <n-icon :component="EllipsisHorizontalOutline" />
          </button>
        </div>
      </header>

      <section class="chapter-book-card">
        <div class="chapter-book-info">
          <div class="chapter-cover">{{ chapterCoverText }}</div>
          <div>
            <h2>{{ selectedProject.title }}</h2>
            <p>{{ selectedProject.genre }} · {{ selectedProject.target_chapter_count }} 章目标 · {{ selectedProject.target_words_per_chapter }} 字/章</p>
          </div>
        </div>
        <div class="chapter-book-stats">
          <div>
            <span>已发布章节</span>
            <strong>{{ publishedDrafts.length }}</strong>
          </div>
          <div>
            <span>草稿章节</span>
            <strong>{{ draftChapterCount }}</strong>
          </div>
          <div>
            <span>总字数</span>
            <strong>{{ totalWords.toLocaleString() }}</strong>
          </div>
        </div>
        <button class="chapter-settings-button" type="button" @click="notifyChapterAction('章节设置将在后续版本开放；当前可在作品资料中维护项目设定。')">
          <n-icon :component="SettingsOutline" />
          章节设置
        </button>
      </section>

      <section class="chapter-table-panel">
        <div class="chapter-toolbar">
          <div class="chapter-filter-tabs">
            <button :class="{ active: chapterFilter === 'all' }" type="button" @click="chapterFilter = 'all'">
              全部章节 <span>{{ totalChapterCount }}</span>
            </button>
            <button :class="{ active: chapterFilter === 'published' }" type="button" @click="chapterFilter = 'published'">
              已发布 <span>{{ publishedDrafts.length }}</span>
            </button>
            <button :class="{ active: chapterFilter === 'draft' }" type="button" @click="chapterFilter = 'draft'">
              草稿 <span>{{ draftChapterCount }}</span>
            </button>
          </div>
          <div class="chapter-tools">
            <button type="button" @click="notifyChapterAction('批量操作将在后续版本开放。')">批量操作</button>
            <select aria-label="选择卷">
              <option>全部卷</option>
              <option>卷一</option>
            </select>
            <select aria-label="排序">
              <option>排序</option>
              <option>章节升序</option>
              <option>章节降序</option>
            </select>
            <label class="chapter-search">
              <n-icon :component="SearchOutline" />
              <input v-model="chapterSearch" placeholder="搜索章节标题..." />
            </label>
          </div>
        </div>

        <div class="chapter-table">
          <div class="chapter-table-head">
            <span>章节</span>
            <span>卷</span>
            <span>字数</span>
            <span>更新时间</span>
            <span>状态</span>
            <span>操作</span>
          </div>
          <div v-if="!filteredChapterRows.length" class="chapter-empty-row">
            暂无匹配章节，启动生产运行后会自动生成章节内容。
          </div>
          <article v-for="row in filteredChapterRows" :key="row.id" class="chapter-table-row">
            <div class="chapter-title-cell">
              <button type="button" aria-label="拖拽排序" @click="notifyChapterAction('拖拽排序将在后续版本开放。')">⋮⋮</button>
              <div>
                <strong>第{{ row.chapter_number }}章 {{ row.title }}</strong>
                <p>{{ chapterSummary(row.summary) }}</p>
              </div>
            </div>
            <span>卷一 · 青云起</span>
            <span>{{ row.word_count.toLocaleString() }}</span>
            <span>{{ row.draft ? `版本 ${row.version}` : '未生成草稿' }}</span>
            <span :class="['chapter-status', row.status === 'accepted' ? 'published' : 'draft']">
              {{ row.status === 'accepted' ? '已发布' : displayStatus(row.status) }}
            </span>
            <div class="chapter-row-actions">
              <button
                type="button"
                :disabled="!row.draft || busy"
                aria-label="编辑章节"
                @click="row.draft ? notifyChapterAction('章节编辑器将在后续版本开放。') : notifyChapterAction('该章节还没有生成草稿。')"
              >
                <n-icon :component="CreateOutline" />
              </button>
              <button type="button" aria-label="复制章节" @click="notifyChapterAction('复制章节将在后续版本开放。')">
                <n-icon :component="CopyOutline" />
              </button>
              <button type="button" aria-label="更多章节操作" @click="notifyChapterAction('更多章节操作将在后续版本开放。')">
                <n-icon :component="EllipsisHorizontalOutline" />
              </button>
            </div>
          </article>
        </div>

        <footer class="chapter-pagination">
          <span>共 {{ filteredChapterRows.length }} 章</span>
          <div>
            <button type="button" @click="notifyChapterAction('上一页将在章节数量更多时开放。')">‹</button>
            <button class="active" type="button">1</button>
            <button type="button" @click="notifyChapterAction('下一页将在章节数量更多时开放。')">›</button>
          </div>
        </footer>
      </section>
    </section>

    <section v-else class="workbench-layout">
      <aside class="panel chapter-rail">
        <div class="panel-head">
          <h2>{{ selectedProject.title }}</h2>
          <button type="button" @click="emit('loadProjectData')">刷新</button>
        </div>
        <div class="run-progress-card">
          <span>当前运行</span>
          <strong>{{ selectedRun ? displayStatus(selectedRun.status) : '未启动' }}</strong>
          <p>{{ selectedRun ? `${selectedRun.completed_chapter_count}/${selectedRun.target_chapter_count} 章 · $${selectedRun.estimated_cost}` : '创建运行后开始监听进度' }}</p>
        </div>
        <div class="chapter-list">
          <button
            v-for="plan in plans"
            :key="plan.id"
            type="button"
            :class="{ active: mainPanelModel === 'plans' }"
            @click="mainPanelModel = 'plans'"
          >
            <span>第{{ plan.chapter_number }}章</span>
            <strong>{{ plan.title_hint }}</strong>
            <em>{{ displayStatus(plan.status) }}</em>
          </button>
          <button
            v-for="draft in drafts"
            :key="draft.id"
            type="button"
            @click="mainPanelModel = 'drafts'"
          >
            <span>第{{ draft.chapter_number }}章</span>
            <strong>{{ draft.title }}</strong>
            <em>{{ displayStatus(draft.status) }}</em>
          </button>
        </div>
      </aside>

      <section class="workbench-center">
        <div class="workbench-tabs">
          <button :class="{ active: mainPanelModel === 'run' }" type="button" @click="mainPanelModel = 'run'">生产驾驶舱</button>
          <button :class="{ active: mainPanelModel === 'plans' }" type="button" @click="mainPanelModel = 'plans'">章节计划</button>
          <button type="button" @click="mainPanelModel = 'drafts'">章节管理</button>
          <button :class="{ active: mainPanelModel === 'events' }" type="button" @click="mainPanelModel = 'events'">运行日志</button>
        </div>

        <article v-if="mainPanelModel === 'run'" class="panel cockpit-panel">
          <div class="panel-head">
            <h2>生产驾驶舱</h2>
            <button type="button" @click="emit('openEventStream')">连接实时日志</button>
          </div>
          <div class="cockpit-grid">
            <div class="engine-box">
              <h3>运行目标</h3>
              <label>
                目标章节
                <input v-model.number="runForm.target_chapter_count" type="number" min="1" />
              </label>
              <label>
                成本上限
                <input v-model.number="runForm.cost_limit" type="number" min="0" step="0.01" />
              </label>
              <select v-if="runs.length" v-model="selectedRunIdModel" @change="emit('loadEvents')">
                <option v-for="run in runs" :key="run.id" :value="run.id">
                  {{ displayStatus(run.status) }} · {{ run.completed_chapter_count }}/{{ run.target_chapter_count }} · ${{ run.estimated_cost }}
                </option>
              </select>
            </div>
            <div class="run-meter">
              <strong>{{ selectedRun ? Math.round((selectedRun.completed_chapter_count / Math.max(selectedRun.target_chapter_count, 1)) * 100) : 0 }}%</strong>
              <span>{{ selectedRun ? displayStatus(selectedRun.status) : '待启动' }}</span>
              <p>已完成 {{ selectedRun?.completed_chapter_count ?? 0 }} / {{ selectedRun?.target_chapter_count ?? runForm.target_chapter_count }} 章</p>
            </div>
            <div class="engine-box">
              <h3>控制</h3>
              <div class="button-row">
                <button class="primary-button" type="button" :disabled="busy || !selectedProject" @click="emit('startRun')">启动</button>
                <button class="ghost-button" type="button" :disabled="!selectedRun" @click="emit('runAction', 'pause')">暂停</button>
                <button class="ghost-button" type="button" :disabled="!selectedRun" @click="emit('runAction', 'resume')">继续</button>
                <button class="ghost-button" type="button" :disabled="!selectedRun" @click="emit('runAction', 'cancel')">取消</button>
              </div>
              <p class="panel-note">{{ notice }}</p>
            </div>
          </div>
        </article>

        <article v-else-if="mainPanelModel === 'plans'" class="panel">
          <div class="panel-head">
            <h2>章节计划</h2>
            <button type="button" @click="emit('loadProjectData')">刷新计划</button>
          </div>
          <div class="plan-list">
            <article v-for="plan in plans" :key="plan.id" class="plan-row">
              <span>第{{ plan.chapter_number }}章 · {{ displayStatus(plan.status) }}</span>
              <h3>{{ plan.title_hint }}</h3>
              <p>{{ plan.goal }}</p>
              <p>{{ plan.conflict }}</p>
              <em>{{ plan.hook }}</em>
            </article>
          </div>
        </article>

        <article v-else class="panel">
          <div class="panel-head">
            <h2>运行日志</h2>
            <button type="button" @click="emit('loadEvents')">刷新日志</button>
          </div>
          <div class="event-log">
            <article v-for="event in events" :key="event.id" class="event-row">
              <span>{{ displayEventType(event.event_type) }}</span>
              <p>{{ event.message }}</p>
              <small>{{ event.created_at }}</small>
            </article>
          </div>
        </article>
      </section>

      <aside class="panel settings-side-panel">
        <div class="panel-head">
          <h2>作品资料</h2>
          <button type="button" @click="sidePanelModel = 'export'">导出</button>
        </div>
        <div class="workbench-tabs side-tabs">
          <button :class="{ active: sidePanelModel === 'bible' }" type="button" @click="sidePanelModel = 'bible'">故事设定</button>
          <button :class="{ active: sidePanelModel === 'project' }" type="button" @click="sidePanelModel = 'project'">项目设定</button>
          <button :class="{ active: sidePanelModel === 'export' }" type="button" @click="sidePanelModel = 'export'">导出</button>
        </div>
        <div v-if="sidePanelModel === 'bible'" class="side-panel-body">
          <textarea v-model="bibleForm.premise" placeholder="故事前提"></textarea>
          <textarea v-model="bibleForm.world_summary" placeholder="世界观摘要"></textarea>
          <textarea v-model="bibleForm.tone_profile" placeholder="文风设定"></textarea>
          <button class="primary-button" type="button" :disabled="!selectedProject" @click="emit('saveBible')">保存故事设定</button>
          <div v-if="readiness" class="readiness" :class="{ ready: readiness.ready }">
            <strong>{{ readiness.ready ? '可以开始运行' : '尚未就绪' }}</strong>
            <p v-for="item in readiness.missing" :key="item.section">{{ displayReadinessSection(item.section) }}：{{ item.message }}</p>
          </div>
        </div>
        <div v-else-if="sidePanelModel === 'project'" class="side-panel-body">
          <input v-model="projectForm.title" placeholder="作品名称" />
          <input v-model="projectForm.genre" placeholder="作品类型" />
          <input v-model.number="projectForm.target_chapter_count" type="number" />
          <input v-model.number="projectForm.target_words_per_chapter" type="number" />
          <textarea v-model="projectForm.style_goal" placeholder="风格目标"></textarea>
          <button class="ghost-button" type="button" @click="emit('setNotice', '当前版本先支持创建时写入项目设定')">保存项目设定</button>
        </div>
        <div v-else class="side-panel-body">
          <strong>文稿导出</strong>
          <p>导出当前项目已通过章节，适合进入后续排版或发布流程。</p>
          <button class="primary-button" type="button" :disabled="!acceptedDrafts.length" @click="emit('exportMarkdown')">导出文稿</button>
        </div>
      </aside>
    </section>
  </section>
</template>
