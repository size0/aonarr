import {
  BookOutline,
  BulbOutline,
  CashOutline,
  CheckboxOutline,
  CreateOutline,
  DocumentTextOutline,
  FolderOpenOutline,
  GlobeOutline,
  HeartOutline,
  HomeOutline,
  ImageOutline,
  LibraryOutline,
  ListOutline,
  MailOutline,
  PeopleOutline,
  ReaderOutline,
  SettingsOutline,
  StatsChartOutline,
} from '@vicons/ionicons5'
import type { WorkspaceNavItem } from './composables/useWorkspace'

export const loginFeatures = [
  { title: '自动连载', desc: '规划、起草、审阅和修订串成稳定生产线。', icon: CreateOutline },
  { title: '作品资料库', desc: '项目设定、故事设定、提示词模板集中管理。', icon: FolderOpenOutline },
  { title: '运行监控', desc: '实时日志、成本估算和质量门状态实时可见。', icon: StatsChartOutline },
]

export const studioSideNav = [
  { label: '概览', icon: HomeOutline, active: false },
  { label: '作品', icon: BookOutline, active: true },
  { label: '章节', icon: DocumentTextOutline, active: false },
  { label: '角色', icon: PeopleOutline, active: false },
  { label: '世界观', icon: GlobeOutline, active: false },
  { label: '资料库', icon: LibraryOutline, active: false },
  { label: '统计', icon: StatsChartOutline, active: false },
  { label: '设置', icon: SettingsOutline, active: false },
]

export const studioOutlines = [
  { title: '第一卷：启程', done: 12, total: 20 },
  { title: '第二卷：迷雾之地', done: 8, total: 20 },
  { title: '第三卷：命运的交汇', done: 0, total: 20 },
]

export const studioCharacters = [
  { name: '艾琳·星语', role: '女主角', short: '艾', tone: 'silver' },
  { name: '洛恩·夜影', role: '男主角', short: '洛', tone: 'blue' },
  { name: '凯瑟琳', role: '重要配角', short: '凯', tone: 'pink' },
  { name: '卡斯塔', role: '反派角色', short: '卡', tone: 'dark' },
]

export const studioChartBars = [
  { day: '5.12', value: 22 },
  { day: '5.13', value: 38 },
  { day: '5.14', value: 56 },
  { day: '5.15', value: 42 },
  { day: '5.16', value: 66 },
  { day: '5.17', value: 90 },
  { day: '5.18', value: 76 },
]

export const studioFeatures = [
  { title: '灵感管理', desc: '随时记录灵感，建立灵感库，让每一个想法都不被错过。', icon: BulbOutline },
  { title: '大纲与章节', desc: '可视化大纲结构，灵活管理章节，让故事脉络清晰可见。', icon: DocumentTextOutline },
  { title: '角色与设定', desc: '详细的角色档案与关系设定，让人物真正立在纸上。', icon: PeopleOutline },
  { title: '世界观构建', desc: '自定义世界设定、历史背景、地理文化等元素，一处管理。', icon: GlobeOutline },
]

export const workspaceNavItems: WorkspaceNavItem[] = [
  { label: '工作台', icon: HomeOutline, page: 'index', indexPanel: 'overview' },
  { label: '作品管理', icon: DocumentTextOutline, page: 'index', indexPanel: 'works' },
  { label: '章节管理', icon: ReaderOutline, page: 'workbench', mainPanel: 'drafts' },
  { label: '人物管理', icon: PeopleOutline, page: 'workbench', sidePanel: 'project' },
  { label: '大纲管理', icon: ListOutline, page: 'workbench', mainPanel: 'plans' },
  { label: '世界观设定', icon: GlobeOutline, page: 'workbench', mainPanel: 'world', sidePanel: 'bible' },
  { label: '素材库', icon: ImageOutline, page: 'workbench', sidePanel: 'project' },
  { label: '数据统计', icon: StatsChartOutline, page: 'index', indexPanel: 'stats' },
  { label: '粉丝互动', icon: HeartOutline, page: 'index', indexPanel: 'fans' },
  { label: '成本管理', icon: CashOutline, page: 'workbench', mainPanel: 'run' },
  { label: '运行日志', icon: MailOutline, page: 'workbench', badge: '实时', mainPanel: 'events' },
  { label: '任务中心', icon: CheckboxOutline, page: 'index', badge: '3', indexPanel: 'tasks' },
  { label: '设置', icon: SettingsOutline, page: 'settings', settingsPanel: 'llm' },
]

export const weekDays = ['一', '二', '三', '四', '五', '六', '日']

export const calendarDays = [
  ...['29', '30'].map((label) => ({ label, muted: true, marked: false, active: false })),
  ...Array.from({ length: 31 }, (_, index) => ({
    label: String(index + 1),
    muted: false,
    marked: index + 1 <= 23,
    active: index + 1 === 20,
  })),
  ...['1', '2'].map((label) => ({ label, muted: true, marked: false, active: false })),
]

export const chartLines = [42, 82, 122, 162, 202]
