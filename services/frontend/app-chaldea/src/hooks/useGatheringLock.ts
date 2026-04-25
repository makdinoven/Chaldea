/**
 * Hook that exposes the active gathering session for a character (FEAT-128).
 *
 * Mirrors the structural pattern of `useBattleLock` but is built on top of
 * the existing Redux `gatheringSlice` (created in task #19). Responsibilities:
 *
 *  1. Reads the current `activeSession` from Redux so consumers can react
 *     to session start/end without remounting.
 *  2. Polls `getActiveGathering(characterId)` every 10 s while a session is
 *     active. The polling thunk also drives lazy-finalize on the server,
 *     so the next poll after `complete_at` returns `active=false` and the
 *     session disappears from Redux.
 *  3. Keeps a client-side `remainingSeconds` counter that ticks every second
 *     so the banner can show a smooth countdown without re-fetching.
 *  4. Stops polling immediately when the character changes or the consumer
 *     unmounts (no zombie timers).
 *
 * Per CLAUDE.md: TypeScript strict, no `React.FC`, no `any`.
 */
import { useEffect, useState } from 'react';
import { useAppDispatch, useAppSelector } from '../redux/store';
import {
  loadActiveGathering,
  selectActiveSession,
} from '../redux/slices/gatheringSlice';

export interface GatheringLockState {
  isGathering: boolean;
  sessionId: number | null;
  completeAt: string | null;
  remainingSeconds: number;
  locationId: number | null;
}

const POLL_INTERVAL_MS = 10_000;
const TICK_INTERVAL_MS = 1_000;

const computeRemainingSeconds = (completeAt: string | null): number => {
  if (!completeAt) return 0;
  const completeMs = Date.parse(completeAt);
  if (Number.isNaN(completeMs)) return 0;
  return Math.max(0, Math.floor((completeMs - Date.now()) / 1000));
};

/**
 * Returns the current gathering-lock state for the given character.
 * If `characterId` is null/undefined, the hook is inert (no polling, no lock).
 */
const useGatheringLock = (
  characterId: number | null | undefined,
): GatheringLockState => {
  const dispatch = useAppDispatch();
  const activeSession = useAppSelector(selectActiveSession);

  const completeAt = activeSession?.complete_at ?? null;
  const isGathering = activeSession !== null;

  const [remainingSeconds, setRemainingSeconds] = useState<number>(() =>
    computeRemainingSeconds(completeAt),
  );

  // ── Polling effect ───────────────────────────────────────────────────────
  // We re-run when characterId or the active-session presence flips. The
  // poll's fulfilled action will update `activeSession` in Redux; once the
  // server reports `active=false` the slice clears it, our selector returns
  // null, this effect re-runs and the interval is cleared on cleanup.
  useEffect(() => {
    if (!characterId) {
      return;
    }

    let cancelled = false;

    // Always do an initial fetch on mount / character switch so we discover
    // an in-flight session that started elsewhere (e.g. another browser tab).
    void dispatch(loadActiveGathering(characterId));

    if (!isGathering) {
      // Not currently gathering — no need to keep hitting the server.
      return () => {
        cancelled = true;
      };
    }

    const intervalId = window.setInterval(() => {
      if (cancelled) return;
      void dispatch(loadActiveGathering(characterId));
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [dispatch, characterId, isGathering]);

  // ── Countdown ticker ─────────────────────────────────────────────────────
  // Client-side 1-second tick recomputed from completeAt so the banner can
  // animate without spamming the API.
  useEffect(() => {
    if (!completeAt) {
      setRemainingSeconds(0);
      return;
    }

    setRemainingSeconds(computeRemainingSeconds(completeAt));

    const tickId = window.setInterval(() => {
      setRemainingSeconds(computeRemainingSeconds(completeAt));
    }, TICK_INTERVAL_MS);

    return () => {
      window.clearInterval(tickId);
    };
  }, [completeAt]);

  return {
    isGathering,
    sessionId: activeSession?.session_id ?? null,
    completeAt,
    remainingSeconds,
    locationId: activeSession?.location_id ?? null,
  };
};

export default useGatheringLock;
