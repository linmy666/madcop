'use client';

import { useState, useEffect } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { apiClient } from '@/lib/api';
import { Trash2, Check } from 'lucide-react';
import { useT, useLocale } from '@/hooks/useTranslation';

export default function SettingsPage() {
  const t = useT();
  const [locale, setLocale] = useLocale();

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
    if (!baseUrl || !model) { setFlash({ msg: t('settings.fillRequired'), ok: false }); return; }
    try {
      const label = presets.find((p) => p.id === providerId)?.label || providerId;
      await apiClient.saveProvider({ provider_id: providerId || 'custom', base_url: baseUrl, api_key: apiKey, model, label });
      setApiKey('');
      setFlash({ msg: t('settings.saveSuccess'), ok: true });
      const updated = await apiClient.getSettings();
      setSettings(updated);
    } catch { setFlash({ msg: t('settings.saveFail'), ok: false }); }
  };

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto p-8 overflow-y-auto h-full">
        <h1 className="text-xl font-semibold mb-6">{t('settings.title')}</h1>
        {flash && <div className="mb-4 p-3 rounded-lg text-sm" style={{ background: flash.ok ? 'var(--accent-dim)' : 'rgba(239,68,68,.1)', color: flash.ok ? 'var(--accent)' : 'var(--danger)' }}>{flash.msg}</div>}

        {/* Language selector */}
        <h2 className="text-xs uppercase tracking-wide mb-3" style={{ color: 'var(--text-2)' }}>{t('settings.language')}</h2>
        <div className="flex gap-2 mb-8">
          {(['en', 'zh'] as const).map((l) => (
            <button
              key={l}
              onClick={() => setLocale(l)}
              className="px-4 py-2 text-sm rounded-lg border transition-colors"
              style={{
                borderColor: locale === l ? 'var(--accent)' : 'var(--border)',
                background: locale === l ? 'var(--accent-dim)' : 'var(--surface)',
                color: locale === l ? 'var(--accent)' : 'var(--text)',
              }}
            >
              {l === 'en' ? t('settings.languageEn') : t('settings.languageZh')}
              {locale === l && <Check size={14} className="inline ml-1" />}
            </button>
          ))}
        </div>

        <h2 className="text-xs uppercase tracking-wide mb-3" style={{ color: 'var(--text-2)' }}>{t('settings.configuredProviders')}</h2>
        <div className="space-y-2 mb-8">
          {(settings?.providers || []).map((p) => (
            <div key={p.provider_id} className="p-3 rounded-xl border" style={{ borderColor: p.provider_id === settings?.active_provider ? 'var(--accent)' : 'var(--border)', background: 'var(--surface)' }}>
              <div className="flex justify-between items-center">
                <div>
                  <div className="font-medium text-sm flex items-center gap-2">{p.label} {p.provider_id === settings?.active_provider && <Check size={14} style={{ color: 'var(--accent)' }} />}</div>
                  <div className="text-xs mt-0.5" style={{ color: 'var(--text-2)' }}>{p.model} · {p.api_key_masked || 'no key'}</div>
                </div>
                <div className="flex gap-3">
                  {p.provider_id !== settings?.active_provider && (
                    <button className="text-xs cursor-pointer hover:text-[var(--accent)]" onClick={async () => { await apiClient.setActiveProvider(p.provider_id); setSettings(await apiClient.getSettings()); }}>{t('settings.setDefault')}</button>
                  )}
                  <button className="text-xs cursor-pointer" title={t('settings.delete')} style={{ color: 'var(--danger)' }} onClick={async () => { await apiClient.deleteProvider(p.provider_id); setSettings(await apiClient.getSettings()); }}><Trash2 size={14} /></button>
                </div>
              </div>
            </div>
          ))}
          {!settings?.providers.length && <p className="text-sm" style={{ color: 'var(--text-2)' }}>{t('settings.noProviders')}</p>}
        </div>

        <h2 className="text-xs uppercase tracking-wide mb-3" style={{ color: 'var(--text-2)' }}>{t('settings.addOrUpdate')}</h2>
        <div className="space-y-3">
          <div>
            <label className="text-xs block mb-1" style={{ color: 'var(--text-2)' }}>{t('settings.provider')}</label>
            <select value={providerId} onChange={(e) => onPresetChange(e.target.value)} className="w-full px-3 py-2 text-sm rounded-lg border outline-none" style={{ background: 'var(--surface)', borderColor: 'var(--border)', color: 'var(--text)' }}>
              <option value="">{t('settings.providerPlaceholder')}</option>
              {presets.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs block mb-1" style={{ color: 'var(--text-2)' }}>{t('settings.baseUrl')}</label>
            <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder={t('settings.baseUrlPlaceholder')} className="w-full px-3 py-2 text-sm rounded-lg border outline-none" style={{ background: 'var(--surface)', borderColor: 'var(--border)', color: 'var(--text)' }} />
          </div>
          <div>
            <label className="text-xs block mb-1" style={{ color: 'var(--text-2)' }}>{t('settings.apiKey')}</label>
            <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={t('settings.apiKeyPlaceholder')} className="w-full px-3 py-2 text-sm rounded-lg border outline-none" style={{ background: 'var(--surface)', borderColor: 'var(--border)', color: 'var(--text)' }} />
          </div>
          <div>
            <label className="text-xs block mb-1" style={{ color: 'var(--text-2)' }}>{t('settings.model')}</label>
            <input value={model} onChange={(e) => setModel(e.target.value)} placeholder={t('settings.modelPlaceholder')} className="w-full px-3 py-2 text-sm rounded-lg border outline-none" style={{ background: 'var(--surface)', borderColor: 'var(--border)', color: 'var(--text)' }} />
          </div>
          <button onClick={handleSave} className="px-4 py-2 text-sm rounded-lg font-medium text-white" style={{ background: 'var(--accent)' }}>{t('settings.save')}</button>
        </div>
      </div>
    </AppShell>
  );
}
