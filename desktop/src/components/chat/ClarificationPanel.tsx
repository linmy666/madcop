import { useState } from 'react'
import { useChatStore } from '../../stores/chatStore'
import { wsManager } from '../../api/websocket'

/**
 * v2.6.3.3 — ClarificationPanel: renders the ask_user option buttons
 * + a free-text input when the LLM needs more info from the user.
 *
 * Shows when pendingClarification is set on the session. The user
 * clicks an option or types a custom answer, then the panel sends
 * a clarification_response back through the WebSocket and the
 * LLM continues with the answer.
 */
export function ClarificationPanel({ sessionId }: { sessionId: string }) {
  const session = useChatStore((s) => s.sessions[sessionId])
  const pc = session?.pendingClarification
  const [customText, setCustomText] = useState('')
  const [submitted, setSubmitted] = useState(false)

  if (!pc || submitted) return null

  const handleChoice = (choice: string) => {
    setSubmitted(true)
    wsManager.send(sessionId, {
      type: 'clarification_response',
      choice,
      toolUseId: pc.toolUseId,
    })
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 12,
        padding: '20px 24px',
        borderRadius: 12,
        background: 'var(--color-surface-container-low)',
        border: '1px solid var(--color-border)',
        maxWidth: 480,
        margin: '16px auto',
      }}
    >
      <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--color-text-primary)' }}>
        {pc.question}
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center' }}>
        {pc.options.map((opt) => (
          <button
            key={opt}
            onClick={() => handleChoice(opt)}
            style={{
              padding: '8px 18px',
              borderRadius: 8,
              border: '1px solid var(--color-border)',
              background: 'var(--color-surface)',
              color: 'var(--color-text-primary)',
              fontSize: 14,
              cursor: 'pointer',
              fontWeight: 500,
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'var(--color-surface-hover)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'var(--color-surface)'
            }}
          >
            {opt}
          </button>
        ))}
      </div>

      {pc.allowFreeText && (
        <div style={{ display: 'flex', gap: 8, width: '100%', marginTop: 4 }}>
          <input
            type="text"
            value={customText}
            onChange={(e) => setCustomText(e.target.value)}
            placeholder="输入你的回答..."
            onKeyDown={(e) => {
              if (e.key === 'Enter' && customText.trim()) {
                handleChoice(customText.trim())
              }
            }}
            style={{
              flex: 1,
              padding: '8px 12px',
              borderRadius: 8,
              border: '1px solid var(--color-border)',
              background: 'var(--color-surface)',
              color: 'var(--color-text-primary)',
              fontSize: 14,
              outline: 'none',
            }}
          />
          <button
            onClick={() => customText.trim() && handleChoice(customText.trim())}
            disabled={!customText.trim()}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: 'none',
              background: customText.trim() ? 'var(--color-brand)' : 'var(--color-border)',
              color: '#fff',
              fontSize: 14,
              cursor: customText.trim() ? 'pointer' : 'default',
              fontWeight: 600,
            }}
          >
            发送
          </button>
        </div>
      )}
    </div>
  )
}