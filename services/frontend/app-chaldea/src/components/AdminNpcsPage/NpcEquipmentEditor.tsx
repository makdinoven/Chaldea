import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../api/api';
import useDebounce from '../../hooks/useDebounce';

/* ── Types ── */

interface NpcEquipmentEditorProps {
  npcId: number;
  npcName: string;
  onClose: () => void;
}

interface ItemData {
  id: number;
  name: string;
  item_type: string;
  image: string | null;
  item_level: number;
  item_rarity: string;
  damage_modifier: number | null;
  strength_modifier: number | null;
  agility_modifier: number | null;
  intelligence_modifier: number | null;
  endurance_modifier: number | null;
}

interface EquipmentSlotData {
  id: number;
  character_id: number;
  slot_type: string;
  item_id: number | null;
  is_enabled: boolean | null;
  enhancement_points_spent: number;
  enhancement_bonuses: string | null;
  socketed_gems: string | null;
  current_durability: number | null;
  item: ItemData | null;
}

/* ── Constants ── */

const NPC_SLOT_TYPES = [
  'head', 'body', 'cloak', 'belt', 'ring',
  'necklace', 'bracelet', 'main_weapon', 'additional_weapons', 'shield',
] as const;

const SLOT_LABELS: Record<string, string> = {
  head: 'Голова',
  body: 'Тело',
  cloak: 'Плащ',
  belt: 'Пояс',
  ring: 'Кольцо',
  necklace: 'Ожерелье',
  bracelet: 'Браслет',
  main_weapon: 'Основное оружие',
  additional_weapons: 'Доп. оружие',
  shield: 'Щит',
};

const RARITY_COLORS: Record<string, string> = {
  common: 'text-white/60',
  rare: 'text-site-blue',
  epic: 'text-[#B875BD]',
  mythical: 'text-site-red',
  legendary: 'text-gold',
  divine: 'text-[#FFD700]',
  demonic: 'text-[#8B0000]',
};

const RARITY_LABELS: Record<string, string> = {
  common: 'Обычный',
  rare: 'Редкий',
  epic: 'Эпический',
  legendary: 'Легендарный',
  mythical: 'Мифический',
  divine: 'Божественный',
  demonic: 'Демонический',
};

/* ── Component ── */

const NpcEquipmentEditor = ({ npcId, npcName, onClose }: NpcEquipmentEditorProps) => {
  const [slots, setSlots] = useState<EquipmentSlotData[]>([]);
  const [loading, setLoading] = useState(true);
  const [pickerSlot, setPickerSlot] = useState<string | null>(null);
  const [pickerItems, setPickerItems] = useState<ItemData[]>([]);
  const [pickerLoading, setPickerLoading] = useState(false);
  const [pickerSearch, setPickerSearch] = useState('');
  const debouncedSearch = useDebounce(pickerSearch);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  /* ── Fetch equipment ── */

  const fetchEquipment = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get<EquipmentSlotData[]>(`${BASE_URL}/inventory/${npcId}/equipment`);
      const data = res.data;
      // Filter to only NPC equipment slots (exclude fast_slot_*)
      const npcSlots = data.filter((s) => (NPC_SLOT_TYPES as readonly string[]).includes(s.slot_type));
      setSlots(npcSlots);
    } catch {
      toast.error('Не удалось загрузить экипировку НПС');
    } finally {
      setLoading(false);
    }
  }, [npcId]);

  useEffect(() => {
    fetchEquipment();
  }, [fetchEquipment]);

  /* ── Fetch items for picker ── */

  const fetchPickerItems = useCallback(async (slotType: string) => {
    setPickerLoading(true);
    try {
      const res = await axios.get(`${BASE_URL}/inventory/items`, {
        params: { item_types: slotType, page: 1, page_size: 100 },
      });
      const data = res.data;
      setPickerItems(Array.isArray(data) ? data : data.items ?? []);
    } catch {
      toast.error('Не удалось загрузить список предметов');
    } finally {
      setPickerLoading(false);
    }
  }, []);

  /* ── Open picker ── */

  const openPicker = (slotType: string) => {
    setPickerSlot(slotType);
    setPickerSearch('');
    fetchPickerItems(slotType);
  };

  const closePicker = () => {
    setPickerSlot(null);
    setPickerItems([]);
    setPickerSearch('');
  };

  /* ── Equip item ── */

  const handleEquip = async (slotType: string, itemId: number) => {
    setActionLoading(slotType);
    try {
      await axios.post(`${BASE_URL}/inventory/admin/npc/${npcId}/equip`, {
        slot_type: slotType,
        item_id: itemId,
      });
      toast.success('Предмет экипирован');
      closePicker();
      await fetchEquipment();
    } catch (err) {
      let message = 'Не удалось экипировать предмет';
      if (axios.isAxiosError(err) && err.response?.data?.detail) {
        const detail = err.response.data.detail;
        if (typeof detail === 'string') message = detail;
      }
      toast.error(message);
    } finally {
      setActionLoading(null);
    }
  };

  /* ── Unequip item ── */

  const handleUnequip = async (slotType: string) => {
    setActionLoading(slotType);
    try {
      await axios.delete(`${BASE_URL}/inventory/admin/npc/${npcId}/unequip/${slotType}`);
      toast.success('Предмет снят');
      await fetchEquipment();
    } catch (err) {
      let message = 'Не удалось снять предмет';
      if (axios.isAxiosError(err) && err.response?.data?.detail) {
        const detail = err.response.data.detail;
        if (typeof detail === 'string') message = detail;
      }
      toast.error(message);
    } finally {
      setActionLoading(null);
    }
  };

  /* ── Helpers ── */

  const getSlotData = (slotType: string): EquipmentSlotData | undefined =>
    slots.find((s) => s.slot_type === slotType);

  const filteredPickerItems = debouncedSearch
    ? pickerItems.filter((item) =>
        item.name.toLowerCase().includes(debouncedSearch.toLowerCase()),
      )
    : pickerItems;

  const formatModifiers = (item: ItemData): string => {
    const mods: string[] = [];
    if (item.damage_modifier) mods.push(`Урон: +${item.damage_modifier}`);
    if (item.strength_modifier) mods.push(`Сила: +${item.strength_modifier}`);
    if (item.agility_modifier) mods.push(`Ловкость: +${item.agility_modifier}`);
    if (item.intelligence_modifier) mods.push(`Интеллект: +${item.intelligence_modifier}`);
    if (item.endurance_modifier) mods.push(`Выносливость: +${item.endurance_modifier}`);
    return mods.length > 0 ? mods.join(', ') : '';
  };

  /* ── Render ── */

  return (
    <div className="gray-bg p-4 sm:p-6 flex flex-col gap-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase tracking-[0.06em]">
          Экипировка: {npcName}
        </h2>
        <button onClick={onClose} className="btn-line !w-auto !px-6">
          Назад
        </button>
      </div>

      {/* Loading */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        </div>
      ) : (
        <>
          {/* Equipment Slots Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {NPC_SLOT_TYPES.map((slotType) => {
              const slotData = getSlotData(slotType);
              const item = slotData?.item ?? null;
              const isLoading = actionLoading === slotType;

              return (
                <div
                  key={slotType}
                  className="flex items-center gap-3 bg-white/[0.03] rounded-card p-3 sm:p-4"
                >
                  {/* Slot label */}
                  <div className="w-[110px] sm:w-[130px] shrink-0">
                    <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                      {SLOT_LABELS[slotType]}
                    </span>
                  </div>

                  {/* Item info */}
                  <div className="flex-1 min-w-0">
                    {item ? (
                      <div className="flex flex-col gap-0.5">
                        <span
                          className={`text-sm font-medium truncate ${RARITY_COLORS[item.item_rarity] ?? 'text-white'}`}
                        >
                          {item.name}
                        </span>
                        <span className="text-white/30 text-xs">
                          {RARITY_LABELS[item.item_rarity] ?? item.item_rarity}
                          {item.item_level ? ` | Ур. ${item.item_level}` : ''}
                        </span>
                      </div>
                    ) : (
                      <span className="text-white/20 text-sm">Пусто</span>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 shrink-0">
                    {isLoading ? (
                      <div className="w-5 h-5 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
                    ) : (
                      <>
                        <button
                          onClick={() => openPicker(slotType)}
                          className="text-xs text-site-blue hover:text-white transition-colors duration-200"
                        >
                          {item ? 'Заменить' : 'Надеть'}
                        </button>
                        {item && (
                          <button
                            onClick={() => handleUnequip(slotType)}
                            className="text-xs text-site-red hover:text-white transition-colors duration-200"
                          >
                            Снять
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Slots not found hint */}
          {slots.length === 0 && !loading && (
            <p className="text-white/30 text-sm text-center py-4">
              Слоты экипировки будут созданы автоматически при первом надевании предмета.
            </p>
          )}
        </>
      )}

      {/* Item Picker Modal */}
      {pickerSlot && (
        <div className="modal-overlay" onClick={closePicker}>
          <div
            className="modal-content gold-outline gold-outline-thick relative w-full max-w-[560px] max-h-[80vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Picker Header */}
            <div className="flex flex-col gap-3 mb-4">
              <h3 className="gold-text text-lg sm:text-xl font-medium uppercase tracking-[0.06em]">
                {SLOT_LABELS[pickerSlot]} — выбор предмета
              </h3>
              <input
                className="input-underline"
                placeholder="Поиск по названию..."
                value={pickerSearch}
                onChange={(e) => setPickerSearch(e.target.value)}
                autoFocus
              />
            </div>

            {/* Picker List */}
            <div className="gold-scrollbar overflow-y-auto flex-1 max-h-[50vh] flex flex-col gap-1">
              {pickerLoading ? (
                <div className="flex items-center justify-center py-8">
                  <div className="w-6 h-6 border-3 border-white/30 border-t-gold rounded-full animate-spin" />
                </div>
              ) : filteredPickerItems.length === 0 ? (
                <p className="text-white/30 text-sm text-center py-8">
                  {pickerItems.length === 0
                    ? 'Нет предметов для этого слота'
                    : 'Ничего не найдено'}
                </p>
              ) : (
                filteredPickerItems.map((item) => {
                  const mods = formatModifiers(item);
                  return (
                    <button
                      key={item.id}
                      onClick={() => handleEquip(pickerSlot, item.id)}
                      disabled={actionLoading === pickerSlot}
                      className="w-full text-left flex items-center gap-3 px-3 py-2.5 rounded-card hover:bg-white/[0.07] transition-colors duration-200 disabled:opacity-50"
                    >
                      {/* Item image */}
                      {item.image ? (
                        <img
                          src={item.image}
                          alt={item.name}
                          className="w-9 h-9 rounded object-cover shrink-0 border border-white/10"
                        />
                      ) : (
                        <div className="w-9 h-9 rounded bg-white/[0.05] shrink-0 flex items-center justify-center text-white/20 text-[10px]">
                          ?
                        </div>
                      )}

                      {/* Item details */}
                      <div className="flex-1 min-w-0">
                        <div
                          className={`text-sm font-medium truncate ${RARITY_COLORS[item.item_rarity] ?? 'text-white'}`}
                        >
                          {item.name}
                        </div>
                        <div className="text-white/30 text-xs truncate">
                          {RARITY_LABELS[item.item_rarity] ?? item.item_rarity}
                          {item.item_level ? ` | Ур. ${item.item_level}` : ''}
                          {mods ? ` | ${mods}` : ''}
                        </div>
                      </div>
                    </button>
                  );
                })
              )}
            </div>

            {/* Close button */}
            <div className="mt-4 flex justify-end">
              <button onClick={closePicker} className="btn-line !w-auto !px-6">
                Закрыть
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default NpcEquipmentEditor;
