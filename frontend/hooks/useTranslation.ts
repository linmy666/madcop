'use client';

import { useEffect, useState, useCallback } from 'react';
import { Locale, getStoredLocale, setStoredLocale, translate } from '@/lib/i18n';

const listeners = new Set<() => void>();

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function notify() {
  listeners.forEach((fn) => fn());
}

export function getLocale(): Locale {
  return getStoredLocale();
}

export function useLocale(): [Locale, (l: Locale) => void] {
  const [locale, setLocale] = useState<Locale>('en');

  useEffect(() => {
    setLocale(getStoredLocale());
    const unsubscribe = subscribe(() => setLocale(getStoredLocale()));
    return () => {
      unsubscribe();
    };
  }, []);

  const set = useCallback((l: Locale) => {
    setStoredLocale(l);
    notify();
  }, []);

  return [locale, set];
}

export function useT() {
  const [locale] = useLocale();
  return (key: string, vars?: Record<string, string | number>) => translate(locale, key, vars);
}
