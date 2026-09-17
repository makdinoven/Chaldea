// FEAT-166 — shared profile-tab primitive: counter for a PanelShell `headerExtra`
// (same look as InventoryPanel's item counter).
import type { ReactNode } from 'react';

interface PanelCounterProps {
  children: ReactNode;
  className?: string;
}

const PanelCounter = ({ children, className = '' }: PanelCounterProps) => (
  <span className={`text-white/50 text-xs font-medium font-mono tabular-nums ${className}`}>
    {children}
  </span>
);

export default PanelCounter;
