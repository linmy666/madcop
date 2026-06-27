'use client';

import { AppShell } from '@/components/layout/AppShell';
import { Clock } from 'lucide-react';
import { useT, useLocale } from '@/hooks/useTranslation';
import { BRAND } from '@/lib/i18n';

export default function TasksPage() {
  const t = useT();
  const [locale] = useLocale();
  const brand = BRAND[locale];
  const subtitle = t('tasks.subtitle').replace('MadCop Agent', brand.name);
  return (
    <AppShell>
      <div className="max-w-2xl mx-auto p-8 overflow-y-auto h-full">
        <h1 className="text-xl font-semibold mb-2">{t('tasks.title')}</h1>
        <p className="text-sm mb-8" style={{ color: 'var(--text-2)' }}>{subtitle}</p>
        <div className="flex flex-col items-center justify-center py-20" style={{ color: 'var(--text-faint)' }}>
          <Clock size={48} className="mb-4 opacity-30" />
          <p className="text-sm">{t('tasks.empty')}</p>
          <p className="text-xs mt-1">{t('tasks.comingSoon')}</p>
        </div>
      </div>
    </AppShell>
  );
}
