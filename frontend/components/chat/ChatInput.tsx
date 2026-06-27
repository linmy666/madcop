'use client';

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent,
} from 'react';
import {
  ArrowUp,
  Paperclip,
  Mic,
  Square,
  Thermometer,
  X,
} from 'lucide-react';
import type { Attachment } from '@/types/chat';
import { useT } from '@/hooks/useTranslation';
import { SlashCommandMenu } from './SlashCommandMenu';

const MASCOT_URL = 'http://127.0.0.1:8765/static/mascot.png';

interface ChatInputProps {
  onSend: (
    text: string,
    attachments: Attachment[],
    temperature: number,
  ) => void;
  disabled?: boolean;
  /** Controlled streaming state — when true, show Stop button. */
  isStreaming?: boolean;
  onStop?: () => void;
  /** Optional initial temperature (defaults to 0.7). */
  initialTemperature?: number;
}

// ── Strength (temperature) presets ─────────────────────────────
const STRENGTH_VALUES = [0.3, 0.7, 1.0] as const;
const STRENGTH_KEYS = ['composer.strength.low', 'composer.strength.medium', 'composer.strength.high'] as const;

// ── File → base64 Attachment helper ────────────────────────────
function readFileAsAttachment(file: File): Promise<Attachment> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const data = reader.result as string;
      resolve({
        name: file.name,
        type: file.type,
        data,
        isImage: file.type.startsWith('image/'),
      });
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// ── Component ──────────────────────────────────────────────────
export default function ChatInput({
  onSend,
  disabled = false,
  isStreaming = false,
  onStop,
  initialTemperature = 0.7,
}: ChatInputProps) {
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [temperature, setTemperature] = useState(initialTemperature);
  const [isRecording, setIsRecording] = useState(false);
  const t = useT();

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<any>(null);

  // ── Auto-grow textarea ──────────────────────────────────────
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);

  // ── File handling ───────────────────────────────────────────
  const handleFileSelect = useCallback(async () => {
    fileInputRef.current?.click();
  }, []);

  const handleFileChange = useCallback(
    async (e: ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files || []);
      const newAtts = await Promise.all(files.map(readFileAsAttachment));
      setAttachments((prev) => [...prev, ...newAtts].slice(0, 8));
      // Reset input so selecting the same file again still fires change
      if (fileInputRef.current) fileInputRef.current.value = '';
    },
    [],
  );

  const removeAttachment = (idx: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== idx));
  };

  // ── Send ────────────────────────────────────────────────────
  const canSend = text.trim().length > 0 && !disabled;

  const handleSend = useCallback(() => {
    if (!canSend) return;
    onSend(text.trim(), attachments, temperature);
    setText('');
    setAttachments([]);
  }, [canSend, text, attachments, temperature, onSend]);

  // ── Key handler: Enter=send, Shift+Enter=newline, "/" = slash menu ──
  const [showSlash, setShowSlash] = useState(false);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Slash command menu
    if (showSlash) return; // let SlashCommandMenu handle keys
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── Voice (Web Speech API) ──────────────────────────────────
  const toggleVoice = useCallback(() => {
    if (isRecording) {
      recognitionRef.current?.stop();
      setIsRecording(false);
      return;
    }

    const SR =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;
    if (!SR) {
      alert('当前浏览器不支持语音输入');
      return;
    }

    const recognition = new SR();
    recognition.lang = 'zh-CN';
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onresult = (event: any) => {
      const transcript = Array.from(event.results)
        .map((r: any) => r[0].transcript)
        .join('');
      setText(transcript);
    };
    recognition.onerror = () => setIsRecording(false);
    recognition.onend = () => setIsRecording(false);

    recognitionRef.current = recognition;
    recognition.start();
    setIsRecording(true);
  }, [isRecording]);

  return (
    <div className="px-4 pb-3 pt-1">
      <div className="mx-auto max-w-3xl relative">
        {/* Slash command menu */}
        <SlashCommandMenu
          visible={showSlash}
          onSelect={() => { setShowSlash(false); setText(''); }}
          onClose={() => { setShowSlash(false); setText(''); }}
        />
        {/* Attachment thumbnails */}
        {attachments.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2 animate-fade-in">
            {attachments.map((att, i) => (
              <div
                key={i}
                className="group/att relative rounded-lg border border-[var(--border)] p-1"
                style={{ background: 'var(--surface)' }}
              >
                {att.isImage ? (
                  <img
                    src={att.data}
                    alt={att.name}
                    className="h-14 w-14 rounded object-cover"
                  />
                ) : (
                  <div className="flex h-14 w-14 flex-col items-center justify-center text-[10px] text-[var(--text-2)]">
                    <Paperclip size={16} />
                    <span className="mt-1 max-w-[3rem] truncate">
                      {att.name}
                    </span>
                  </div>
                )}
                <button
                  onClick={() => removeAttachment(i)}
                  className="absolute -right-1.5 -top-1.5 rounded-full border border-[var(--border)] p-0.5 text-[var(--text-2)] opacity-0 transition-opacity group-hover/att:opacity-100 hover:text-[var(--danger)]"
                  style={{ background: 'var(--surface-2)' }}
                >
                  <X size={11} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Input row */}
        <div
          className="flex items-end gap-2 rounded-2xl border border-[var(--border)] px-3 py-2 transition-colors focus-within:border-[var(--accent)]"
          style={{
            background: 'var(--surface)',
            boxShadow: 'var(--shadow)',
          }}
        >
          {/* Attach button */}
          <button
            onClick={handleFileSelect}
            disabled={disabled}
            className="flex-shrink-0 rounded-lg p-1.5 text-[var(--text-3)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--text)] disabled:opacity-40"
            title={t('composer.attach')}
          >
            <Paperclip size={18} />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/*,.pdf,.txt,.md,.json,.csv,.py,.js,.ts,.tsx,.jsx"
            onChange={handleFileChange}
            className="hidden"
          />

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setShowSlash(e.target.value === '/' || e.target.value.startsWith('/'));
            }}
            onKeyDown={handleKeyDown}
            placeholder={t('composer.placeholder')}
            rows={1}
            disabled={disabled}
            className="flex-1 resize-none bg-transparent py-1.5 text-[14px] leading-6 text-[var(--text)] placeholder:text-[var(--text-faint)] focus:outline-none disabled:opacity-50"
            style={{ maxHeight: '200px' }}
          />

          {/* Voice button */}
          <button
            onClick={toggleVoice}
            disabled={disabled}
            className={`flex-shrink-0 rounded-lg p-1.5 transition-colors hover:bg-[var(--surface-2)] disabled:opacity-40 ${
              isRecording ? 'text-[var(--danger)]' : 'text-[var(--text-3)]'
            }`}
            title={t('composer.voice')}
          >
            <Mic size={18} className={isRecording ? 'animate-pulse' : ''} />
          </button>

          {/* Send / Stop button */}
          {isStreaming && onStop ? (
            <button
              onClick={onStop}
              className="flex-shrink-0 rounded-lg p-1.5 text-white transition-opacity hover:opacity-90"
              style={{ background: 'var(--danger)' }}
              title={t('composer.stop')}
            >
              <Square size={16} fill="currentColor" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!canSend}
              className="flex-shrink-0 rounded-lg p-1.5 text-white transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-30"
              style={{ background: 'var(--accent)' }}
              title={t('composer.send')}
            >
              <ArrowUp size={18} strokeWidth={2.5} />
            </button>
          )}
        </div>

        {/* Bottom row: strength selector */}
        <div className="mt-2 flex items-center gap-3 px-1">
          <div className="flex items-center gap-1.5">
            <Thermometer
              size={13}
              className="text-[var(--text-3)]"
            />
            <span className="text-[11px] text-[var(--text-3)]">{t('composer.strengthHint')}</span>
            <div className="flex items-center gap-0.5">
              {STRENGTH_VALUES.map((v, i) => {
                const active = temperature === v;
                return (
                  <button
                    key={v}
                    onClick={() => setTemperature(v)}
                    className={`rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors ${
                      active
                        ? 'text-white'
                        : 'text-[var(--text-3)] hover:bg-[var(--surface-2)]'
                    }`}
                    style={
                      active
                        ? { background: 'var(--accent)' }
                        : undefined
                    }
                  >
                    {t(STRENGTH_KEYS[i])}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="ml-auto flex items-center gap-1.5 text-[11px] text-[var(--text-faint)]">
            <img
              src={MASCOT_URL}
              alt=""
              width={16}
              height={16}
              className="rounded-sm opacity-60"
            />
            <span>MadCop Agent</span>
          </div>
        </div>
      </div>
    </div>
  );
}
