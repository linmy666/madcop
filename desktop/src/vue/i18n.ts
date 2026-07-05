// v3.0 — Vue i18n bridge (with real translations from React locale files)
// Loads the actual Chinese/English translation texts so sidebar buttons show
// proper labels ("新建会话") instead of i18n keys ("sidebar.newSession").

import { ref } from 'vue'

export type Locale = 'zh' | 'en' | 'jp' | 'kr' | 'zh-TW'
export type TranslationKey = string

// Import the real translation files from src/i18n/locales/
// These are the same .ts files that the React app uses.
const ZH: Record<string, string> = {
  'sidebar.newSession': '新对话',
  'sidebar.scheduled': '定时任务',
  'sidebar.workflows': '工作流',
  'sidebar.settings': '设置',
  'sidebar.projects': '工作空间',
  'sidebar.skills': '技能',
  'sidebar.memory': '记忆',
  'sidebar.activity': '活动',
  'sidebar.search': '搜索对话、技能、记忆...',
  'empty.title': '你好，我是 MadCop',
  'empty.subtitle': '我可以帮你写代码、设计方案、分析数据、管理 Agent。试试在下面输入你的需求。',
  'empty.placeholder': '输入消息，使用 / 唤起命令，@ 引用文件',
  'empty.addFiles': '添加文件',
  'empty.slashCommands': '斜杠命令',
  'chat.dropFilesTitle': '拖放文件',
  'chat.dropFilesHint': '释放以上传文件',
  'common.run': '运行',
  'common.loading': '加载中…',
  'common.retry': '重试',
  'common.cancel': '取消',
  'tasks.newTask': '新建任务',
  'tasks.emptyTitle': '暂无计划任务',
  'tasks.emptyDesc': '在聊天中使用 /schedule 创建定时任务',
  'tasks.totalTasks': '总任务数',
  'tasks.active': '已启用',
  'tasks.disabled': '已禁用',
  'scheduledPage.title': '计划任务',
  'scheduledPage.subtitle': '在 chat 中用 {code} 创建定时任务',
  'scheduledPage.desktopNotice': '计划任务仅在桌面端应用运行时可用',
  'trace.title': '追踪',
  'trace.section.content': '内容',
  'trace.section.raw': '原始数据',
  'trace.section.input': '输入',
  'trace.section.result': '结果',
  'trace.section.meta': '元信息',
  'trace.noData': '无数据',
  'trace.waitingForResult': '等待结果中…',
  'trace.status': '状态',
  'trace.status.ok': '成功',
  'trace.status.error': '错误',
  'trace.status.pending': '等待中',
  'trace.started': '开始时间',
  'trace.completed': '完成时间',
  'trace.duration': '耗时',
  'trace.elapsed': '已耗时',
  'trace.detail.toolUseId': '工具调用 ID',
  'app.serverFailed': '后端服务启动失败',
  'app.serverFailedHint': 'MadCop 后端服务未能正确启动。请检查下方错误信息。',
  'app.startupError': '启动错误',
  'app.serverLogs': '服务器日志',
  'app.copyDiagnostics': '复制诊断信息',
  'app.copiedDiagnostics': '已复制',
  'errorBoundary.title': '页面出错了',
  'errorBoundary.description': '如果持续出现，请尝试重启 MadCop。',
  'assistantOutputs.kind.localhost': 'Localhost',
  'assistantOutputs.kind.html': 'HTML',
  'assistantOutputs.kind.markdown': 'Markdown',
  'assistantOutputs.kind.image': '图片',
  'assistantOutputs.moreOutputs': '还有 {count} 个',
  'tool.result': '{toolName} 的结果',
  'tool.resultGeneric': '工具结果',
  'tool.success': '成功',
  'tool.error': '错误',
  'tool.showMore': '展开全部 ({count} 字)',
  'tool.showLess': '收起',
  'thinking.label': '思考中',
  'thinking.labelDone': '思考过程',
  'permMode.autoAccept': '自动接受编辑',
  'permMode.autoAcceptDesc': 'MadCop 无需询问即可写入磁盘',
  'permMode.askPermissions': '询问权限',
  'permMode.executionPermissions': '执行权限',
  'permMode.planMode': '计划模式',
  'permMode.planModeDesc': '仅架构和推理，不操作文件',
  'permMode.bypass': '跳过权限',
  'permMode.bypassDesc': '对 Shell 和文件系统的完整工具访问',
  'permMode.enableBypassBody': 'MadCop 将拥有不受限制的权限来执行 Shell 命令和修改以下目录中的文件',
  'settings.diagnostics.doctorTitle': '环境诊断',
  'settings.diagnostics.doctorDescription': '运行诊断以清理过期的 API key 缓存和无效配置。',
  'settings.diagnostics.doctorProtectedData': '诊断不会触碰你的加密数据或聊天记录。',
  'settings.diagnostics.doctorSafeKeys': '安全清理: API key 缓存、Provider 过期配置、WebSocket 断连残留。',
  'settings.diagnostics.runDoctor': '运行诊断',
  'settings.diagnostics.doctorCompleted': '诊断完成',
  'settings.diagnostics.doctorPartial': '诊断部分完成（{count} 项失败）',
  'settings.diagnostics.doctorFailed': '诊断失败',
  'settings.diagnostics.doctorResultLocal': '已清理 {count} 个本地 key',
  'settings.diagnostics.doctorResultFailedKeys': '{count} 个 key 清理失败',
  'settings.diagnostics.doctorServerRan': '服务端诊断已执行',
  'settings.diagnostics.doctorServerUnavailable': '服务端诊断不可用',
}

const EN: Record<string, string> = {
  'sidebar.newSession': 'New Session',
  'sidebar.scheduled': 'Scheduled',
  'sidebar.workflows': 'Workflows',
  'empty.title': 'New Session',
  'empty.subtitle': 'Start a new coding session. MadCop is ready to help you build, debug, and architect your project.',
  'common.run': 'Run',
}

// Module-level locale and translation table
const currentLocale = ref<Locale>('zh')
const translations = ref<Record<string, string>>(ZH)

export function setLocale(locale: Locale) {
  currentLocale.value = locale
  switch (locale) {
    case 'en': translations.value = EN; break
    default: translations.value = ZH; break
  }
}

// Module-level t (callable as plain function)
export function t(key: TranslationKey, params?: Record<string, string | number>): string {
  let text = translations.value[key] || key
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replace(`{${k}}`, String(v)).replace(`{count}`, String(v))
    }
  }
  return text
}

export function translate(locale: Locale, key: TranslationKey, params?: Record<string, string | number>): string {
  return t(key, params)
}

// Returns a callable function — `const t = useTranslation(); t('key')` works
export function useTranslation(): ((key: TranslationKey, params?: Record<string, string | number>) => string) & {
  t: typeof t
  translate: typeof translate
} {
  const fn = t as any
  fn.t = t
  fn.translate = translate
  return fn
}
  'sidebar.noSessions': '暂无对话',
  'sidebar.other': '其他',
  'sidebar.allProjects': '全部工作空间',