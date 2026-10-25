import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

/*
  A small menu by the click: a title, a few actions, and actions that open a
  list of their own (e.g. «Передать» → who to). Closes on a click away or Esc;
  stays inside the screen.
*/

export interface MenuEntry {
  label: string;
  onSelect?: () => void;
  /** A second list instead of an action (shown in place of the menu). */
  children?: MenuEntry[];
  disabled?: boolean;
  /** Why it is disabled, or a word more. */
  hint?: string;
  danger?: boolean;
}

interface PopoverMenuProps {
  at: { x: number; y: number };
  title?: ReactNode;
  /** Lines under the title (what the item does). */
  details?: ReactNode;
  entries: MenuEntry[];
  onClose: () => void;
}

const EDGE_PX = 8;

const PopoverMenu = ({ at, title, details, entries, onClose }: PopoverMenuProps) => {
  const box = useRef<HTMLDivElement>(null);
  const [sub, setSub] = useState<MenuEntry | null>(null);
  const [pos, setPos] = useState(at);

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    setPos({
      x: Math.max(EDGE_PX, Math.min(at.x, window.innerWidth - width - EDGE_PX)),
      y: Math.max(EDGE_PX, Math.min(at.y, window.innerHeight - height - EDGE_PX)),
    });
  }, [at.x, at.y, sub]);

  useEffect(() => {
    const away = (e: PointerEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) onClose();
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    // The click that opened the menu must not close it.
    const timer = setTimeout(() => document.addEventListener('pointerdown', away), 0);
    document.addEventListener('keydown', esc);
    return () => {
      clearTimeout(timer);
      document.removeEventListener('pointerdown', away);
      document.removeEventListener('keydown', esc);
    };
  }, [onClose]);

  const list = sub?.children ?? entries;
  return createPortal(
    <div
      ref={box}
      role="menu"
      className="dropdown-menu fixed z-[1000] w-[min(260px,calc(100vw-16px))] !p-1.5 border border-white/10"
      style={{ left: pos.x, top: pos.y }}
    >
      {!sub && title && <div className="px-2.5 pt-1.5 pb-1 gold-text text-sm font-medium leading-tight">{title}</div>}
      {!sub && details && <div className="px-2.5 pb-2 text-[11px] text-white/55 leading-snug">{details}</div>}
      {sub && (
        <button
          type="button"
          onClick={() => setSub(null)}
          className="w-full text-left px-2.5 py-1.5 text-xs text-white/50 hover:text-site-blue"
        >
          ‹ {sub.label}
        </button>
      )}
      {list.map((entry) => (
        <button
          key={entry.label}
          type="button"
          role="menuitem"
          disabled={entry.disabled}
          onClick={() => {
            if (entry.children) {
              setSub(entry);
              return;
            }
            onClose();
            entry.onSelect?.();
          }}
          className={`dropdown-item w-full text-left !py-2 !px-2.5 !text-sm flex flex-col disabled:opacity-40 disabled:cursor-not-allowed ${
            entry.danger ? '!text-site-red' : ''
          }`}
        >
          <span className="flex items-center justify-between gap-2">
            {entry.label}
            {entry.children && <span className="text-white/40">›</span>}
          </span>
          {entry.hint && <span className="text-[10px] text-white/40 leading-snug">{entry.hint}</span>}
        </button>
      ))}
      {list.length === 0 && <p className="px-2.5 py-2 text-xs text-white/40">Здесь ничего не сделать</p>}
    </div>,
    document.body,
  );
};

export default PopoverMenu;
