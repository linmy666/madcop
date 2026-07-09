/**
 * v3.2 — Intent clarifier
 *
 * Heuristic detection of underspecified user queries, plus a list of
 * follow-up candidates to surface. Inspired by:
 *  - CAMBIGNQ (Lee et al. 2023) — clarifying question generation
 *  - ChatGPT inline form pattern — show options under the input bar
 *  - Notion AI — auto-fill sensible defaults, let user override
 *
 * This is a pure local heuristic — no LLM round-trip, zero failure mode.
 * If the heuristic says "ambiguous" but the user disagrees, they can
 * just ignore the prompt and submit; nothing breaks.
 */

// Words/phrases that strongly suggest a missing parameter
const AMBIGUITY_MARKERS = [
  // Chinese
  /^\s*(今天|明天|昨晚|早上|中午|下午|晚上|现在)\s*(天气|温度|气温|时间|几号)/,
  /^\s*(这里|那里|这边|那边|附近|本地|当地|我的|你的)\s*(天气|怎么样|如何)/,
  /^\s*(最近|马上|立刻|以后|以前)\s*(的)?(怎么样|如何|什么时候)/,
  // English
  /^\s*(today|tomorrow|tonight|now|recently|later)\s*(weather|time)/i,
  /^\s*(here|there|nearby|local|my|your)\s*(weather|like|is|are)/i,
  /^\s*(best|top|good|cheap|fast|popular)\s+(restaurant|hotel|cafe|place|app)/i,
  /^\s*how (do|can|should) (i|you|we)\s/i,
  /^\s*what('s| is)? the (best|fastest|cheapest|most popular)/i,
]

// Common parameter slots we can detect missing
const PARAMETER_SLOTS: Record<string, string[]> = {
  location: ['city', 'country', 'address', 'place', '城市', '地点', '位置', '哪里'],
  time: ['when', 'time', 'date', '什么时候', '几点', '哪天', '日期'],
  subject: ['who', 'what', 'which', '什么', '谁', '哪个'],
  quantity: ['how many', 'how much', '几个', '多少'],
  preference: ['best', 'cheapest', 'fastest', '最好', '最便宜', '最快'],
  comparison: ['vs', 'or', 'compare', '和', '还是', '对比'],
}

export interface Clarification {
  slot: string
  question: string
  options?: string[]
  fallback?: string  // default to use if user ignores
}

/**
 * Returns a list of clarifications the user should probably provide.
 * Empty list means the query is specific enough.
 */
export function detectAmbiguity(query: string): Clarification[] {
  const q = query.trim()
  if (!q || q.length < 3) return []

  // 1. Quick marker check
  const hasMarker = AMBIGUITY_MARKERS.some((p) => p.test(q))
  if (!hasMarker) return []

  // 2. Detect which slot is missing
  const clarifications: Clarification[] = []

  const lowerQ = q.toLowerCase()

  // Weather / time queries
  if (/(天气|weather|temperature)/i.test(lowerQ)) {
    if (!/[\u4e00-\u9fff]*(市|区|县|州|省|国|city|country|state)/i.test(q) && !/\b(in|at|near)\s+[A-Z]/i.test(q)) {
      // Try to find a recent city from common Chinese cities
      const COMMON_CITIES = ['北京', '上海', '广州', '深圳', '杭州', '成都', '南京', '武汉', '西安', '重庆']
      clarifications.push({
        slot: 'location',
        question: '哪个城市？',
        options: COMMON_CITIES,
        fallback: '北京',
      })
    }
  }

  // Recommendation queries
  if (/(最好|最便宜|最快|最好吃|推荐|best|recommend|top)/i.test(lowerQ)) {
    if (!/[\u4e00-\u9fff]*(餐厅|酒店|咖啡|店|电影院|restaurants?|hotels?|cafes?)/i.test(q)) {
      clarifications.push({
        slot: 'subject',
        question: '什么类型的？',
        options: ['餐厅', '咖啡店', '酒店', '景点', '购物'],
        fallback: '餐厅',
      })
    }
    if (!/[\u4e00-\u9fff]*(附近|这里|那里|市中心|nearby|near\s+me|in\s+\w+)/i.test(q)) {
      clarifications.push({
        slot: 'location',
        question: '什么位置？',
        options: ['附近', '市中心', '不限'],
        fallback: '附近',
      })
    }
  }

  // "How to" / how-do
  if (/^\s*(怎么|如何|怎样|how)/i.test(q)) {
    if (!/(用|通过|使用|using|with|via|通过\s)/i.test(q)) {
      clarifications.push({
        slot: 'method',
        question: '用哪种方式？',
        options: ['代码', '工具', '在线服务', '让我选'],
        fallback: '让我选',
      })
    }
  }

  return clarifications
}
