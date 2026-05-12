<script setup lang="ts">
import { NSpin, useMessage } from 'naive-ui'
import { ref, onMounted, watch } from 'vue'
import { dataApi, type FanqieBook, type FanqieBookStats } from '@/api/data'

const message = useMessage()
const loading = ref(false)
const collecting = ref(false)

// ── Fanqie books from API
const fanqieBooks = ref<FanqieBook[]>([])
const selectedBookId = ref<string | null>(null)
const bookStats = ref<FanqieBookStats | null>(null)
const loadingStats = ref(false)
const loginReady = ref(true)
const errorMsg = ref('')
const showCookieDialog = ref(false)
const cookieInput = ref('')
const importingCookie = ref(false)

// ── Computed totals from all books
function totalReads() { return fanqieBooks.value.reduce((s, b) => s + b.read_count, 0) }
function totalFavs() { return fanqieBooks.value.reduce((s, b) => s + b.favorite_count, 0) }
function totalComments() { return fanqieBooks.value.reduce((s, b) => s + b.comment_count, 0) }
function totalWords() { return fanqieBooks.value.reduce((s, b) => s + b.word_count, 0) }

async function loadFanqieBooks() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await dataApi.fanqieBooks()
    fanqieBooks.value = res.books || []
    loginReady.value = true
    if (fanqieBooks.value.length > 0 && !selectedBookId.value) {
      selectedBookId.value = fanqieBooks.value[0].book_id
    }
  } catch (e: any) {
    const detail = e?.response?.data?.detail || ''
    if (detail.includes('登录态')) {
      loginReady.value = false
      errorMsg.value = '请先在发布中心配置番茄小说登录态'
    } else {
      errorMsg.value = detail || '加载失败'
    }
  } finally {
    loading.value = false
  }
}

async function loadBookStats(bookId: string) {
  loadingStats.value = true
  try {
    bookStats.value = await dataApi.fanqieBookStats(bookId)
  } catch {
    bookStats.value = null
  } finally {
    loadingStats.value = false
  }
}

watch(selectedBookId, (id) => { if (id) loadBookStats(id) })

async function triggerCollect() {
  collecting.value = true
  try {
    const res = await dataApi.triggerCollect()
    message.success(`\u91C7\u96C6\u5B8C\u6210: ${res.books_count} \u672C\u4E66, \u65B0\u589E ${res.saved} \u6761\u8BB0\u5F55`)
    await loadFanqieBooks()
  } catch (e: any) {
    const detail = e?.response?.data?.detail || ''
    if (detail.includes('\u767B\u5F55\u6001')) {
      loginReady.value = false
      errorMsg.value = detail
    } else {
      message.error(detail || '\u91C7\u96C6\u5931\u8D25')
    }
  } finally {
    collecting.value = false
  }
}

async function checkCookieStatus() {
  try {
    const status = await dataApi.cookieStatus()
    loginReady.value = status.fanqie?.ready || false
    if (!loginReady.value) {
      errorMsg.value = status.fanqie?.message || '\u756A\u8304 Cookie \u672A\u914D\u7F6E'
    }
  } catch { /* ignore */ }
}

async function handleImportCookie() {
  if (!cookieInput.value.trim()) { message.warning('\u8BF7\u7C98\u8D34 Cookie'); return }
  importingCookie.value = true
  try {
    const res = await dataApi.importCookies('fanqie', cookieInput.value.trim())
    message.success(res.message)
    showCookieDialog.value = false
    cookieInput.value = ''
    loginReady.value = true
    errorMsg.value = ''
    await loadFanqieBooks()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '\u5BFC\u5165\u5931\u8D25')
  } finally {
    importingCookie.value = false
  }
}

onMounted(async () => {
  await checkCookieStatus()
  if (loginReady.value) await loadFanqieBooks()
})

function fmtNum(n: number): string {
  if (n >= 100000) return (n / 10000).toFixed(1) + '\u4E07'
  if (n >= 10000) return (n / 10000).toFixed(2) + '\u4E07'
  return n.toLocaleString()
}
function fmtWords(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + '\u4E07\u5B57'
  return n.toLocaleString() + '\u5B57'
}
</script>

<template>
  <div class="page-data">
    <div class="page-head-row">
      <div>
        <h1 class="page-title">&#x1F4CA; 数据看板</h1>
        <p class="page-desc">番茄小说作者后台数据实时概览</p>
      </div>
      <div class="head-controls">
        <button class="btn btn-primary" :disabled="collecting" @click="triggerCollect">
          {{ collecting ? '⏳ 采集中...' : '📡 采集数据' }}
        </button>
        <button class="btn btn-ghost" @click="loadFanqieBooks">🔄 刷新</button>
      </div>
    </div>

    <!-- Login not ready -->
    <div v-if="!loginReady" class="alert-box">
      <span class="alert-icon">&#x26A0;&#xFE0F;</span>
      <div class="alert-body">
        <div class="alert-title">{{ errorMsg || '番茄 Cookie 未配置' }}</div>
        <div class="alert-sub">需要导入番茄小说浏览器 Cookie 才能获取数据</div>
        <button class="btn btn-primary btn-sm" style="margin-top:8px" @click="showCookieDialog = true">&#x1F510; 导入 Cookie</button>
      </div>
    </div>

    <!-- Cookie import dialog -->
    <div v-if="showCookieDialog" class="modal-overlay" @click.self="showCookieDialog = false">
      <div class="modal-box">
        <div class="modal-header">
          <h3>导入番茄小说 Cookie</h3>
          <button class="modal-close" @click="showCookieDialog = false">&times;</button>
        </div>
        <div class="modal-body">
          <div class="import-steps">
            <p><b>1.</b> 打开 <a href="https://fanqienovel.com/main/writer/data" target="_blank" class="link">fanqienovel.com</a> 并登录</p>
            <p><b>2.</b> 按 F12 → Application → Cookies</p>
            <p><b>3.</b> 复制所有 cookie（或从 DevTools 网络请求头中复制 Cookie 字段）</p>
          </div>
          <textarea v-model="cookieInput" class="cookie-textarea" rows="5"
            placeholder="sessionid=xxx; novel_web_id=yyy; sid_tt=zzz; ..."></textarea>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="showCookieDialog = false">取消</button>
          <button class="btn btn-primary" :disabled="importingCookie" @click="handleImportCookie">
            {{ importingCookie ? '导入中...' : '确认导入' }}
          </button>
        </div>
      </div>
    </div>

    <n-spin :show="loading">
      <!-- Stats row -->
      <div v-if="fanqieBooks.length > 0" class="stat-grid">
        <div class="stat-card">
          <div class="sc-icon" style="background:#eff6ff;color:#3b82f6">&#x1F441;</div>
          <div class="sc-body">
            <div class="sc-value">{{ fmtNum(totalReads()) }}</div>
            <div class="sc-label">总阅读</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="sc-icon" style="background:#f0fdf4;color:#22c55e">⭐</div>
          <div class="sc-body">
            <div class="sc-value">{{ fmtNum(totalFavs()) }}</div>
            <div class="sc-label">总收藏</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="sc-icon" style="background:#faf5ff;color:#a855f7">&#x1F4AC;</div>
          <div class="sc-body">
            <div class="sc-value">{{ fmtNum(totalComments()) }}</div>
            <div class="sc-label">总评论</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="sc-icon" style="background:#fff7ed;color:#f97316">&#x1F4DD;</div>
          <div class="sc-body">
            <div class="sc-value">{{ fmtWords(totalWords()) }}</div>
            <div class="sc-label">总字数</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="sc-icon" style="background:#fef3c7;color:#f59e0b">&#x1F4D6;</div>
          <div class="sc-body">
            <div class="sc-value">{{ fanqieBooks.length }}</div>
            <div class="sc-label">作品数</div>
          </div>
        </div>
      </div>

      <!-- Book cards -->
      <div v-if="fanqieBooks.length > 0" class="book-section">
        <div class="section-head">
          <h2>&#x1F345; 作品概览</h2>
          <span class="section-sub">点击作品查看详细数据趋势</span>
        </div>
        <div class="book-grid">
          <div v-for="b in fanqieBooks" :key="b.book_id"
            :class="['book-card', { active: selectedBookId === b.book_id }]"
            @click="selectedBookId = b.book_id"
          >
            <div class="bc-cover" v-if="b.cover_url">
              <img :src="b.cover_url" :alt="b.title" />
            </div>
            <div class="bc-cover bc-placeholder" v-else>&#x1F4D5;</div>
            <div class="bc-body">
              <div class="bc-title">{{ b.title }}</div>
              <div class="bc-meta">
                <span v-if="b.category" class="bc-cat">{{ b.category }}</span>
                <span>{{ fmtWords(b.word_count) }}</span>
                <span>{{ b.chapter_count }}章</span>
              </div>
              <div class="bc-stats">
                <span class="bc-stat"><span class="bcs-val">{{ fmtNum(b.read_count) }}</span>读</span>
                <span class="bc-stat"><span class="bcs-val">{{ fmtNum(b.favorite_count) }}</span>藏</span>
                <span class="bc-stat"><span class="bcs-val">{{ fmtNum(b.comment_count) }}</span>评</span>
              </div>
              <div class="bc-status">{{ b.creation_status || '连载中' }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Book detail stats (snapshot) -->
      <div v-if="selectedBookId && bookStats?.stats" class="detail-section">
        <div class="section-head">
          <h2>&#x1F4C8; {{ bookStats.stats.book_name }} — 实时数据</h2>
        </div>
        <n-spin :show="loadingStats" size="small">
          <div class="detail-grid">
            <div class="detail-card">
              <div class="dc-label">日读者 UV</div>
              <div class="dc-val">{{ bookStats.stats.reader_uv_daily }}</div>
              <div :class="['dc-incr', Number(bookStats.stats.reader_uv_daily_incr) >= 0 ? 'up' : 'down']">
                {{ Number(bookStats.stats.reader_uv_daily_incr) >= 0 ? '↑' : '↓' }}{{ bookStats.stats.reader_uv_daily_incr }}%
              </div>
            </div>
            <div class="detail-card">
              <div class="dc-label">14天读者</div>
              <div class="dc-val">{{ bookStats.stats.reader_uv_14day }}</div>
              <div :class="['dc-incr', Number(bookStats.stats.reader_uv_14day_incr) >= 0 ? 'up' : 'down']">
                {{ Number(bookStats.stats.reader_uv_14day_incr) >= 0 ? '↑' : '↓' }}{{ bookStats.stats.reader_uv_14day_incr }}%
              </div>
            </div>
            <div class="detail-card">
              <div class="dc-label">日收藏</div>
              <div class="dc-val">{{ bookStats.stats.shelf_cnt_daily }}</div>
              <div :class="['dc-incr', Number(bookStats.stats.shelf_cnt_daily_incr) >= 0 ? 'up' : 'down']">
                {{ Number(bookStats.stats.shelf_cnt_daily_incr) >= 0 ? '↑' : '↓' }}{{ bookStats.stats.shelf_cnt_daily_incr }}%
              </div>
            </div>
            <div class="detail-card">
              <div class="dc-label">读完率</div>
              <div class="dc-val">{{ bookStats.stats.read_completion_rate }}%</div>
            </div>
            <div class="detail-card">
              <div class="dc-label">追读率</div>
              <div class="dc-val">{{ bookStats.stats.pursue_read_rate }}%</div>
            </div>
            <div class="detail-card">
              <div class="dc-label">评分</div>
              <div class="dc-val">{{ bookStats.stats.mark_score || '-' }}</div>
            </div>
            <div class="detail-card">
              <div class="dc-label">分类排名</div>
              <div class="dc-val">{{ bookStats.stats.rank_cat > 0 ? '#' + bookStats.stats.rank_cat : '-' }}</div>
            </div>
            <div class="detail-card">
              <div class="dc-label">风险等级</div>
              <div class="dc-val">{{ bookStats.stats.risk_rate }}</div>
            </div>
          </div>

          <!-- Intro text -->
          <div v-if="bookStats.stats.main_intro" class="intro-box">
            <span v-html="bookStats.stats.main_intro"></span>
            <span v-if="bookStats.stats.sub_intro" class="intro-sub" v-html="'\u00A0\u00B7\u00A0' + bookStats.stats.sub_intro"></span>
          </div>
        </n-spin>
      </div>

      <!-- Empty state -->
      <div v-if="fanqieBooks.length === 0 && loginReady && !loading" class="empty-state">
        <div class="empty-icon">&#x1F4CA;</div>
        <div>暂无作品数据</div>
        <div class="empty-sub">点击「采集数据」从番茄后台拉取</div>
      </div>
    </n-spin>
  </div>
</template>

<style scoped>
.page-data{max-width:1100px}
.page-head-row{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:22px}
.page-title{font-size:22px;font-weight:800;color:var(--gray-900);letter-spacing:-.3px}
.page-desc{font-size:13px;color:var(--gray-400);margin-top:6px}
.head-controls{display:flex;gap:8px;align-items:center}

/* Alert */
.alert-box{display:flex;align-items:flex-start;gap:12px;padding:18px 22px;margin-bottom:20px;
  background:#fffbeb;border:1px solid #fde68a;border-radius:14px}
.alert-icon{font-size:20px}
.alert-title{font-size:14px;font-weight:600;color:#92400e}
.alert-sub{font-size:12px;color:#a16207;margin-top:2px}

/* Stats */
.stat-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:22px}
.stat-card{display:flex;align-items:center;gap:14px;padding:18px;background:#fff;
  border:1px solid var(--gray-200);border-radius:14px;transition:all .18s}
.stat-card:hover{box-shadow:0 4px 16px rgba(0,0,0,.06);transform:translateY(-2px)}
.sc-icon{width:44px;height:44px;border-radius:12px;display:flex;align-items:center;
  justify-content:center;font-size:20px;flex-shrink:0}
.sc-body{min-width:0}
.sc-value{font-size:18px;font-weight:700;color:var(--gray-800)}
.sc-label{font-size:12px;color:var(--gray-400);margin-top:2px}

/* Book section */
.book-section{margin-bottom:24px}
.section-head{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.section-head h2{font-size:15px;font-weight:600;color:var(--gray-700)}
.section-sub{font-size:12px;color:var(--gray-400)}

.book-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.book-card{display:flex;gap:14px;background:#fff;border:1px solid var(--gray-200);
  border-radius:14px;padding:16px;cursor:pointer;transition:all .18s}
.book-card:hover{box-shadow:0 4px 16px rgba(0,0,0,.06);transform:translateY(-2px)}
.book-card.active{border-color:var(--primary);box-shadow:0 0 0 3px rgba(99,102,241,.12)}
.bc-cover{width:56px;height:76px;border-radius:6px;overflow:hidden;flex-shrink:0;background:var(--gray-100)}
.bc-cover img{width:100%;height:100%;object-fit:cover}
.bc-placeholder{display:flex;align-items:center;justify-content:center;font-size:24px}
.bc-body{flex:1;min-width:0;display:flex;flex-direction:column;gap:4px}
.bc-title{font-size:14px;font-weight:600;color:var(--gray-800);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bc-meta{font-size:11px;color:var(--gray-400);display:flex;gap:6px;flex-wrap:wrap}
.bc-cat{color:var(--primary);font-weight:500}
.bc-stats{display:flex;gap:12px;margin-top:auto}
.bc-stat{font-size:11px;color:var(--gray-500)}
.bcs-val{font-weight:700;color:var(--gray-700);margin-right:2px}
.bc-status{font-size:10px;padding:1px 8px;border-radius:10px;background:#dcfce7;color:#16a34a;
  font-weight:600;width:fit-content;margin-top:2px}

/* Detail section */
.detail-section{margin-bottom:24px}
.detail-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:12px}
.detail-card{background:#fff;border:1px solid var(--gray-200);border-radius:14px;
  padding:16px 18px;text-align:center;transition:all .18s}
.detail-card:hover{box-shadow:0 4px 16px rgba(0,0,0,.06);transform:translateY(-2px)}
.dc-label{font-size:11px;color:var(--gray-400);margin-bottom:6px}
.dc-val{font-size:20px;font-weight:700;color:var(--gray-800)}
.dc-incr{font-size:11px;margin-top:4px;font-weight:600}
.dc-incr.up{color:#16a34a}
.dc-incr.down{color:#dc2626}
.intro-box{background:#f8fafc;border:1px solid var(--gray-200);border-radius:12px;
  padding:14px 18px;font-size:13px;color:var(--gray-600);line-height:1.6}
.intro-box :deep(i){font-style:normal;font-weight:700;color:var(--primary)}
.intro-sub{color:var(--gray-400)}

/* Empty */
.empty-state{text-align:center;padding:60px 20px;background:#fff;border:2px dashed var(--gray-200);
  border-radius:16px;color:var(--gray-400);font-size:14px}
.empty-state .empty-icon{font-size:40px;margin-bottom:8px}
.empty-state .empty-sub{font-size:12px;margin-top:4px}

/* Modal */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.4);display:flex;
  align-items:center;justify-content:center;z-index:1000}
.modal-box{background:#fff;border-radius:16px;width:520px;max-width:90vw;box-shadow:0 20px 60px rgba(0,0,0,.2)}
.modal-header{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--gray-200)}
.modal-header h3{font-size:16px;font-weight:600;color:var(--gray-800)}
.modal-close{background:none;border:none;font-size:18px;cursor:pointer;color:var(--gray-400);padding:4px 8px}
.modal-close:hover{color:var(--gray-700)}
.modal-body{padding:16px 20px}
.modal-footer{display:flex;justify-content:flex-end;gap:8px;padding:12px 20px;border-top:1px solid var(--gray-200)}
.import-steps{margin-bottom:12px;font-size:13px;color:var(--gray-600);line-height:1.8}
.import-steps p{margin:0}
.link{color:var(--primary);text-decoration:underline}
.cookie-textarea{width:100%;border:1px solid var(--gray-200);border-radius:8px;padding:10px 12px;
  font-family:monospace;font-size:12px;resize:vertical;outline:none;color:var(--gray-700)}
.cookie-textarea:focus{border-color:var(--primary);box-shadow:0 0 0 2px rgba(99,102,241,.12)}
.btn-sm{padding:4px 12px;font-size:12px}

@media (max-width:900px) {
  .stat-grid{grid-template-columns:repeat(2,1fr)}
  .book-grid{grid-template-columns:1fr}
  .totals-bar{grid-template-columns:repeat(2,1fr)}
}
</style>
