import ModalShell from '../../CommonComponents/ModalShell/ModalShell';

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
 * Small reusable confirmation modal on the site's ModalShell.
 * Generic on purpose — it is reused for «Отмена», draft overwrite and
 * draft deletion. Callers mount it conditionally, so it is always open.
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
    <ModalShell
      open
      onClose={onCancel}
      title={title}
      size="sm"
      footer={
        <>
          <button type="button" className="btn-line w-full sm:w-auto !text-xs !py-2 !px-5" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            type="button"
            autoFocus
            className={
              danger
                ? 'w-full sm:w-auto px-5 py-2 rounded-[10px] border border-site-red/60 text-site-red text-xs font-medium hover:bg-site-red/10 transition-colors duration-200 ease-site'
                : 'btn-blue w-full sm:w-auto !py-2 !px-5 !text-xs'
            }
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </>
      }
    >
      <p className="text-white/80 text-sm break-words">{message}</p>
    </ModalShell>
  );
};

export default ConfirmDialog;
