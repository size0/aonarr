<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Component } from 'vue'
import { NButton, NIcon, NTag } from 'naive-ui'
import { AddOutline, CheckmarkDoneOutline, ChevronBackOutline, ChevronForwardOutline } from '@vicons/ionicons5'
import type { ChapterDraft, SerialRun } from '../types'
import { displayStatus, type WorkspaceIndexPanel, type WorkspaceTask, type WorkspaceWork } from '../composables/useWorkspace'
import { calendarDays, chartLines, weekDays } from '../workspaceConfig'

type WorkspaceMetric = {
  label: string
  value: string
  delta: string
  icon: Component
  tone: string
  color: string
  points: string
}

type WorkspaceDataSummaryItem = {
  label: string
  value: string
  up: string
}

const props = defineProps<{
  acceptedDrafts: ChapterDraft[]
  drafts: ChapterDraft[]
  notice: string
  runs: SerialRun[]
  selectedProjectTitle: string
  username: string
  workspaceDataSummary: WorkspaceDataSummaryItem[]
  workspaceIndexPanel: WorkspaceIndexPanel
  workspaceMetrics: WorkspaceMetric[]
  workspaceTasks: WorkspaceTask[]
  workspaceWorks: WorkspaceWork[]
}>()

const emit = defineEmits<{
  openCreateProject: []
  refresh: []
  selectIndexPanel: [panel: WorkspaceIndexPanel]
  selectWorkspaceProject: [projectId: string]
  setNotice: [message: string]
  workspaceTask: [task: WorkspaceTask]
}>()

const statsRange = ref('30天')

const pageCopy = computed(() => {
  const copy: Record<WorkspaceIndexPanel, { title: string; description: string }> = {
    overview: { title: `下午好，${props.username}`, description: props.notice },
    works: { title: '作品管理', description: '集中查看作品列表、创建新作品，并进入单本书生产工作台' },
    stats: { title: '数据统计', description: '查看运行事件、提示词模板、自动修订和存储状态' },
    fans: { title: '粉丝互动', description: '互动运营模块预留中，后续可接入评论、私信和读者反馈' },
    tasks: { title: '任务中心', description: '按当前项目状态列出可执行的生产任务' },
  }
  return copy[props.workspaceIndexPanel]
})

function handleWorkMore(workId: string) {
  if (!workId) {
    emit('openCreateProject')
    return
  }
  emit('selectWorkspaceProject', workId)
}

function notify(message: string) {
  emit('setNotice', message)
}

function selectStatsRange(range: string) {
  statsRange.value = range
  notify(`已切换数据统计范围：${range}`)
}
</script>

<template>
  <section class="content">
    <div class="welcome-row">
      <div>
        <h1>{{ pageCopy.title }} <span v-if="workspaceIndexPanel === 'overview'">👋</span></h1>
        <p>{{ pageCopy.description }} · 当前项目：{{ selectedProjectTitle }}</p>
      </div>
      <n-button type="primary" size="large" class="new-work-btn" @click="emit('openCreateProject')">
        <template #icon>
          <n-icon :component="AddOutline" />
        </template>
        新建作品
      </n-button>
    </div>

    <section v-if="workspaceIndexPanel === 'overview'" class="metrics-grid">
      <article v-for="metric in workspaceMetrics" :key="metric.label" :class="['metric-card', metric.tone]">
        <div class="metric-icon">
          <n-icon :component="metric.icon" />
        </div>
        <div class="metric-copy">
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
          <em>{{ metric.delta }}</em>
        </div>
        <svg class="sparkline" viewBox="0 0 260 62" aria-hidden="true">
          <defs>
            <linearGradient :id="`${metric.tone}-fill`" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" :stop-color="metric.color" stop-opacity="0.18" />
              <stop offset="100%" :stop-color="metric.color" stop-opacity="0" />
            </linearGradient>
          </defs>
          <polygon :points="`${metric.points} 260,62 0,62`" :fill="`url(#${metric.tone}-fill)`" />
          <polyline :points="metric.points" fill="none" :stroke="metric.color" stroke-width="3.2" />
        </svg>
      </article>
    </section>

    <section :class="['dashboard-grid', { 'index-focus-grid': workspaceIndexPanel !== 'overview' }]">
      <article
        v-if="workspaceIndexPanel === 'overview' || workspaceIndexPanel === 'works'"
        :class="['panel', 'works-panel', { 'index-focus-panel': workspaceIndexPanel === 'works' }]"
      >
        <div class="panel-head">
          <h2>我的作品</h2>
          <button
            type="button"
            @click="workspaceIndexPanel === 'works' ? emit('refresh') : emit('selectIndexPanel', 'works')"
          >
            全部作品
            <n-icon :component="ChevronForwardOutline" />
          </button>
        </div>

        <div class="work-list">
          <div
            v-for="work in workspaceWorks"
            :key="work.id"
            class="work-row"
            @click="emit('selectWorkspaceProject', work.id)"
          >
            <div :class="['book-cover', work.coverTone]">
              <span>{{ work.cover }}</span>
            </div>
            <div class="work-info">
              <div>
                <strong>{{ work.title }}</strong>
                <n-tag size="small" :type="work.statusType" :bordered="false">{{ displayStatus(work.status) }}</n-tag>
              </div>
              <p>{{ work.meta }}</p>
            </div>
            <div class="work-stat">
              <span>草稿数</span>
              <strong>{{ work.words }}</strong>
            </div>
            <div class="work-stat">
              <span>计划数</span>
              <strong>{{ work.reads }}</strong>
            </div>
            <div class="work-stat">
              <span>通过数</span>
              <strong>{{ work.favorites }}</strong>
            </div>
            <div class="work-time">
              <span>更新时间</span>
              <strong>{{ work.updated }}</strong>
            </div>
            <button class="more-btn" type="button" aria-label="更多操作" @click.stop="handleWorkMore(work.id)">···</button>
          </div>

          <div class="create-row">
            <div class="create-icon">
              <n-icon :component="AddOutline" />
            </div>
            <div>
              <strong>创建新作品</strong>
              <p>创建后进入单本书生产工作台，配置故事设定和自动连载</p>
            </div>
            <n-button secondary type="primary" @click="emit('openCreateProject')">新建作品</n-button>
          </div>
        </div>
      </article>

      <article v-if="workspaceIndexPanel === 'overview'" class="panel calendar-panel">
        <div class="panel-head">
          <h2>创作日历</h2>
          <button type="button" @click="notify('创作目标设置将在后续版本开放；当前可在生产驾驶舱设置运行目标。')">设置目标</button>
        </div>
        <div class="month-head">
          <n-button quaternary circle size="small" @click="notify('日历月份切换将在后续版本开放。')">
            <template #icon>
              <n-icon :component="ChevronBackOutline" />
            </template>
          </n-button>
          <strong>2024年5月</strong>
          <n-button quaternary circle size="small" @click="notify('日历月份切换将在后续版本开放。')">
            <template #icon>
              <n-icon :component="ChevronForwardOutline" />
            </template>
          </n-button>
        </div>
        <div class="calendar-grid">
          <span v-for="day in weekDays" :key="day" class="week-day">{{ day }}</span>
          <button
            v-for="day in calendarDays"
            :key="`${day.label}-${day.muted}`"
            :class="{ muted: day.muted, active: day.active, marked: day.marked }"
            type="button"
            @click="notify(`创作日历 ${day.label} 日详情将在后续版本开放。`)"
          >
            {{ day.label }}
          </button>
        </div>
        <div class="calendar-summary">
          <div>
            <span>草稿数</span>
            <strong>{{ drafts.length }}</strong>
          </div>
          <div>
            <span>运行数</span>
            <strong>{{ runs.length }}</strong>
          </div>
          <div>
            <span>连续任务</span>
            <strong>{{ acceptedDrafts.length }} <em>章</em></strong>
          </div>
        </div>
      </article>

      <article
        v-if="workspaceIndexPanel === 'overview' || workspaceIndexPanel === 'stats'"
        :class="['panel', 'stats-panel', { 'index-focus-panel': workspaceIndexPanel === 'stats' }]"
      >
        <div class="panel-head">
          <h2>数据统计</h2>
          <div class="tabs">
            <button :class="{ active: statsRange === '7天' }" type="button" @click="selectStatsRange('7天')">7天</button>
            <button :class="{ active: statsRange === '30天' }" type="button" @click="selectStatsRange('30天')">30天</button>
            <button :class="{ active: statsRange === '90天' }" type="button" @click="selectStatsRange('90天')">90天</button>
            <button :class="{ active: statsRange === '自定义' }" type="button" @click="selectStatsRange('自定义')">自定义</button>
          </div>
        </div>
        <div class="data-summary">
          <div v-for="item in workspaceDataSummary" :key="item.label">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
            <em>↑ {{ item.up }}</em>
          </div>
        </div>
        <svg class="line-chart" viewBox="0 0 820 230" aria-hidden="true">
          <g class="grid-lines">
            <line v-for="y in chartLines" :key="y" x1="0" x2="820" :y1="y" :y2="y" />
          </g>
          <polyline points="0,178 72,138 145,184 218,120 292,86 365,150 438,116 510,160 585,78 656,132 742,118 820,156" />
          <polyline class="blue" points="0,166 72,152 145,128 218,170 292,142 365,94 438,130 510,118 585,150 656,108 742,100 820,138" />
          <polyline class="green" points="0,184 72,166 145,150 218,146 292,174 365,152 438,160 510,135 585,142 656,118 742,106 820,128" />
          <polyline class="orange" points="0,190 72,176 145,180 218,168 292,164 365,148 438,156 510,138 585,150 656,130 742,122 820,136" />
        </svg>
      </article>

      <article v-if="workspaceIndexPanel === 'fans'" class="panel task-panel index-focus-panel">
        <div class="panel-head">
          <h2>粉丝互动</h2>
          <button type="button" @click="notify('粉丝互动模块后续可接入评论、私信、投票和读者反馈。')">
            接入说明
            <n-icon :component="ChevronForwardOutline" />
          </button>
        </div>
        <div class="task-list">
          <div class="task-row">
            <div class="task-check purple">
              <n-icon :component="CheckmarkDoneOutline" />
            </div>
            <div>
              <strong>评论汇总</strong>
              <p>等待接入发布平台后同步读者评论和关键词</p>
            </div>
            <n-tag type="info" :bordered="false">待接入</n-tag>
          </div>
          <div class="task-row">
            <div class="task-check green">
              <n-icon :component="CheckmarkDoneOutline" />
            </div>
            <div>
              <strong>读者反馈</strong>
              <p>可作为后续自动修订和剧情规划的输入来源</p>
            </div>
            <n-tag type="warning" :bordered="false">预留</n-tag>
          </div>
          <div class="task-row">
            <div class="task-check orange">
              <n-icon :component="CheckmarkDoneOutline" />
            </div>
            <div>
              <strong>章节投票</strong>
              <p>适合用于分支剧情、番外方向和运营活动</p>
            </div>
            <n-tag type="info" :bordered="false">规划中</n-tag>
          </div>
        </div>
      </article>

      <article
        v-if="workspaceIndexPanel === 'overview' || workspaceIndexPanel === 'tasks'"
        :class="['panel', 'task-panel', { 'index-focus-panel': workspaceIndexPanel === 'tasks' }]"
      >
        <div class="panel-head">
          <h2>任务中心</h2>
          <button
            type="button"
            @click="workspaceIndexPanel === 'tasks' ? notify('当前已展示全部可执行任务。') : emit('selectIndexPanel', 'tasks')"
          >
            更多任务
            <n-icon :component="ChevronForwardOutline" />
          </button>
        </div>
        <div class="task-list">
          <button
            v-for="task in workspaceTasks"
            :key="task.title"
            class="task-row task-action"
            type="button"
            @click="emit('workspaceTask', task)"
          >
            <div :class="['task-check', task.tone]">
              <n-icon :component="CheckmarkDoneOutline" />
            </div>
            <div>
              <strong>{{ task.title }}</strong>
              <p>{{ task.progress }}</p>
            </div>
            <n-tag :type="task.type" :bordered="false">{{ task.badge }}</n-tag>
          </button>
        </div>
      </article>
    </section>
  </section>
</template>
