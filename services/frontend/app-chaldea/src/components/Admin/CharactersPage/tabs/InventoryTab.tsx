import { useEffect, useState, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../../../redux/store';
import {
  fetchAdminInventory,
  fetchAdminEquipment,
  addAdminInventoryItem,
  removeAdminInventoryItem,
  unequipAdminItem,
  selectAdminInventory,
  selectAdminEquipment,
  selectAdminDetailLoading,
} from '../../../../redux/slices/adminCharactersSlice';
import { searchItemsCatalog } from '../../../../api/adminCharacters';
import { EQUIPMENT_SLOT_ORDER, EQUIPMENT_SLOT_LABELS } from '../../../ProfilePage/constants';
import type { ItemData } from '../types';

interface InventoryTabProps {
  characterId: number;
}

const DEBOUNCE_MS = 300;

const InventoryTab = ({ characterId }: InventoryTabProps) => {
  const dispatch = useAppDispatch();
  const inventory = useAppSelector(selectAdminInventory);
  const equipment = useAppSelector(selectAdminEquipment);
  const loading = useAppSelector(selectAdminDetailLoading);

  // Add item state
  const [showAddPanel, setShowAddPanel] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<ItemData[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedItem, setSelectedItem] = useState<ItemData | null>(null);
  const [addQuantity, setAddQuantity] = useState(1);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Confirm delete state
  const [deleteTarget, setDeleteTarget] = useState<{ itemId: number; name: string } | null>(null);

  // Confirm unequip state
  const [unequipTarget, setUnequipTarget] = useState<{ slotType: string; name: string } | null>(
    null,
  );

  useEffect(() => {
    dispatch(fetchAdminInventory(characterId));
    dispatch(fetchAdminEquipment(characterId));
  }, [dispatch, characterId]);

  const handleSearch = useCallback(
    (value: string) => {
      setSearchQuery(value);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (!value.trim()) {
        setSearchResults([]);
        return;
      }
      debounceRef.current = setTimeout(async () => {
        setSearching(true);
        try {
          const results = await searchItemsCatalog(value);
          setSearchResults(results);
        } catch {
          setSearchResults([]);
        } finally {
          setSearching(false);
        }
      }, DEBOUNCE_MS);
    },
    [],
  );

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const handleAddItem = async () => {
    if (!selectedItem) return;
    await dispatch(
      addAdminInventoryItem({
        characterId,
        itemId: selectedItem.id,
        quantity: addQuantity,
      }),
    );
    setSelectedItem(null);
    setSearchQuery('');
    setSearchResults([]);
    setAddQuantity(1);
    setShowAddPanel(false);
  };

  const handleRemoveItem = async () => {
    if (!deleteTarget) return;
    await dispatch(
      removeAdminInventoryItem({ characterId, itemId: deleteTarget.itemId }),
    );
    setDeleteTarget(null);
  };

  const handleUnequip = async () => {
    if (!unequipTarget) return;
    await dispatch(
      unequipAdminItem({ characterId, slotType: unequipTarget.slotType }),
    );
    setUnequipTarget(null);
  };

  if (loading && inventory.length === 0 && equipment.length === 0) {
    return (
      <div className="flex justify-center items-center py-12">
        <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="space-y-6"
    >
      {/* Equipment slots */}
      <div className="gray-bg p-6">
        <h3 className="gold-text text-lg font-medium uppercase mb-4">Экипировка</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {EQUIPMENT_SLOT_ORDER.map((slotType) => {
            const slot = equipment.find((e) => e.slot_type === slotType);
            const hasItem = slot?.item != null;
            return (
              <div
                key={slotType}
                className="flex flex-col items-center gap-2 p-3 rounded-card bg-white/[0.04]"
              >
                <span className="text-white/50 text-xs uppercase tracking-[0.06em]">
                  {EQUIPMENT_SLOT_LABELS[slotType] ?? slotType}
                </span>
                {hasItem && slot?.item ? (
                  <>
                    {slot.item.image && (
                      <img
                        src={slot.item.image}
                        alt={slot.item.name}
                        className="w-12 h-12 rounded-full object-cover border border-white/20"
                      />
                    )}
                    <span className="text-white text-xs text-center">{slot.item.name}</span>
                    <button
                      className="text-site-blue text-xs hover:opacity-80 transition-opacity duration-200"
                      onClick={() =>
                        setUnequipTarget({
                          slotType,
                          name: slot.item!.name,
                        })
                      }
                    >
                      Снять
                    </button>
                  </>
                ) : (
                  <span className="text-white/30 text-xs">Пусто</span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Inventory items */}
      <div className="gray-bg p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="gold-text text-lg font-medium uppercase">Инвентарь</h3>
          <button className="btn-line text-sm" onClick={() => setShowAddPanel(!showAddPanel)}>
            {showAddPanel ? 'Закрыть' : 'Добавить предмет'}
          </button>
        </div>

        {/* Add item panel */}
        <AnimatePresence>
          {showAddPanel && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="mb-4 overflow-hidden"
            >
              <div className="p-4 rounded-card bg-white/[0.04] space-y-3">
                <input
                  type="text"
                  className="input-underline w-full"
                  placeholder="Поиск предмета по названию..."
                  value={searchQuery}
                  onChange={(e) => handleSearch(e.target.value)}
                />

                {searching && (
                  <p className="text-white/50 text-sm">Поиск...</p>
                )}

                {searchResults.length > 0 && !selectedItem && (
                  <div className="dropdown-menu max-h-[200px] overflow-y-auto gold-scrollbar">
                    {searchResults.map((item) => (
                      <button
                        key={item.id}
                        className="dropdown-item w-full text-left"
                        onClick={() => {
                          setSelectedItem(item);
                          setSearchQuery(item.name);
                          setSearchResults([]);
                        }}
                      >
                        <span className="text-white">{item.name}</span>
                        <span className="text-white/40 text-xs ml-2">
                          [{item.item_type}] Ур.{item.item_level}
                        </span>
                      </button>
                    ))}
                  </div>
                )}

                {selectedItem && (
                  <div className="flex items-center gap-4">
                    <span className="text-white text-sm">
                      Выбрано: <span className="text-gold">{selectedItem.name}</span>
                    </span>
                    <div className="flex items-center gap-2">
                      <label className="text-white/60 text-xs">Кол-во:</label>
                      <input
                        type="number"
                        className="input-underline w-[80px]"
                        min={1}
                        value={addQuantity}
                        onChange={(e) => setAddQuantity(Math.max(1, Number(e.target.value)))}
                      />
                    </div>
                    <button className="btn-blue text-sm" onClick={handleAddItem}>
                      Добавить
                    </button>
                    <button
                      className="text-white/50 text-sm hover:text-site-blue transition-colors duration-200"
                      onClick={() => {
                        setSelectedItem(null);
                        setSearchQuery('');
                      }}
                    >
                      Отмена
                    </button>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Item list */}
        {inventory.length === 0 ? (
          <p className="text-white/50 text-center py-4">Инвентарь пуст</p>
        ) : (
          <motion.div
            initial="hidden"
            animate="visible"
            variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.03 } } }}
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
          >
            {inventory.map((inv) => (
              <motion.div
                key={inv.id}
                variants={{
                  hidden: { opacity: 0, y: 5 },
                  visible: { opacity: 1, y: 0 },
                }}
                className="flex items-center gap-3 p-3 rounded-card bg-white/[0.04] hover:bg-white/[0.07] transition-colors duration-200"
              >
                {inv.item.image && (
                  <img
                    src={inv.item.image}
                    alt={inv.item.name}
                    className="w-10 h-10 rounded-full object-cover border border-white/20 flex-shrink-0"
                  />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm truncate">{inv.item.name}</p>
                  <p className="text-white/40 text-xs">
                    x{inv.quantity} | {inv.item.item_type}
                  </p>
                </div>
                <button
                  className="text-site-red text-xs hover:opacity-80 transition-opacity duration-200 flex-shrink-0"
                  onClick={() =>
                    setDeleteTarget({ itemId: inv.item_id, name: inv.item.name })
                  }
                >
                  Удалить
                </button>
              </motion.div>
            ))}
          </motion.div>
        )}
      </div>

      {/* Delete item confirmation modal */}
      <AnimatePresence>
        {deleteTarget && (
          <div className="modal-overlay" onClick={() => setDeleteTarget(null)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="gold-text text-2xl uppercase mb-4">Удаление предмета</h2>
              <p className="text-white mb-6">
                Удалить предмет{' '}
                <span className="text-gold font-medium">{deleteTarget.name}</span> из инвентаря?
              </p>
              <div className="flex gap-4">
                <button className="btn-blue" onClick={handleRemoveItem}>
                  Удалить
                </button>
                <button className="btn-line" onClick={() => setDeleteTarget(null)}>
                  Отмена
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Unequip confirmation modal */}
      <AnimatePresence>
        {unequipTarget && (
          <div className="modal-overlay" onClick={() => setUnequipTarget(null)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="gold-text text-2xl uppercase mb-4">Снять предмет</h2>
              <p className="text-white mb-6">
                Снять{' '}
                <span className="text-gold font-medium">{unequipTarget.name}</span> со слота{' '}
                {EQUIPMENT_SLOT_LABELS[unequipTarget.slotType] ?? unequipTarget.slotType}?
              </p>
              <div className="flex gap-4">
                <button className="btn-blue" onClick={handleUnequip}>
                  Снять
                </button>
                <button className="btn-line" onClick={() => setUnequipTarget(null)}>
                  Отмена
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default InventoryTab;
