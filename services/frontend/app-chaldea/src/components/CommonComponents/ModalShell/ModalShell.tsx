// The site's one modal (FEAT-166, born in the profile): a portaled dialog in a
// gold frame, with a header band, a body that scrolls on its own gold
// scrollbar, and an optional pinned footer. Every modal on the site is built on
// it, so they all look and behave alike.
//
// Always rendered into document.body: a parent with `backdrop-blur` or a
// motion transform creates a containing block that breaks `position: fixed`
// for in-place overlays. The frame sits on the dialog and only the body
// scrolls — a frame on a scrolling box scrolls away with its content.
import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'motion/react';
import { X } from 'lucide-react';
import { hasPaddingClass } from '../../ProfilePage/shared/classUtils';

export type ModalShellSize = 'sm' | 'md' | 'lg' | 'xl';

interface ModalShellProps {
  open: boolean;
  onClose: () => void;
  /** Gold uppercase header title; without it the close button floats top-right */
  title?: string;
  /** 18px icon left of the title (lucide `text-gold` or project SVG) */
  icon?: ReactNode;
  /** Controls before the icon and title, e.g. a «back» button */
  headerStart?: ReactNode;
  size?: ModalShellSize;
  /** Close on overlay click (default true) */
  closeOnBackdrop?: boolean;
  /**
   * Close on Escape (default true). Off for editors where a stray key press
   * would throw away unsaved work; the X still closes.
   */
  closeOnEscape?: boolean;
  /**
   * Default true. `false` hides the X and ignores backdrop clicks and Escape
   * (e.g. while a request is in flight).
   */
  dismissible?: boolean;
  /** Pinned action row under the body (callers use `w-full sm:w-auto` buttons) */
  footer?: ReactNode;
  /** Extra classes for the scrollable body; any padding class here replaces the default `p-4 sm:p-6` */
  bodyClassName?: string;
  children: ReactNode;
}

const SIZE_CLASSES: Record<ModalShellSize, string> = {
  sm: 'max-w-md',
  md: 'max-w-xl',
  lg: 'max-w-3xl',
  xl: 'max-w-5xl',
};

/**
 * Open modals, oldest first. Modals open on top of one another (a confirm over
 * the dialog that asked for it); Escape belongs to the topmost alone, or one
 * press would close the whole stack.
 */
const openStack: symbol[] = [];

const CLOSE_BUTTON_CLASSES =
  'flex items-center justify-center w-8 h-8 shrink-0 text-white/40 hover:text-white transition-colors duration-200 ease-site';

const ModalShell = ({
  open,
  onClose,
  title,
  icon,
  headerStart,
  size = 'md',
  closeOnBackdrop = true,
  closeOnEscape = true,
  dismissible = true,
  footer,
  bodyClassName = '',
  children,
}: ModalShellProps) => {
  const stackId = useRef(Symbol('modal'));
  useEffect(() => {
    if (!open) return undefined;
    const id = stackId.current;
    openStack.push(id);
    return () => {
      const at = openStack.lastIndexOf(id);
      if (at >= 0) openStack.splice(at, 1);
    };
  }, [open]);

  useEffect(() => {
    if (!open || !dismissible || !closeOnEscape) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || openStack[openStack.length - 1] !== stackId.current) return;
      onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, dismissible, closeOnEscape, onClose]);

  if (typeof document === 'undefined') return null;

  const handleBackdropClick = () => {
    if (dismissible && closeOnBackdrop) onClose();
  };

  const closeButton = dismissible ? (
    <button
      type="button"
      onClick={onClose}
      aria-label="Закрыть"
      className={`${CLOSE_BUTTON_CLASSES} ${title ? 'ml-auto -mr-1.5' : 'absolute top-3 right-3 z-10'}`}
    >
      <X size={18} strokeWidth={1.8} />
    </button>
  ) : null;

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="modal-shell-overlay"
          className="modal-overlay px-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          onClick={handleBackdropClick}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={title}
            className={`modal-content gold-outline gold-outline-thick !p-0 !overflow-visible !animate-none relative w-full ${SIZE_CLASSES[size]} flex flex-col max-h-[90dvh]`}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            onClick={(event) => event.stopPropagation()}
          >
            {title ? (
              <div className="gradient-divider-h relative flex items-center gap-2.5 px-5 py-4 bg-black/20 rounded-t-[15px] shrink-0 min-w-0">
                {headerStart}
                {icon}
                <h3 className="gold-text text-sm font-medium uppercase tracking-[0.12em] min-w-0 break-words">
                  {title}
                </h3>
                {closeButton}
              </div>
            ) : (
              closeButton
            )}
            <div
              className={`flex-1 min-h-0 overflow-y-auto gold-scrollbar ${
                hasPaddingClass(bodyClassName) ? '' : 'p-4 sm:p-6'
              } ${bodyClassName}`}
            >
              {children}
            </div>
            {footer && (
              <div className="shrink-0 px-4 sm:px-6 py-4 border-t border-white/10 flex flex-wrap justify-end gap-3">
                {footer}
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
};

export default ModalShell;
