<script setup lang="ts">
import { ref, nextTick, onMounted, computed } from 'vue'

interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
}

interface SessionItem {
  id: string
  title: string
  message_count: number
  summary: string
  updated_at: string
}

const messages = ref<ChatMsg[]>([])
const inputText = ref('')
const streaming = ref(false)
const chatBox = ref<HTMLElement | null>(null)
const novelCount = ref(0)
const sessionCount = ref(0)

// Session 管理
const sessions = ref<SessionItem[]>([])
const currentSessionId = ref<string>('')
const sidebarOpen = ref(true)

const currentSession = computed(() =>
  sessions.value.find(s => s.id === currentSessionId.value)
)

const quickPrompts = [
  '现在什么题材最火？',
  '帮我分析一下最近的新书趋势',
  '我想写都市文，有什么好的方向？',
  '帮我想 3 个有潜力的故事创意',
  '生成一个玄幻小说的完整大纲',
]

function scrollToBottom() {
  nextTick(() => {
    if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
  })
}

async function fetchSummary() {
  try {
    const r = await fetch('/api/v1/inspiration/context-summary')
    if (r.ok) {
      const d = await r.json()
      novelCount.value = d.total_novels || 0
      sessionCount.value = d.session_count || 0
    }
  } catch { /* ignore */ }
}

async function fetchSessions() {
  try {
    const r = await fetch('/api/v1/inspiration/sessions')
    if (r.ok) sessions.value = await r.json()
  } catch { /* ignore */ }
}

async function loadSession(sessionId: string) {
  if (streaming.value) return
  try {
    const r = await fetch(`/api/v1/inspiration/sessions/${sessionId}`)
    if (!r.ok) return
    const data = await r.json()
    currentSessionId.value = sessionId
    messages.value = (data.messages || []).map((m: any) => ({
      role: m.role,
      content: m.content,
    }))
    scrollToBottom()
  } catch { /* ignore */ }
}

async function newChat() {
  if (streaming.value) return
  currentSessionId.value = ''
  messages.value = []
}

async function deleteSession(sessionId: string) {
  if (!confirm('确定删除此对话？')) return
  try {
    await fetch(`/api/v1/inspiration/sessions/${sessionId}`, { method: 'DELETE' })
    if (currentSessionId.value === sessionId) {
      currentSessionId.value = ''
      messages.value = []
    }
    await fetchSessions()
  } catch { /* ignore */ }
}

async function sendMessage(text?: string) {
  const content = (text || inputText.value).trim()
  if (!content || streaming.value) return

  inputText.value = ''
  messages.value.push({ role: 'user', content })
  messages.value.push({ role: 'assistant', content: '' })
  const assistantIdx = messages.value.length - 1
  streaming.value = true
  scrollToBottom()

  try {
    const resp = await fetch('/api/v1/inspiration/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: currentSessionId.value || null,
        messages: messages.value.slice(0, -1).map(m => ({ role: m.role, content: m.content })),
      }),
    })

    if (!resp.ok || !resp.body) {
      messages.value[assistantIdx].content = '请求失败，请重试'
      streaming.value = false
      return
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const payload = line.slice(6).trim()
        if (payload === '[DONE]') break
        try {
          const parsed = JSON.parse(payload)
          // 首条返回 session_id
          if (parsed.session_id && !currentSessionId.value) {
            currentSessionId.value = parsed.session_id
          }
          if (parsed.content) {
            messages.value[assistantIdx].content += parsed.content
            scrollToBottom()
          }
        } catch { /* skip */ }
      }
    }
  } catch (e) {
    messages.value[assistantIdx].content += '\n\n连接中断，请重试'
  } finally {
    streaming.value = false
    scrollToBottom()
    // 刷新 session 列表
    await fetchSessions()
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

function renderMarkdown(text: string): string {
  if (!text) return ''
  let html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/```[\w]*\n([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
    .replace(/`(.+?)`/g, '<code class="inline-code">$1</code>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
  html = html.replace(/(<li>.*?<\/li>(?:<br>)?)+/g, (match) => {
    return '<ul>' + match.replace(/<br>/g, '') + '</ul>'
  })
  return '<p>' + html + '</p>'
}

function formatTime(iso: string) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return `${Math.floor(diff / 86400000)}天前`
}

onMounted(async () => {
  await Promise.all([fetchSummary(), fetchSessions()])
  if (messages.value.length) nextTick(scrollToBottom)
})
</script>

<template>
  <div class="chat-page">
    <!-- Sidebar: session list -->
    <div class="sidebar" :class="{ collapsed: !sidebarOpen }">
      <div class="sidebar-header">
        <button class="new-chat-btn" @click="newChat">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3v10M3 8h10"/></svg>
          新对话
        </button>
        <button class="toggle-btn" @click="sidebarOpen = !sidebarOpen" :title="sidebarOpen ? '收起' : '展开'">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
            <path v-if="sidebarOpen" d="M10 3L5 8l5 5"/>
            <path v-else d="M6 3l5 5-5 5"/>
          </svg>
        </button>
      </div>
      <div v-if="sidebarOpen" class="session-list">
        <div
          v-for="s in sessions" :key="s.id"
          class="session-item"
          :class="{ active: s.id === currentSessionId }"
          @click="loadSession(s.id)"
        >
          <div class="session-title">{{ s.title }}</div>
          <div class="session-meta">
            <span>{{ s.message_count }}条</span>
            <span>{{ formatTime(s.updated_at) }}</span>
          </div>
          <button class="session-del" @click.stop="deleteSession(s.id)" title="删除">×</button>
        </div>
        <div v-if="sessions.length === 0" class="session-empty">暂无对话记录</div>
      </div>
      <div v-if="sidebarOpen" class="sidebar-footer">
        <span class="sidebar-stat">{{ novelCount }} 本小说 · {{ sessions.length }} 次对话</span>
      </div>
    </div>

    <!-- Main chat area -->
    <div class="chat-main">
      <div class="chat-container">
        <!-- Welcome when empty -->
        <div v-if="messages.length === 0" class="welcome">
          <div class="welcome-icon">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
              <rect width="48" height="48" rx="16" fill="url(#g1)"/>
              <path d="M16 20h16M16 26h10M14 14h20a2 2 0 012 2v16a2 2 0 01-2 2H18l-6 4v-4h2a2 2 0 01-2-2V16a2 2 0 012-2z" stroke="#fff" stroke-width="2" stroke-linecap="round"/>
              <defs><linearGradient id="g1" x1="0" y1="0" x2="48" y2="48"><stop stop-color="#6366f1"/><stop offset="1" stop-color="#8b5cf6"/></linearGradient></defs>
            </svg>
          </div>
          <h2 class="welcome-title">你好，我是墨语</h2>
          <p class="welcome-sub">你的 AI 小说创作顾问 · 拥有记忆</p>
          <p class="welcome-desc">
            我掌握了番茄小说平台 <strong>{{ novelCount }}</strong> 本热门小说的实时数据，
            可以帮你分析市场趋势、推荐创作方向、生成大纲。<br>
            我会<strong>记住你的偏好和创作方向</strong>，跨对话延续我们的讨论。
          </p>
          <div class="quick-prompts">
            <button v-for="q in quickPrompts" :key="q" class="quick-btn" @click="sendMessage(q)">{{ q }}</button>
          </div>
        </div>

        <!-- Messages -->
        <div v-else ref="chatBox" class="msg-list">
          <div v-for="(msg, i) in messages" :key="i" class="msg-row" :class="msg.role">
            <div class="msg-avatar">
              <span v-if="msg.role === 'user'">👤</span>
              <span v-else class="ai-avatar">墨</span>
            </div>
            <div class="msg-bubble">
              <div v-if="msg.role === 'assistant' && !msg.content && streaming" class="typing-dots">
                <span></span><span></span><span></span>
              </div>
              <div v-else class="msg-content" v-html="renderMarkdown(msg.content)"></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Input bar -->
      <div class="input-bar">
        <div class="input-wrap">
          <textarea
            v-model="inputText"
            class="chat-input"
            :placeholder="streaming ? '墨语正在思考...' : '问我任何关于小说创作的问题...'"
            :disabled="streaming"
            rows="1"
            @keydown="handleKeydown"
          ></textarea>
          <button class="send-btn" :class="{ active: inputText.trim() && !streaming }" :disabled="!inputText.trim() || streaming" @click="sendMessage()">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13"/><path d="M22 2L15 22L11 13L2 9L22 2Z"/></svg>
          </button>
        </div>
        <div class="input-hint">
          Enter 发送 / Shift+Enter 换行
          <template v-if="currentSession">
            · 当前: {{ currentSession.title }}
          </template>
        </div>
      </div>
    </div>
  </div>
</template>


<style scoped>
.chat-page{display:flex;height:100%;overflow:hidden}

/* Sidebar */
.sidebar{width:260px;border-right:1px solid var(--gray-200);background:var(--gray-50);display:flex;flex-direction:column;flex-shrink:0;transition:width .2s}
.sidebar.collapsed{width:44px}
.sidebar-header{display:flex;align-items:center;gap:6px;padding:12px 10px;border-bottom:1px solid var(--gray-200)}
.new-chat-btn{flex:1;display:flex;align-items:center;gap:6px;padding:8px 12px;border:1px dashed var(--gray-300);border-radius:8px;background:transparent;color:var(--gray-600);font-size:13px;cursor:pointer;transition:all .15s}
.new-chat-btn:hover{border-color:var(--primary);color:var(--primary);background:#fff}
.collapsed .new-chat-btn{display:none}
.toggle-btn{width:28px;height:28px;border:none;background:transparent;color:var(--gray-400);cursor:pointer;border-radius:6px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.toggle-btn:hover{background:var(--gray-200);color:var(--gray-600)}
.session-list{flex:1;overflow-y:auto;padding:8px 6px}
.session-item{padding:10px 12px;border-radius:8px;cursor:pointer;position:relative;transition:background .12s;margin-bottom:2px}
.session-item:hover{background:var(--gray-200)}
.session-item.active{background:var(--primary-light);border-left:3px solid var(--primary)}
.session-title{font-size:13px;font-weight:600;color:var(--gray-800);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:20px}
.session-meta{font-size:11px;color:var(--gray-400);margin-top:3px;display:flex;gap:8px}
.session-del{position:absolute;right:6px;top:50%;transform:translateY(-50%);width:20px;height:20px;border:none;background:transparent;color:var(--gray-300);font-size:14px;cursor:pointer;border-radius:4px;display:none;align-items:center;justify-content:center}
.session-item:hover .session-del{display:flex}
.session-del:hover{background:var(--gray-300);color:var(--gray-600)}
.session-empty{padding:24px 12px;text-align:center;color:var(--gray-400);font-size:12px}
.sidebar-footer{padding:8px 12px;border-top:1px solid var(--gray-200)}
.sidebar-stat{font-size:11px;color:var(--gray-400)}

/* Main */
.chat-main{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}
.chat-container{flex:1;overflow:hidden;display:flex;flex-direction:column}

/* Welcome */
.welcome{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px 20px;text-align:center}
.welcome-icon{margin-bottom:16px}
.welcome-title{font-size:24px;font-weight:800;color:var(--gray-800);margin:0 0 4px}
.welcome-sub{font-size:14px;color:var(--gray-400);margin:0 0 12px;font-weight:500}
.welcome-desc{font-size:13px;color:var(--gray-500);max-width:460px;line-height:1.7;margin:0 0 24px}
.welcome-desc strong{color:var(--primary);font-weight:700}
.quick-prompts{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;max-width:520px}
.quick-btn{padding:8px 16px;border:1px solid var(--gray-200);border-radius:20px;background:#fff;color:var(--gray-600);font-size:13px;cursor:pointer;transition:all .15s;white-space:nowrap}
.quick-btn:hover{border-color:var(--primary);color:var(--primary);background:var(--primary-light)}

/* Messages */
.msg-list{flex:1;overflow-y:auto;padding:20px 24px;display:flex;flex-direction:column;gap:16px}
.msg-row{display:flex;gap:10px;max-width:800px;width:100%;margin:0 auto}
.msg-row.user{flex-direction:row-reverse}
.msg-avatar{width:32px;height:32px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0}
.msg-row.user .msg-avatar{background:var(--gray-100)}
.ai-avatar{width:32px;height:32px;border-radius:10px;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800}
.msg-bubble{max-width:calc(100% - 50px);min-width:0}
.msg-row.user .msg-bubble{background:var(--primary);color:#fff;border-radius:16px 16px 4px 16px;padding:10px 16px}
.msg-row.assistant .msg-bubble{background:#fff;border:1px solid var(--gray-200);border-radius:16px 16px 16px 4px;padding:12px 16px}
.msg-content{font-size:14px;line-height:1.7;word-break:break-word}
.msg-content :deep(h2){font-size:16px;font-weight:700;margin:12px 0 6px;color:var(--gray-800)}
.msg-content :deep(h3){font-size:15px;font-weight:700;margin:10px 0 4px;color:var(--gray-800)}
.msg-content :deep(h4){font-size:14px;font-weight:700;margin:8px 0 4px;color:var(--gray-700)}
.msg-content :deep(ul){padding-left:20px;margin:6px 0}
.msg-content :deep(li){margin:2px 0}
.msg-content :deep(strong){font-weight:700;color:var(--gray-800)}
.msg-content :deep(code.inline-code){background:var(--gray-100);padding:1px 5px;border-radius:4px;font-size:12px}
.msg-content :deep(pre){background:var(--gray-50);border:1px solid var(--gray-200);border-radius:8px;padding:10px;overflow-x:auto;margin:8px 0}
.msg-content :deep(pre code){font-size:12px}
.msg-content :deep(p){margin:4px 0}
.msg-row.user .msg-content :deep(strong){color:#fff}

/* Typing */
.typing-dots{display:flex;gap:4px;padding:4px 0}
.typing-dots span{width:6px;height:6px;background:var(--gray-400);border-radius:50%;animation:typingBounce .6s infinite alternate}
.typing-dots span:nth-child(2){animation-delay:.2s}
.typing-dots span:nth-child(3){animation-delay:.4s}
@keyframes typingBounce{to{opacity:.3;transform:translateY(-3px)}}

/* Input */
.input-bar{padding:12px 24px 16px;border-top:1px solid var(--gray-200);background:#fff}
.input-wrap{display:flex;align-items:flex-end;gap:8px;max-width:800px;margin:0 auto;background:var(--gray-50);border:1px solid var(--gray-200);border-radius:14px;padding:6px 6px 6px 12px;transition:border-color .15s}
.input-wrap:focus-within{border-color:var(--primary);box-shadow:0 0 0 3px rgba(99,102,241,.1)}
.chat-input{flex:1;border:none;background:transparent;resize:none;font-size:14px;line-height:1.5;padding:6px 0;outline:none;color:var(--gray-800);font-family:inherit;min-height:24px;max-height:120px}
.chat-input::placeholder{color:var(--gray-400)}
.chat-input:disabled{opacity:.5}
.send-btn{width:36px;height:36px;border:none;border-radius:10px;background:var(--gray-200);color:var(--gray-400);cursor:not-allowed;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all .15s}
.send-btn.active{background:var(--primary);color:#fff;cursor:pointer}
.send-btn.active:hover{background:var(--primary-hover)}
.input-hint{text-align:center;font-size:11px;color:var(--gray-300);margin-top:6px}
</style>
