<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NIcon, NInput, NTag } from 'naive-ui'
import {
  AddOutline,
  ArrowForwardOutline,
  MoonOutline,
  SearchOutline,
  SparklesOutline,
} from '@vicons/ionicons5'
import type { PageName } from '../composables/useWorkspace'
import {
  studioCharacters,
  studioChartBars,
  studioFeatures,
  studioOutlines,
  studioSideNav,
} from '../workspaceConfig'

const props = defineProps<{
  hasToken: boolean
}>()

const emit = defineEmits<{
  navigate: [page: PageName]
  notice: [message: string]
}>()

const landingNotice = ref('')

function enterWorkspace() {
  emit('navigate', props.hasToken ? 'index' : 'login')
}

function navigateAfterAuth(page: PageName) {
  emit('navigate', props.hasToken ? page : 'login')
}

function showLandingNotice(message: string) {
  landingNotice.value = message
  emit('notice', message)
}

function scrollToSelector(selector: string) {
  document.querySelector(selector)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>

<template>
  <main class="studio-page">
    <header class="site-header">
      <button class="brand" type="button" @click="emit('navigate', 'studio')">
        <span class="brand-feather" />
        <strong>aonarr</strong>
      </button>

      <nav class="main-nav" aria-label="主导航">
        <button class="active" type="button" @click="scrollToSelector('.hero')">首页</button>
        <button type="button" @click="scrollToSelector('.feature-strip')">功能</button>
        <button type="button" @click="navigateAfterAuth('settings')">提示词</button>
        <button type="button" @click="navigateAfterAuth('workbench')">自动修订</button>
        <button type="button" @click="navigateAfterAuth('workbench')">导出</button>
        <button type="button" @click="showLandingNotice('aonarr 当前提供自托管小说创作工作台，商业化 Beta 部署骨架已就绪。')">关于</button>
      </nav>

      <div class="header-actions">
        <n-button quaternary circle aria-label="切换主题" @click="showLandingNotice('主题切换将在后续版本开放。')">
          <template #icon>
            <n-icon :component="MoonOutline" />
          </template>
        </n-button>
        <n-button secondary size="large" @click="emit('navigate', 'login')">登录</n-button>
        <n-button type="primary" size="large" @click="enterWorkspace">
          进入工作台
        </n-button>
      </div>
    </header>

    <section class="hero">
      <div class="hero-bg" aria-hidden="true" />

      <section class="hero-copy">
        <div class="pill">
          <n-icon :component="SparklesOutline" />
          专为小说创作者打造的一站式自动连载平台
        </div>

        <h1>
          让灵感成章，
          <span>让连载自动推进</span>
        </h1>

        <p>
          aonarr 将故事设定、章节计划、正文起草、质量审阅、自动修订和导出放进同一个自托管工作台，帮助作者把长篇小说生产流程变得稳定、透明、可持续。
        </p>

        <div class="hero-actions">
          <n-button type="primary" size="large" @click="enterWorkspace">
            开始创作
            <template #icon>
              <n-icon :component="ArrowForwardOutline" />
            </template>
          </n-button>
          <n-button secondary size="large" @click="emit('navigate', 'login')">查看登录页</n-button>
        </div>

        <p v-if="landingNotice" class="panel-note">{{ landingNotice }}</p>

        <div class="hero-stats">
          <div>
            <strong>自动化</strong>
            <span>规划 / 起草 / 审阅</span>
          </div>
          <div>
            <strong>模型</strong>
            <span>模板可编辑</span>
          </div>
          <div>
            <strong>自托管</strong>
            <span>本地自托管</span>
          </div>
        </div>
      </section>

      <section class="product-preview" aria-label="工作台预览">
        <aside class="preview-sidebar">
          <div class="sidebar-heading">
            <span />
            <strong>我的作品</strong>
          </div>
          <button
            v-for="item in studioSideNav"
            :key="item.label"
            :class="{ active: item.active }"
            type="button"
            @click="showLandingNotice(`${item.label} 是产品预览入口，请进入工作台使用真实数据。`)"
          >
            <n-icon :component="item.icon" />
            {{ item.label }}
          </button>
        </aside>

        <div class="preview-main">
          <div class="preview-toolbar">
            <n-input placeholder="搜索作品、章节、角色..." round>
              <template #prefix>
                <n-icon :component="SearchOutline" />
              </template>
            </n-input>
            <n-button type="primary" @click="enterWorkspace">
              <template #icon>
                <n-icon :component="AddOutline" />
              </template>
              新建作品
            </n-button>
          </div>

          <div class="preview-grid">
            <section class="continue-card">
              <h2>继续创作</h2>
              <div class="book-row">
                <div class="book-cover">星火</div>
                <div>
                  <strong>长夜星火</strong>
                  <span>自动运行于 2 分钟前</span>
                  <div class="progress"><i /></div>
                  <em>进度：32%</em>
                </div>
              </div>
            </section>

            <section class="outline-card">
              <h2>章节大纲</h2>
              <div v-for="outline in studioOutlines" :key="outline.title" class="outline-row">
                <span>{{ outline.title }}</span>
                <em>{{ outline.done }}/{{ outline.total }} 章</em>
              </div>
            </section>

            <section class="characters-card">
              <div class="section-head">
                <h2>角色设定</h2>
                <button type="button" @click="navigateAfterAuth('workbench')">查看全部</button>
              </div>
              <div class="character-grid">
                <div v-for="character in studioCharacters" :key="character.name" class="character-card">
                  <div :class="['avatar', character.tone]">{{ character.short }}</div>
                  <strong>{{ character.name }}</strong>
                  <span>{{ character.role }}</span>
                </div>
              </div>
            </section>

            <section class="recent-card">
              <h2>最近运行</h2>
              <div class="recent-row">
                <div>
                  <strong>第三章：迷雾中的相遇</strong>
                  <span>2 分钟前 · 审阅通过</span>
                </div>
                <button type="button" @click="enterWorkspace">打开</button>
              </div>
            </section>
          </div>
        </div>
      </section>

      <section class="floating-stats">
        <div class="section-head">
          <h2>创作统计</h2>
          <n-tag size="small" :bordered="false">本周</n-tag>
        </div>
        <div class="chart">
          <div v-for="bar in studioChartBars" :key="bar.day" class="bar-wrap">
            <div class="bar" :style="{ height: `${bar.value}%` }" />
            <span>{{ bar.day }}</span>
          </div>
        </div>
        <div class="chart-tip">今日 2,350 字</div>
      </section>
    </section>

    <section class="feature-strip">
      <article v-for="feature in studioFeatures" :key="feature.title" class="feature-item">
        <div class="feature-icon">
          <n-icon :component="feature.icon" />
        </div>
        <div>
          <strong>{{ feature.title }}</strong>
          <p>{{ feature.desc }}</p>
        </div>
      </article>
    </section>
  </main>
</template>
