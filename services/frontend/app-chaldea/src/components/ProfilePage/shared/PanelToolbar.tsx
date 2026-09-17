// FEAT-166 — shared profile-tab primitive: fixed filters/search strip under a
// PanelShell header. Pair with PanelScrollArea.
import type { ReactNode } from 'react';

interface PanelToolbarProps {
  children: ReactNode;
  className?: string;
}

const PanelToolbar = ({ children, className = '' }: PanelToolbarProps) => (
  <div
    className={`shrink-0 min-w-0 px-4 lg:px-5 pt-3.5 pb-2 flex flex-wrap items-center gap-3 ${className}`}
  >
    {children}
  </div>
);

export default PanelToolbar;
