'use client';

import { useState, useEffect } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { apiClient } from '@/lib/api';
import { Trash2, Plus } from 'lucide-react';

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
    await apiClient.addMemory({ kind: 'semantic', title: newMemory.slice(0, 30), content: newMemory, tags: ['manual', 'user-profile'] });
    setNewMemory('');
    load();
  };

  const handleDelete = async (id: string) => {
    await apiClient.deleteMemory(id);
    load();
  };

  const layerLabel = (kind: string) => ({ semantic: '知识', episodic: '事件', reflective: '偏好' }[kind] || kind);

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto p-8 overflow-y-auto h-full">
        <h1 className="text-xl font-semibold mb-2">记忆</h1>
        <p className="text-sm mb-6" style={{ color: 'var(--text-2)' }}>
          madcop 会自动记住你的身份、偏好和重要信息。你也可以手动添加或删除记忆。
        </p>

        <div className="flex gap-2 mb-6">
          <input
            value={newMemory}
            onChange={(e) => setNewMemory(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleAdd(); }}
            placeholder="例: 用户喜欢吃火锅"
            className="flex-1 px-3 py-2 text-sm rounded-lg border outline-none"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)', color: 'var(--text)' }}
          />
          <button
            onClick={handleAdd}
            className="px-4 py-2 text-sm rounded-lg font-medium text-white flex items-center gap-1"
            style={{ background: 'var(--accent)' }}
          >
            <Plus size={15} /> 添加
          </button>
        </div>

        <h2 className="text-xs uppercase tracking-wide mb-3" style={{ color: 'var(--text-2)' }}>
          已有记忆 ({items.length})
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
                <button onClick={() => handleDelete(m.id)} className="ml-2 p-1 rounded hover:bg-[var(--surface-3)]" style={{ color: 'var(--danger)' }}>
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
          {!items.length && <p className="text-sm" style={{ color: 'var(--text-2)' }}>还没有任何记忆。开始对话或手动添加。</p>}
        </div>
      </div>
    </AppShell>
  );
}
