<script setup lang="ts">
import { NMessageProvider, NDialogProvider } from 'naive-ui'
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useNovelsStore } from '@/stores/novels'

const router = useRouter()
const route = useRoute()
const store = useNovelsStore()

const navItems = [
  { icon: '📋', label: '工作台', path: '/dashboard' },
  { icon: '✍️', label: '创作台', path: '/studio' },
  { icon: '💡', label: '灵感大纲', path: '/inspiration' },
  { icon: '', label: '拆书分析', path: '/booklab' },
  { icon: '�', label: '作品蓝图', path: '/blueprint' },
  { icon: '📤', label: '发布中心', path: '/publish' },
  { icon: '📊', label: '数据看板', path: '/data' },
  { icon: '📈', label: '数据预测', path: '/predict' },
  { icon: '🤖', label: '学习中心', path: '/learn' },
  { icon: '🧩', label: '提示词', path: '/prompts' },
  { icon: '⚙️', label: '设置', path: '/settings' },
]

const activeKey = computed(() => route.path)
const totalWords = computed(() => store.novels.reduce((s, n) => s + (n.current_word_count || 0), 0))
const currentNovel = computed(() => store.novels[0])
const statusLabel: Record<string, string> = { writing: '连载中', draft: '草稿', completed: '已完结', paused: '暂停' }

const greetWord = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '上午好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

function navigateTo(path: string) {
  router.push(path)
}
</script>

<template>
  <n-message-provider>
  <n-dialog-provider>
  <div class="app-layout">
    <!-- ========== Left Sidebar ========== -->
    <aside class="sidebar">
      <div class="sidebar-logo">
        <div class="logo-icon">墨</div>
        <span class="logo-text">墨语小说</span>
        <span class="badge">专业版</span>
      </div>

      <nav class="sidebar-nav">
        <div
          v-for="item in navItems"
          :key="item.path"
          class="nav-item"
          :class="{ active: activeKey === item.path }"
          @click="navigateTo(item.path)"
        >
          <span class="icon">{{ item.icon }}</span>{{ item.label }}
        </div>
      </nav>

      <div class="sidebar-bottom">
        <div class="novel-widget" v-if="currentNovel" @click="navigateTo('/studio')">
          <div class="nw-head">
            <span class="nw-label">当前作品</span>
          </div>
          <div class="nw-title">《{{ currentNovel.title }}》</div>
          <div class="nw-meta">
            <span>字数: {{ (currentNovel.current_word_count || 0).toLocaleString() }}</span>
          </div>
          <div class="nw-status">
            状态: <span class="nw-status-text">{{ statusLabel[currentNovel.status] || '草稿' }}</span>
          </div>
          <button class="nw-switch" @click.stop="navigateTo('/dashboard')">切换作品</button>
        </div>
        <div class="daily-goal">
          <div class="goal-label">今日写作目标 <span class="edit-btn">编辑</span></div>
          <div class="goal-value">{{ totalWords.toLocaleString() }} <span>字</span></div>
          <div class="goal-status">{{ totalWords > 0 ? '🖊 去写作 →' : '📝 等待开始' }}</div>
        </div>
      </div>

      <div class="sidebar-user">
        <div class="avatar">🖊</div>
        <span class="name">写书的少年</span>
        <div class="actions">
          <span @click="navigateTo('/settings')">⚙️</span>
        </div>
      </div>
    </aside>

    <!-- ========== Main ========== -->
    <div class="main">
      <header class="topbar">
        <div class="topbar-greet">
          <h2>{{ greetWord }}，创作者 👋</h2>
        </div>
        <div class="search-box">
          🔍 <input placeholder="搜索功能、作品、知识">
        </div>
        <div class="topbar-icons">
          <div class="icon-btn">🔔<span class="dot"></span></div>
          <div class="icon-btn">❓</div>
          <div class="top-avatar" @click="navigateTo('/settings')"></div>
        </div>
      </header>

      <div class="content-scroll">
        <router-view />
      </div>
    </div>
  </div>
  </n-dialog-provider>
  </n-message-provider>
</template>

<style>
/* ========== Reset & Variables ========== */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --primary:#6366f1;--primary-light:#eef2ff;--primary-dark:#4f46e5;
  --primary-gradient:linear-gradient(135deg,#818cf8 0%,#6366f1 50%,#4f46e5 100%);
  --success:#22c55e;--warning:#f59e0b;--danger:#ef4444;
  --gray-50:#f8fafc;--gray-100:#f1f5f9;--gray-200:#e2e8f0;--gray-300:#cbd5e1;
  --gray-400:#94a3b8;--gray-500:#64748b;--gray-600:#475569;--gray-700:#334155;
  --gray-800:#1e293b;--gray-900:#0f172a;
  --sidebar-w:220px;--right-w:320px;
  --radius:12px;--radius-sm:8px;--radius-xs:6px;
  --shadow-sm:0 1px 2px rgba(0,0,0,.04);
  --shadow:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);
  --shadow-md:0 4px 6px -1px rgba(0,0,0,.07),0 2px 4px -2px rgba(0,0,0,.05);
  --shadow-lg:0 10px 15px -3px rgba(0,0,0,.08),0 4px 6px -4px rgba(0,0,0,.05);
}
html{font-size:15px}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans SC","Microsoft YaHei",sans-serif;
  background:var(--gray-50);color:var(--gray-800);line-height:1.5;margin:0;padding:0}

/* ========== App Layout ========== */
.app-layout{display:flex;height:100vh;overflow:hidden}

/* ========== Sidebar ========== */
.sidebar{width:var(--sidebar-w);background:#fff;border-right:1px solid var(--gray-200);
  display:flex;flex-direction:column;flex-shrink:0;overflow-y:auto}
.sidebar-logo{padding:20px 16px 16px;display:flex;align-items:center;gap:8px}
.sidebar-logo .logo-icon{width:30px;height:30px;background:var(--primary-gradient);
  border-radius:var(--radius-xs);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:14px}
.sidebar-logo .logo-text{font-size:15px;font-weight:700;color:var(--gray-800);letter-spacing:-.2px}
.sidebar-logo .badge{font-size:10px;background:var(--primary-light);color:var(--primary);
  padding:2px 7px;border-radius:10px;font-weight:600}
.sidebar-nav{flex:1;padding:4px 10px}
.nav-item{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:var(--radius-sm);
  cursor:pointer;color:var(--gray-500);font-size:13.5px;transition:all .15s;margin-bottom:1px;
  user-select:none;border-left:3px solid transparent}
.nav-item:hover{background:var(--gray-100);color:var(--gray-700)}
.nav-item.active{background:var(--primary-light);color:var(--primary);font-weight:600;
  border-left-color:var(--primary)}
.nav-item .icon{width:20px;text-align:center;font-size:15px;flex-shrink:0}

/* Sidebar bottom */
.sidebar-bottom{padding:12px 14px;border-top:1px solid var(--gray-200)}
.novel-widget{background:var(--gray-50);border-radius:var(--radius-sm);padding:12px;margin-bottom:10px;
  cursor:pointer;transition:all .15s;border:1px solid var(--gray-200)}
.novel-widget:hover{border-color:var(--primary);background:var(--primary-light)}
.nw-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:4px}
.nw-label{font-size:11px;color:var(--gray-400);font-weight:500}
.nw-title{font-size:13px;font-weight:700;color:var(--gray-800);margin-bottom:4px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nw-meta{font-size:11px;color:var(--gray-500);margin-bottom:2px}
.nw-status{font-size:11px;color:var(--gray-400);margin-bottom:8px}
.nw-status-text{color:var(--success);font-weight:500}
.nw-switch{width:100%;padding:5px 0;border:1px solid var(--gray-200);border-radius:var(--radius-xs);
  background:#fff;font-size:12px;color:var(--gray-500);cursor:pointer;transition:all .12s}
.nw-switch:hover{border-color:var(--primary);color:var(--primary)}

.daily-goal{background:var(--gray-50);border-radius:var(--radius-sm);padding:12px}
.daily-goal .goal-label{font-size:11px;color:var(--gray-400);display:flex;align-items:center;gap:6px;margin-bottom:6px;font-weight:500}
.daily-goal .goal-label .edit-btn{font-size:10px;color:var(--primary);cursor:pointer;font-weight:500}
.daily-goal .goal-value{font-size:26px;font-weight:700;color:var(--gray-800);letter-spacing:-.5px}
.daily-goal .goal-value span{font-size:13px;color:var(--gray-400);font-weight:400}
.daily-goal .goal-status{margin-top:6px;font-size:11px;color:var(--primary);cursor:pointer;font-weight:500}
.daily-goal .goal-status:hover{text-decoration:underline}

.sidebar-user{display:flex;align-items:center;gap:10px;padding:12px 16px;border-top:1px solid var(--gray-200)}
.sidebar-user .avatar{width:32px;height:32px;border-radius:50%;background:linear-gradient(135deg,#818cf8,#a78bfa);
  display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px;font-weight:600}
.sidebar-user .name{font-size:13px;font-weight:500;flex:1;color:var(--gray-700)}
.sidebar-user .actions{display:flex;gap:6px}
.sidebar-user .actions span{cursor:pointer;font-size:14px;color:var(--gray-400);transition:color .12s}
.sidebar-user .actions span:hover{color:var(--gray-700)}

/* ========== Main Content ========== */
.main{flex:1;display:flex;flex-direction:column;overflow:hidden;background:var(--gray-50)}
.topbar{padding:14px 28px;background:#fff;border-bottom:1px solid var(--gray-200);
  display:flex;align-items:center;gap:16px;flex-shrink:0}
.topbar-greet{margin-right:auto}
.topbar-greet h2{font-size:16px;font-weight:600;color:var(--gray-800)}
.search-box{display:flex;align-items:center;gap:8px;background:var(--gray-100);
  border-radius:20px;padding:7px 16px;font-size:12px;color:var(--gray-400);min-width:240px;
  border:1px solid transparent;transition:border-color .15s}
.search-box:focus-within{border-color:var(--primary);background:#fff}
.search-box input{border:none;background:none;outline:none;font-size:13px;width:100%;color:var(--gray-600)}
.topbar-icons{display:flex;align-items:center;gap:8px}
.topbar-icons .icon-btn{width:34px;height:34px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;cursor:pointer;color:var(--gray-500);position:relative;font-size:15px;
  transition:all .12s}
.topbar-icons .icon-btn:hover{background:var(--gray-100)}
.topbar-icons .icon-btn .dot{position:absolute;top:5px;right:5px;width:7px;height:7px;
  background:var(--danger);border-radius:50%;border:2px solid #fff}
.topbar .top-avatar{width:34px;height:34px;border-radius:50%;
  background:linear-gradient(135deg,#818cf8,#a78bfa);cursor:pointer;transition:transform .12s}
.topbar .top-avatar:hover{transform:scale(1.05)}

.content-scroll{flex:1;overflow-y:auto;padding:24px 28px}

/* ========== Common Reusable ========== */
.btn{display:inline-flex;align-items:center;gap:6px;padding:7px 16px;border-radius:var(--radius-sm);
  font-size:13px;font-weight:500;cursor:pointer;border:none;transition:all .15s}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn-primary{background:var(--primary);color:#fff}
.btn-primary:hover:not(:disabled){background:var(--primary-dark);box-shadow:0 2px 8px rgba(99,102,241,.25)}
.btn-ghost{background:var(--gray-100);color:var(--gray-600)}
.btn-ghost:hover:not(:disabled){background:var(--gray-200)}

.panel{background:#fff;border-radius:var(--radius);border:1px solid var(--gray-200);overflow:hidden}
.right-card{background:#fff;border-radius:var(--radius);border:1px solid var(--gray-200);
  padding:16px;margin-bottom:16px}
.right-card .card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.right-card .card-title{font-size:14px;font-weight:600}
.right-card .card-link{font-size:11px;color:var(--primary);cursor:pointer}

.status-badge{display:inline-flex;align-items:center;padding:2px 10px;border-radius:10px;font-size:11px;font-weight:500}
.status-badge.published{background:#dcfce7;color:#16a34a}
.status-badge.writing,.status-badge.generated{background:#fef3c7;color:#d97706}
.status-badge.draft{background:var(--gray-100);color:var(--gray-500)}

/* Scrollbar */
::-webkit-scrollbar{width:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--gray-300);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--gray-400)}
</style>
