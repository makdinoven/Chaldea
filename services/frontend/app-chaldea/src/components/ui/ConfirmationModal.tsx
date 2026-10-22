import ModalShell from '../CommonComponents/ModalShell/ModalShell';

interface ConfirmationModalProps {
  isOpen: boolean;
  title?: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/** A yes/no question in the site's modal. Escape and the backdrop cancel. */
const ConfirmationModal = ({
  isOpen,
  title = 'Вы уверены?',
  message,
  onConfirm,
  onCancel,
}: ConfirmationModalProps) => (
  <ModalShell
    open={isOpen}
    onClose={onCancel}
    title={title}
    size="sm"
    footer={
      <>
        <button className="btn-line w-full sm:w-auto sm:max-w-[160px]" onClick={onCancel}>
          Отмена
        </button>
        <button className="btn-blue w-full sm:w-auto" onClick={onConfirm}>
          Подтвердить
        </button>
      </>
    }
  >
    <p className="text-white text-base text-center break-words">{message}</p>
  </ModalShell>
);

export default ConfirmationModal;
