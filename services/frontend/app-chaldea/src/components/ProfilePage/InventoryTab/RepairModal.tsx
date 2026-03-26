import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  selectInventory,
  selectRepairLoading,
  repairItem,
} from '../../../redux/slices/profileSlice';
import type { InventoryItem } from '../../../redux/slices/profileSlice';

interface RepairModalProps {
  isOpen: boolean;
  characterId: number;
  inventoryItem: InventoryItem;
  source: string;
  onClose: () => void;
}

const RepairModal = ({ isOpen, characterId, inventoryItem, source, onClose }: RepairModalProps) => {
  const dispatch = useAppDispatch();
  const inventory = useAppSelector(selectInventory);
  const repairBusy = useAppSelector(selectRepairLoading);

  const repairKits = inventory.filter(
    (inv) => inv.item.repair_power != null && inv.item.repair_power > 0,
  );

  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [isOpen, onClose]);

  const handleRepair = async (repairKitItemId: number) => {
    try {
      const result = await dispatch(
        repairItem({
          characterId,
          payload: {
            item_row_id: inventoryItem.id,
            repair_kit_item_id: repairKitItemId,
            source,
          },
        }),
      );
      if (result.meta.requestStatus === 'fulfilled') {
        toast.success('Предмет починен!');
        onClose();
      } else {
        const payload = result.payload as string | undefined;
        toast.error(payload ?? 'Не удалось починить предмет');
      }
    } catch {
      toast.error('Произошла ошибка при ремонте');
    }
  };

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <motion.div
          key="repair-modal-overlay"
          className="modal-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          onClick={onClose}
        >
          <motion.div
            className="modal-content gold-outline gold-outline-thick max-w-sm mx-4"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="gold-text text-xl font-medium uppercase mb-2 text-center">
              Починить
            </h2>
            <p className="text-white text-sm text-center mb-4">
              {inventoryItem.item.name}
            </p>

            {repairKits.length === 0 ? (
              <p className="text-white/50 text-sm text-center mb-4">
                Нет ремонт-комплектов в инвентаре
              </p>
            ) : (
              <div className="flex flex-col gap-2 mb-4">
                {repairKits.map((kit) => (
                  <button
                    key={kit.id}
                    onClick={() => handleRepair(kit.item.id)}
                    disabled={repairBusy}
                    className={`
                      flex items-center justify-between gap-3
                      px-3 py-2 rounded-card
                      bg-white/5 hover:bg-white/10
                      transition-colors duration-200
                      text-left
                      ${repairBusy ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
                    `}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      {kit.item.image && (
                        <img
                          src={kit.item.image}
                          alt={kit.item.name}
                          className="w-8 h-8 rounded-full object-cover flex-shrink-0"
                        />
                      )}
                      <div className="min-w-0">
                        <span className="text-white text-sm block truncate">
                          {kit.item.name}
                        </span>
                        <span className="text-white/50 text-xs">
                          +{kit.item.repair_power}% | x{kit.quantity}
                        </span>
                      </div>
                    </div>
                    <span className="text-site-blue text-sm font-medium flex-shrink-0">
                      Починить
                    </span>
                  </button>
                ))}
              </div>
            )}

            <button onClick={onClose} className="btn-line w-full">
              Отмена
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
};

export default RepairModal;
