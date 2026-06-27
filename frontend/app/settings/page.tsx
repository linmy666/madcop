'use client';

import { useState, useEffect } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { apiClient } from '@/lib/api';
import { Trash2, Plus, Check } from 'lucide-react';

export default function SettingsPage() {
  const [settings, setSettings] = useState<Awaited<ReturnType<typeof apiClient.getSettings>> | null>(null);
  const [providerId, setProviderId] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [flash, setFlash] = useState<{ msg: string; ok: boolean } | null>(null);

  useEffect(() => {
    apiClient.getSettings().then(setSettings).catch(() => {});
  }, []);

  const presets = settings?.presets || [];

  const onPresetChange = (id: string) => {
    setProviderId(id);
    const preset = presets.find((p) => p.id === id);
    if (preset) {
      setBaseUrl(preset.base_url);
      setModel(preset.default_model);
    }
  };

  const handleSave = async () => {
    if (!baseUrl || !model) { setFlash({ msg: '请填写 Base URL 和 Model', ok: false }); return; }
    try {
      const label = presets.find((p) => p.id === providerId)?.label || providerId;
      await apiClient.saveProvider({ provider_id: providerId || 'custom', base_url: baseUrl, api_key: apiKey, model, label });
      setApiKey('');
      setFlash({ msg: '保存成功', ok: true });
      const updated = await apiClient.getSettings();
      setSettings(updated);
    } catch { setFlash({ msg: '保存失败', ok: false }); }
  };

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto p-8 overflow-y-auto h-full">
        <h1 className="text-xl font-semibold mb-6">设置</h1>
        {flash && <div className="mb-4 p-3 rounded-lg text-sm" style={{ background: flash.ok ? 'var(--accent-dim)' : 'rgba(239,68,68,.1)', color: flash.ok ? 'var(--accent)' : 'var(--danger)' }}>{flash.msg}</div>}

        <h2 className="text-xs uppercase tracking-wide mb-3" style={{ color: 'var(--text-2)' }}>已配置的 Provider</h2>
        <div className="space-y-2 mb-8">
          {(settings?.providers || []).map((p) => (
            <div key={p.provider_id} className="p-3 rounded-xl border" style={{ borderColor: p.provider_id === settings?.active_provider ? 'var(--accent)' : 'var(--border)', background: 'var(--surface)' }}>
              <div className="flex justify-between items-center">
                <div>
                  <div className="font-medium text-sm flex items-center gap-2">{p.label} {p.provider_id === settings?.active_provider && <Check size={14} style={{ color: 'var(--accent)' }} />}</div>
                  <div className="text-xs mt-0.5" style={{ color: 'var(--text-2)' }}>{p.model} · {p.api_key_masked || 'no key'}</div>
                </div>
                <div className="flex gap-2">
                  {p.provider_id !== settings?.active_provider && (
                    <button className="text-xs cursor-pointer hover:text-[var(--accent)]" onClick={async () => { await apiClient.setActiveProvider(p.provider_id); setSettings(await apiClient.getSettings()); }}>设为默认</button>
                  )}
                  <button className="text-xs cursor-pointer" style={{ color: 'var(--danger)' }} onClick={async () => { await apiClient.deleteProvider(p.provider_id); setSettings(await apiClient.getSettings()); }}><Trash2 size={14} /></button>
                </div>
              </div>
            </div>
          ))}
          {!settings?.providers.length && <p className="text-sm" style={{ color: 'var(--text-2)' }}>还没有配置 Provider</p>}
        </div>

        <h2 className="text-xs uppercase tracking-wide mb-3" style={{ color: 'var(--text-2)' }}>添加 / 更新 Provider</h2>
        <div className="space-y-3">
          <div>
            <label className="text-xs block mb-1" style={{ color: 'var(--text-2)' }}>Provider</label>
            <select value={providerId} onChange={(e) => onPresetChange(e.target.value)} className="w-full px-3 py-2 text-sm rounded-lg border outline-none" style={{ background: 'var(--surface)', borderColor: 'var(--border)', color: 'var(--text)' }}>
              <option value="">— 选择 —</option>
              {presets.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs block mb-1" style={{ color: 'var(--text-2)' }}>API Base URL</label>
            <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.openai.com/v1" className="w-full px-3 py-2 text-sm rounded-lg border outline-none" style={{ background: 'var(--surface)', borderColor: 'var(--border)', color: 'var(--text)' }} />
          </div>
          <div>
            <label className="text-xs block mb-1" style={{ color: 'var(--text-2)' }}>API Key</label>
            <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-..." className="w-full px-3 py-2 text-sm rounded-lg border outline-none" style={{ background: 'var(--surface)', borderColor: 'var(--border)', color: 'var(--text)' }} />
          </div>
          <div>
            <label className="text-xs block mb-1" style={{ color: 'var(--text-2)' }}>Model</label>
            <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="gpt-4o-mini" className="w-full px-3 py-2 text-sm rounded-lg border outline-none" style={{ background: 'var(--surface)', borderColor: 'var(--border)', color: 'var(--text)' }} />
          </div>
          <button onClick={handleSave} className="px-4 py-2 text-sm rounded-lg font-medium text-white" style={{ background: 'var(--accent)' }}>保存</button>
        </div>
      </div>
    </AppShell>
  );
}
