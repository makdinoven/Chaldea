import { useEffect, useState } from 'react';
import { useAppDispatch, useAppSelector } from '../redux/store';
import { getMe } from '../redux/slices/userSlice';
import { parseServerDate } from '../utils/serverDate';

/**
 * FEAT-175 activity lock of the selected character, as sent by `/users/me`
 * (`character.activity_lock`, computed by character-service):
 * - `dungeon` — the character is inside a dungeon run;
 * - `unconscious` — knocked out after a wipe until `until` (naive UTC);
 * - `asleep` — FEAT-180: sleeping in a house bedroom until woken;
 * - `reading` — FEAT-180 stage 6b: reading in a house library until stopped.
 * While locked the backend refuses outside-world actions with 409.
 */
export type ActivityLockReason = 'dungeon' | 'unconscious' | 'asleep' | 'reading';

export interface ActivityLockData {
  locked: boolean;
  reason: ActivityLockReason | null;
  until: string | null;
  dungeon_session_id: number | null;
}

export interface ActivityLockState {
  locked: boolean;
  reason: ActivityLockReason | null;
  /** End of unconsciousness (local Date), null otherwise. */
  until: Date | null;
  dungeonSessionId: number | null;
  /** Short Russian explanation, null when not locked. */
  message: string | null;
}

const NOT_LOCKED: ActivityLockState = {
  locked: false,
  reason: null,
  until: null,
  dungeonSessionId: null,
  message: null,
};

/** "HH:MM" in the player's own timezone. */
export const formatLocalTime = (date: Date): string =>
  date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });

const readLock = (raw: unknown): ActivityLockData | null => {
  if (!raw || typeof raw !== 'object') return null;
  return raw as ActivityLockData;
};

const useActivityLock = (): ActivityLockState => {
  const dispatch = useAppDispatch();
  const raw = useAppSelector((state) => state.user.character?.activity_lock);
  const lock = readLock(raw);
  const [now, setNow] = useState(() => Date.now());

  const untilDate = lock?.reason === 'unconscious' ? parseServerDate(lock.until) : null;
  const untilMs = untilDate ? untilDate.getTime() : null;

  // Re-evaluate when the knock-out ends and refresh the profile, so the lock
  // disappears without a page reload.
  useEffect(() => {
    if (untilMs === null) return;
    const left = untilMs - Date.now();
    if (left <= 0) return;
    const timer = setTimeout(() => {
      setNow(Date.now());
      dispatch(getMe());
    }, left + 1000);
    return () => clearTimeout(timer);
  }, [untilMs, dispatch]);

  if (!lock || !lock.locked) return NOT_LOCKED;

  if (lock.reason === 'unconscious') {
    if (untilMs !== null && untilMs <= now) return NOT_LOCKED;
    return {
      locked: true,
      reason: 'unconscious',
      until: untilDate,
      dungeonSessionId: null,
      message: untilDate
        ? `Персонаж без сознания до ${formatLocalTime(untilDate)}`
        : 'Персонаж без сознания',
    };
  }

  if (lock.reason === 'asleep') {
    return {
      locked: true,
      reason: 'asleep',
      until: null,
      dungeonSessionId: null,
      message: 'Персонаж спит',
    };
  }

  if (lock.reason === 'reading') {
    return {
      locked: true,
      reason: 'reading',
      until: null,
      dungeonSessionId: null,
      message: 'Персонаж читает',
    };
  }

  return {
    locked: true,
    reason: 'dungeon',
    until: null,
    dungeonSessionId: lock.dungeon_session_id ?? null,
    message: 'Персонаж находится в подземелье',
  };
};

export default useActivityLock;
