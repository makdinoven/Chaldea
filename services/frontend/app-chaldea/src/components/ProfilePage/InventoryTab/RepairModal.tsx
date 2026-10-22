import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  selectInventory,
  selectRepairLoading,
  repairItem,
} from '../../../redux/slices/profileSlice';
import type { InventoryItem } from '../../../redux/slices/profileSlice';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';

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

  return (
    <ModalShell
      open={isOpen}
      onClose={onClose}
      title="Починить"
      size="sm"
      footer={
        <button onClick={onClose} className="btn-line w-full sm:w-auto">
          Отмена
        </button>
      }
    >
            <p className="text-white text-sm text-center mb-4">
              {inventoryItem.item.name}
            </p>

            {repairKits.length === 0 ? (
              <p className="text-white/50 text-sm text-center">
                Нет ремонт-комплектов в инвентаре
              </p>
            ) : (
              <div className="flex flex-col gap-2">
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

    </ModalShell>
  );
};

export default RepairModal;
