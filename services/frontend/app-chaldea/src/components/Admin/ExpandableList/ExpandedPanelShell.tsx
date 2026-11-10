import type { ReactNode, RefObject } from 'react';
import { motion } from 'motion/react';

/**
 * FEAT-208/210 — animated panel under a plate: header (gold title left, `actions` right — wraps
 * on mobile), `tabs` (usually `PanelTabs`), then `children` in a box keyed by `bodyKey`
 * (change it — e.g. `${id}-${tab}` — to remount the section). Once the open animation finishes
 * the page scrolls to `scrollTargetRef` (the plate). Render it as the `children` of an open
 * `ExpandableRow` (it animates in/out through the row's `AnimatePresence`).
 */
interface ExpandedPanelShellProps {
  title: string;
  /** Header buttons (ReadyToggle, «Удалить», …); omitted → no actions block */
  actions?: ReactNode;
  tabs?: ReactNode;
  bodyKey: string;
  scrollTargetRef: RefObject<HTMLElement>;
  children: ReactNode;
}

const PANEL_VARIANTS = {
  collapsed: { opacity: 0, height: 0 },
  open: { opacity: 1, height: 'auto' },
};

const ExpandedPanelShell = ({ title, actions, tabs, bodyKey, scrollTargetRef, children }: ExpandedPanelShellProps) => (
  <motion.div
    variants={PANEL_VARIANTS}
    initial="collapsed"
    animate="open"
    exit="collapsed"
    transition={{ duration: 0.25, ease: 'easeOut' }}
    onAnimationComplete={(definition) => {
      if (definition === 'open') {
        scrollTargetRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }}
    className="overflow-hidden"
  >
    <div className="flex flex-col gap-4 px-3 pb-3 pt-1 sm:px-5 sm:pb-5 min-w-0">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 border-t border-white/10 pt-3">
        <h2 className="gold-text text-lg sm:text-xl font-medium uppercase tracking-[0.06em] break-words min-w-0">
          {title}
        </h2>
        {actions && <div className="flex flex-wrap items-center gap-4 sm:ml-auto">{actions}</div>}
      </div>

      {tabs}

      <div key={bodyKey} className="min-w-0">
        {children}
      </div>
    </div>
  </motion.div>
);

export default ExpandedPanelShell;
