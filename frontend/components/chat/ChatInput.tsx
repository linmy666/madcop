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
  Paperclip,
  Mic,
  Square,
  ArrowUp,
  Thermometer,
  X,
  Image as ImageIcon,
} from 'lucide-react';
import type { Attachment } from '@/types/chat';
import { useT } from '@/hooks/useTranslation';
import { shouldSubmitOnEnter } from '@/lib/sendShortcut';
import { SlashCommandMenu } from './SlashCommandMenu';

interface ChatInputProps {
  onSend: (text: string, attachments: Attachment[], temperature: number) => void;
  disabled?: boolean;
  isStreaming?: boolean;
  onStop?: () => void;
  initialTemperature?: number;
}

const STRENGTH_VALUES = [0.3, 0.7, 1.0] as const;
const STRENGTH_KEYS = ['composer.strength.low', 'composer.strength.medium', 'composer.strength.high'] as const;

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

export default function ChatInput({
  onSend,
  disabled = false,
  isStreaming = false,
  onStop,
  initialTemperature = 0.7,
}: ChatInputProps) {
  const t = useT();
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [temperature, setTemperature] = useState(initialTemperature);
  const [isRecording, setIsRecording] = useState(false);
  const [showSlash, setShowSlash] = useState(false);
  const [sendBehavior] = useState<'enter' | 'modifierEnter'>('enter');
  const [dragOver, setDragOver] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<any>(null);

  // Auto-grow textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  }, [text]);

  const canSend = !disabled && (text.trim().length > 0 || attachments.length > 0);

  const handleSend = useCallback(() => {
    if (!canSend) return;
    onSend(text, attachments, temperature);
    setText('');
    setAttachments([]);
    setShowSlash(false);
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }, 0);
  }, [canSend, text, attachments, temperature, onSend]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (showSlash) return;
    if (e.nativeEvent.isComposing) return;
    if (shouldSubmitOnEnter(e.nativeEvent, sendBehavior)) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    const newAttachments = await Promise.all(
      files.map((f) => readFileAsAttachment(f)),
    );
    setAttachments((prev) => [...prev, ...newAttachments].slice(0, 8));
    e.target.value = '';
  };

  // Drag & drop files onto the composer
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };
  const handleDragLeave = () => setDragOver(false);
  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const files = Array.from(e.dataTransfer.files || []);
    const newAttachments = await Promise.all(
      files.map((f) => readFileAsAttachment(f)),
    );
    setAttachments((prev) => [...prev, ...newAttachments].slice(0, 8));
  };

  const toggleVoice = () => {
    const btn = document.getElementById('voiceBtn');
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
      setIsRecording(false);
      return;
    }
    const SR: any = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      alert(t('composer.voiceUnsupported'));
      return;
    }
    const recognition = new SR();
    recognition.lang = 'zh-CN';
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.onresult = (ev: any) => {
      let text = '';
      for (let i = 0; i < ev.results.length; i++) text += ev.results[i][0].transcript;
      setText(text);
    };
    recognition.onend = () => {
      setIsRecording(false);
      recognitionRef.current = null;
    };
    recognition.start();
    recognitionRef.current = recognition;
    setIsRecording(true);
  };

  return (
    <div
      className="px-4 pb-3 pt-1"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drop overlay */}
      {dragOver && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center pointer-events-none animate-fade-in"
          style={{ background: 'var(--accent-dim)' }}
        >
          <div
            className="px-6 py-3 rounded-lg border-2"
            style={{
              background: 'var(--surface)',
              borderColor: 'var(--accent)',
              color: 'var(--text)',
            }}
          >
            {t('composer.drop')}
          </div>
        </div>
      )}

      <div className="mx-auto max-w-3xl relative">
        <SlashCommandMenu
          visible={showSlash}
          onSelect={() => { setShowSlash(false); setText(''); }}
          onClose={() => { setShowSlash(false); setText(''); }}
        />

        {/* Attachments preview */}
        {attachments.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5 animate-fade-in">
            {attachments.map((att, i) => (
              <div
                key={i}
                className="group/att relative flex items-center gap-1.5 rounded-lg border px-1.5 py-1"
                style={{ background: 'var(--surface-1)', borderColor: 'var(--border)' }}
              >
                {att.isImage ? (
                  <img
                    src={att.data}
                    alt={att.name}
                    className="h-7 w-7 rounded object-cover"
                  />
                ) : (
                  <Paperclip size={11} style={{ color: 'var(--text-3)' }} />
                )}
                <span className="text-[10px] truncate max-w-[80px]" style={{ color: 'var(--text-2)' }}>
                  {att.name}
                </span>
                <button
                  onClick={() => setAttachments((prev) => prev.filter((_, j) => j !== i))}
                  className="ml-0.5 p-0.5 rounded hover:bg-[var(--surface-hover)]"
                  style={{ color: 'var(--text-3)' }}
                >
                  <X size={10} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Composer box */}
        <div
          className="rounded-2xl border transition-colors"
          style={{
            background: 'var(--surface)',
            borderColor: 'var(--border)',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setShowSlash(e.target.value === '/' || e.target.value.startsWith('/ '));
            }}
            onKeyDown={handleKeyDown}
            placeholder={t('composer.placeholder')}
            rows={1}
            disabled={disabled}
            className="w-full bg-transparent px-4 pt-3 pb-1.5 text-[14px] leading-6 outline-none placeholder:text-[var(--text-faint)] resize-none disabled:opacity-50"
            style={{ maxHeight: '200px', color: 'var(--text)' }}
          />

          {/* Bottom row: tools + send */}
          <div className="flex items-center gap-1 px-2 pb-2">
            {/* Attach button */}
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled}
              className="h-7 w-7 flex items-center justify-center rounded transition-colors hover:bg-[var(--surface-hover)] disabled:opacity-40"
              style={{ color: 'var(--text-3)' }}
              title={t('composer.attach')}
            >
              <Paperclip size={15} />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="image/*,.pdf,.txt,.md,.json,.csv,.py,.js,.ts,.tsx,.jsx"
              onChange={handleFileChange}
              className="hidden"
            />

            {/* Voice button */}
            <button
              id="voiceBtn"
              onClick={toggleVoice}
              disabled={disabled}
              className={`h-7 w-7 flex items-center justify-center rounded transition-colors hover:bg-[var(--surface-hover)] disabled:opacity-40 ${
                isRecording ? 'animate-pulse' : ''
              }`}
              style={{
                color: isRecording ? 'var(--danger)' : 'var(--text-3)',
                background: isRecording ? 'rgba(220,38,38,.1)' : 'transparent',
              }}
              title={t('composer.voice')}
            >
              <Mic size={15} />
            </button>

            <div className="flex-1" />

            {/* Strength selector */}
            <div
              className="flex items-center gap-0.5 rounded-md p-0.5"
              style={{ background: 'var(--surface-1)' }}
            >
              <Thermometer
                size={11}
                className="mx-1"
                style={{ color: 'var(--text-3)' }}
              />
              {STRENGTH_VALUES.map((v, i) => {
                const active = temperature === v;
                return (
                  <button
                    key={v}
                    onClick={() => setTemperature(v)}
                    className="px-2 py-0.5 text-[10px] rounded transition-colors"
                    style={{
                      background: active ? 'var(--accent)' : 'transparent',
                      color: active ? 'var(--accent-text)' : 'var(--text-3)',
                    }}
                  >
                    {t(STRENGTH_KEYS[i])}
                  </button>
                );
              })}
            </div>

            {/* Send / Stop button */}
            {isStreaming && onStop ? (
              <button
                onClick={onStop}
                className="h-7 w-7 flex items-center justify-center rounded transition-opacity hover:opacity-90"
                style={{ background: 'var(--danger)', color: '#ffffff' }}
                title="Stop"
              >
                <Square size={12} fill="currentColor" />
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!canSend}
                className="h-7 w-7 flex items-center justify-center rounded transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-30"
                style={{ background: 'var(--accent)', color: 'var(--accent-text)' }}
                title={t('composer.send')}
              >
                <ArrowUp size={14} strokeWidth={2.5} />
              </button>
            )}
          </div>
        </div>

        <div className="mt-1.5 text-center text-[10px]" style={{ color: 'var(--text-faint)' }}>
          {t('composer.strengthHint')} · {sendBehavior === 'enter' ? 'Enter' : '⌘+Enter'}
        </div>
      </div>
    </div>
  );
}
