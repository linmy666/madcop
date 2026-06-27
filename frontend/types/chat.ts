export type Role = 'system' | 'user' | 'assistant' | 'tool';

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  result?: string | null;
}

export interface Message {
  id: string;
  role: Role;
  content: string;
  reasoning?: string;
  toolCalls?: ToolCall[];
  model?: string;
  timestamp?: number;
  attachments?: Attachment[];
}

export interface Attachment {
  name: string;
  type: string;
  data: string; // base64 data URL
  isImage: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  model?: string;
  createdAt: number;
}

export interface Provider {
  provider_id: string;
  label: string;
  base_url: string;
  model: string;
  api_key_masked?: string;
  has_key: boolean;
}

export interface ProviderPreset {
  id: string;
  label: string;
  base_url: string;
  default_model: string;
}

export interface MemoryEntry {
  id: string;
  kind: string;
  title: string;
  content: string;
  tags: string[];
  created_at: number;
}

export interface SSEEvent {
  type: 'text' | 'reasoning' | 'tool' | 'tool_result' | 'done' | 'error';
  content?: string;
  name?: string;
  args?: Record<string, unknown>;
  result?: string;
  model?: string;
  finish_reason?: string;
  message?: string;
}
