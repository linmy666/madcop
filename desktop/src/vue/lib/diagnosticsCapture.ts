// v3.0 — stub (Vue version of diagnosticsCapture)
export function reportReactError(error: unknown, info?: any) {
  if (typeof console !== 'undefined') console.warn('[diagnostics]', error, info)
}
