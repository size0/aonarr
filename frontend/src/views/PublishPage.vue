<script setup lang="ts">
import { NModal, useMessage } from 'naive-ui'
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { publishingApi, type Platform, type PublishJob } from '@/api/publishing'
import { useNovelsStore } from '@/stores/novels'

const message = useMessage()
const novelsStore = useNovelsStore()

const platforms = ref<Platform[]>([
  { id: 'fanqie', name: '番茄小说', url: 'https://fanqienovel.com', login_ready: false, login_status: '加载中…', modified_at: null },
  { id: 'qidian', name: '起点中文网', url: 'https://write.qq.com', login_ready: false, login_status: '加载中…', modified_at: null },
])
const jobs = ref<PublishJob[]>([])
const loading = ref(false)

// ── Login capture state ───────────────────────────────────────
const capturingPlatform = ref<string | null>(null)
const captureCountdown = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null
let statusPollTimer: ReturnType<typeof setInterval> | null = null

// ── Load ──────────────────────────────────────────────────────
async function loadPlatforms() {
  try {
    const data = await publishingApi.listPlatforms()
    // Merge API response into existing platforms to preserve order
    for (const p of data) {
      const existing = platforms.value.find(e => e.id === p.id)
      if (existing) { Object.assign(existing, p) }
      else { platforms.value.push(p) }
    }
  } catch { /* empty */ }
}

async function loadJobs() {
  loading.value = true
  try {
    jobs.value = await publishingApi.listJobs()
  } finally {
    loading.value = false
  }
}

// ── Login capture with polling ────────────────────────────────
function startCountdown(seconds: number) {
  captureCountdown.value = seconds
  stopCountdown()
  countdownTimer = setInterval(() => {
    captureCountdown.value--
    if (captureCountdown.value <= 0) stopCountdown()
  }, 1000)
}
function stopCountdown() {
  if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
}

function startStatusPoll(platform: string) {
  stopStatusPoll()
  statusPollTimer = setInterval(async () => {
    try {
      const status = await publishingApi.getLoginStatus(platform)
      if (status.ready) {
        message.success('登录态采集成功！')
        stopStatusPoll()
        stopCountdown()
        capturingPlatform.value = null
        await loadPlatforms()
      }
    } catch { /* ignore */ }
  }, 3000)
}
function stopStatusPoll() {
  if (statusPollTimer) { clearInterval(statusPollTimer); statusPollTimer = null }
}

async function captureLogin(platform: string) {
  capturingPlatform.value = platform
  const timeout = 300
  startCountdown(timeout)
  startStatusPoll(platform)

  try {
    await publishingApi.captureLogin(platform, timeout)
    message.success('登录态采集成功')
    await loadPlatforms()
  } catch (e: any) {
    const status = e.response?.status
    const detail = e.response?.data?.detail
    if (status === 408) {
      message.warning('登录超时，请重试')
    } else if (status === 500 && detail?.includes('playwright')) {
      message.error('未安装 Playwright，请在后端运行: pip install playwright && playwright install chromium')
    } else if (e.code === 'ECONNABORTED') {
      message.warning('请求超时，请检查后端是否还在运行登录采集')
    } else {
      message.error(detail || '登录态采集失败')
    }
  } finally {
    capturingPlatform.value = null
    stopCountdown()
    stopStatusPoll()
  }
}

async function clearLogin(platform: string) {
  if (!confirm('确定清除登录态？清除后需要重新登录')) return
  try {
    await publishingApi.clearLogin(platform)
    await loadPlatforms()
    message.success('已清除登录态')
  } catch {
    message.error('清除失败')
  }
}

// ── Schedule publish ──────────────────────────────────────────
const showSchedule = ref(false)
const scheduling = ref(false)
const scheduleForm = ref({ novel_id: '', platform: 'fanqie' as string })

const novelOptions = computed(() =>
  novelsStore.novels.map(n => ({ label: n.title, value: n.id }))
)

const platformMeta: Record<string, { name: string; icon: string; color: string; bg: string; url: string }> = {
  fanqie: { name: '番茄小说', icon: '🍅', color: '#ef4444', bg: '#fef2f2', url: 'fanqienovel.com' },
  qidian: { name: '起点中文网', icon: '📖', color: '#3b82f6', bg: '#eff6ff', url: 'write.qq.com' },
}

async function handleSchedule() {
  if (!scheduleForm.value.novel_id) { message.warning('请选择作品'); return }
  scheduling.value = true
  try {
    const result = await publishingApi.schedule({
      novel_id: scheduleForm.value.novel_id,
      platform: scheduleForm.value.platform,
    })
    message.success(`已创建 ${result.count} 个发布任务`)
    showSchedule.value = false
    await loadJobs()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '创建失败')
  } finally {
    scheduling.value = false
  }
}

// ── Job actions ───────────────────────────────────────────────
async function cancelJob(id: string) {
  try {
    await publishingApi.cancelJob(id)
    await loadJobs()
    message.success('已取消')
  } catch { message.error('取消失败') }
}

async function retryJob(id: string) {
  try {
    await publishingApi.retryJob(id)
    await loadJobs()
    message.success('已重新加入队列')
  } catch { message.error('重试失败') }
}

const statusLabel: Record<string, { text: string; cls: string }> = {
  pending: { text: '等待中', cls: 'st-pending' },
  publishing: { text: '发布中', cls: 'st-publishing' },
  success: { text: '成功', cls: 'st-success' },
  failed: { text: '失败', cls: 'st-failed' },
  cancelled: { text: '已取消', cls: 'st-cancelled' },
}

function fmtTime(s: string | null) {
  if (!s) return '-'
  return new Date(s).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function fmtCountdown(s: number) {
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${sec.toString().padStart(2, '0')}`
}

onMounted(async () => {
  await Promise.all([loadPlatforms(), loadJobs(), novelsStore.loadNovels()])
})
onBeforeUnmount(() => { stopCountdown(); stopStatusPoll() })
</script>

<template>
  <div class="pg">
    <div class="pg-header">
      <div>
        <h1 class="pg-title">发布中心</h1>
        <p class="pg-desc">管理平台登录态，创建和监控发布任务</p>
      </div>
      <button class="btn btn-primary" @click="showSchedule = true">+ 创建发布任务</button>
    </div>

    <!-- ═══ Platform Cards ═══ -->
    <section class="pg-section">
      <div class="section-head">
        <h3 class="section-title">平台登录</h3>
        <span class="section-hint">采集浏览器登录态后即可自动发布</span>
      </div>

      <div class="platform-grid">
        <div v-for="p in platforms" :key="p.id" class="plat-card">
          <div class="plat-top">
            <div class="plat-icon" :style="{ background: platformMeta[p.id]?.bg, color: platformMeta[p.id]?.color }">
              {{ platformMeta[p.id]?.icon || '📤' }}
            </div>
            <div class="plat-info">
              <div class="plat-name">{{ p.name }}</div>
              <div class="plat-url">{{ platformMeta[p.id]?.url || '' }}</div>
            </div>
            <div class="plat-status" :class="p.login_ready ? 'ready' : 'not-ready'">
              {{ p.login_ready ? '✓ 已登录' : '未配置' }}
            </div>
          </div>

          <div class="plat-detail">
            <span class="plat-msg">{{ p.login_status }}</span>
            <span v-if="p.modified_at" class="plat-time">{{ p.modified_at.slice(0, 10) }}</span>
          </div>

          <!-- Capturing banner -->
          <div v-if="capturingPlatform === p.id" class="capture-banner">
            <div class="capture-indicator">
              <span class="capture-dot"></span>
              <span>浏览器已打开，请完成登录…</span>
            </div>
            <span class="capture-countdown">{{ fmtCountdown(captureCountdown) }}</span>
          </div>

          <div class="plat-actions">
            <button
              class="btn"
              :class="p.login_ready ? 'btn-ghost' : 'btn-primary'"
              :disabled="capturingPlatform === p.id"
              @click="captureLogin(p.id)"
            >
              <template v-if="capturingPlatform === p.id">⏳ 等待登录...</template>
              <template v-else>{{ p.login_ready ? '🔄 重新登录' : '🔑 配置登录' }}</template>
            </button>
            <button v-if="p.login_ready" class="btn btn-danger-ghost" @click="clearLogin(p.id)">清除</button>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══ Job Queue ═══ -->
    <section class="pg-section">
      <div class="section-head">
        <div class="section-left">
          <h3 class="section-title">发布队列</h3>
          <span class="section-count">{{ jobs.length }} 条</span>
        </div>
        <button class="btn btn-ghost btn-sm" @click="loadJobs">🔄 刷新</button>
      </div>

      <div v-if="jobs.length === 0 && !loading" class="empty-state">
        <div class="empty-visual">📤</div>
        <div class="empty-title">暂无发布任务</div>
        <div class="empty-desc">创建发布任务后，系统将自动按计划发布</div>
        <button class="btn btn-primary btn-sm" @click="showSchedule = true">+ 创建任务</button>
      </div>

      <div v-else class="job-table">
        <div class="jt-header">
          <span class="jt-col col-platform">平台</span>
          <span class="jt-col col-chapter">章节ID</span>
          <span class="jt-col col-status">状态</span>
          <span class="jt-col col-retry">重试</span>
          <span class="jt-col col-error">错误信息</span>
          <span class="jt-col col-time">创建时间</span>
          <span class="jt-col col-actions">操作</span>
        </div>
        <div v-for="j in jobs" :key="j.id" class="jt-row">
          <span class="jt-col col-platform">
            <span class="jt-platform-tag" :style="{ color: platformMeta[j.platform]?.color, background: platformMeta[j.platform]?.bg }">
              {{ platformMeta[j.platform]?.icon }} {{ j.platform === 'fanqie' ? '番茄' : '起点' }}
            </span>
          </span>
          <span class="jt-col col-chapter jt-mono">{{ j.chapter_id.slice(0, 8) }}…</span>
          <span class="jt-col col-status">
            <span class="jt-status" :class="statusLabel[j.status]?.cls || ''">
              {{ statusLabel[j.status]?.text || j.status }}
            </span>
          </span>
          <span class="jt-col col-retry">{{ j.retry_count }}</span>
          <span class="jt-col col-error" :title="j.error_message || ''">{{ j.error_message || '-' }}</span>
          <span class="jt-col col-time">{{ fmtTime(j.created_at) }}</span>
          <span class="jt-col col-actions">
            <button v-if="j.status === 'pending'" class="act-btn danger" title="取消" @click="cancelJob(j.id)">✕</button>
            <button v-if="j.status === 'failed'" class="act-btn" title="重试" @click="retryJob(j.id)">🔄</button>
          </span>
        </div>
      </div>
    </section>

    <!-- ═══ Schedule Modal ═══ -->
    <n-modal v-model:show="showSchedule" :mask-closable="false" style="width:480px;max-width:94vw">
      <div class="modal-wrap">
        <div class="modal-header">
          <h3>创建发布任务</h3>
          <button class="modal-close" @click="showSchedule = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <label>作品</label>
            <select v-model="scheduleForm.novel_id" class="form-select">
              <option value="" disabled>请选择作品</option>
              <option v-for="o in novelOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </div>
          <div class="form-row">
            <label>平台</label>
            <div class="platform-picker">
              <button
                v-for="(meta, key) in platformMeta" :key="key"
                :class="['pp-btn', { active: scheduleForm.platform === key }]"
                :style="scheduleForm.platform === key ? { borderColor: meta.color, background: meta.bg, color: meta.color } : {}"
                @click="scheduleForm.platform = key"
              >
                {{ meta.icon }} {{ meta.name }}
              </button>
            </div>
          </div>
          <div class="form-hint">
            将为所选作品的所有章节创建发布任务
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="showSchedule = false">取消</button>
          <button class="btn btn-primary" :disabled="scheduling" @click="handleSchedule">
            {{ scheduling ? '创建中...' : '创建任务' }}
          </button>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<style scoped>
.pg{max-width:1000px}

/* Header */
.pg-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:24px}
.pg-title{font-size:22px;font-weight:800;color:var(--gray-900);letter-spacing:-.3px}
.pg-desc{font-size:13px;color:var(--gray-400);margin-top:6px}

/* Sections */
.pg-section{background:#fff;border:1px solid var(--gray-200);border-radius:16px;padding:22px;margin-bottom:16px;
  animation:fadeIn .2s}
@keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.section-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:8px}
.section-left{display:flex;align-items:center;gap:8px}
.section-title{font-size:15px;font-weight:600;color:var(--gray-800)}
.section-hint{font-size:12px;color:var(--gray-400)}
.section-count{font-size:11px;color:var(--gray-400);background:var(--gray-100);padding:2px 8px;border-radius:10px;font-weight:500}
.btn-sm{padding:6px 12px;font-size:12px}

/* ── Platform Cards ── */
.platform-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:14px}
.plat-card{border:1px solid var(--gray-200);border-radius:14px;padding:20px;transition:all .18s}
.plat-card:hover{border-color:var(--gray-300);box-shadow:0 4px 16px rgba(0,0,0,.06)}
.plat-top{display:flex;align-items:center;gap:12px;margin-bottom:10px}
.plat-icon{width:44px;height:44px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0}
.plat-info{flex:1;min-width:0}
.plat-name{font-size:15px;font-weight:600;color:var(--gray-800)}
.plat-url{font-size:11px;color:var(--gray-400);margin-top:1px}
.plat-status{font-size:11px;padding:3px 10px;border-radius:10px;font-weight:600;flex-shrink:0}
.plat-status.ready{background:#dcfce7;color:#16a34a}
.plat-status.not-ready{background:var(--gray-100);color:var(--gray-400)}

.plat-detail{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;
  padding:10px 14px;background:var(--gray-50);border-radius:10px}
.plat-msg{font-size:12px;color:var(--gray-500)}
.plat-time{font-size:11px;color:var(--gray-300)}

/* Capture banner */
.capture-banner{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;
  margin-bottom:12px;background:linear-gradient(90deg,#eef2ff,#f5f3ff);border:1px solid #e0e7ff;
  border-radius:12px;animation:fadeIn .3s}
.capture-indicator{display:flex;align-items:center;gap:8px;font-size:13px;color:#6366f1;font-weight:500}
.capture-dot{width:8px;height:8px;border-radius:50%;background:#6366f1;animation:blink 1.2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
.capture-countdown{font-size:14px;font-weight:700;color:#6366f1;font-variant-numeric:tabular-nums}

.plat-actions{display:flex;gap:8px}
.btn-danger-ghost{background:none;border:1px solid #fecaca;color:#ef4444;font-size:12px;padding:6px 12px;
  border-radius:var(--radius-xs);cursor:pointer;transition:all .15s}
.btn-danger-ghost:hover{background:#fef2f2;border-color:#f87171}

/* ── Job Table ── */
.job-table{border:1px solid var(--gray-200);border-radius:12px;overflow:hidden}
.jt-header{display:flex;align-items:center;padding:10px 16px;background:var(--gray-50);border-bottom:1px solid var(--gray-200);
  font-size:12px;font-weight:600;color:var(--gray-500)}
.jt-row{display:flex;align-items:center;padding:12px 16px;border-bottom:1px solid var(--gray-100);
  font-size:13px;transition:background .12s}
.jt-row:last-child{border-bottom:none}
.jt-row:hover{background:var(--gray-50)}

.jt-col{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.col-platform{width:90px;flex-shrink:0}
.col-chapter{width:100px;flex-shrink:0}
.col-status{width:80px;flex-shrink:0}
.col-retry{width:50px;flex-shrink:0;text-align:center}
.col-error{flex:1;min-width:0;color:var(--gray-400);font-size:12px}
.col-time{width:100px;flex-shrink:0;color:var(--gray-400);font-size:12px}
.col-actions{width:70px;flex-shrink:0;display:flex;justify-content:flex-end;gap:4px}

.jt-platform-tag{font-size:11px;padding:2px 8px;border-radius:6px;font-weight:500;display:inline-flex;align-items:center;gap:3px}
.jt-mono{font-family:ui-monospace,monospace;font-size:11px;color:var(--gray-500)}
.jt-status{font-size:11px;padding:2px 8px;border-radius:10px;font-weight:600}
.st-pending{background:var(--gray-100);color:var(--gray-500)}
.st-publishing{background:#fef3c7;color:#d97706}
.st-success{background:#dcfce7;color:#16a34a}
.st-failed{background:#fee2e2;color:#dc2626}
.st-cancelled{background:var(--gray-100);color:var(--gray-400)}

.act-btn{width:28px;height:28px;border:none;background:none;border-radius:var(--radius-xs);
  cursor:pointer;font-size:12px;display:flex;align-items:center;justify-content:center;transition:all .12s}
.act-btn:hover{background:var(--gray-100)}
.act-btn.danger:hover{background:#fee2e2}

/* Empty */
.empty-state{text-align:center;padding:48px 20px}
.empty-visual{font-size:40px;margin-bottom:12px}
.empty-title{font-size:15px;font-weight:600;color:var(--gray-500);margin-bottom:4px}
.empty-desc{font-size:13px;color:var(--gray-400);margin-bottom:16px}

/* ── Modal ── */
.modal-wrap{background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.15)}
.modal-header{display:flex;align-items:center;justify-content:space-between;padding:20px 24px;
  border-bottom:1px solid var(--gray-200)}
.modal-header h3{font-size:16px;font-weight:700;color:var(--gray-800)}
.modal-close{width:32px;height:32px;border:none;background:none;border-radius:var(--radius-xs);
  cursor:pointer;font-size:16px;color:var(--gray-400);display:flex;align-items:center;justify-content:center;
  transition:all .12s}
.modal-close:hover{background:var(--gray-100);color:var(--gray-700)}

.modal-body{padding:24px;display:flex;flex-direction:column;gap:18px}
.form-row{display:flex;flex-direction:column;gap:6px}
.form-row label{font-size:12px;font-weight:600;color:var(--gray-500);text-transform:uppercase;letter-spacing:.3px}
.form-select{padding:10px 14px;border:1px solid var(--gray-200);border-radius:var(--radius-xs);
  font-size:13px;color:var(--gray-700);outline:none;background:#fff;transition:border-color .15s;width:100%;
  -webkit-appearance:none;appearance:none;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%239ca3af' viewBox='0 0 16 16'%3E%3Cpath d='M8 11L3 6h10z'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 12px center}
.form-select:focus{border-color:var(--primary)}
.form-hint{font-size:12px;color:var(--gray-400);padding:8px 12px;background:var(--gray-50);
  border-radius:var(--radius-xs);border-left:3px solid var(--primary)}

.platform-picker{display:flex;gap:8px}
.pp-btn{padding:10px 16px;border:1.5px solid var(--gray-200);border-radius:var(--radius-xs);
  background:#fff;font-size:13px;cursor:pointer;transition:all .12s;color:var(--gray-500);flex:1;text-align:center}
.pp-btn:hover{border-color:var(--gray-300);background:var(--gray-50)}
.pp-btn.active{font-weight:600}

.modal-footer{display:flex;justify-content:flex-end;gap:8px;padding:16px 24px;
  border-top:1px solid var(--gray-200);background:var(--gray-50)}

@media (max-width:700px) {
  .platform-grid{grid-template-columns:1fr}
  .col-error,.col-retry{display:none}
}
</style>
