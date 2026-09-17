// FEAT-151 — shared profile-tab primitive: centered icon + message
// (empty quests detail, no invites, empty history/filter, 0 titles/skills).
import type { ReactNode } from 'react';
import { hasPaddingClass } from './classUtils';

interface EmptyStateProps {
  /** Lucide icon (or project SVG), styled `text-white/20` by the caller */
  icon?: ReactNode;
  message: string;
  /** Optional secondary line under the message (FEAT-166) */
  hint?: string;
  /** Optional action (link/button) rendered below the message */
  action?: ReactNode;
  className?: string;
}

const EmptyState = ({ icon, message, hint, action, className = '' }: EmptyStateProps) => {
  const padding = hasPaddingClass(className) ? '' : 'py-14';
  return (
    <div
      className={`flex flex-col items-center justify-center gap-3 ${padding} text-center ${className}`}
    >
      {icon}
      <p className="text-sm text-white/40">{message}</p>
      {hint && <p className="-mt-2 text-xs text-white/30">{hint}</p>}
      {action}
    </div>
  );
};

export default EmptyState;
