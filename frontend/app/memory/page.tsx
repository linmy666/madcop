'use client';

import { useState, useEffect } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { apiClient } from '@/lib/api';
import { Trash2, Plus } from 'lucide-react';
import { useT, useLocale } from '@/hooks/useTranslation';
import { BRAND } from '@/lib/i18n';

interface MemItem {
  id: string;
  kind: string;
  title: string;
  content: string;
  tags: string[];
}

export default function MemoryPage() {
  const [items, setItems] = useState<MemItem[]>([]);
  const [newMemory, setNewMemory] = useState('');
  const t = useT();
  const [locale] = useLocale();

  const load = async () => {
    try {
      const data = await apiClient.getMemory();
      const all = [...(data.semantic || []), ...(data.episodic || []), ...(data.reflective || [])];
      setItems(all);
    } catch { /* empty */ }
  };

  useEffect(() => { load(); }, []);

  const handleAdd = async () => {
    if (!newMemory.trim()) return;
    try {
      await apiClient.addMemory({ kind: 'semantic', title: newMemory.slice(0, 30), content: newMemory, tags: ['manual', 'user-profile'] });
      setNewMemory('');
      load();
    } catch {
      alert(t('memory.addFail'));
    }
  };

  const handleDelete = async (id: string) => {
    await apiClient.deleteMemory(id);
    load();
  };

  const layerLabel = (kind: string) => {
    const labels: Record<string, Record<typeof locale, string>> = {
      semantic: { en: 'Knowledge', zh: '知识' },
      episodic: { en: 'Event', zh: '事件' },
      reflective: { en: 'Preference', zh: '偏好' },
    };
    return labels[kind]?.[locale] || kind;
  };

  // Personalise the subtitle so the user sees their assistant name
  const subtitle = t('memory.subtitle').replace('MadCop Agent', BRAND[locale].name);

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto p-8 overflow-y-auto h-full">
        <h1 className="text-xl font-semibold mb-2">{t('memory.title')}</h1>
        <p className="text-sm mb-6" style={{ color: 'var(--text-2)' }}>{subtitle}</p>

        <div className="flex gap-2 mb-6">
          <input
            value={newMemory}
            onChange={(e) => setNewMemory(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleAdd(); }}
            placeholder={t('memory.addPlaceholder')}
            className="flex-1 px-3 py-2 text-sm rounded-lg border outline-none"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)', color: 'var(--text)' }}
          />
          <button
            onClick={handleAdd}
            className="px-4 py-2 text-sm rounded-lg font-medium text-white flex items-center gap-1"
            style={{ background: 'var(--accent)' }}
          >
            <Plus size={15} /> {t('memory.add')}
          </button>
        </div>

        <h2 className="text-xs uppercase tracking-wide mb-3" style={{ color: 'var(--text-2)' }}>
          {t('memory.saved', { count: items.length })}
        </h2>
        <div className="space-y-2">
          {items.map((m) => (
            <div key={m.id} className="p-3 rounded-xl border" style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
              <div className="flex justify-between items-start">
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm">{m.title}</div>
                  <div className="text-xs mt-1" style={{ color: 'var(--text-2)' }}>
                    {layerLabel(m.kind)} · {(m.tags || []).join(', ')}
                  </div>
                  <div className="text-xs mt-1" style={{ color: 'var(--text-3)' }}>{m.content}</div>
                </div>
                <button onClick={() => handleDelete(m.id)} className="ml-2 p-1 rounded hover:bg-[var(--surface-3)]" title={t('memory.delete')} style={{ color: 'var(--danger)' }}>
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
          {!items.length && <p className="text-sm" style={{ color: 'var(--text-2)' }}>{t('memory.empty')}</p>}
        </div>
      </div>
    </AppShell>
  );
}
