import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'motion/react';

interface ConfirmationModalProps {
  isOpen: boolean;
  title?: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}

const ConfirmationModal = ({
  isOpen,
  title = 'Вы уверены?',
  message,
  onConfirm,
  onCancel,
}: ConfirmationModalProps) => {
  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCancel();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onCancel]);

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <motion.div
          key="confirmation-modal-overlay"
          className="modal-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          onClick={onCancel}
        >
          <motion.div
            className="modal-content gold-outline gold-outline-thick max-w-md"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="gold-text text-2xl font-medium uppercase mb-4 text-center">
              {title}
            </h2>
            <p className="text-white text-base mb-6 text-center">
              {message}
            </p>
            <div className="flex gap-4 justify-center">
              <button className="btn-blue" onClick={onConfirm}>
                Подтвердить
              </button>
              <button className="btn-line max-w-[160px]" onClick={onCancel}>
                Отмена
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
};

export default ConfirmationModal;
