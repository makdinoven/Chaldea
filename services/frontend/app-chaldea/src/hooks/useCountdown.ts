import { useState, useEffect, useRef, useCallback } from 'react';
import { parseServerDate } from '../utils/serverDate';
import { formatRemaining } from '../utils/formatRemaining';

/**
 * Countdown hook that counts down to a target timestamp.
 * @param targetTimestamp - Unix timestamp (seconds) when the countdown ends, or null to disable.
 * @returns { remaining, formatted, isDone }
 *   - remaining: seconds left (0 when done)
 *   - formatted: string in MM:SS format
 *   - isDone: true when countdown reaches 0
 */
const useCountdown = (targetTimestamp: number | null) => {
  const calcRemaining = useCallback((): number => {
    if (!targetTimestamp) return 0;
    const now = Math.floor(Date.now() / 1000);
    return Math.max(0, targetTimestamp - now);
  }, [targetTimestamp]);

  const [remaining, setRemaining] = useState(calcRemaining);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setRemaining(calcRemaining());

    if (!targetTimestamp) return;

    intervalRef.current = setInterval(() => {
      const left = calcRemaining();
      setRemaining(left);
      if (left <= 0 && intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }, 1000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [targetTimestamp, calcRemaining]);

  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  const formatted = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;

  return { remaining, formatted, isDone: remaining <= 0 };
};

export default useCountdown;

/* ── FEAT-198 (A8): live countdown to a server timestamp ─────────────────── */

export interface CountdownTo {
  /** Seconds left (0 when done or no target). */
  remaining: number;
  /** «2 д 05:13:20» / «05:13:20» / «13:20». */
  formatted: string;
  /** «осталось …». */
  text: string;
  /** True when there is a target and it has passed. */
  isDone: boolean;
}

/**
 * Ticks every second until `target` (a `Date` or a naive-UTC server string,
 * parsed with `parseServerDate`). `onDone` fires once when the target passes
 * while mounted (e.g. to refresh `/users/me`).
 */
export const useCountdownTo = (
  target: Date | string | null | undefined,
  onDone?: () => void,
): CountdownTo => {
  const targetMs =
    target instanceof Date ? target.getTime() : parseServerDate(target ?? null)?.getTime() ?? null;
  const [now, setNow] = useState(() => Date.now());
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    setNow(Date.now());
    if (targetMs === null || targetMs <= Date.now()) return;
    const timer = setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (current >= targetMs) {
        clearInterval(timer);
        onDoneRef.current?.();
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [targetMs]);

  const remaining = targetMs === null ? 0 : Math.max(0, Math.ceil((targetMs - now) / 1000));
  const formatted = formatRemaining(remaining);
  return { remaining, formatted, text: `осталось ${formatted}`, isDone: targetMs !== null && remaining <= 0 };
};
