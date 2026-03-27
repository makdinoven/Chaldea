import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  depositToStorage,
  fetchStorage,
  claimFromStorage,
  selectStorageItems,
  selectStorageTotalGold,
  selectStorageLoading,
  selectStorageError,
  selectActionLoading,
} from '../../../redux/slices/auctionSlice';
import { RARITY_COLOR_MAP } from '../../Auction/AuctionListingCard';
import type { AuctionStorageItemResponse } from '../../../types/auction';

/* -- Types -- */

interface InventoryItemData {
  id: number;
  character_id: number;
  item_id: number;
  quantity: number;
  is_identified: boolean;
  enhancement_points_spent?: number;
  socketed_gems: string | null;
  current_durability: number | null;
  item: {
    id: number;
    name: string;
    image: string | null;
    item_type: string;
    item_rarity: string;
    item_level: number;
    max_stack_size: number;
    price: number;
  };
}

interface NpcAuctionModalProps {
  npcId: number;
  npcName: string;
  npcAvatar: string | null;
  onClose: () => void;
}

type AuctionNpcTab = 'deposit' | 'withdraw';

/* -- Helpers -- */

const SOURCE_LABELS: Record<string, string> = {
  purchase: 'Покупка',
  expired: 'Истекший лот',
  cancelled: 'Отмена',
  sale_proceeds: 'Выручка',
  deposit: 'Размещено',
};

/* -- Storage Row (withdraw tab) -- */

const StorageRow = ({
  item,
  selected,
  onToggle,
}: {
  item: AuctionStorageItemResponse;
  selected: boolean;
  onToggle: (id: number) => void;
}) => {
  const rarityColor = item.item
    ? (RARITY_COLOR_MAP[item.item.item_rarity] ?? 'text-white')
    : 'text-gold';
  const isGold = item.gold_amount > 0 && !item.item;

  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: 10 },
        visible: { opacity: 1, y: 0 },
      }}
      className={
        'flex items-center gap-3 p-3 rounded-card transition-colors duration-200 ease-site cursor-pointer ' +
        (selected ? 'bg-white/10 ring-1 ring-gold/30' : 'bg-white/5 hover:bg-white/[0.07]')
      }
      onClick={() => onToggle(item.id)}
    >
      {/* Checkbox */}
      <div
        className={
          'w-5 h-5 rounded-md border-2 flex-shrink-0 flex items-center justify-center transition-colors ' +
          (selected ? 'border-gold bg-gold/20' : 'border-white/20')
        }
      >
        {selected && <span className="text-gold text-xs font-bold">&check;</span>}
      </div>

      {/* Image / Icon */}
      <div className="w-10 h-10 rounded-full bg-white/5 flex-shrink-0 flex items-center justify-center overflow-hidden">
        {isGold ? (
          <span className="gold-text text-lg font-medium">$</span>
        ) : item.item?.image ? (
          <img src={item.item.image} alt={item.item.name} className="w-full h-full object-cover" />
        ) : (
          <span className="text-white/30 text-lg">?</span>
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className={`${rarityColor} text-sm font-medium truncate`}>
          {isGold
            ? `${item.gold_amount.toLocaleString('ru-RU')} золота`
            : item.item?.name ?? 'Неизвестный предмет'}
        </p>
        <p className="text-white/40 text-xs">
          {SOURCE_LABELS[item.source] ?? item.source}
          {!isGold && item.quantity > 1 && ` x${item.quantity}`}
        </p>
      </div>
    </motion.div>
  );
};

/* -- Main Component -- */

const NpcAuctionModal = ({ npcId, npcName, npcAvatar, onClose }: NpcAuctionModalProps) => {
  const dispatch = useAppDispatch();
  const characterId = useAppSelector((state) => state.user.character?.id) as number | null;

  const storageItems = useAppSelector(selectStorageItems);
  const storageTotalGold = useAppSelector(selectStorageTotalGold);
  const storageLoading = useAppSelector(selectStorageLoading);
  const storageError = useAppSelector(selectStorageError);
  const actionLoading = useAppSelector(selectActionLoading);

  const [tab, setTab] = useState<AuctionNpcTab>('deposit');

  // Deposit-tab state
  const [inventoryItems, setInventoryItems] = useState<InventoryItemData[]>([]);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);
  const [quantity, setQuantity] = useState(1);

  // Withdraw-tab state
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  // Fetch inventory for deposit tab
  const fetchInventory = useCallback(async () => {
    if (!characterId) return;
    setInventoryLoading(true);
    try {
      const { data } = await axios.get<InventoryItemData[]>(`/inventory/${characterId}/items`);
      setInventoryItems(data);
    } catch {
      toast.error('Не удалось загрузить инвентарь');
    } finally {
      setInventoryLoading(false);
    }
  }, [characterId]);

  useEffect(() => {
    fetchInventory();
  }, [fetchInventory]);

  // Fetch storage when switching to withdraw tab
  useEffect(() => {
    if (tab === 'withdraw' && characterId) {
      dispatch(fetchStorage(characterId));
    }
  }, [dispatch, tab, characterId]);

  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose();
  };

  /* -- Deposit logic -- */

  const selectedItem = inventoryItems.find((i) => i.id === selectedItemId);
  const maxQuantity = selectedItem ? Math.min(selectedItem.quantity, selectedItem.item.max_stack_size) : 1;

  const handleDeposit = async () => {
    if (!characterId || !selectedItemId) {
      toast.error('Выберите предмет для размещения на складе');
      return;
    }

    try {
      const result = await dispatch(
        depositToStorage({
          character_id: characterId,
          inventory_item_id: selectedItemId,
          quantity,
        }),
      ).unwrap();
      toast.success(result.message || 'Предмет помещён на склад аукциона');
      // Reset form
      setSelectedItemId(null);
      setQuantity(1);
      // Refresh inventory and storage
      fetchInventory();
      if (characterId) dispatch(fetchStorage(characterId));
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось поместить предмет на склад');
    }
  };

  /* -- Withdraw (claim) logic -- */

  const toggleItem = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    if (selectedIds.size === storageItems.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(storageItems.map((i) => i.id)));
    }
  };

  const handleClaim = async (ids: number[]) => {
    if (ids.length === 0 || !characterId) return;
    try {
      const result = await dispatch(
        claimFromStorage({ character_id: characterId, storage_ids: ids }),
      ).unwrap();
      toast.success(result.message || 'Предметы забраны');
      setSelectedIds(new Set());
      dispatch(fetchStorage(characterId));
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось забрать предметы');
    }
  };

  const handleClaimSelected = () => handleClaim(Array.from(selectedIds));
  const handleClaimAll = () => handleClaim(storageItems.map((i) => i.id));

  return (
    <div className="modal-overlay !bg-black/80" onClick={handleOverlayClick}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="modal-content gold-outline gold-outline-thick relative max-w-2xl w-full mx-3 sm:mx-4 max-h-[90vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 sm:top-4 sm:right-4 text-white/50 hover:text-white transition-colors z-10"
          aria-label="Закрыть"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {/* Header: NPC info */}
        <div className="flex items-center gap-3 mb-4 pr-8">
          <div className="gold-outline relative w-12 h-12 sm:w-14 sm:h-14 rounded-full overflow-hidden bg-black/40 shrink-0">
            {npcAvatar ? (
              <img src={npcAvatar} alt={npcName} className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-white/20">
                <svg xmlns="http://www.w3.org/2000/svg" className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </div>
            )}
          </div>
          <div className="flex flex-col min-w-0">
            <h2 className="gold-text text-lg sm:text-xl font-medium uppercase tracking-wide truncate">
              {npcName}
            </h2>
            <span className="text-white/50 text-xs uppercase tracking-wide">Склад аукциона</span>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-white/10 mb-4">
          <button
            onClick={() => setTab('deposit')}
            className={`
              flex-1 pb-2 text-sm sm:text-base font-medium uppercase tracking-wide
              transition-colors duration-200 border-b-2
              ${tab === 'deposit'
                ? 'text-gold border-gold'
                : 'text-white/50 border-transparent hover:text-white/80'
              }
            `}
          >
            Положить на склад
          </button>
          <button
            onClick={() => setTab('withdraw')}
            className={`
              flex-1 pb-2 text-sm sm:text-base font-medium uppercase tracking-wide
              transition-colors duration-200 border-b-2
              ${tab === 'withdraw'
                ? 'text-gold border-gold'
                : 'text-white/50 border-transparent hover:text-white/80'
              }
            `}
          >
            Забрать со склада
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto gold-scrollbar pr-1 min-h-0">
          <AnimatePresence mode="wait">
            {tab === 'deposit' ? (
              <motion.div
                key="deposit"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.2 }}
              >
                {/* Info */}
                <div className="mb-4 p-3 rounded-card bg-white/5 border border-white/10">
                  <p className="text-white/50 text-sm text-center">
                    Поместите предмет на склад, чтобы затем выставить его на аукцион через страницу аукциона
                  </p>
                </div>

                {/* Inventory items */}
                <div className="mb-5">
                  <label className="text-white/60 text-sm block mb-2">Выберите предмет</label>
                  {inventoryLoading ? (
                    <div className="flex items-center justify-center py-6">
                      <div className="w-6 h-6 border-2 border-gold border-t-transparent rounded-full animate-spin" />
                    </div>
                  ) : inventoryItems.length === 0 ? (
                    <p className="text-white/30 text-sm">Инвентарь пуст</p>
                  ) : (
                    <div className="max-h-[250px] overflow-y-auto gold-scrollbar space-y-1">
                      {inventoryItems.map((inv) => {
                        const rarityColor = RARITY_COLOR_MAP[inv.item.item_rarity] ?? 'text-white';
                        const isSelected = inv.id === selectedItemId;
                        return (
                          <div
                            key={inv.id}
                            onClick={() => {
                              setSelectedItemId(inv.id);
                              setQuantity(1);
                            }}
                            className={
                              'flex items-center gap-3 p-2 rounded-card cursor-pointer transition-colors duration-200 ease-site ' +
                              (isSelected ? 'bg-white/10 ring-1 ring-gold/30' : 'bg-white/5 hover:bg-white/[0.07]')
                            }
                          >
                            <div className="w-8 h-8 rounded-full bg-white/5 flex-shrink-0 flex items-center justify-center overflow-hidden">
                              {inv.item.image ? (
                                <img src={inv.item.image} alt={inv.item.name} className="w-full h-full object-cover" />
                              ) : (
                                <span className="text-white/30 text-sm">?</span>
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className={`${rarityColor} text-sm truncate`}>{inv.item.name}</p>
                              <p className="text-white/40 text-xs">Ур. {inv.item.item_level} &middot; x{inv.quantity}</p>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Quantity (if stackable) */}
                {selectedItem && maxQuantity > 1 && (
                  <div className="mb-4">
                    <label className="text-white/60 text-sm block mb-1">
                      Количество (макс. {maxQuantity})
                    </label>
                    <input
                      type="number"
                      value={quantity}
                      onChange={(e) => {
                        const val = parseInt(e.target.value, 10);
                        setQuantity(isNaN(val) ? 1 : Math.max(1, Math.min(val, maxQuantity)));
                      }}
                      min={1}
                      max={maxQuantity}
                      className="input-underline text-sm w-24"
                    />
                  </div>
                )}

                {/* Submit */}
                <button
                  onClick={handleDeposit}
                  disabled={actionLoading || !selectedItemId}
                  className="btn-blue w-full disabled:opacity-50"
                >
                  {actionLoading ? 'Помещение...' : 'Положить на склад'}
                </button>
              </motion.div>
            ) : (
              <motion.div
                key="withdraw"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.2 }}
              >
                {/* Gold summary */}
                {storageTotalGold > 0 && (
                  <div className="mb-4 p-3 rounded-card bg-white/5 flex items-center justify-between">
                    <p className="text-white/60 text-sm">
                      Всего золота на складе:{' '}
                      <span className="gold-text font-medium">
                        {storageTotalGold.toLocaleString('ru-RU')}
                      </span>
                    </p>
                  </div>
                )}

                {/* Error */}
                {storageError && (
                  <div className="text-center py-4">
                    <p className="text-site-red">{storageError}</p>
                  </div>
                )}

                {/* Loading */}
                {storageLoading && (
                  <div className="flex items-center justify-center py-12">
                    <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
                  </div>
                )}

                {/* Empty state */}
                {!storageLoading && !storageError && storageItems.length === 0 && (
                  <div className="text-center py-12">
                    <p className="text-white/50 text-lg">Склад пуст</p>
                    <p className="text-white/30 text-sm mt-2">
                      Купленные и возвращённые предметы появятся здесь
                    </p>
                  </div>
                )}

                {/* Items */}
                {!storageLoading && storageItems.length > 0 && (
                  <>
                    {/* Actions bar */}
                    <div className="flex items-center justify-between mb-4 gap-2 flex-wrap">
                      <button
                        onClick={selectAll}
                        className="text-site-blue text-sm hover:text-white transition-colors"
                      >
                        {selectedIds.size === storageItems.length ? 'Снять выделение' : 'Выбрать все'}
                      </button>
                      <div className="flex gap-2">
                        <button
                          onClick={handleClaimSelected}
                          disabled={selectedIds.size === 0 || actionLoading}
                          className="btn-blue !px-4 !py-2 !text-sm disabled:opacity-50"
                        >
                          {actionLoading ? '...' : `Забрать (${selectedIds.size})`}
                        </button>
                        <button
                          onClick={handleClaimAll}
                          disabled={storageItems.length === 0 || actionLoading}
                          className="btn-line !text-sm !w-auto !px-4 disabled:opacity-50"
                        >
                          Забрать все
                        </button>
                      </div>
                    </div>

                    <motion.div
                      initial="hidden"
                      animate="visible"
                      variants={{
                        hidden: {},
                        visible: { transition: { staggerChildren: 0.04 } },
                      }}
                      className="space-y-2"
                    >
                      {storageItems.map((item) => (
                        <StorageRow
                          key={item.id}
                          item={item}
                          selected={selectedIds.has(item.id)}
                          onToggle={toggleItem}
                        />
                      ))}
                    </motion.div>
                  </>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  );
};

export default NpcAuctionModal;
