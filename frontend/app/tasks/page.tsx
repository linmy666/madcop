'use client';

import { AppShell } from '@/components/layout/AppShell';
import { Clock } from 'lucide-react';

export default function TasksPage() {
  return (
    <AppShell>
      <div className="max-w-2xl mx-auto p-8 overflow-y-auto h-full">
        <h1 className="text-xl font-semibold mb-2">定时任务</h1>
        <p className="text-sm mb-8" style={{ color: 'var(--text-2)' }}>
          创建计划任务，让 madcop 在指定时间自动执行。
        </p>
        <div className="flex flex-col items-center justify-center py-20" style={{ color: 'var(--text-faint)' }}>
          <Clock size={48} className="mb-4 opacity-30" />
          <p className="text-sm">暂无定时任务</p>
          <p className="text-xs mt-1">此功能即将推出</p>
        </div>
      </div>
    </AppShell>
  );
}
