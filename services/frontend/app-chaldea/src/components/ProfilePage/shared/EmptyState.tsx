// FEAT-151 — shared profile-tab primitive: centered icon + message
// (empty quests detail, no invites, empty history/filter, 0 titles/skills).
import type { ReactNode } from 'react';

interface EmptyStateProps {
  /** Lucide icon (or project SVG), styled `text-white/20` by the caller */
  icon?: ReactNode;
  message: string;
  /** Optional action (link/button) rendered below the message */
  action?: ReactNode;
  className?: string;
}

const EmptyState = ({ icon, message, action, className = '' }: EmptyStateProps) => {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-3 py-14 text-center ${className}`}
    >
      {icon}
      <p className="text-sm text-white/40">{message}</p>
      {action}
    </div>
  );
};

export default EmptyState;
