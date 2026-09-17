// FEAT-166 — shared profile-tab primitive: the list area under a PanelToolbar.
// Scrolls internally on `lg+` only (page scroll below `lg`). Use with
// `<PanelShell className={PANEL_DESKTOP_HEIGHT_CLASS} bodyClassName="flex-1 min-h-0 flex flex-col">`.
import type { ReactNode } from 'react';

interface PanelScrollAreaProps {
  children: ReactNode;
  className?: string;
}

const PanelScrollArea = ({ children, className = '' }: PanelScrollAreaProps) => (
  <div
    className={`flex-1 min-h-0 px-4 lg:px-5 pt-2 pb-4 lg:overflow-y-auto gold-scrollbar-wide ${className}`}
  >
    {children}
  </div>
);

export default PanelScrollArea;
