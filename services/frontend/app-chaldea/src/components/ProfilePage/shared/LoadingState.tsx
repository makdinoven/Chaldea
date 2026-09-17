// FEAT-166 — shared profile-tab primitive: the one gold spinner.
// `md` — tab/panel loading, `sm` — section loading,
// `xs` — bare inline 16px spinner (buttons, "load more").

import { hasPaddingClass } from './classUtils';

interface LoadingStateProps {
  size?: 'xs' | 'sm' | 'md';
  /** Optional caption under the spinner (not rendered for `xs`, used as aria-label) */
  label?: string;
  className?: string;
}

const SPINNER_BASE = 'border-2 border-gold border-t-transparent rounded-full animate-spin';

const LoadingState = ({ size = 'md', label, className = '' }: LoadingStateProps) => {
  if (size === 'xs') {
    return (
      <span
        role="status"
        aria-label={label ?? 'Загрузка'}
        className={`inline-block w-4 h-4 shrink-0 ${SPINNER_BASE} ${className}`}
      />
    );
  }

  const spinnerSize = size === 'md' ? 'w-8 h-8' : 'w-6 h-6';
  // Caller padding (e.g. `py-32`) replaces the default instead of competing with it.
  const padding = hasPaddingClass(className) ? '' : size === 'md' ? 'py-20' : 'py-6';

  return (
    <div
      role="status"
      className={`flex flex-col items-center justify-center gap-3 ${padding} ${className}`}
    >
      <span className={`${spinnerSize} ${SPINNER_BASE}`} />
      {label && <p className="text-sm text-white/40">{label}</p>}
    </div>
  );
};

export default LoadingState;
