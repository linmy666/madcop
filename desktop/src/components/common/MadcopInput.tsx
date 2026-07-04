// v3.0 — MadCop Input.
//
// Single-line text input, optional label + hint, hairline border
// 1.5px, square corners, 13px font. No floating label, no
// animations on focus — the border just darkens.

import { forwardRef, type InputHTMLAttributes, type ReactNode } from 'react'
import { madcop } from '../../foundations/tokens'

export interface MadcopInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: ReactNode
  hint?: ReactNode
  invalid?: boolean
  prefix?: ReactNode
  suffix?: ReactNode
}

export const MadcopInput = forwardRef<HTMLInputElement, MadcopInputProps>(function MadcopInput(
  { label, hint, invalid, prefix, suffix, style, ...rest },
  ref,
) {
  return (
    <label style={{ display: 'block' }}>
      {label && (
        <div style={{
          fontSize: madcop.type.size.caption, color: 'var(--madcop-ink-body)',
          fontWeight: 500, marginBottom: 4,
        }}>{label}</div>
      )}
      <div style={{
        display: 'flex', alignItems: 'center',
        border: `1.5px solid ${invalid ? 'var(--madcop-danger)' : 'var(--madcop-line)'}`,
        background: 'var(--madcop-panel-sunken)',
        padding: '0 10px',
        transition: 'border-color 140ms',
      }}>
        {prefix && <span style={{ color: 'var(--madcop-ink-muted)', marginRight: 6 }}>{prefix}</span>}
        <input
          ref={ref}
          style={{
            flex: 1, border: 'none', outline: 'none', background: 'transparent',
            padding: '6px 0', fontSize: madcop.type.size.body,
            color: 'var(--madcop-ink)', fontFamily: madcop.type.family.ui,
            ...style,
          }}
          {...rest}
        />
        {suffix && <span style={{ color: 'var(--madcop-ink-muted)', marginLeft: 6 }}>{suffix}</span>}
      </div>
      {hint && (
        <div style={{ fontSize: madcop.type.size.micro, color: 'var(--madcop-ink-muted)', marginTop: 4 }}>{hint}</div>
      )}
    </label>
  )
})
