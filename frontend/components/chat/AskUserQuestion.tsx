'use client';

import { useState } from 'react';
import { Check } from 'lucide-react';

interface QuestionOption {
  label: string;
  description?: string;
}

interface Props {
  question: string;
  options?: QuestionOption[];
  multiSelect?: boolean;
  onAnswer: (answer: string) => void;
}

export function AskUserQuestion({ question, options, multiSelect, onAnswer }: Props) {
  const [selected, setSelected] = useState<string[]>([]);

  const handleSelect = (label: string) => {
    if (multiSelect) {
      setSelected((prev) =>
        prev.includes(label) ? prev.filter((s) => s !== label) : [...prev, label],
      );
    } else {
      onAnswer(label);
    }
  };

  const handleSubmit = () => {
    onAnswer(selected.join(', '));
  };

  return (
    <div
      className="my-3 rounded-xl border p-4 animate-slide-up"
      style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
    >
      <p className="text-sm font-medium mb-3" style={{ color: 'var(--text)' }}>{question}</p>
      <div className="flex flex-col gap-2">
        {(options || []).map((opt) => {
          const isSelected = selected.includes(opt.label);
          return (
            <button
              key={opt.label}
              onClick={() => handleSelect(opt.label)}
              className="flex items-center gap-3 px-3 py-2 rounded-lg border text-left text-sm transition-all"
              style={{
                borderColor: isSelected ? 'var(--accent)' : 'var(--border)',
                background: isSelected ? 'var(--accent-dim)' : 'transparent',
                color: 'var(--text)',
              }}
            >
              <div
                className="flex h-5 w-5 items-center justify-center rounded border transition-all"
                style={{
                  borderColor: isSelected ? 'var(--accent)' : 'var(--border)',
                  background: isSelected ? 'var(--accent)' : 'transparent',
                }}
              >
                {isSelected && <Check size={12} style={{ color: 'white' }} />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-medium text-[13px]">{opt.label}</div>
                {opt.description && (
                  <div className="text-[11px] mt-0.5" style={{ color: 'var(--text-3)' }}>
                    {opt.description}
                  </div>
                )}
              </div>
            </button>
          );
        })}
      </div>
      {multiSelect && selected.length > 0 && (
        <button
          onClick={handleSubmit}
          className="mt-3 px-4 py-1.5 text-sm rounded-lg font-medium text-white"
          style={{ background: 'var(--accent)' }}
        >
          Submit ({selected.length})
        </button>
      )}
    </div>
  );
}
