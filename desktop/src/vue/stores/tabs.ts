// v3.0 — unified tab store re-export
import { useTabStore } from './tabStore'
import type { Tab, TabType } from './tabStore'

export { useTabStore }
export { SETTINGS_TAB_ID, SCHEDULED_TAB_ID, TRACE_LIST_TAB_ID, TERMINAL_TAB_PREFIX, TRACE_TAB_PREFIX, WORKBENCH_TAB_PREFIX } from './tabStore'
export type { Tab, TabType }
export const useTabs = useTabStore
