// v3.0 — MadCop Button.
//
// Three variants: solid, outline, ghost. Three sizes: sm/md/lg.
// No gradients, no shadows by default (borders before shadows).
// Naming: <MadcopButton variant="solid|outline|ghost" size="sm|md|lg" tone="accent|neutral|danger">

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { madcop } from '../../foundations/tokens'

export type MadcopButtonVariant = 'solid' | 'outline' | 'ghost'
export type MadcopButtonSize = 'sm' | 'md' | 'lg'
export type MadcopButtonTone = 'accent' | 'neutral' | 'danger' | 'success'

export interface MadcopButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: MadcopButtonVariant
  size?: MadcopButtonSize
  tone?: MadcopButtonTone
  block?: boolean
  iconLeft?: ReactNode
  iconRight?: ReactNode
}

const sizeStyle: Record<MadcopButtonSize, React.CSSProperties> = {
  sm: { padding: '4px 10px', fontSize: madcop.type.size.caption, gap: 6 },
  md: { padding: '6px 14px', fontSize: madcop.type.size.body, gap: 8 },
  lg: { padding: '10px 20px', fontSize: madcop.type.size.base, gap: 10 },
}

const toneColors: Record<MadcopButtonTone, { fg: string; bg: string; border: string }> = {
  accent:  { fg: 'var(--madcop-accent-ink)',  bg: 'var(--madcop-accent)',       border: 'var(--madcop-accent)' },
  neutral: { fg: 'var(--madcop-ink)',         bg: 'var(--madcop-panel-raised)', border: 'var(--madcop-line)' },
  danger:  { fg: 'var(--madcop-danger)',      bg: 'transparent',                border: 'var(--madcop-danger)' },
  success: { fg: 'var(--madcop-success)',     bg: 'transparent',                border: 'var(--madcop-success)' },
}

export const MadcopButton = forwardRef<HTMLButtonElement, MadcopButtonProps>(function MadcopButton(
  { variant = 'solid', size = 'md', tone = 'accent', block, iconLeft, iconRight, children, style, ...rest },
  ref,
) {
  const c = toneColors[tone]
  const styles: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    fontFamily: madcop.type.family.ui, fontWeight: 500,
    border: `1.5px solid ${c.border}`,
    borderRadius: 0,
    cursor: 'pointer',
    width: block ? '100%' : 'auto',
    transition: 'background 140ms, color 140ms, border-color 140ms',
    ...sizeStyle[size],
    ...(variant === 'solid' && { background: c.bg, color: c.fg }),
    ...(variant === 'outline' && { background: 'transparent', color: c.border, borderColor: c.border }),
    ...(variant === 'ghost' && { background: 'transparent', color: c.border, borderColor: 'transparent' }),
    ...style,
  }
  return (
    <button ref={ref} style={styles} {...rest}>
      {iconLeft}
      {children}
      {iconRight}
    </button>
  )
})
