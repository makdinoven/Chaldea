import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';

/*
  Full-screen 3D pages (the dungeon table, the books of the skill tree, the
  battle arena): the scene takes the whole screen and only the site header
  stays over it. The header can be tucked away with a tab at the top of the
  screen and brought back the same way; the choice is remembered in this
  browser. Pages that are not full-screen always show the header.
*/

const HIDDEN_KEY = 'chaldea.fullscreenHeaderHidden';

const readHidden = () => {
  try {
    return localStorage.getItem(HIDDEN_KEY) === '1';
  } catch {
    return false;
  }
};

let headerHidden = readHidden();
let fullscreenPages = 0;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

const setHeaderHidden = (hidden: boolean) => {
  headerHidden = hidden;
  try {
    localStorage.setItem(HIDDEN_KEY, hidden ? '1' : '0');
  } catch {
    // private mode / storage blocked: the choice lasts until the page reloads
  }
  emit();
};

/** Whether the site header is tucked away now (only ever on a full-screen page). */
export const useHeaderHidden = () =>
  useSyncExternalStore(subscribe, () => fullscreenPages > 0 && headerHidden);

/** Bottom edge of the site header on screen (desktop and mobile headers are different elements). */
const useHeaderBottom = (hidden: boolean) => {
  const [bottom, setBottom] = useState(0);
  useEffect(() => {
    if (hidden) {
      setBottom(0);
      return;
    }
    const visibleHeader = () =>
      Array.from(document.querySelectorAll('header')).find((h) => h.offsetHeight > 0) ?? null;
    const measure = () => setBottom(Math.max(0, Math.round(visibleHeader()?.getBoundingClientRect().bottom ?? 0)));
    measure();
    // The header comes back on the next frame after being shown.
    const frame = requestAnimationFrame(measure);
    window.addEventListener('resize', measure);
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
    document.querySelectorAll('header').forEach((h) => observer?.observe(h));
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', measure);
      observer?.disconnect();
    };
  }, [hidden]);
  return bottom;
};

/**
 * Makes the page full-screen while `active`: no page scroll, the header may be
 * tucked away. `top` is where the page's own overlays start (under the header, or 0).
 */
export const useFullscreenPage = (active = true) => {
  useEffect(() => {
    if (!active) return;
    fullscreenPages += 1;
    emit();
    window.scrollTo(0, 0);
    const root = document.documentElement;
    const previous = root.style.overflow;
    root.style.overflow = 'hidden';
    return () => {
      fullscreenPages -= 1;
      root.style.overflow = previous;
      emit();
    };
  }, [active]);
  const hidden = useHeaderHidden();
  const top = useHeaderBottom(hidden || !active);
  const toggleHeader = useCallback(() => setHeaderHidden(!headerHidden), []);
  return { top, headerHidden: hidden, toggleHeader };
};

/** The tab at the top of a full-screen page that tucks the header away and brings it back. */
export const HeaderToggle = ({ top, hidden, onToggle }: { top: number; hidden: boolean; onToggle: () => void }) => (
  <button
    type="button"
    onClick={onToggle}
    style={{ top }}
    className="fixed left-1/2 -translate-x-1/2 z-[60] w-14 h-7 flex items-center justify-center rounded-b-card bg-black/80 backdrop-blur-sm border border-t-0 border-gold/40 text-gold/80 hover:text-gold hover:border-gold/70 shadow-card transition-colors duration-200 ease-site"
    aria-label={hidden ? 'Показать шапку' : 'Скрыть шапку'}
    title={hidden ? 'Показать шапку' : 'Скрыть шапку'}
  >
    <svg viewBox="0 0 12 8" className={`w-4 h-2.5 transition-transform duration-200 ${hidden ? 'rotate-180' : ''}`} aria-hidden>
      <path d="M1 7l5-5 5 5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  </button>
);
