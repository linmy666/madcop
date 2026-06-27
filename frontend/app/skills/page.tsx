'use client';

import { useState, useEffect } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { apiClient } from '@/lib/api';
import { Trash2, Plus, BookOpen, X } from 'lucide-react';
import { useT, useLocale } from '@/hooks/useTranslation';

interface Skill {
  name: string;
  description: string;
  triggers: string[];
  source: string;
  created_at: string;
  body_preview: string;
}

export default function SkillsPage() {
  const t = useT();
  const [locale] = useLocale();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState('');
  const [newBody, setNewBody] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await apiClient.listSkills();
      setSkills(data.skills || []);
    } catch {
      setSkills([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleDelete = async (name: string) => {
    if (!confirm(t('trace.resumeConfirm').replace(t('trace.resume'), t('skills.delete')))) return;
    try {
      await apiClient.deleteSkill(name);
      load();
    } catch (e) {
      alert((e as Error).message);
    }
  };

  const handleAdd = async () => {
    if (!newName.trim() || !newBody.trim()) return;
    try {
      const r = await fetch('http://127.0.0.1:8765/api/skills', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newName,
          description: newName,
          body: newBody,
          triggers: [],
          source: 'manual',
        }),
      });
      if (r.ok) {
        setShowAdd(false);
        setNewName('');
        setNewBody('');
        load();
      }
    } catch (e) {
      alert((e as Error).message);
    }
  };

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto p-8 overflow-y-auto h-full">
        <h1 className="text-xl font-semibold mb-2">{t('skills.title')}</h1>
        <p className="text-sm mb-6" style={{ color: 'var(--text-2)' }}>{t('skills.subtitle')}</p>

        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-2)' }}>
            {t('skills.saved', { count: skills.length })}
          </h2>
          <button
            onClick={() => setShowAdd((s) => !s)}
            className="flex items-center gap-1 px-3 py-1 text-[12px] rounded-lg"
            style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
          >
            <Plus size={12} />
            {t('skills.add')}
          </button>
        </div>

        {/* Add form */}
        {showAdd && (
          <div
            className="mb-4 p-4 rounded-xl border animate-slide-up"
            style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
          >
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-sm font-medium">{t('skills.add')}</h3>
              <button onClick={() => setShowAdd(false)} className="p-1 rounded hover:bg-[var(--surface-2)]">
                <X size={14} style={{ color: 'var(--text-2)' }} />
              </button>
            </div>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder={t('skills.placeholder')}
              className="w-full mb-2 px-3 py-2 text-sm rounded-lg border outline-none"
              style={{ background: 'var(--surface-2)', borderColor: 'var(--border)', color: 'var(--text)' }}
            />
            <textarea
              value={newBody}
              onChange={(e) => setNewBody(e.target.value)}
              placeholder={t('skills.body')}
              rows={5}
              className="w-full px-3 py-2 text-sm rounded-lg border outline-none font-mono"
              style={{ background: 'var(--surface-2)', borderColor: 'var(--border)', color: 'var(--text)' }}
            />
            <div className="flex gap-2 mt-3">
              <button
                onClick={handleAdd}
                disabled={!newName.trim() || !newBody.trim()}
                className="px-4 py-1.5 text-sm rounded-lg font-medium text-white disabled:opacity-40"
                style={{ background: 'var(--accent)' }}
              >
                {t('skills.add')}
              </button>
            </div>
          </div>
        )}

        {loading && (
          <div className="text-center text-sm py-8" style={{ color: 'var(--text-3)' }}>...</div>
        )}

        {!loading && skills.length === 0 && (
          <div className="text-center text-sm py-8" style={{ color: 'var(--text-faint)' }}>
            <BookOpen size={32} className="mx-auto mb-2 opacity-30" />
            {t('skills.empty')}
          </div>
        )}

        <div className="space-y-2">
          {skills.map((s) => {
            const isExpanded = expanded === s.name;
            return (
              <div
                key={s.name}
                className="rounded-xl border overflow-hidden"
                style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
              >
                <div
                  onClick={() => setExpanded(isExpanded ? null : s.name)}
                  className="flex items-center gap-3 p-3 cursor-pointer"
                >
                  <BookOpen size={14} style={{ color: 'var(--accent)' }} className="flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm truncate">{s.name}</div>
                    <div className="text-[11px] truncate" style={{ color: 'var(--text-3)' }}>
                      {s.description}
                    </div>
                  </div>
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded"
                    style={{
                      background: s.source === 'auto' ? 'var(--accent-dim)' : 'var(--surface-2)',
                      color: s.source === 'auto' ? 'var(--accent)' : 'var(--text-2)',
                    }}
                  >
                    {s.source === 'auto' ? t('skills.sourceAuto') : t('skills.sourceManual')}
                  </span>
                  {s.triggers && s.triggers.length > 0 && (
                    <div className="hidden md:flex gap-1">
                      {s.triggers.slice(0, 3).map((tr, i) => (
                        <span
                          key={i}
                          className="text-[10px] px-1.5 py-0.5 rounded"
                          style={{ background: 'var(--surface-2)', color: 'var(--text-2)' }}
                        >
                          {tr}
                        </span>
                      ))}
                    </div>
                  )}
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDelete(s.name); }}
                    className="p-1 rounded hover:bg-[var(--surface-2)]"
                    style={{ color: 'var(--danger)' }}
                    title={t('skills.delete')}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
                {isExpanded && (
                  <div
                    className="px-3 pb-3 text-[12px] border-t"
                    style={{ borderColor: 'var(--border)', color: 'var(--text-2)' }}
                  >
                    <pre className="mt-2 whitespace-pre-wrap font-mono text-[11px]" style={{ color: 'var(--text-2)' }}>
                      {s.body_preview}
                    </pre>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </AppShell>
  );
}
