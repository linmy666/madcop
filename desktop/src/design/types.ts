// v2.8.0 — Design tool shared types
import type { Data } from './core/bundle/core'

export interface DesignComponent {
  type: string
  props: Record<string, any>
}

export type { Data as DesignData }