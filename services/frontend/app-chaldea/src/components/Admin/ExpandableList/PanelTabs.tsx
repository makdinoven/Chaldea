import { useEffect, useRef } from 'react';
import { motion } from 'motion/react';

/**
 * FEAT-208/210 — tab strip of an expanded panel (horizontal scroll on mobile, animated underline).
 * `layoutId` must be unique per list (e.g. `npc-panel-tab`). Clicking the active tab does nothing.
 * The active tab is scrolled into view inside the strip (narrow screens), without moving the page.
 */
interface PanelTabsProps<K extends string> {
  tabs: readonly K[];
  labels: Record<K, string>;
  active: K;
  onSelect: (tab: K) => void;
  layoutId: string;
}

const PanelTabs = <K extends string>({ tabs, labels, active, onSelect, layoutId }: PanelTabsProps<K>) => {
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const nav = navRef.current;
    const tab = nav?.querySelector<HTMLElement>('[aria-selected="true"]');
    if (!nav || !tab) return;
    const left = tab.offsetLeft - nav.offsetLeft;
    if (left < nav.scrollLeft || left + tab.offsetWidth > nav.scrollLeft + nav.clientWidth) {
      nav.scrollTo({ left: Math.max(0, left - (nav.clientWidth - tab.offsetWidth) / 2), behavior: 'smooth' });
    }
  }, [active]);

  return (
  <nav ref={navRef} role="tablist" className="flex gap-4 sm:gap-6 border-b border-white/10 overflow-x-auto gold-scrollbar">
    {tabs.map((tab) => (
      <button
        key={tab}
        type="button"
        role="tab"
        aria-selected={active === tab}
        onClick={() => {
          if (tab !== active) onSelect(tab);
        }}
        className={`nav-link text-sm sm:text-base pb-3 relative whitespace-nowrap shrink-0 transition-colors duration-200 ${
          active === tab ? 'text-site-blue' : ''
        }`}
      >
        {labels[tab]}
        {active === tab && (
          <motion.div
            layoutId={layoutId}
            className="absolute bottom-0 left-0 right-0 h-[2px] bg-site-blue"
            transition={{ duration: 0.2, ease: 'easeOut' }}
          />
        )}
      </button>
    ))}
  </nav>
  );
};

export default PanelTabs;
