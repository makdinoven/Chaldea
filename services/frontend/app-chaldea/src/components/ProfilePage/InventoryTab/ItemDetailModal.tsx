import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'motion/react';
import { useAppSelector, useAppDispatch } from '../../../redux/store';
import {
  selectItemDetailModal,
  selectInventory,
  selectRepairLoading,
  closeItemDetailModal,
  fetchItemDetail,
  repairItem,
} from '../../../redux/slices/profileSlice';
import { STAT_LABELS, PERCENTAGE_STATS } from '../constants';
import toast from 'react-hot-toast';

/** Russian labels for item types */
const ITEM_TYPE_LABELS: Record<string, string> = {
  head: 'Шлем',
  body: 'Броня',
  cloak: 'Плащ',
  belt: 'Пояс',
  shield: 'Щит',
  ring: 'Кольцо',
  necklace: 'Ожерелье',
  bracelet: 'Браслет',
  main_weapon: 'Оружие',
  additional_weapons: 'Дополнительное оружие',
  consumable: 'Зелье',
  scroll: 'Свиток',
  resource: 'Ресурс',
  misc: 'Разное',
  blueprint: 'Чертёж',
  recipe: 'Рецепт',
  gem: 'Камень',
  rune: 'Руна',
};

/** Russian labels for item rarities */
const RARITY_LABELS: Record<string, string> = {
  common: 'Обычный',
  rare: 'Редкий',
  epic: 'Эпический',
  mythical: 'Мифический',
  legendary: 'Легендарный',
};

/** Rarity text color classes */
const RARITY_COLORS: Record<string, string> = {
  common: 'text-rarity-common',
  rare: 'text-rarity-rare',
  epic: 'text-rarity-epic',
  mythical: 'text-rarity-mythical',
  legendary: 'text-rarity-legendary',
};

/** Modifier field keys that are numeric on ItemData */
const MODIFIER_FIELDS = [
  // Main stats
  'strength_modifier',
  'agility_modifier',
  'intelligence_modifier',
  'endurance_modifier',
  'health_modifier',
  'energy_modifier',
  'mana_modifier',
  'stamina_modifier',
  'charisma_modifier',
  'luck_modifier',
  'damage_modifier',
  'dodge_modifier',
  // Combat
  'critical_hit_chance_modifier',
  'critical_damage_modifier',
  // Resistances
  'res_physical_modifier',
  'res_catting_modifier',
  'res_crushing_modifier',
  'res_piercing_modifier',
  'res_magic_modifier',
  'res_fire_modifier',
  'res_ice_modifier',
  'res_watering_modifier',
  'res_electricity_modifier',
  'res_wind_modifier',
  'res_sainting_modifier',
  'res_damning_modifier',
  'res_effects_modifier',
  // Vulnerabilities
  'vul_physical_modifier',
  'vul_catting_modifier',
  'vul_crushing_modifier',
  'vul_piercing_modifier',
  'vul_magic_modifier',
  'vul_fire_modifier',
  'vul_ice_modifier',
  'vul_watering_modifier',
  'vul_electricity_modifier',
  'vul_wind_modifier',
  'vul_sainting_modifier',
  'vul_damning_modifier',
  'vul_effects_modifier',
  // Recovery
  'health_recovery',
  'energy_recovery',
  'mana_recovery',
  'stamina_recovery',
] as const;

/** Map modifier field to stat label key */
const MODIFIER_TO_STAT: Record<string, string> = {
  strength_modifier: 'strength',
  agility_modifier: 'agility',
  intelligence_modifier: 'intelligence',
  endurance_modifier: 'endurance',
  health_modifier: 'health',
  energy_modifier: 'energy',
  mana_modifier: 'mana',
  stamina_modifier: 'stamina',
  charisma_modifier: 'charisma',
  luck_modifier: 'luck',
  damage_modifier: 'damage',
  dodge_modifier: 'dodge',
  critical_hit_chance_modifier: 'critical_hit_chance',
  critical_damage_modifier: 'critical_damage',
  res_physical_modifier: 'res_physical',
  res_catting_modifier: 'res_catting',
  res_crushing_modifier: 'res_crushing',
  res_piercing_modifier: 'res_piercing',
  res_magic_modifier: 'res_magic',
  res_fire_modifier: 'res_fire',
  res_ice_modifier: 'res_ice',
  res_watering_modifier: 'res_watering',
  res_electricity_modifier: 'res_electricity',
  res_wind_modifier: 'res_wind',
  res_sainting_modifier: 'res_sainting',
  res_damning_modifier: 'res_damning',
  res_effects_modifier: 'res_effects',
  vul_physical_modifier: 'vul_physical',
  vul_catting_modifier: 'vul_catting',
  vul_crushing_modifier: 'vul_crushing',
  vul_piercing_modifier: 'vul_piercing',
  vul_magic_modifier: 'vul_magic',
  vul_fire_modifier: 'vul_fire',
  vul_ice_modifier: 'vul_ice',
  vul_watering_modifier: 'vul_watering',
  vul_electricity_modifier: 'vul_electricity',
  vul_wind_modifier: 'vul_wind',
  vul_sainting_modifier: 'vul_sainting',
  vul_damning_modifier: 'vul_damning',
  vul_effects_modifier: 'vul_effects',
  health_recovery: 'health',
  energy_recovery: 'energy',
  mana_recovery: 'mana',
  stamina_recovery: 'stamina',
};

const RECOVERY_FIELDS = new Set([
  'health_recovery',
  'energy_recovery',
  'mana_recovery',
  'stamina_recovery',
]);

interface DurabilityBarProps {
  current: number;
  max: number;
  large?: boolean;
}

const DurabilityBar = ({ current, max, large = false }: DurabilityBarProps) => {
  const pct = max > 0 ? (current / max) * 100 : 0;
  const barColor =
    current === 0
      ? 'bg-red-800'
      : pct < 25
        ? 'bg-site-red'
        : pct < 50
          ? 'bg-yellow-500'
          : 'bg-stat-energy';

  return (
    <div className="w-full">
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs text-white/70">Прочность</span>
        <span className={`text-xs ${current === 0 ? 'text-site-red font-medium' : 'text-white/70'}`}>
          {current === 0 ? 'Сломан' : `${current}/${max}`}
        </span>
      </div>
      <div className={`w-full ${large ? 'h-2.5' : 'h-1.5'} bg-white/10 rounded-full overflow-hidden`}>
        <div
          className={`h-full ${barColor} rounded-full transition-all duration-300`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
};

interface ItemDetailModalInnerProps {
  characterId: number;
}

const ItemDetailModalInner = ({ characterId }: ItemDetailModalInnerProps) => {
  const dispatch = useAppDispatch();
  const modal = useAppSelector(selectItemDetailModal);
  const inventory = useAppSelector(selectInventory);
  const repairBusy = useAppSelector(selectRepairLoading);

  const { isOpen, inventoryItem, detail, loading, slotType } = modal;

  // Fetch item detail when modal opens
  useEffect(() => {
    if (!isOpen || !inventoryItem || !characterId) return;
    const source = slotType ? 'equipment' : 'inventory';
    dispatch(fetchItemDetail({
      characterId,
      inventoryItemId: inventoryItem.id,
      source,
    }));
  }, [isOpen, inventoryItem, characterId, slotType, dispatch]);

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') dispatch(closeItemDetailModal());
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [isOpen, dispatch]);

  const handleClose = () => dispatch(closeItemDetailModal());

  // Find repair kits in inventory
  const repairKits = inventory.filter(
    (inv) => inv.item.repair_power != null && inv.item.repair_power > 0,
  );

  const handleRepair = async (repairKitItemId: number) => {
    if (!inventoryItem) return;
    const source = slotType ? 'equipment' : 'inventory';
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
        // Re-fetch detail
        dispatch(fetchItemDetail({
          characterId,
          inventoryItemId: inventoryItem.id,
          source,
        }));
      } else {
        const payload = result.payload as string | undefined;
        toast.error(payload ?? 'Не удалось починить предмет');
      }
    } catch {
      toast.error('Произошла ошибка при ремонте');
    }
  };

  const item = detail?.item ?? inventoryItem?.item;
  if (!item) return null;

  const isUnidentified = detail ? !detail.is_identified : inventoryItem?.is_identified === false;
  const enhancementSpent = detail?.enhancement_points_spent ?? inventoryItem?.enhancement_points_spent ?? 0;
  const maxDurability = detail?.max_durability ?? item.max_durability ?? 0;
  const currentDurability = detail?.current_durability ?? inventoryItem?.current_durability;
  const effectiveDurability = currentDurability ?? maxDurability;
  const hasDurability = maxDurability > 0;
  const needsRepair = hasDurability && effectiveDurability < maxDurability;

  const rarityColor = RARITY_COLORS[item.item_rarity] ?? 'text-white';
  const rarityLabel = RARITY_LABELS[item.item_rarity] ?? item.item_rarity;
  const typeLabel = ITEM_TYPE_LABELS[item.item_type] ?? item.item_type;

  // Collect base modifiers
  const baseModMap: Record<string, number> = {};
  for (const field of MODIFIER_FIELDS) {
    const val = (item as unknown as Record<string, number>)[field];
    if (val && val !== 0) {
      baseModMap[field] = val;
    }
  }

  // Enhancement bonuses (sharpening)
  const enhancementBonuses = detail?.enhancement_bonuses ?? {};
  const enhBonusMap: Record<string, number> = {};
  if (enhancementBonuses) {
    for (const [field, count] of Object.entries(enhancementBonuses)) {
      if (!count || count === 0) continue;
      // Per-stat increment: crit chance +0.5%, crit damage +1%, resistances +0.1%, main stats +1
      let increment = 1;
      if (field === 'critical_hit_chance_modifier') increment = 0.5;
      else if (field === 'critical_damage_modifier') increment = 1.0;
      else if (field.startsWith('res_')) increment = 0.1;
      enhBonusMap[field] = Math.round(count * increment * 100) / 100;
    }
  }

  // Gem/rune bonuses from socketed items
  const gemBonusMap: Record<string, number> = {};
  const socketedItems = detail?.socketed_items ?? [];
  for (const slot of socketedItems) {
    if (!slot?.item_id || !slot.modifiers) continue;
    for (const [key, val] of Object.entries(slot.modifiers)) {
      if (val && val !== 0) {
        // Convert stat key (e.g. "strength") to field (e.g. "strength_modifier")
        const field = key.endsWith('_modifier') ? key : `${key}_modifier`;
        gemBonusMap[field] = (gemBonusMap[field] ?? 0) + val;
      }
    }
  }

  // Build unified stat list: all fields that have any value (base, enhancement, or gem)
  const allFields = new Set([...Object.keys(baseModMap), ...Object.keys(enhBonusMap), ...Object.keys(gemBonusMap)]);
  const combinedModifiers: { field: string; label: string; baseValue: number; enhBonus: number; gemBonus: number; totalValue: number; isRecovery: boolean; isPercentage: boolean }[] = [];
  for (const field of MODIFIER_FIELDS) {
    if (!allFields.has(field)) continue;
    const baseVal = baseModMap[field] ?? 0;
    const enhVal = enhBonusMap[field] ?? 0;
    const gemVal = gemBonusMap[field] ?? 0;
    const total = Math.round((baseVal + enhVal + gemVal) * 100) / 100;
    if (total === 0 && baseVal === 0) continue;
    const statKey = MODIFIER_TO_STAT[field] ?? field;
    const label = STAT_LABELS[statKey] ?? statKey;
    const isRecovery = RECOVERY_FIELDS.has(field);
    const isPercentage = PERCENTAGE_STATS.has(statKey);
    combinedModifiers.push({
      field,
      label: isRecovery ? `${label} (восст.)` : label,
      baseValue: baseVal,
      enhBonus: enhVal,
      gemBonus: gemVal,
      totalValue: total,
      isRecovery,
      isPercentage,
    });
  }

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <motion.div
          key="item-detail-overlay"
          className="modal-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          onClick={handleClose}
        >
          <motion.div
            className="modal-content gold-outline gold-outline-thick w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto gold-scrollbar"
            style={{ overflowX: 'hidden' }}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            onClick={(e) => e.stopPropagation()}
          >
            {loading && !detail ? (
              <div className="flex items-center justify-center py-12">
                <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
              </div>
            ) : (
              <div className="overflow-hidden">
                {/* Header: image + name + rarity */}
                <div className="flex items-start gap-4 mb-4">
                  <div className={`w-20 h-20 sm:w-24 sm:h-24 flex-shrink-0 rounded-full overflow-hidden border-2 border-gold/40 bg-white/5 flex items-center justify-center`}>
                    {item.image ? (
                      <img
                        src={item.image}
                        alt={item.name}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <span className="text-3xl text-white/30">?</span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase break-words">
                        {item.name}
                      </h2>
                      {enhancementSpent > 0 && (
                        <span className="text-gold text-sm font-medium bg-gold/10 px-2 py-0.5 rounded-full">
                          +{enhancementSpent}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <span className={`text-sm font-medium ${rarityColor}`}>
                        {rarityLabel}
                      </span>
                      <span className="text-white/40 text-xs">|</span>
                      <span className="text-white/70 text-sm">{typeLabel}</span>
                      <span className="text-white/40 text-xs">|</span>
                      <span className="text-white/70 text-sm">Ур. {item.item_level}</span>
                    </div>
                  </div>
                </div>

                {/* Durability bar */}
                {hasDurability && (
                  <div className="mb-4">
                    <DurabilityBar current={effectiveDurability} max={maxDurability} large />
                  </div>
                )}

                {/* Description */}
                {item.description && (
                  <div className="mb-4">
                    <p className="text-white/80 text-sm leading-relaxed">{item.description}</p>
                  </div>
                )}

                {/* Modifiers / Stats */}
                {combinedModifiers.length > 0 && (
                  <div className="mb-4">
                    <h3 className="gold-text text-base font-medium uppercase mb-2">
                      Характеристики
                      {enhancementSpent > 0 && (
                        <span className="text-gold/60 text-xs ml-2 normal-case">(заточка {enhancementSpent}/15)</span>
                      )}
                    </h3>
                    {isUnidentified ? (
                      <p className="text-white/50 text-sm">???</p>
                    ) : (
                      <div className="flex flex-col gap-0.5">
                        {combinedModifiers.map((mod) => {
                          const hasBonuses = mod.enhBonus !== 0 || mod.gemBonus !== 0;
                          const isNewStat = mod.baseValue === 0 && hasBonuses;
                          const suffix = mod.isPercentage ? '%' : '';
                          return (
                            <div
                              key={mod.field}
                              className="flex justify-between items-center py-0.5 gap-3"
                            >
                              <span className={`text-xs sm:text-sm truncate ${isNewStat ? 'text-purple-300' : 'text-white/70'}`}>
                                {mod.label}
                                {isNewStat && <span className="text-purple-400/60 text-[10px] ml-1">NEW</span>}
                              </span>
                              <span className="flex items-center gap-1 shrink-0 text-right">
                                {/* Total value */}
                                <span className={`text-sm font-medium ${
                                  mod.totalValue > 0 ? 'text-stat-energy' : 'text-site-red'
                                }`}>
                                  {mod.totalValue > 0 ? '+' : ''}{mod.totalValue}{suffix}
                                </span>
                                {/* Bonus breakdown */}
                                {hasBonuses && (
                                  <span className="text-[9px] text-white/25 whitespace-nowrap">
                                    ({mod.baseValue}{suffix}
                                    {mod.enhBonus !== 0 && (
                                      <span className="text-gold/70">+{mod.enhBonus}{suffix}</span>
                                    )}
                                    {mod.gemBonus !== 0 && (
                                      <span className="text-site-blue/70">+{mod.gemBonus}{suffix}</span>
                                    )}
                                    )
                                  </span>
                                )}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}

                {/* Sockets */}
                {item.socket_count > 0 && (
                  <div className="mb-4">
                    <h3 className="gold-text text-base font-medium uppercase mb-2 text-center">
                      {['ring', 'necklace', 'bracelet'].includes(item.item_type) ? 'Камни' : 'Руны'} [{(detail?.socketed_items ?? []).filter((s: any) => s.item_id != null).length}/{item.socket_count}]
                    </h3>
                    <div className="flex gap-3 flex-wrap justify-center">
                      {Array.from({ length: item.socket_count }, (_, i) => {
                        const slot = (detail?.socketed_items ?? [])[i];
                        const hasFill = slot?.item_id != null;
                        return (
                          <div key={i} className="group relative">
                            <div
                              className={`w-12 h-12 rounded-lg border-2 ${
                                hasFill
                                  ? slot?.item_type === 'rune'
                                    ? 'border-purple-400/60 bg-purple-400/10'
                                    : 'border-gold/60 bg-gold/10'
                                  : 'border-white/20 bg-white/5'
                              } flex items-center justify-center overflow-hidden`}
                            >
                              {hasFill && slot?.image ? (
                                <img src={slot.image} alt={slot.name ?? ''} className="w-10 h-10 object-cover rounded" />
                              ) : hasFill ? (
                                <span className="text-gold text-sm font-medium">
                                  {slot?.item_type === 'rune' ? '᚛' : '◆'}
                                </span>
                              ) : (
                                <span className="text-white/20 text-lg">○</span>
                              )}
                            </div>
                            {/* Tooltip on hover */}
                            {hasFill && slot && (
                              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-50 pointer-events-none">
                                <div className="bg-[#1a1a2e] border border-gold/30 rounded-lg px-3 py-2 shadow-lg min-w-[160px]">
                                  <p className={`text-sm font-medium mb-1 ${slot.item_type === 'rune' ? 'text-purple-300' : 'text-gold'}`}>
                                    {slot.name}
                                  </p>
                                  {Object.entries(slot.modifiers || {}).filter(([, v]) => v !== 0).map(([key, val]) => (
                                    <p key={key} className="text-xs text-site-blue">
                                      {STAT_LABELS[key] ?? key}: {Number(val) > 0 ? '+' : ''}{val}
                                      {PERCENTAGE_STATS.has(key) ? '%' : ''}
                                    </p>
                                  ))}
                                  {Object.keys(slot.modifiers || {}).length === 0 && (
                                    <p className="text-xs text-white/40">Нет бонусов</p>
                                  )}
                                </div>
                                <div className="w-2 h-2 bg-[#1a1a2e] border-r border-b border-gold/30 rotate-45 absolute left-1/2 -translate-x-1/2 -bottom-1" />
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Identification status */}
                {isUnidentified && (
                  <div className="mb-4 px-3 py-2 bg-white/5 rounded-card">
                    <span className="text-white/60 text-sm">Предмет не опознан</span>
                  </div>
                )}

                {/* Repair section */}
                {needsRepair && (
                  <div className="mb-4">
                    <h3 className="gold-text text-base font-medium uppercase mb-2">
                      Ремонт
                    </h3>
                    {repairKits.length === 0 ? (
                      <p className="text-white/50 text-sm">Нет ремонт-комплектов</p>
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
                  </div>
                )}

                {/* Footer: level, price */}
                <div className="flex items-center justify-between pt-3 border-t border-white/10">
                  <span className="text-white/50 text-xs">
                    Уровень {item.item_level}
                  </span>
                  {item.price > 0 && (
                    <span className="text-gold text-xs">
                      {item.price} монет
                    </span>
                  )}
                </div>

                {/* Close button */}
                <button
                  onClick={handleClose}
                  className="btn-line w-full mt-4"
                >
                  Закрыть
                </button>
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
};

interface ItemDetailModalProps {
  characterId: number;
}

const ItemDetailModal = ({ characterId }: ItemDetailModalProps) => {
  const { isOpen } = useAppSelector(selectItemDetailModal);
  if (!isOpen) return null;
  return <ItemDetailModalInner characterId={characterId} />;
};

export default ItemDetailModal;
