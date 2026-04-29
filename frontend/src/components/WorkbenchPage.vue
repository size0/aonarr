<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NIcon } from 'naive-ui'
import { ChevronBackOutline } from '@vicons/ionicons5'
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
            :class="{ active: mainPanelModel === 'drafts' }"
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
          <button :class="{ active: mainPanelModel === 'drafts' }" type="button" @click="mainPanelModel = 'drafts'">草稿审阅</button>
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

        <article v-else-if="mainPanelModel === 'drafts'" class="panel">
          <div class="panel-head">
            <h2>草稿审阅</h2>
            <button type="button" :disabled="!acceptedDrafts.length" @click="emit('exportMarkdown')">导出文稿</button>
          </div>
          <article v-for="draft in drafts" :key="draft.id" class="draft-card">
            <h3>{{ draft.title }}</h3>
            <div class="draft-meta">
              <span>{{ displayStatus(draft.status) }}</span>
              <span v-if="draft.quality_score !== undefined && draft.quality_score !== null">评分 {{ draft.quality_score }}</span>
              <span>版本 {{ draft.version }}</span>
            </div>
            <div class="button-row">
              <button class="small-button" type="button" :disabled="busy" @click="emit('setDraftStatus', draft, 'accepted')">通过</button>
              <button class="small-button" type="button" :disabled="busy" @click="emit('setDraftStatus', draft, 'needs_revision')">需要修订</button>
              <button class="small-button" type="button" :disabled="busy" @click="emit('setDraftStatus', draft, 'rejected')">拒绝</button>
            </div>
            <p v-if="draft.review_summary" class="review-summary">{{ draft.review_summary }}</p>
            <p>{{ draft.body }}</p>
          </article>
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
