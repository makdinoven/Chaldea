import type { ReactNode } from 'react';

/**
 * Desktop-only fixed panel height from the FEAT-149 mock
 * (viewport minus the site header / tabs area, ~130px).
 * Below `lg` panels are auto-height without internal scrolls.
 */
export const PANEL_DESKTOP_HEIGHT_CLASS = 'lg:h-[calc(100vh-130px)]';

interface PanelShellProps {
  /** Gold uppercase header title; the header row is omitted when not provided */
  title?: string;
  /** Icon rendered to the left of the title (existing project SVG or lucide icon) */
  icon?: ReactNode;
  /** Right-aligned extra content in the header row (e.g., a counter) */
  headerExtra?: ReactNode;
  /** Extra classes for the outer <section> (widths, heights, ordering) */
  className?: string;
  /**
   * Overrides the default body classes.
   * Default: `flex-1 min-h-0 p-4 lg:p-5 lg:overflow-y-auto gold-scrollbar-wide`
   * (single scrollable content area on desktop, auto height below `lg`).
   * Pass e.g. `flex-1 min-h-0 flex flex-col p-4` to manage inner scrolls yourself.
   */
  bodyClassName?: string;
  children: ReactNode;
}

/**
 * PanelShell — shared wrapper for the three /profile panels (FEAT-149).
 * Dark translucent background + blur + gold border + shadow,
 * built exclusively from existing design-system tokens.
 */
const PanelShell = ({
  title,
  icon,
  headerExtra,
  className = '',
  bodyClassName,
  children,
}: PanelShellProps) => {
  return (
    <section
      className={`gold-outline relative rounded-card bg-site-bg backdrop-blur-[10px] shadow-card flex flex-col min-w-0 w-full ${className}`}
    >
      {title && (
        <div className="gradient-divider-h relative flex items-center gap-2.5 px-5 py-4 bg-black/20 rounded-t-card shrink-0">
          {icon}
          <h3 className="gold-text text-sm font-medium uppercase tracking-[0.12em]">
            {title}
          </h3>
          {headerExtra && (
            <div className="ml-auto flex items-center">{headerExtra}</div>
          )}
        </div>
      )}
      <div
        className={
          bodyClassName ?? 'flex-1 min-h-0 p-4 lg:p-5 lg:overflow-y-auto gold-scrollbar-wide'
        }
      >
        {children}
      </div>
    </section>
  );
};

export default PanelShell;
