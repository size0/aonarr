<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NCheckbox, NForm, NFormItem, NIcon, NInput } from 'naive-ui'
import {
  ArrowBackOutline,
  ChatbubbleEllipsesOutline,
  ChevronDownOutline,
  CreateOutline,
  EyeOffOutline,
  EyeOutline,
  GlobeOutline,
  LockClosedOutline,
  LogoWechat,
  MailOutline,
  PaperPlaneOutline,
  PhonePortraitOutline,
} from '@vicons/ionicons5'
import { loginFeatures } from '../workspaceConfig'

const props = defineProps<{
  busy: boolean
  canLoginSubmit: boolean
  notice: string
  password: string
  remember: boolean
  showDevLoginHint: boolean
  username: string
}>()

const emit = defineEmits<{
  fillDevLogin: []
  login: []
  navigateStudio: []
  notice: [message: string]
  'update:password': [value: string]
  'update:remember': [value: boolean]
  'update:username': [value: string]
}>()

const usernameModel = computed({
  get: () => props.username,
  set: (value: string) => emit('update:username', value),
})

const passwordModel = computed({
  get: () => props.password,
  set: (value: string) => emit('update:password', value),
})

const rememberModel = computed({
  get: () => props.remember,
  set: (value: boolean) => emit('update:remember', value),
})
</script>

<template>
  <main class="login-page">
    <header class="login-header">
      <button class="brand" type="button" @click="emit('navigateStudio')">
        <span class="brand-mark">
          <n-icon :component="CreateOutline" />
        </span>
        <span>
          <strong>aonarr</strong>
          <em>长篇小说自动连载工作台</em>
        </span>
      </button>

      <nav class="top-nav" aria-label="产品导航">
        <button type="button" @click="emit('navigateStudio')">首页</button>
        <button type="button">功能</button>
        <button type="button">提示词</button>
        <button type="button">运行日志</button>
        <button type="button">导出</button>
      </nav>

      <div class="header-actions">
        <button class="language-btn" type="button">
          <n-icon :component="GlobeOutline" />
          简体中文
          <n-icon :component="ChevronDownOutline" />
        </button>
        <n-button secondary size="large" :disabled="busy" @click="emit('navigateStudio')">
          <template #icon>
            <n-icon :component="ArrowBackOutline" />
          </template>
          返回首页
        </n-button>
      </div>
    </header>

    <section class="login-shell">
      <section class="intro-panel">
        <div class="intro-copy">
          <div class="eyebrow">
            <n-icon :component="PaperPlaneOutline" />
            专为网文作者打造
          </div>
          <h1>
            让每一次灵感，
            <span>都自动落成章节</span>
          </h1>
          <p>
            从故事设定、章节规划、正文起草到质量审阅和自动修订，aonarr 帮你把长篇小说生产流程整理成可控、可追踪、可自托管的工作台。
          </p>

          <div class="feature-list">
            <article v-for="feature in loginFeatures" :key="feature.title">
              <span>
                <n-icon :component="feature.icon" />
              </span>
              <div>
                <strong>{{ feature.title }}</strong>
                <p>{{ feature.desc }}</p>
              </div>
            </article>
          </div>

          <div class="quote-card">
            <div class="quote-mark">“</div>
            <p>把提示词、章节计划、修订反馈和运行成本都放进同一条生产线，长篇连载终于不再靠散乱文档硬撑。</p>
            <div class="quote-author">
              <span>S</span>
              <div>
                <strong>aonarr</strong>
                <em>本地自动化原型</em>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="form-panel" aria-label="登录">
        <div class="login-card">
          <div class="login-title">
            <span class="title-icon">
              <n-icon :component="LockClosedOutline" />
            </span>
            <h2>欢迎回来</h2>
            <p>登录你的 aonarr 工作空间</p>
          </div>

          <n-form class="login-form" :show-label="false" @submit.prevent="emit('login')">
            <label class="field-label" for="account">邮箱 / 用户名</label>
            <n-form-item>
              <n-input
                id="account"
                v-model:value="usernameModel"
                size="large"
                placeholder="请输入邮箱或用户名"
                autocomplete="username"
              >
                <template #prefix>
                  <n-icon :component="MailOutline" />
                </template>
              </n-input>
            </n-form-item>

            <div class="password-head">
              <label class="field-label" for="password">密码</label>
              <button type="button" @click="emit('notice', '本地 MVP 暂未启用找回密码')">忘记密码？</button>
            </div>
            <n-form-item>
              <n-input
                id="password"
                v-model:value="passwordModel"
                size="large"
                type="password"
                show-password-on="click"
                placeholder="请输入密码"
                autocomplete="current-password"
              >
                <template #prefix>
                  <n-icon :component="LockClosedOutline" />
                </template>
                <template #password-visible-icon>
                  <n-icon :component="EyeOutline" />
                </template>
                <template #password-invisible-icon>
                  <n-icon :component="EyeOffOutline" />
                </template>
              </n-input>
            </n-form-item>

            <div class="form-extra">
              <n-checkbox v-model:checked="rememberModel">记住登录状态</n-checkbox>
              <span>{{ notice }}</span>
            </div>

            <n-button
              attr-type="submit"
              type="primary"
              size="large"
              block
              class="login-submit"
              :loading="busy"
              :disabled="!canLoginSubmit"
            >
              登录工作台
            </n-button>
          </n-form>

          <div class="divider">
            <span />
            <em>或使用以下方式登录</em>
            <span />
          </div>

          <div class="social-grid">
            <n-button secondary size="large" @click="emit('notice', '微信登录暂未启用')">
              <template #icon>
                <n-icon class="wechat" :component="LogoWechat" />
              </template>
              微信
            </n-button>
            <n-button secondary size="large" @click="emit('notice', 'QQ 登录暂未启用')">
              <template #icon>
                <n-icon class="qq" :component="ChatbubbleEllipsesOutline" />
              </template>
              QQ
            </n-button>
            <n-button secondary size="large" @click="emit('notice', '手机号登录暂未启用')">
              <template #icon>
                <n-icon class="phone" :component="PhonePortraitOutline" />
              </template>
              手机号
            </n-button>
          </div>

          <p v-if="showDevLoginHint" class="register-line">
            本地默认账号：
            <button type="button" @click="emit('fillDevLogin')">填入 admin / change-me</button>
          </p>
        </div>
      </section>
    </section>
  </main>
</template>
