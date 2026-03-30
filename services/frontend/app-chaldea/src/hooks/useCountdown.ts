import { useState, useEffect, useRef, useCallback } from 'react';

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
