import { useEffect, useState } from 'react';
import { fetchBattlePreview, type BattlePreview } from '../api/battles';

interface BattlePreviewState {
  preview: BattlePreview | null;
  loading: boolean;
  error: boolean;
}

/** Refresh cadence for the in-battle banner (FEAT-152 §3.2). */
const REFRESH_INTERVAL_MS = 15_000;

/**
 * Fetches the compact battle preview (`GET /battles/{id}/preview`, JWT via
 * shared axios interceptors) for the battle-lock banner and refreshes it
 * every 15 s while mounted.
 *
 * Errors are intentionally silent here (no toast): per FEAT-152 §3.2 the
 * consumer must degrade to a generic "Вы в бою" banner that still informs
 * the user, so the failure is never invisible to them. `error` is exposed
 * for consumers that want to react explicitly.
 */
const useBattlePreview = (
  battleId: number | null | undefined,
): BattlePreviewState => {
  const [state, setState] = useState<BattlePreviewState>({
    preview: null,
    loading: false,
    error: false,
  });

  useEffect(() => {
    if (!battleId) {
      setState({ preview: null, loading: false, error: false });
      return;
    }

    let cancelled = false;
    setState((prev) => ({ ...prev, loading: true }));

    const load = async (): Promise<void> => {
      try {
        const data = await fetchBattlePreview(battleId);
        if (!cancelled) {
          setState({ preview: data, loading: false, error: false });
        }
      } catch {
        if (!cancelled) {
          // Keep the last successful preview (if any) so a transient
          // network error doesn't blank the banner between refreshes.
          setState((prev) => ({
            preview: prev.preview,
            loading: false,
            error: true,
          }));
        }
      }
    };

    load();
    const interval = setInterval(load, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [battleId]);

  return state;
};

export default useBattlePreview;
