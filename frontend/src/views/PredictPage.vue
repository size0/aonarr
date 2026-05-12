<script setup lang="ts">
import { NForm, NFormItem, NInput, NSelect, useMessage } from 'naive-ui'
import { ref, computed } from 'vue'
import { predictionApi, type EvaluateResult } from '@/api/data'

const message = useMessage()
const loading = ref(false)
const form = ref({ title: '', genre: '', tags: [] as string[], synopsis: '', firstChapters: '' })
const result = ref<EvaluateResult | null>(null)

const genreOptions = ['玄幻','仙侠','都市','科幻','历史','悬疑','言情','奇幻','军事','游戏'].map(g => ({ label: g, value: g }))
const tagOptions = [
  '重生','穿越','系统','无敌流','升级流','退婚流','赘婿','甜宠','虐恋','豪门',
  '修仙','妖族','末世','星际','热血','搞笑','治愈','暗黑','悬疑推理','商战',
].map(t => ({ label: t, value: t }))

const scoreColor = computed(() => {
  const s = result.value?.overall_score || 0
  if (s >= 70) return '#22c55e'
  if (s >= 40) return '#f59e0b'
  return '#ef4444'
})

async function predict() {
  if (!form.value.genre && !form.value.synopsis && !form.value.firstChapters) {
    message.warning('请至少填写题材、简介或前三章内容')
    return
  }
  loading.value = true
  try {
    result.value = await predictionApi.evaluate({
      title: form.value.title,
      genre: form.value.genre,
      tags: form.value.tags,
      synopsis: form.value.synopsis,
      first_chapters: form.value.firstChapters,
    })
    message.success('预测完成')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '预测失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page-predict">
    <div class="page-head">
      <h1 class="page-title">� 写前预评估</h1>
      <p class="page-desc">输入作品信息，AI 预测市场表现、签约概率和优化建议</p>
    </div>

    <div class="predict-layout">
      <!-- Left: Form -->
      <div class="form-card">
        <h3 class="card-title">📝 输入预测参数</h3>
        <n-form label-placement="top">
          <n-form-item label="作品标题">
            <n-input v-model:value="form.title" placeholder="如: 星陨传说" />
          </n-form-item>
          <n-form-item label="题材 / 赛道">
            <n-select v-model:value="form.genre" :options="genreOptions" placeholder="选择题材" clearable />
          </n-form-item>
          <n-form-item label="标签">
            <n-select v-model:value="form.tags" :options="tagOptions" placeholder="选择标签" multiple filterable tag clearable :max-tag-count="4" />
          </n-form-item>
          <n-form-item label="简介 (150-300字为佳)">
            <n-input v-model:value="form.synopsis" type="textarea" :rows="4" placeholder="简要描述故事核心卖点和冲突" />
          </n-form-item>
          <n-form-item label="前三章正文 (可选)">
            <n-input v-model:value="form.firstChapters" type="textarea" :rows="5" placeholder="粘贴前三章内容，提供越多信息预测越准" />
          </n-form-item>
          <button class="btn btn-primary btn-full" :disabled="loading" @click="predict">
            {{ loading ? '⏳ 分析中...' : '🔮 开始预测' }}
          </button>
        </n-form>
        <div class="form-tip">
          <span class="tip-badge">{{ result?.method === 'llm' ? '🤖 LLM 预测' : '📊 规则引擎' }}</span>
          提供越完整的信息，预测结果越准确
        </div>
      </div>

      <!-- Right: Results -->
      <div class="result-card">
        <h3 class="card-title">📊 预测结果</h3>

        <div v-if="!result" class="result-empty">
          <div class="empty-icon">🔮</div>
          <div class="empty-title">等待预测</div>
          <div class="empty-sub">填写左侧参数后点击预测按钮</div>
        </div>

        <template v-else>
          <!-- Score ring -->
          <div class="score-section">
            <div class="score-ring" :style="{ '--score-color': scoreColor }">
              <div class="score-value">{{ result.overall_score || 0 }}</div>
              <div class="score-label">综合评分</div>
            </div>
            <div class="score-meta">
              <span class="method-tag">{{ result.method === 'llm' ? '🤖 AI 分析' : '📊 规则引擎' }}</span>
              <span v-if="result.model_used" class="model-tag">{{ result.model_used }}</span>
            </div>
          </div>

          <!-- Key metrics -->
          <div class="metric-grid">
            <div class="m-item">
              <div class="m-icon">👁</div>
              <div class="m-val">{{ result.estimated_daily_reads || '—' }}</div>
              <div class="m-label">预估日均阅读</div>
            </div>
            <div class="m-item">
              <div class="m-icon">🔄</div>
              <div class="m-val">{{ result.follow_rate || '—' }}</div>
              <div class="m-label">追更率</div>
            </div>
            <div class="m-item">
              <div class="m-icon">📝</div>
              <div class="m-val">{{ result.signing_probability || '—' }}</div>
              <div class="m-label">签约概率</div>
            </div>
            <div class="m-item">
              <div class="m-icon">🔥</div>
              <div class="m-val-sm">{{ result.genre_heat || '—' }}</div>
              <div class="m-label">题材热度</div>
            </div>
          </div>

          <!-- Competitive analysis -->
          <div v-if="result.competitive_analysis" class="info-block">
            <div class="ib-title">🏆 竞品分析</div>
            <div class="ib-text">{{ result.competitive_analysis }}</div>
          </div>

          <!-- Best time -->
          <div v-if="result.best_publish_time" class="info-block">
            <div class="ib-title">⏰ 建议发布时间</div>
            <div class="ib-text">{{ result.best_publish_time }}</div>
          </div>

          <!-- Risk warnings -->
          <div v-if="result.risk_warnings?.length" class="list-block warn">
            <div class="lb-title">⚠️ 风险提示</div>
            <div v-for="(w, i) in result.risk_warnings" :key="i" class="lb-item">{{ w }}</div>
          </div>

          <!-- Suggestions -->
          <div v-if="result.optimization_suggestions?.length" class="list-block success">
            <div class="lb-title">💡 优化建议</div>
            <div v-for="(s, i) in result.optimization_suggestions" :key="i" class="lb-item">{{ s }}</div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-predict{max-width:1060px}
.page-head{margin-bottom:24px}
.page-title{font-size:22px;font-weight:800;color:var(--gray-900);letter-spacing:-.3px}
.page-desc{font-size:13px;color:var(--gray-400);margin-top:6px}

.predict-layout{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start}
.form-card,.result-card{background:#fff;border:1px solid var(--gray-200);border-radius:16px;padding:24px;transition:all .18s}
.form-card:hover,.result-card:hover{border-color:var(--gray-300);box-shadow:0 4px 20px rgba(0,0,0,.05)}
.card-title{font-size:15px;font-weight:700;color:var(--gray-800);margin-bottom:16px}

.btn-full{width:100%;justify-content:center}
.form-tip{margin-top:12px;font-size:12px;color:var(--gray-400);display:flex;align-items:center;gap:6px}
.tip-badge{font-size:11px;padding:1px 6px;border-radius:4px;background:var(--gray-100);color:var(--gray-500)}

/* Result empty */
.result-empty{text-align:center;padding:60px 0;color:var(--gray-400)}
.result-empty .empty-icon{font-size:40px;margin-bottom:12px}
.result-empty .empty-title{font-size:16px;font-weight:600;color:var(--gray-500);margin-bottom:4px}
.result-empty .empty-sub{font-size:13px}

/* Score */
.score-section{display:flex;align-items:center;gap:20px;margin-bottom:20px}
.score-ring{width:90px;height:90px;border-radius:50%;border:5px solid var(--score-color, #6366f1);
  display:flex;flex-direction:column;align-items:center;justify-content:center;flex-shrink:0;
  background:linear-gradient(135deg,rgba(99,102,241,.05),rgba(99,102,241,.02))}
.score-value{font-size:32px;font-weight:800;color:var(--gray-800);line-height:1}
.score-label{font-size:11px;color:var(--gray-400);margin-top:3px}
.score-meta{display:flex;flex-direction:column;gap:4px}
.method-tag,.model-tag{font-size:12px;padding:2px 8px;border-radius:4px;background:var(--gray-100);color:var(--gray-600);width:fit-content}

/* Metrics */
.metric-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px}
.m-item{padding:16px;background:var(--gray-50);border-radius:12px;text-align:center;border:1px solid var(--gray-100);transition:all .15s}
.m-item:hover{border-color:var(--gray-200);background:#fff}
.m-icon{font-size:20px;margin-bottom:6px}
.m-val{font-size:18px;font-weight:700;color:var(--gray-800)}
.m-val-sm{font-size:13px;font-weight:600;color:var(--gray-700);line-height:1.4}
.m-label{font-size:11px;color:var(--gray-400);margin-top:4px}

/* Info blocks */
.info-block{padding:14px 16px;background:var(--gray-50);border-radius:12px;margin-bottom:10px;border:1px solid var(--gray-100)}
.ib-title{font-size:13px;font-weight:600;color:var(--gray-700);margin-bottom:4px}
.ib-text{font-size:13px;color:var(--gray-500);line-height:1.6}

/* List blocks */
.list-block{padding:14px 16px;border-radius:12px;margin-bottom:10px}
.list-block.warn{background:#fffbeb;border:1px solid #fef3c7}
.list-block.success{background:#f0fdf4;border:1px solid #dcfce7}
.lb-title{font-size:13px;font-weight:600;color:var(--gray-700);margin-bottom:8px}
.lb-item{font-size:13px;color:var(--gray-600);line-height:1.6;padding:2px 0 2px 16px;position:relative}
.lb-item::before{content:'•';position:absolute;left:4px;color:var(--gray-400)}

@media (max-width:800px) {
  .predict-layout{grid-template-columns:1fr}
}
</style>
