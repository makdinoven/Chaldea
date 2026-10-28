import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type FocusEvent,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { Info } from 'lucide-react';

/*
  A small contextual tooltip in the design system's `site-tooltip` look.
  Portaled to <body> with fixed positioning, so panels with overflow-hidden
  don't clip it. Opens on mouse hover and keyboard focus; on touch it opens by
  tap (the «i» button, or a wrapper around a disabled control). Closes on
  Escape, on a tap outside and when the mouse leaves.
*/

/** Gap between the trigger and the tooltip, and the minimum margin to the viewport edge (px). */
const GAP = 8;
const EDGE = 8;

interface Position {
  top: number;
  left: number;
}

const isEmpty = (content: ReactNode) => content == null || content === false || content === '';

/** Open state, positioning and the portaled bubble of one tooltip. */
const useTooltip = (content: ReactNode) => {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<Position | null>(null);
  const anchorRef = useRef<HTMLElement | null>(null);
  const tipRef = useRef<HTMLDivElement | null>(null);
  const lastPointer = useRef<string>('mouse');
  const id = useId();

  const place = useCallback(() => {
    const anchor = anchorRef.current;
    const tip = tipRef.current;
    if (!anchor || !tip) return;
    const r = anchor.getBoundingClientRect();
    const w = tip.offsetWidth;
    const h = tip.offsetHeight;
    const vw = document.documentElement.clientWidth;
    const above = r.top - GAP - h;
    const top = above >= EDGE ? above : r.bottom + GAP;
    const left = Math.min(Math.max(r.left + r.width / 2 - w / 2, EDGE), Math.max(EDGE, vw - w - EDGE));
    setPos({ top, left });
  }, []);

  useLayoutEffect(() => {
    if (open) place();
    else setPos(null);
  }, [open, place, content]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    const onDown = (e: globalThis.PointerEvent) => {
      if (anchorRef.current?.contains(e.target as Node)) return;
      setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onDown);
    window.addEventListener('scroll', place, true);
    window.addEventListener('resize', place);
    return () => {
      window.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onDown);
      window.removeEventListener('scroll', place, true);
      window.removeEventListener('resize', place);
    };
  }, [open, place]);

  const bubble = open && !isEmpty(content)
    ? createPortal(
      <div ref={tipRef} id={id} role="tooltip"
        className="site-tooltip gold-outline !fixed z-[1100] w-max max-w-[min(300px,calc(100vw-16px))] !normal-case !font-normal text-white/85 text-xs leading-relaxed text-left whitespace-normal shadow-dropdown pointer-events-none animate-fade-in"
        style={{ top: pos?.top ?? 0, left: pos?.left ?? 0, visibility: pos ? 'visible' : 'hidden' }}>
        {content}
      </div>,
      document.body,
    )
    : null;

  /** Mouse: hover opens; touch / pen: only taps do. */
  const pointerHandlers = {
    onPointerEnter: (e: PointerEvent) => {
      lastPointer.current = e.pointerType;
      if (e.pointerType === 'mouse') setOpen(true);
    },
    onPointerLeave: (e: PointerEvent) => {
      if (e.pointerType === 'mouse') setOpen(false);
    },
    onPointerDown: (e: PointerEvent) => {
      lastPointer.current = e.pointerType;
    },
  };

  /** Keyboard focus opens (a tap also focuses, but that is handled by the click). */
  const onFocus = (e: FocusEvent) => {
    if ((e.target as Element).matches?.(':focus-visible')) setOpen(true);
  };

  /** A tap toggles; a mouse click keeps the hover-opened tooltip open. */
  const toggleByClick = () => setOpen((o) => (lastPointer.current === 'mouse' ? true : !o));

  return { open, setOpen, anchorRef, id, bubble, pointerHandlers, onFocus, toggleByClick };
};

interface WithTooltipProps {
  /** Tooltip content; nothing is shown when empty. */
  content: ReactNode;
  children: ReactNode;
  className?: string;
  /**
   * The wrapped control is disabled — a tap, a click or keyboard focus on the
   * wrapper opens the tooltip with the reason. The control itself must have
   * `pointer-events: none` (disabled buttons get no pointer events anyway).
   */
  tapToggle?: boolean;
}

/** Wraps a control (a button, a tile) with a hover / focus tooltip. */
export const WithTooltip = ({ content, children, className = '', tapToggle = false }: WithTooltipProps) => {
  const { open, setOpen, anchorRef, id, bubble, pointerHandlers, onFocus, toggleByClick } = useTooltip(content);
  const has = !isEmpty(content);
  const toggles = tapToggle && has;

  return (
    <span
      ref={(el) => {
        anchorRef.current = el;
      }}
      className={`relative ${toggles ? 'cursor-help focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold/60 rounded-card' : ''} ${className}`}
      aria-describedby={open ? id : undefined}
      tabIndex={toggles ? 0 : undefined}
      {...(has ? pointerHandlers : {})}
      onFocus={(e) => has && onFocus(e)}
      onBlur={() => setOpen(false)}
      onClick={() => toggles && toggleByClick()}
      onKeyDown={(e: KeyboardEvent) => {
        if (toggles && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          setOpen((o) => !o);
        }
      }}
    >
      {children}
      {bubble}
    </span>
  );
};

interface InfoTooltipProps {
  content: ReactNode;
  /** Accessible name of the «i» button. */
  label?: string;
  className?: string;
  size?: number;
}

/** A round «i» button that shows `content` on hover, focus or tap. */
export const InfoTooltip = ({ content, label = 'Подробнее', className = '', size = 14 }: InfoTooltipProps) => {
  const { open, setOpen, anchorRef, id, bubble, pointerHandlers, onFocus, toggleByClick } = useTooltip(content);
  if (isEmpty(content)) return null;
  return (
    <button
      type="button"
      ref={(el) => {
        anchorRef.current = el;
      }}
      aria-label={label}
      aria-expanded={open}
      aria-describedby={open ? id : undefined}
      className={`inline-flex items-center justify-center shrink-0 rounded-full p-0.5 text-white/45 hover:text-gold focus-visible:text-gold focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold/60 transition-colors duration-200 ease-site ${className}`}
      {...pointerHandlers}
      onFocus={onFocus}
      onBlur={() => setOpen(false)}
      onClick={(e) => {
        e.stopPropagation();
        toggleByClick();
      }}
    >
      <Info size={size} />
      {bubble}
    </button>
  );
};

export default InfoTooltip;
