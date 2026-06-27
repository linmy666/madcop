/**
 * Lightweight i18n for MadCop Agent.
 * - Default: en
 * - Persisted in localStorage
 * - Brand: zh shows "周巡", en shows "MadCop Agent"
 * - Slogans: zh shows "周思万虑，巡行无疆", en shows "Infinite Minds, Boundless Strides"
 */

export type Locale = 'en' | 'zh';

export const STORAGE_KEY = 'madcop-locale';

export function getStoredLocale(): Locale {
  if (typeof window === 'undefined') return 'en';
  const v = window.localStorage.getItem(STORAGE_KEY);
  return v === 'zh' ? 'zh' : 'en';
}

export function setStoredLocale(locale: Locale): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(STORAGE_KEY, locale);
}

// ─── Brand (locale-dependent) ─────────────────────────────────
export const BRAND = {
  en: {
    name: 'MadCop Agent',
    shortName: 'MadCop',
    slogan: 'Infinite Minds, Boundless Strides',
  },
  zh: {
    name: '周巡',
    shortName: '周巡',
    slogan: '周思万虑，巡行无疆',
  },
} as const;

// ─── Translations ─────────────────────────────────────────────
type Dict = Record<string, string>;

const en: Dict = {
  // Sidebar
  'sidebar.newChat': 'New chat',
  'sidebar.searchPlaceholder': 'Search history...',
  'sidebar.nav.chat': 'Chat',
  'sidebar.nav.memory': 'Memory',
  'sidebar.nav.tasks': 'Tasks',
  'sidebar.nav.settings': 'Settings',
  'sidebar.themeToggle': 'Toggle theme',
  'sidebar.emptyConversations': 'No conversations yet',

  // Top bar
  'topbar.toggleSidebar': 'Toggle sidebar',

  // Welcome
  'welcome.title': 'What can I help you with?',
  'welcome.subtitle': 'Your local AI agent · Web search, weather, file ops, cross-session memory',

  // Chat input
  'composer.placeholder': 'Type a message... (Enter to send, Shift+Enter for newline)',
  'composer.attach': 'Attach',
  'composer.voice': 'Voice input',
  'composer.send': 'Send',
  'composer.stop': 'Stop',
  'composer.strength.low': 'Low',
  'composer.strength.medium': 'Medium',
  'composer.strength.high': 'High',
  'composer.strengthHint': 'Reasoning effort',
  'composer.voiceUnsupported': 'Browser does not support voice recognition',
  'composer.attachLimit': 'Max 8 attachments',

  // Message
  'msg.copy': 'Copy',
  'msg.copied': 'Copied',
  'msg.copyPrompt': 'Copy prompt',
  'msg.thinking': 'Reasoning',
  'msg.thinkingDone': 'Reasoning',
  'msg.toolCall': 'Tool call',
  'msg.toolCalledOne': 'called 1 tool',
  'msg.toolCalledMany': 'called {count} tools',
  'msg.streaming': 'Thinking',
  'msg.attachment': 'Attachment',

  // Settings
  'settings.title': 'Settings',
  'settings.configuredProviders': 'Configured Providers',
  'settings.noProviders': 'No providers configured',
  'settings.setDefault': 'Set as default',
  'settings.delete': 'Delete',
  'settings.addOrUpdate': 'Add / Update Provider',
  'settings.provider': 'Provider',
  'settings.providerPlaceholder': '— Select —',
  'settings.baseUrl': 'API Base URL',
  'settings.baseUrlPlaceholder': 'https://api.openai.com/v1',
  'settings.apiKey': 'API Key',
  'settings.apiKeyPlaceholder': 'sk-...',
  'settings.model': 'Model',
  'settings.modelPlaceholder': 'gpt-4o-mini',
  'settings.save': 'Save',
  'settings.cancel': 'Cancel',
  'settings.saveSuccess': 'Saved',
  'settings.saveFail': 'Save failed',
  'settings.fillRequired': 'Please fill Base URL and Model',
  'settings.language': 'Language',
  'settings.languageEn': 'English',
  'settings.languageZh': '中文',

  // Memory
  'memory.title': 'Memory',
  'memory.subtitle': 'MadCop Agent automatically remembers your identity, preferences, and important information. You can also add or delete memories manually.',
  'memory.addPlaceholder': 'e.g., User loves hotpot',
  'memory.add': 'Add',
  'memory.saved': 'Saved memories ({count})',
  'memory.empty': 'No memories yet. Start a conversation or add one manually.',
  'memory.layer.semantic': 'Knowledge',
  'memory.layer.episodic': 'Event',
  'memory.layer.reflective': 'Preference',
  'memory.delete': 'Delete',
  'memory.addFail': 'Add failed',

  // Tasks
  'tasks.title': 'Scheduled tasks',
  'tasks.subtitle': 'Create scheduled tasks so MadCop Agent runs them at specified times automatically.',
  'tasks.empty': 'No scheduled tasks',
  'tasks.comingSoon': 'This feature is coming soon',

  // Memory bar / rage
  'rage.tooltip': 'Context window usage (怒氣值)',
};

const zh: Dict = {
  // Sidebar
  'sidebar.newChat': '新对话',
  'sidebar.searchPlaceholder': '搜索历史会话...',
  'sidebar.nav.chat': '对话',
  'sidebar.nav.memory': '记忆',
  'sidebar.nav.tasks': '任务',
  'sidebar.nav.settings': '设置',
  'sidebar.themeToggle': '切换主题',
  'sidebar.emptyConversations': '还没有对话',

  // Top bar
  'topbar.toggleSidebar': '折叠侧边栏',

  // Welcome
  'welcome.title': '有什么可以帮你的？',
  'welcome.subtitle': '你的本地 AI Agent · 支持 Web 搜索、天气查询、文件操作、跨会话记忆',

  // Chat input
  'composer.placeholder': '输入消息... (Enter 发送, Shift+Enter 换行)',
  'composer.attach': '附件',
  'composer.voice': '语音输入',
  'composer.send': '发送',
  'composer.stop': '停止',
  'composer.strength.low': '低',
  'composer.strength.medium': '中',
  'composer.strength.high': '高',
  'composer.strengthHint': '推理强度',
  'composer.voiceUnsupported': '浏览器不支持语音识别',
  'composer.attachLimit': '最多 8 个附件',

  // Message
  'msg.copy': '复制',
  'msg.copied': '已复制',
  'msg.copyPrompt': '复制提示',
  'msg.thinking': '推理过程',
  'msg.thinkingDone': '推理过程',
  'msg.toolCall': '工具调用',
  'msg.toolCalledOne': '调用了 1 个工具',
  'msg.toolCalledMany': '调用了 {count} 个工具',
  'msg.streaming': '思考中',
  'msg.attachment': '附件',

  // Settings
  'settings.title': '设置',
  'settings.configuredProviders': '已配置的 Provider',
  'settings.noProviders': '还没有配置 Provider',
  'settings.setDefault': '设为默认',
  'settings.delete': '删除',
  'settings.addOrUpdate': '添加 / 更新 Provider',
  'settings.provider': 'Provider',
  'settings.providerPlaceholder': '— 选择 —',
  'settings.baseUrl': 'API Base URL',
  'settings.baseUrlPlaceholder': 'https://api.openai.com/v1',
  'settings.apiKey': 'API Key',
  'settings.apiKeyPlaceholder': 'sk-...',
  'settings.model': 'Model',
  'settings.modelPlaceholder': 'gpt-4o-mini',
  'settings.save': '保存',
  'settings.cancel': '取消',
  'settings.saveSuccess': '保存成功',
  'settings.saveFail': '保存失败',
  'settings.fillRequired': '请填写 Base URL 和 Model',
  'settings.language': '语言',
  'settings.languageEn': 'English',
  'settings.languageZh': '中文',

  // Memory
  'memory.title': '记忆',
  'memory.subtitle': '周巡会自动记住你的身份、偏好和重要信息。你也可以手动添加或删除记忆。',
  'memory.addPlaceholder': '例：用户喜欢吃火锅',
  'memory.add': '添加',
  'memory.saved': '已有记忆 ({count})',
  'memory.empty': '还没有任何记忆。开始对话或手动添加。',
  'memory.layer.semantic': '知识',
  'memory.layer.episodic': '事件',
  'memory.layer.reflective': '偏好',
  'memory.delete': '删除',
  'memory.addFail': '添加失败',

  // Tasks
  'tasks.title': '定时任务',
  'tasks.subtitle': '创建计划任务，让周巡在指定时间自动执行。',
  'tasks.empty': '暂无定时任务',
  'tasks.comingSoon': '此功能即将推出',

  // Memory bar / rage
  'rage.tooltip': '上下文使用率（怒气值）',
};

const dicts: Record<Locale, Dict> = { en, zh };

export function translate(locale: Locale, key: string, vars?: Record<string, string | number>): string {
  const dict = dicts[locale] || en;
  let s = dict[key] || en[key] || key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      s = s.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v));
    }
  }
  return s;
}
