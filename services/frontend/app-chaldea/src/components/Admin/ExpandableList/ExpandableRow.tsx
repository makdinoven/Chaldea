import type { ReactNode, Ref } from 'react';
import { AnimatePresence } from 'motion/react';
import { readyTooltip, type ReadyMark } from './readyMark';

/**
 * FEAT-208/210 — compact clickable plate of an expandable admin list; the panel
 * (`ExpandedPanelShell`) is passed as `children` and rendered under it while `open`.
 *
 * Layout: mobile = column (first cell, then `cells`), `sm+` = CSS grid from `gridClassName`
 * (e.g. `sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto]` — the LAST column must be `auto`,
 * it holds the desktop chevron). The first cell = `avatar` + `title` (+ ✓ when ready) + `subtitle`.
 * `cells` are the remaining grid cells (a fragment); indent their mobile variants with
 * `pl-[52px] sm:pl-0` to align under the title. A ready plate gets a translucent gold background.
 * Use the same `rowRef` as the panel's `scrollTargetRef` for the open row.
 */
interface ExpandableRowProps {
  open: boolean;
  onToggle: () => void;
  avatar: ReactNode;
  title: string;
  /** Small grey line under the title, e.g. `#12 · 5 ур.` */
  subtitle?: ReactNode;
  ready?: ReadyMark | null;
  cells?: ReactNode;
  /** `sm:grid-cols-[...]` of the button grid (full class literal so Tailwind sees it) */
  gridClassName: string;
  /** Small caption over the plate, e.g. «Открыт по ссылке» */
  badge?: string;
  rowRef?: Ref<HTMLDivElement>;
  /** The expanded panel (rendered only while open) */
  children?: ReactNode;
}

const plateBg = (open: boolean, ready: boolean): string => {
  if (ready) return open ? 'bg-gold/[0.09] gold-outline relative' : 'bg-gold/[0.06]';
  return open ? 'bg-white/[0.04] gold-outline relative' : '';
};

const Chevron = ({ open, className }: { open: boolean; className: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className={`w-5 h-5 shrink-0 text-white/50 transition-transform duration-200 ${className} ${open ? 'rotate-180' : ''}`}
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
    strokeWidth={2}
  >
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
  </svg>
);

const ExpandableRow = ({
  open,
  onToggle,
  avatar,
  title,
  subtitle,
  ready,
  cells,
  gridClassName,
  badge,
  rowRef,
  children,
}: ExpandableRowProps) => (
  <div
    ref={rowRef}
    className={`scroll-mt-4 rounded-card transition-colors duration-200 ${plateBg(open, !!ready?.ready)}`}
  >
    {badge && (
      <div className="px-3 sm:px-4 pt-2 text-[11px] font-medium uppercase tracking-[0.06em] text-gold/70">
        {badge}
      </div>
    )}
    <button
      type="button"
      aria-expanded={open}
      onClick={onToggle}
      className={`w-full text-left flex flex-col sm:grid ${gridClassName} sm:items-center gap-2 sm:gap-4 px-3 sm:px-4 py-3 rounded-card transition-colors duration-200 ${
        open ? '' : 'hover:bg-white/[0.05]'
      }`}
    >
      {/* Avatar + title */}
      <div className="flex items-center gap-3 min-w-0">
        {avatar}
        <div className="flex flex-col min-w-0">
          <span className="flex items-center gap-1.5 min-w-0">
            <span className={`text-sm sm:text-base font-medium truncate ${open ? 'gold-text' : 'text-white'}`}>
              {title}
            </span>
            {ready?.ready && (
              <span
                className="text-gold text-sm leading-none shrink-0"
                aria-label="Готов"
                title={readyTooltip(ready.by, ready.at) ?? 'Готов'}
              >
                ✓
              </span>
            )}
          </span>
          {subtitle && <span className="text-white/40 text-xs">{subtitle}</span>}
        </div>
        <Chevron open={open} className="sm:hidden ml-auto" />
      </div>

      {cells}

      {/* Desktop chevron — always the last grid column */}
      <Chevron open={open} className="hidden sm:block sm:[grid-column-end:-1]" />
    </button>

    <AnimatePresence initial>{open && children}</AnimatePresence>
  </div>
);

export default ExpandableRow;
