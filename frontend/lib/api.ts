/**
 * API client — talks to the madcop FastAPI backend at localhost:8765.
 * In production, Next.js rewrites /api/* to the backend (see next.config.ts).
 */

const BASE = 'http://127.0.0.1:8765';

export async function api<T = unknown>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  if (!res.ok) throw new Error(`API ${path}: ${res.status}`);
  return res.json();
}

/** SSE stream reader for /api/chat */
export async function* streamChat(
  messages: Array<{ role: string; content: string | unknown[] }>,
  temperature: number,
): AsyncGenerator<unknown, void, unknown> {
  const res = await fetch(`${BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, temperature }),
  });

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        yield JSON.parse(line.slice(6));
      } catch {
        // skip malformed
      }
    }
  }
}

export const apiClient = {
  health: () => api<{ status: string; version: string }>('/api/health'),

  // Settings
  getSettings: () => api<{
    active_provider: string;
    providers: Array<{
      provider_id: string;
      label: string;
      base_url: string;
      model: string;
      api_key_masked: string;
      has_key: boolean;
    }>;
    presets: Array<{
      id: string;
      label: string;
      base_url: string;
      default_model: string;
    }>;
  }>('/api/settings'),

  saveProvider: (data: {
    provider_id: string;
    base_url: string;
    api_key: string;
    model: string;
    label: string;
  }) =>
    api('/api/settings', { method: 'POST', body: JSON.stringify(data) }),

  setActiveProvider: (provider_id: string) =>
    api('/api/settings/active', {
      method: 'POST',
      body: JSON.stringify({ provider_id }),
    }),

  deleteProvider: (id: string) =>
    api(`/api/settings/${id}`, { method: 'DELETE' }),

  // Memory
  getMemory: () => api<{
    episodic: Array<{
      id: string;
      kind: string;
      title: string;
      content: string;
      tags: string[];
    }>;
    semantic: Array<{
      id: string;
      kind: string;
      title: string;
      content: string;
      tags: string[];
    }>;
    reflective: Array<{
      id: string;
      kind: string;
      title: string;
      content: string;
      tags: string[];
    }>;
    total: number;
  }>('/api/memory'),

  addMemory: (data: {
    kind: string;
    title: string;
    content: string;
    tags: string[];
  }) => api('/api/memory', { method: 'POST', body: JSON.stringify(data) }),

  deleteMemory: (id: string) =>
    api(`/api/memory/${id}`, { method: 'DELETE' }),

  searchMemory: (q: string) =>
    api(`/api/memory/search?q=${encodeURIComponent(q)}`),
};
