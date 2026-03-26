import { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchSocketInfo,
  insertGem,
  extractGem,
  clearSocketInfo,
  selectSocketInfo,
  selectSocketInfoLoading,
  selectSocketLoading,
  fetchCharacterProfession,
} from '../../../redux/slices/craftingSlice';
import { fetchInventory, fetchEquipment } from '../../../redux/slices/profileSlice';
import type { AvailableGem, SocketGemInfo } from '../../../types/gems';

interface JewelryItemRef {
  rowId: number;
  itemId: number;
  name: string;
  image: string | null;
  itemType: string;
  itemRarity: string;
  socketCount: number;
  socketedGems: (number | null)[];
  enhancementPointsSpent: number;
  source: 'inventory' | 'equipment';
}

interface GemSocketModalProps {
  characterId: number;
  item: JewelryItemRef;
  onClose: () => void;
}

const ITEM_TYPE_LABELS: Record<string, string> = {
  ring: 'Кольцо',
  necklace: 'Ожерелье',
  bracelet: 'Браслет',
  head: 'Шлем',
  body: 'Броня',
  cloak: 'Плащ',
  belt: 'Пояс',
  main_weapon: 'Основное оружие',
  additional_weapons: 'Дополнительное оружие',
  shield: 'Щит',
};

const MODIFIER_LABELS: Record<string, string> = {
  strength: 'Сила',
  agility: 'Ловкость',
  intelligence: 'Интеллект',
  endurance: 'Выносливость',
  health: 'Здоровье',
  energy: 'Энергия',
  mana: 'Мана',
  stamina: 'Стамина',
  charisma: 'Харизма',
  luck: 'Удача',
  damage: 'Урон',
  dodge: 'Уклонение',
  health_recovery: 'Реген. здоровья',
  energy_recovery: 'Реген. энергии',
  mana_recovery: 'Реген. маны',
  res_fire: 'Сопр. огню',
  res_water: 'Сопр. воде',
  res_earth: 'Сопр. земле',
  res_air: 'Сопр. воздуху',
  vul_fire: 'Уяз. огню',
  vul_water: 'Уяз. воде',
  vul_earth: 'Уяз. земле',
  vul_air: 'Уяз. воздуху',
};

const JEWELRY_TYPES = new Set(['ring', 'necklace', 'bracelet']);

const GemSocketModal = ({ characterId, item, onClose }: GemSocketModalProps) => {
  const dispatch = useAppDispatch();
  const socketInfo = useAppSelector(selectSocketInfo);
  const infoLoading = useAppSelector(selectSocketInfoLoading);
  const socketLoading = useAppSelector(selectSocketLoading);

  const isJewelry = JEWELRY_TYPES.has(item.itemType);
  const insertableName = isJewelry ? 'камень' : 'руну';
  const insertableNamePlural = isJewelry ? 'камней' : 'рун';
  const insertableLabel = isJewelry ? 'Камень' : 'Руна';

  const [selectedSlotIndex, setSelectedSlotIndex] = useState<number | null>(null);
  const [selectedGem, setSelectedGem] = useState<AvailableGem | null>(null);
  const [mode, setMode] = useState<'idle' | 'insert' | 'extract'>('idle');

  // Fetch socket info on open
  useEffect(() => {
    dispatch(fetchSocketInfo({
      characterId,
      itemRowId: item.rowId,
      source: item.source,
    }));
    return () => {
      dispatch(clearSocketInfo());
    };
  }, [dispatch, characterId, item.rowId, item.source]);

  const refreshData = useCallback(() => {
    dispatch(fetchSocketInfo({
      characterId,
      itemRowId: item.rowId,
      source: item.source,
    }));
    dispatch(fetchInventory(characterId));
    if (item.source === 'equipment') {
      dispatch(fetchEquipment(characterId));
    }
  }, [dispatch, characterId, item]);

  const handleSlotClick = useCallback((slot: SocketGemInfo) => {
    if (slot.gem_item_id) {
      // Filled slot -> extract mode
      setSelectedSlotIndex(slot.slot_index);
      setSelectedGem(null);
      setMode('extract');
    } else {
      // Empty slot -> insert mode
      setSelectedSlotIndex(slot.slot_index);
      setSelectedGem(null);
      setMode('insert');
    }
  }, []);

  const handleSelectGem = useCallback((gem: AvailableGem) => {
    setSelectedGem(gem);
  }, []);

  const handleInsert = useCallback(async () => {
    if (selectedSlotIndex === null || !selectedGem) return;

    const result = await dispatch(insertGem({
      characterId,
      payload: {
        item_row_id: item.rowId,
        gem_inventory_id: selectedGem.inventory_item_id,
        slot_index: selectedSlotIndex,
        source: item.source,
      },
    }));

    if (result.meta.requestStatus === 'fulfilled') {
      const data = result.payload as {
        xp_earned: number;
        rank_up: boolean;
        new_rank_name: string | null;
      };
      toast.success(`${insertableLabel} вставлен${isJewelry ? '' : 'а'}!`);
      if (data.xp_earned > 0) {
        toast.success(`+${data.xp_earned} XP`, { duration: 3000 });
      }
      if (data.rank_up && data.new_rank_name) {
        toast.success(`Повышение ранга: ${data.new_rank_name}!`, { duration: 5000 });
        dispatch(fetchCharacterProfession(characterId));
      }
      setMode('idle');
      setSelectedSlotIndex(null);
      setSelectedGem(null);
      refreshData();
    } else {
      const err = result.payload as string | undefined;
      toast.error(err ?? `Не удалось вставить ${insertableName}`);
    }
  }, [dispatch, characterId, item, selectedSlotIndex, selectedGem, refreshData, insertableLabel, isJewelry, insertableName]);

  const handleExtract = useCallback(async () => {
    if (selectedSlotIndex === null) return;

    const result = await dispatch(extractGem({
      characterId,
      payload: {
        item_row_id: item.rowId,
        slot_index: selectedSlotIndex,
        source: item.source,
      },
    }));

    if (result.meta.requestStatus === 'fulfilled') {
      const data = result.payload as {
        gem_preserved: boolean;
        gem_name: string;
        xp_earned: number;
        rank_up: boolean;
        new_rank_name: string | null;
      };

      if (data.gem_preserved) {
        toast.success(`${insertableLabel} извлечен${isJewelry ? '' : 'а'}! "${data.gem_name}" сохранён в инвентаре.`);
      } else {
        toast.error(`${insertableLabel} разрушен${isJewelry ? '' : 'а'}! "${data.gem_name}" уничтожен${isJewelry ? '' : 'а'}.`);
      }
      if (data.xp_earned > 0) {
        toast.success(`+${data.xp_earned} XP`, { duration: 3000 });
      }
      if (data.rank_up && data.new_rank_name) {
        toast.success(`Повышение ранга: ${data.new_rank_name}!`, { duration: 5000 });
        dispatch(fetchCharacterProfession(characterId));
      }
      setMode('idle');
      setSelectedSlotIndex(null);
      refreshData();
    } else {
      const err = result.payload as string | undefined;
      toast.error(err ?? `Не удалось извлечь ${insertableName}`);
    }
  }, [dispatch, characterId, item, selectedSlotIndex, refreshData, insertableLabel, isJewelry, insertableName]);

  const selectedSlot = socketInfo?.slots.find((s) => s.slot_index === selectedSlotIndex);

  const formatModifiers = (modifiers: Record<string, number>) => {
    return Object.entries(modifiers)
      .filter(([, v]) => v !== 0)
      .map(([key, val]) => {
        const label = MODIFIER_LABELS[key] ?? key;
        return `${label}: ${val > 0 ? '+' : ''}${val}`;
      });
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="modal-content gold-outline gold-outline-thick w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto gold-scrollbar"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="w-14 h-14 rounded-full overflow-hidden bg-white/[0.05] flex-shrink-0 flex items-center justify-center">
            {item.image ? (
              <img src={item.image} alt={item.name} className="w-full h-full object-cover" />
            ) : (
              <span className="text-white/30 text-xl">?</span>
            )}
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="gold-text text-xl font-medium uppercase truncate">{item.name}</h2>
            <p className="text-white/60 text-sm">
              {ITEM_TYPE_LABELS[item.itemType] ?? item.itemType}
              {item.source === 'equipment' && (
                <span className="text-site-blue ml-2">(экипировано)</span>
              )}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-white/50 hover:text-white transition-colors text-xl leading-none p-1"
          >
            &times;
          </button>
        </div>

        {infoLoading ? (
          <div className="flex items-center justify-center py-10">
            <div className="w-6 h-6 border-2 border-gold border-t-transparent rounded-full animate-spin" />
          </div>
        ) : socketInfo ? (
          <>
            {/* Socket slots visual */}
            <div className="mb-5">
              <h3 className="text-white text-sm font-medium uppercase tracking-wide mb-3">
                Слоты ({socketInfo.slots.filter((s) => s.gem_item_id).length}/{socketInfo.socket_count})
              </h3>
              <div className="flex flex-wrap gap-3 justify-center">
                {socketInfo.slots.map((slot) => (
                  <button
                    key={slot.slot_index}
                    onClick={() => handleSlotClick(slot)}
                    className={`
                      relative flex flex-col items-center gap-1 p-2 rounded-card w-20 sm:w-24
                      transition-all duration-200 ease-site cursor-pointer
                      ${selectedSlotIndex === slot.slot_index
                        ? 'bg-gold/[0.12] border border-gold/30'
                        : 'bg-white/[0.04] border border-white/10 hover:bg-white/[0.08]'
                      }
                    `}
                  >
                    <div className={`
                      w-10 h-10 sm:w-12 sm:h-12 rounded-full flex items-center justify-center
                      ${slot.gem_item_id
                        ? 'bg-gold/[0.15] border border-gold/40'
                        : 'bg-white/[0.05] border border-dashed border-white/20'
                      }
                    `}>
                      {slot.gem_item_id && slot.gem_image ? (
                        <img
                          src={slot.gem_image}
                          alt={slot.gem_name ?? ''}
                          className="w-8 h-8 sm:w-10 sm:h-10 rounded-full object-cover"
                        />
                      ) : slot.gem_item_id ? (
                        <span className="text-gold text-lg">&#9670;</span>
                      ) : (
                        <span className="text-white/20 text-xs">Пусто</span>
                      )}
                    </div>
                    {slot.gem_name && (
                      <span className="text-white text-[10px] leading-tight text-center line-clamp-2">
                        {slot.gem_name}
                      </span>
                    )}
                    <span className="text-[10px] text-white/40">#{slot.slot_index + 1}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Insert mode: show available gems */}
            <AnimatePresence mode="wait">
              {mode === 'insert' && selectedSlotIndex !== null && (
                <motion.div
                  key="insert-panel"
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -5 }}
                  className="mb-5"
                >
                  <h3 className="text-white text-sm font-medium uppercase tracking-wide mb-2">
                    Выберите {insertableName} для слота #{selectedSlotIndex + 1}
                  </h3>
                  {socketInfo.available_gems.length === 0 ? (
                    <p className="text-site-red text-sm py-2">Нет {insertableNamePlural} в инвентаре</p>
                  ) : (
                    <div className="space-y-1 max-h-[200px] overflow-y-auto gold-scrollbar pr-1">
                      {socketInfo.available_gems.map((gem) => (
                        <button
                          key={gem.inventory_item_id}
                          onClick={() => handleSelectGem(gem)}
                          className={`
                            w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-left
                            transition-all duration-200 ease-site cursor-pointer
                            ${selectedGem?.inventory_item_id === gem.inventory_item_id
                              ? 'bg-gold/[0.12] border border-gold/30'
                              : 'bg-white/[0.03] border border-transparent hover:bg-white/[0.06]'
                            }
                          `}
                        >
                          <div className="w-8 h-8 rounded-full overflow-hidden bg-white/[0.05] flex-shrink-0 flex items-center justify-center">
                            {gem.image ? (
                              <img src={gem.image} alt={gem.name} className="w-full h-full object-cover" />
                            ) : (
                              <span className="text-gold text-sm">&#9670;</span>
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <span className="text-white text-sm truncate block">{gem.name}</span>
                            <span className="text-white/40 text-[10px]">x{gem.quantity}</span>
                          </div>
                          <div className="text-right">
                            {formatModifiers(gem.modifiers).map((mod, i) => (
                              <span key={i} className="block text-site-blue text-[10px] leading-tight">
                                {mod}
                              </span>
                            ))}
                          </div>
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Selected gem preview + insert button */}
                  {selectedGem && (
                    <div className="mt-3 p-3 rounded-card bg-white/[0.04] border border-gold/20">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-8 h-8 rounded-full overflow-hidden bg-white/[0.05] flex-shrink-0 flex items-center justify-center">
                          {selectedGem.image ? (
                            <img src={selectedGem.image} alt={selectedGem.name} className="w-full h-full object-cover" />
                          ) : (
                            <span className="text-gold text-sm">&#9670;</span>
                          )}
                        </div>
                        <span className="text-white text-sm font-medium">{selectedGem.name}</span>
                      </div>
                      <div className="flex flex-wrap gap-x-3 gap-y-0.5 mb-3">
                        {formatModifiers(selectedGem.modifiers).map((mod, i) => (
                          <span key={i} className="text-site-blue text-xs">{mod}</span>
                        ))}
                      </div>
                      <button
                        onClick={handleInsert}
                        disabled={socketLoading}
                        className={`btn-blue w-full text-sm py-2 ${socketLoading ? 'opacity-40 cursor-not-allowed' : ''}`}
                      >
                        {socketLoading ? (
                          <span className="flex items-center justify-center gap-2">
                            <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                            Вставка...
                          </span>
                        ) : (
                          'Вставить'
                        )}
                      </button>
                    </div>
                  )}
                </motion.div>
              )}

              {/* Extract mode: show gem info + extract button */}
              {mode === 'extract' && selectedSlot?.gem_item_id && (
                <motion.div
                  key="extract-panel"
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -5 }}
                  className="mb-5"
                >
                  <h3 className="text-white text-sm font-medium uppercase tracking-wide mb-2">
                    Извлечение {isJewelry ? 'камня' : 'руны'} из слота #{(selectedSlot.slot_index) + 1}
                  </h3>
                  <div className="p-3 rounded-card bg-white/[0.04] border border-white/10">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-8 h-8 rounded-full overflow-hidden bg-white/[0.05] flex-shrink-0 flex items-center justify-center">
                        {selectedSlot.gem_image ? (
                          <img src={selectedSlot.gem_image} alt={selectedSlot.gem_name ?? ''} className="w-full h-full object-cover" />
                        ) : (
                          <span className="text-gold text-sm">&#9670;</span>
                        )}
                      </div>
                      <span className="text-white text-sm font-medium">{selectedSlot.gem_name}</span>
                    </div>
                    {Object.keys(selectedSlot.gem_modifiers).length > 0 && (
                      <div className="flex flex-wrap gap-x-3 gap-y-0.5 mb-3">
                        {formatModifiers(selectedSlot.gem_modifiers).map((mod, i) => (
                          <span key={i} className="text-site-blue text-xs">{mod}</span>
                        ))}
                      </div>
                    )}
                    <div className="bg-site-red/10 border border-site-red/30 rounded-lg p-2 mb-3">
                      <p className="text-site-red text-xs text-center">
                        {insertableLabel} может быть разрушен{isJewelry ? '' : 'а'} при извлечении. Шанс сохранения зависит от вашего ранга.
                      </p>
                    </div>
                    <button
                      onClick={handleExtract}
                      disabled={socketLoading}
                      className={`btn-blue w-full text-sm py-2 ${socketLoading ? 'opacity-40 cursor-not-allowed' : ''}`}
                    >
                      {socketLoading ? (
                        <span className="flex items-center justify-center gap-2">
                          <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                          Извлечение...
                        </span>
                      ) : (
                        `Извлечь ${insertableName}`
                      )}
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Close button */}
            <div className="flex justify-end">
              <button onClick={onClose} className="btn-line text-sm py-2.5">
                Закрыть
              </button>
            </div>
          </>
        ) : (
          <p className="text-site-red text-sm text-center py-4">
            Не удалось загрузить информацию о слотах
          </p>
        )}
      </motion.div>
    </div>
  );
};

export default GemSocketModal;
