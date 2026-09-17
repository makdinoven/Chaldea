// FEAT-166 — shared profile-tab primitive: centered error message with an
// optional retry button (pass `onRetry` only if the tab already had a retry).
import { AlertTriangle } from 'lucide-react';
import { hasPaddingClass } from './classUtils';

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
  className?: string;
}

const ErrorState = ({ message, onRetry, className = '' }: ErrorStateProps) => {
  const padding = hasPaddingClass(className) ? '' : 'py-14';
  return (
    <div
      role="alert"
      className={`flex flex-col items-center justify-center gap-3 ${padding} text-center ${className}`}
    >
      <AlertTriangle size={32} strokeWidth={1.5} className="text-site-red/60" />
      <p className="text-sm text-white/60">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-line">
          Повторить
        </button>
      )}
    </div>
  );
};

export default ErrorState;
