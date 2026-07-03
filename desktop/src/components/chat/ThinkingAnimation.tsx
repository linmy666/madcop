import { useEffect, useState } from 'react'

/**
 * Hand-drawn stick-figure "step animation" that the MadCop agent shows
 * while it thinks about a user question. Inspired by Claude Code's
 * shimmering sun-flower — but ours is a stick figure flipping through
 * a tiny notepad and finally raising its hand when the answer is ready.
 *
 * Auto-progresses through 4 stages:
 *   1. reading   — eyes scanning the user's question
 *   2. thinking — head tilted, pencil scribbling
 *   3. searching — magnifying glass moving over a list
 *   4. ready     — hand raised, answer about to land
 *
 * If the agent is taking longer than ~8s, it loops back to "thinking".
 *
 * Uses inline SVG (no external assets) so it works even when the
 * renderer is offline. The hand-drawn feel comes from
 *  - stroke-linecap="round"
 *  - stroke-linejoin="round"
 *  - a tiny 1.2px jitter offset on the "wobble" animation
 */

const STAGES = ['reading', 'thinking', 'searching', 'ready'] as const
type Stage = (typeof STAGES)[number]

const STAGE_DURATION_MS = 2200

const STAGE_LABELS: Record<Stage, string> = {
  reading: '正在读问题',
  thinking: '正在拆解思路',
  searching: '正在查记忆 / 工具',
  ready: '正在写答案',
}

export function ThinkingAnimation({ active = true, stage: forcedStage }: { active?: boolean; stage?: string | null }) {
  const [stage, setStage] = useState<Stage>('reading')
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (!active) return
    // If the backend provides a real stage, use it instead of cycling
    if (forcedStage && STAGES.includes(forcedStage as Stage)) {
      setStage(forcedStage as Stage)
      return
    }
    let cancelled = false
    let i = 0
    const advance = () => {
      if (cancelled) return
      i = (i + 1) % STAGES.length
      setStage(STAGES[i] as Stage)
      setTick((t) => t + 1)
    }
    const t = window.setInterval(advance, STAGE_DURATION_MS)
    return () => {
      cancelled = true
      window.clearInterval(t)
    }
  }, [active, forcedStage])

  return (
    <>
      <style>{thinkingAnimationStyles}</style>
      <div
        role="status"
        aria-live="polite"
        data-thinking-stage={stage}
        data-thinking-tick={tick}
        className="flex items-center gap-2 rounded-lg border border-[var(--color-brand)]/20 bg-[var(--color-brand)]/5 px-3 py-2"
      >
        <div className="relative h-9 w-9 shrink-0">
          <StickFigure stage={stage} />
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-[12px] font-medium text-[var(--color-brand)]">
            MadCop 正在思考
          </span>
          <span
            key={stage}
            className="text-[11px] text-[var(--color-text-secondary)] thinking-stage-text"
          >
            {STAGE_LABELS[stage]}
            <span className="thinking-dots" />
          </span>
        </div>
      </div>
    </>
  )
}

function StickFigure({ stage }: { stage: Stage }) {
  // Each stage draws the same stick figure but with different "props"
  // and a tiny animation that suggests the action.
  return (
    <svg
      viewBox="0 0 40 40"
      width={36}
      height={36}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="thinking-figure"
      data-stage={stage}
    >
      {/* head */}
      <circle cx="20" cy="11" r={4.2} className="thinking-head" />
      {/* body */}
      <line x1="20" y1="15" x2="20" y2="26" />
      {/* arms (pose changes per stage) */}
      <Arms stage={stage} />
      {/* legs */}
      <line x1="20" y1="26" x2="15" y2="34" />
      <line x1="20" y1="26" x2="25" y2="34" />
      {/* stage-specific prop */}
      {stage === 'reading' && <ReadingProp />}
      {stage === 'thinking' && <ThinkingProp />}
      {stage === 'searching' && <SearchProp />}
      {stage === 'ready' && <ReadyProp />}
    </svg>
  )
}

function Arms({ stage }: { stage: Stage }) {
  // Each stage has a different arm pose.
  switch (stage) {
    case 'reading':
      // Both arms down holding the paper
      return (
        <>
          <line x1="20" y1="19" x2="14" y2="24" />
          <line x1="20" y1="19" x2="26" y2="24" />
        </>
      )
    case 'thinking':
      // Right arm up holding a pencil near the head
      return (
        <>
          <line x1="20" y1="19" x2="13" y2="24" />
          <line x1="20" y1="19" x2="27" y2="14" />
        </>
      )
    case 'searching':
      // Right arm out holding a magnifying glass
      return (
        <>
          <line x1="20" y1="19" x2="13" y2="24" />
          <line x1="20" y1="19" x2="29" y2="19" />
        </>
      )
    case 'ready':
      // Right arm up in a wave
      return (
        <>
          <line x1="20" y1="19" x2="13" y2="24" />
          <line x1="20" y1="19" x2="27" y2="11" />
        </>
      )
  }
}

function ReadingProp() {
  // Tiny notepad in front of the figure
  return (
    <g className="thinking-prop-reading">
      <rect x="11" y="22" width="9" height="6" rx="0.6" />
      <line x1="13" y1="25" x2="18" y2="25" />
      <line x1="13" y1="27" x2="18" y2="27" />
    </g>
  )
}

function ThinkingProp() {
  // A small squiggle next to the head, like a thought bubble trail
  return (
    <g className="thinking-prop-thinking">
      <path d="M 27 9 q 1.2 -1 2 0 q 1.2 -1 2 0" />
      <circle cx="32" cy="6" r="0.8" fill="currentColor" />
      {/* pencil */}
      <line x1="27" y1="14" x2="30" y2="11" />
      <line x1="30" y1="11" x2="31.4" y2="9.6" strokeWidth="0.7" />
    </g>
  )
}

function SearchProp() {
  // A magnifying glass at the end of the right arm
  return (
    <g className="thinking-prop-searching">
      <circle cx="29" cy="19" r={2.4} />
      <line x1="30.7" y1="20.7" x2="32.6" y2="22.6" strokeWidth="1.1" />
      <line x1="28" y1="19" x2="30" y2="19" strokeWidth="0.6" />
    </g>
  )
}

function ReadyProp() {
  // A small sparkle / "answer bubble" — the response is about to land
  return (
    <g className="thinking-prop-ready">
      <circle cx="28" cy="9" r="1.4" fill="currentColor" stroke="none" />
      <line x1="25" y1="6" x2="26" y2="7" strokeWidth="0.9" />
      <line x1="31" y1="7" x2="30" y2="6" strokeWidth="0.9" />
      <line x1="32" y1="11" x2="33" y2="10" strokeWidth="0.9" />
      <line x1="25" y1="11" x2="24" y2="10" strokeWidth="0.9" />
    </g>
  )
}

// CSS — embedded as a <style> so we don't need a separate CSS file.
export const thinkingAnimationStyles = `
@keyframes thinking-stage-text-fade {
  0% { opacity: 0; transform: translateY(2px); }
  20% { opacity: 1; transform: translateY(0); }
  100% { opacity: 1; transform: translateY(0); }
}
.thinking-stage-text {
  display: inline-block;
  animation: thinking-stage-text-fade 350ms ease-out;
}

/* the prop wobble — gives the hand-drawn feel */
@keyframes thinking-wobble {
  0%, 100% { transform: translate(0, 0) rotate(0deg); }
  25% { transform: translate(-0.2px, 0.1px) rotate(-0.5deg); }
  50% { transform: translate(0.2px, -0.1px) rotate(0.4deg); }
  75% { transform: translate(-0.1px, 0.2px) rotate(-0.3deg); }
}
.thinking-figure { animation: thinking-wobble 1.6s ease-in-out infinite; transform-origin: 20px 30px; }

/* the head bobs a bit more for "thinking" */
@keyframes thinking-head-bob {
  0%, 100% { transform: translate(0, 0) rotate(0deg); }
  40% { transform: translate(0.4px, -0.3px) rotate(2deg); }
  60% { transform: translate(-0.3px, 0.2px) rotate(-1.5deg); }
}
.thinking-figure[data-stage="thinking"] .thinking-head {
  animation: thinking-head-bob 1.4s ease-in-out infinite;
  transform-origin: 20px 11px;
}

/* arms: tiny hand wave when "ready" */
@keyframes thinking-wave {
  0%, 100% { transform: rotate(0deg); }
  20% { transform: rotate(-12deg); }
  60% { transform: rotate(10deg); }
}
.thinking-figure[data-stage="ready"] .thinking-prop-ready {
  transform-origin: 27px 9px;
  animation: thinking-wave 1.2s ease-in-out infinite;
}

/* searching: magnifying glass drifts slightly */
@keyframes searching-drift {
  0%, 100% { transform: translate(0, 0); }
  50% { transform: translate(1px, -1px); }
}
.thinking-figure[data-stage="searching"] .thinking-prop-searching {
  animation: searching-drift 1.2s ease-in-out infinite;
}

/* reading: the notepad scrolls (paper shake) */
@keyframes reading-shake {
  0%, 100% { transform: translate(0, 0); }
  50% { transform: translate(0.3px, 0); }
}
.thinking-figure[data-stage="reading"] .thinking-prop-reading {
  animation: reading-shake 0.6s ease-in-out infinite;
}

/* the three-dot loader */
@keyframes thinking-dots-cycle {
  0%, 20% { content: ''; }
  40% { content: '·'; }
  60% { content: '··'; }
  80%, 100% { content: '···'; }
}
.thinking-dots::after {
  content: '';
  display: inline-block;
  width: 1.5em;
  text-align: left;
  animation: thinking-dots-cycle 1.4s steps(1, end) infinite;
}
`
