import { useCountdownTo } from '../../hooks/useCountdown';

interface RemainingTextProps {
  /** Target moment: a `Date` or a naive-UTC server timestamp. */
  until: Date | string | null | undefined;
  /** Text before the clock (default «осталось»). */
  prefix?: string;
  /** Shown once the target has passed; nothing by default. */
  doneText?: string;
  /** Fires once when the target passes while mounted. */
  onDone?: () => void;
  className?: string;
}

/**
 * FEAT-198 (A8) — a live countdown «осталось 2 д 05:13:20». Owns its own
 * one-second tick so the parent does not re-render every second.
 */
const RemainingText = ({ until, prefix = 'осталось', doneText, onDone, className = '' }: RemainingTextProps) => {
  const { formatted, isDone } = useCountdownTo(until, onDone);
  if (!until) return null;
  if (isDone) return doneText ? <span className={className}>{doneText}</span> : null;
  return (
    <span className={className}>
      {prefix ? `${prefix} ` : ''}
      <span className="font-mono tabular-nums">{formatted}</span>
    </span>
  );
};

export default RemainingText;
