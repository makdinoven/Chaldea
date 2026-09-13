import { motion } from 'motion/react';

export interface ConfirmDialogProps {
  /** Modal heading. */
  title: string;
  /** Body text explaining the consequence of confirming. */
  message: string;
  /** Label of the confirming button. Defaults to «Подтвердить». */
  confirmLabel?: string;
  /** Label of the dismissing button. Defaults to «Отмена». */
  cancelLabel?: string;
  /** Renders the confirm button in the destructive (red) style. */
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Small reusable confirmation modal built on the design-system
 * `modal-overlay` / `modal-content` / `gold-outline` classes.
 * Generic on purpose — it is reused for «Отмена», draft overwrite and
 * draft deletion.
 */
const ConfirmDialog = ({
  title,
  message,
  confirmLabel = 'Подтвердить',
  cancelLabel = 'Отмена',
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) => {
  return (
    <div
      className="modal-overlay p-4"
      role="presentation"
      onClick={onCancel}
    >
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="modal-content gold-outline gold-outline-thick !w-[min(92vw,480px)] !max-w-[min(92vw,480px)] !p-5 sm:!p-7"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="gold-text text-lg sm:text-xl uppercase mb-3 break-words">{title}</h2>
        <p className="text-white/80 text-sm mb-6 break-words">{message}</p>
        <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2.5 sm:gap-3">
          <button type="button" className="btn-line !text-xs !py-2 !px-5" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            type="button"
            autoFocus
            className={
              danger
                ? 'px-5 py-2 rounded-[10px] border border-site-red/60 text-site-red text-xs font-medium hover:bg-site-red/10 transition-colors duration-200 ease-site'
                : 'btn-blue !py-2 !px-5 !text-xs'
            }
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </motion.div>
    </div>
  );
};

export default ConfirmDialog;
