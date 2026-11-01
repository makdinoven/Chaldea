import { useEffect, useMemo, useState } from 'react';
import { fetchSubclasses, type Subclass, type SubclassPassive } from '../api/subclasses';

/*
  The public subclass registry (GET /skills/subclasses) keyed by subclass key,
  with each subclass's passive (FEAT-188). The caller shows `error` to the
  player — it is already a Russian message.
*/

interface SubclassRegistry {
  /** subclass_key → subclass */
  subclasses: Record<string, Subclass>;
  /** subclass_key → its passive (subclasses without one are left out) */
  passives: Record<string, SubclassPassive>;
  loading: boolean;
  error: string | null;
}

/**
 * @param enabled  fetch only once this is true (e.g. a subclass is known)
 * @param classId  narrow to one class; omitted — every class's subclasses
 */
const useSubclassRegistry = (enabled: boolean, classId?: number | null): SubclassRegistry => {
  const [list, setList] = useState<Subclass[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchSubclasses(classId ?? undefined)
      .then((data) => {
        if (!cancelled) setList(data);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Не удалось загрузить подклассы.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, classId]);

  const { subclasses, passives } = useMemo(() => {
    const byKey: Record<string, Subclass> = {};
    const passiveByKey: Record<string, SubclassPassive> = {};
    for (const s of list) {
      byKey[s.key] = s;
      if (s.passive) passiveByKey[s.key] = s.passive;
    }
    return { subclasses: byKey, passives: passiveByKey };
  }, [list]);

  return { subclasses, passives, loading, error };
};

export default useSubclassRegistry;
