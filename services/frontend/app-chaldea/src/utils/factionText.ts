import { useEffect, useState } from 'react';
import { fetchSubclasses } from '../api/subclasses';
import type { FactionConditionParams } from '../api/factions';

/**
 * FEAT-205 — the backend writes a subclass condition with raw keys
 * («Подкласс: berserker или duelist»); the names live in the skills-service
 * registry. One shared request per page; on failure the keys stay as they are
 * (the text is still readable, and the caller already shows its own errors).
 */
let subclassPromise: Promise<Record<string, string>> | null = null;

const loadSubclassNames = (): Promise<Record<string, string>> => {
  if (!subclassPromise) {
    subclassPromise = fetchSubclasses()
      .then((list) => Object.fromEntries(list.map((s) => [s.key, s.name])))
      .catch((e: unknown) => {
        subclassPromise = null;
        throw e;
      });
  }
  return subclassPromise;
};

/** key → name; empty until loaded. `onError` gets a Russian message. */
export const useSubclassNames = (onError?: (message: string) => void): Record<string, string> => {
  const [names, setNames] = useState<Record<string, string>>({});
  useEffect(() => {
    let cancelled = false;
    loadSubclassNames()
      .then((map) => {
        if (!cancelled) setNames(map);
      })
      .catch((e: unknown) => {
        if (!cancelled && onError) onError(e instanceof Error ? e.message : 'Не удалось загрузить подклассы.');
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return names;
};

/** The condition text with subclass keys replaced by their names. */
export const factionConditionText = (
  cond: { type: string; text: string; params?: FactionConditionParams | null },
  subclassNames: Record<string, string>,
): string => {
  if (cond.type !== 'subclass') return cond.text;
  const keys = Array.isArray(cond.params?.subclass_keys) ? (cond.params?.subclass_keys as unknown[]) : null;
  if (!keys || keys.length === 0) return cond.text;
  return `Подкласс: ${keys.map((k) => subclassNames[String(k)] ?? String(k)).join(' или ')}`;
};

/** Server texts (e.g. a join block reason) may quote raw subclass keys — swap in the names. */
export const replaceSubclassKeys = (text: string, subclassNames: Record<string, string>): string =>
  text.replace(/[a-z0-9_]{3,50}/g, (key) => subclassNames[key] ?? key);
