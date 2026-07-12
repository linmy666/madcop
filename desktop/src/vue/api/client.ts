const ENV_BASE_URL =
  typeof import.meta !== 'undefined' &&
  typeof import.meta.env?.VITE_DESKTOP_SERVER_URL === 'string' &&
  import.meta.env.VITE_DESKTOP_SERVER_URL.length > 0
    ? import.meta.env.VITE_DESKTOP_SERVER_URL
    : undefined

// Default only used before initializeDesktopServerUrl() runs. The desktop
// preload resolves the real server URL (http://127.0.0.1:8765) and calls
// setBaseUrl(); this matches that so REST and chat/WS share one source of truth.
const DEFAULT_BASE_URL = ENV_BASE_URL || 'http://127.0.0.1:8765'

let baseUrl = DEFAULT_BASE_URL
let authToken: string | null = null
const DIAGNOSTICS_PATH = '/api/diagnostics/events'
const DEFAULT_REQUEST_TIMEOUT_MS = 120_000

function getErrorMessage(status: number, body: unknown) {
  if (body && typeof body === 'object') {
    const obj = body as Record<string, unknown>

    // Our own handlers use { message }
    if (typeof obj.message === 'string' && obj.message.trim().length > 0) {
      return obj.message
    }

    // FastAPI HTTPException serializes as { detail }. `detail` can be a
    // plain string, or a list of validation errors ({ loc, msg, type }).
    const detail = obj.detail
    if (typeof detail === 'string' && detail.trim().length > 0) {
      return detail
    }
    if (Array.isArray(detail) && detail.length > 0) {
      const msgs = detail
        .map((d) =>
          d && typeof d === 'object' && typeof (d as Record<string, unknown>).msg === 'string'
            ? (d as Record<string, unknown>).msg
            : typeof d === 'string'
              ? d
              : null,
        )
        .filter((m): m is string => !!m)
      if (msgs.length > 0) {
        return msgs.join('; ')
      }
    }

    // Some upstreams nest the real error under { error } / { error: { message } }
    const err = obj.error
    if (typeof err === 'string' && err.trim().length > 0) {
      return err
    }
    if (err && typeof err === 'object' && typeof (err as Record<string, unknown>).message === 'string') {
      return (err as Record<string, unknown>).message as string
    }
  }

  if (typeof body === 'string' && body.trim().length > 0) {
    return body
  }

  return `API error ${status}`
}

export function setBaseUrl(url: string) {
  baseUrl = url.replace(/\/$/, '')
}

export function getBaseUrl() {
  return baseUrl
}

export function getApiUrl(pathOrUrl: string) {
  try {
    return new URL(pathOrUrl).toString()
  } catch {
    // PATCHED for madcop backend compat: tolerate null/undefined inputs
    // so the React UI surfaces the actual API error instead of a generic
    // "Cannot read properties of undefined (reading 'startsWith')".
    if (!pathOrUrl) {
      return `${baseUrl}/api/__missing_path__`
    }
    const normalizedPath = pathOrUrl.startsWith('/') ? pathOrUrl : `/${pathOrUrl}`
    return `${baseUrl}${normalizedPath}`
  }
}

export function setAuthToken(token: string | null) {
  const trimmed = token?.trim() ?? ''
  authToken = trimmed.length > 0 ? trimmed : null
}

export function getAuthToken() {
  return authToken
}

export function getDefaultBaseUrl() {
  return DEFAULT_BASE_URL
}

export function hasExplicitDefaultBaseUrl() {
  return Boolean(ENV_BASE_URL)
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(getErrorMessage(status, body))
    this.name = 'ApiError'
  }
}

async function request<T>(method: string, path: string, body?: unknown, options?: { timeout?: number }): Promise<T> {
  const url = `${baseUrl}${path}`
  const headers = buildHeaders()

  const controller = new AbortController()
  const timeoutMs = options?.timeout ?? DEFAULT_REQUEST_TIMEOUT_MS
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })
    clearTimeout(timeout)

    if (!res.ok) {
      // PATCHED for madcop backend compat: 404/405 = endpoint not yet implemented in madcop,
      // return null instead of throwing so the desktop UI can still render.
      if (res.status === 404 || res.status === 405) {
        return null as T
      }
      const errorBody = await res.json().catch(() => res.text())
      throw new ApiError(res.status, errorBody)
    }

    if (res.status === 204) return undefined as T
    // PATCHED for madcop backend compat: also tolerate empty / non-object
    // bodies so `const { x } = await api.get(...)` never throws on a missing
    // field.  Returns an empty object so destructuring yields undefined fields.
    const text = await res.text()
    if (!text || text.trim() === '') {
      return {} as T
    }
    try {
      return JSON.parse(text) as T
    } catch {
      return {} as T
    }
  } catch (err) {
    clearTimeout(timeout)
    if (controller.signal.aborted) {
      const timeoutError = new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`)
      reportApiFailure(method, path, timeoutError)
      throw timeoutError
    }
    reportApiFailure(method, path, err)
    throw err
  }
}

function reportApiFailure(method: string, path: string, error: unknown) {
  if (path.startsWith('/api/diagnostics')) return

  const details: Record<string, unknown> = {
    method,
    path,
    errorName: error instanceof Error ? error.name : typeof error,
    message: sanitizeDiagnosticValue(error instanceof Error ? error.message : String(error)),
  }

  if (error instanceof ApiError) {
    details.status = error.status
    details.response = sanitizeDiagnosticValue(error.body)
  }

  void rawRecordDiagnosticEvent({
    type: 'client_api_request_failed',
    severity: 'warn',
    summary: `${method} ${path} failed: ${details.message}`,
    details,
  })
}

export function rawRecordDiagnosticEvent(event: {
  type: string
  severity?: 'debug' | 'info' | 'warn' | 'error'
  summary: string
  sessionId?: string
  details?: unknown
}) {
  return fetch(`${baseUrl}${DIAGNOSTICS_PATH}`, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify(event),
  }).catch(() => undefined)
}

function buildHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }

  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`
  }

  return headers
}

function sanitizeDiagnosticValue(value: unknown): unknown {
  if (!authToken) return value

  if (typeof value === 'string') {
    return value.split(authToken).join('[redacted]')
  }

  if (Array.isArray(value)) {
    return value.map((entry) => sanitizeDiagnosticValue(entry))
  }

  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, entry]) => [key, sanitizeDiagnosticValue(entry)]),
    )
  }

  return value
}

export const api = {
  get: <T>(path: string, options?: { timeout?: number }) => request<T>('GET', path, undefined, options),
  post: <T>(path: string, body?: unknown, options?: { timeout?: number }) => request<T>('POST', path, body, options),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
}
