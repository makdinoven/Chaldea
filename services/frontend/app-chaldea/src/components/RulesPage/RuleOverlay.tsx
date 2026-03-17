import { motion, AnimatePresence } from 'motion/react';
import DOMPurify from 'dompurify';
import { X } from 'react-feather';
import { GameRule } from '../../api/rules';

interface RuleOverlayProps {
  rule: GameRule | null;
  onClose: () => void;
}

const RuleOverlay = ({ rule, onClose }: RuleOverlayProps) => {
  return (
    <AnimatePresence>
      {rule && (
        <motion.div
          className="modal-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          onClick={onClose}
        >
          <motion.div
            className="modal-content gold-outline gold-outline-thick relative max-h-[80vh] flex flex-col"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Close button */}
            <button
              onClick={onClose}
              className="absolute top-4 right-4 text-white hover:text-site-blue transition-colors duration-200 z-10"
            >
              <X size={24} />
            </button>

            {/* Title */}
            <h2 className="gold-text text-2xl font-medium uppercase mb-6 pr-8">
              {rule.title}
            </h2>

            {/* Scrollable content */}
            <div
              className="gold-scrollbar overflow-y-auto flex-1 text-white text-base leading-relaxed prose-rules"
              dangerouslySetInnerHTML={{
                __html: DOMPurify.sanitize(rule.content || ''),
              }}
            />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default RuleOverlay;
