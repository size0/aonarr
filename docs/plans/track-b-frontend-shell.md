# Track B: 前端壳 + 全部页面框架

独立可并行的前端轨道：Vue 3 项目初始化、路由、布局、所有页面骨架（用 mock 数据）。

## 前置条件
- 无依赖，和 Track A 同时启动
- API 接口先用 mock，等 Track A 完成后对接

## 交付物
1. `NovelForgeX/frontend/` 完整 Vue 3 + TypeScript + Vite 项目
2. TailwindCSS + Naive UI 配置
3. Vue Router 路由表 (11 个页面)
4. 全局布局: 侧边栏 + 顶栏 + 主内容区
5. 所有页面骨架 (用 mock 数据渲染):
   - Dashboard, Studio, BookLab, WorldView, Outline
   - PublishHub, DataBoard, Predict, LearnHub, Prompts, Settings
6. Pinia stores 骨架
7. API 客户端层 (axios wrapper + 类型定义)
8. 设置页: 模型配置面板 (双预设切换 + 阶段绑定 UI)

## 页面设计要点
- **Dashboard**: 作品卡片网格 + 快捷操作 + 写作统计折线图 + 日历热力图
- **Studio**: 左(章节树) + 中(Tiptap编辑器+SSE流) + 右(审核/伏笔面板)
- **BookLab**: 拖拽上传区 + 分析进度条 + 结果Tab(大纲/图谱/时间线/百科)
- **WorldView**: 四个子Tab(图谱/地图/时间线/百科), 图谱用 vis-network 占位
- **PublishHub**: 发布计划日历 + 平台状态卡片 + 发布队列表格
- **DataBoard**: ECharts 折线图/漏斗图/词云 + 竞品对比表
- **Predict**: 输入表单(题材/简介/前3章) + 预测结果卡片
- **LearnHub**: 知识库树 + 趋势图 + 优化日志时间线
- **Settings**: 模型配置(双预设) + 发布账号 + 定时任务 + 代理配置

## 接口约定
```typescript
// API 客户端统一接口，先用 mock 实现
export const novelApi = {
  list: () => Promise<NovelDTO[]>,
  create: (data: NovelCreate) => Promise<NovelDTO>,
  // ...
}
// mock 开关
const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'
```

## 步骤
1. `npm create vite@latest frontend -- --template vue-ts`
2. 安装依赖: naive-ui, tailwindcss, vue-router, pinia, axios, echarts, vis-network, @tiptap/*
3. 配置 TailwindCSS + Naive UI
4. 全局布局组件
5. 路由表 + 页面文件
6. 各页面 UI 骨架 (mock 数据)
7. Pinia stores
8. API 客户端层 + 类型定义
9. 设置页模型配置面板

## 预计工时
3-4 天
