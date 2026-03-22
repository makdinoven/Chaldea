import { useState, useEffect } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { updateMobLoot, selectMobsSaving } from '../../../redux/slices/mobsSlice';
import type { MobLootEntry } from '../../../api/mobs';
import useDebounce from '../../../hooks/useDebounce';

interface AdminMobLootProps {
  templateId: number;
  lootTable: MobLootEntry[];
  onUpdate: () => void;
}

interface ItemSearchResult {
  id: number;
  name: string;
  rarity?: string;
}

interface LootFormEntry {
  item_id: number;
  item_name: string;
  drop_chance: number;
  min_quantity: number;
  max_quantity: number;
}

const AdminMobLoot = ({ templateId, lootTable, onUpdate }: AdminMobLootProps) => {
  const dispatch = useAppDispatch();
  const saving = useAppSelector(selectMobsSaving);

  const [entries, setEntries] = useState<LootFormEntry[]>(
    lootTable.map((e) => ({
      item_id: e.item_id,
      item_name: e.item_name || `Предмет #${e.item_id}`,
      drop_chance: e.drop_chance,
      min_quantity: e.min_quantity,
      max_quantity: e.max_quantity,
    })),
  );

  // Item search
  const [searchQuery, setSearchQuery] = useState('');
  const debouncedQuery = useDebounce(searchQuery);
  const [searchResults, setSearchResults] = useState<ItemSearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  useEffect(() => {
    setEntries(
      lootTable.map((e) => ({
        item_id: e.item_id,
        item_name: e.item_name || `Предмет #${e.item_id}`,
        drop_chance: e.drop_chance,
        min_quantity: e.min_quantity,
        max_quantity: e.max_quantity,
      })),
    );
  }, [lootTable]);

  useEffect(() => {
    if (!debouncedQuery) {
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    axios.get('/inventory/items', { params: { q: debouncedQuery, page: 1, page_size: 20 } })
      .then((res) => {
        const data = res.data;
        const items = Array.isArray(data) ? data : data.items ?? [];
        setSearchResults(items);
      })
      .catch(() => toast.error('Не удалось найти предметы'))
      .finally(() => setSearchLoading(false));
  }, [debouncedQuery]);

  const handleAddItem = (item: ItemSearchResult) => {
    if (entries.some((e) => e.item_id === item.id)) {
      toast.error('Этот предмет уже добавлен');
      return;
    }
    setEntries((prev) => [
      ...prev,
      {
        item_id: item.id,
        item_name: item.name,
        drop_chance: 10,
        min_quantity: 1,
        max_quantity: 1,
      },
    ]);
    setSearchQuery('');
    setSearchResults([]);
  };

  const handleRemoveEntry = (itemId: number) => {
    setEntries((prev) => prev.filter((e) => e.item_id !== itemId));
  };

  const handleEntryChange = (
    itemId: number,
    field: 'drop_chance' | 'min_quantity' | 'max_quantity',
    value: string,
  ) => {
    setEntries((prev) =>
      prev.map((e) =>
        e.item_id === itemId
          ? { ...e, [field]: value === '' ? 0 : Number(value) }
          : e,
      ),
    );
  };

  const validate = (): boolean => {
    for (const entry of entries) {
      if (entry.drop_chance < 0 || entry.drop_chance > 100) {
        toast.error(`Шанс дропа для "${entry.item_name}" должен быть от 0 до 100`);
        return false;
      }
      if (entry.min_quantity < 1) {
        toast.error(`Минимальное количество для "${entry.item_name}" должно быть не менее 1`);
        return false;
      }
      if (entry.max_quantity < entry.min_quantity) {
        toast.error(`Максимальное количество для "${entry.item_name}" не может быть меньше минимального`);
        return false;
      }
    }
    return true;
  };

  const handleSave = async () => {
    if (!validate()) return;
    try {
      await dispatch(
        updateMobLoot({
          templateId,
          entries: entries.map((e) => ({
            item_id: e.item_id,
            drop_chance: e.drop_chance,
            min_quantity: e.min_quantity,
            max_quantity: e.max_quantity,
          })),
        }),
      ).unwrap();
      onUpdate();
    } catch {
      // Error already shown by thunk
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">
        Лут-таблица ({entries.length} предметов)
      </h3>

      {/* Current entries */}
      {entries.length > 0 && (
        <div className="flex flex-col gap-3">
          {entries.map((entry) => (
            <div
              key={entry.item_id}
              className="bg-white/[0.05] rounded-card p-3 sm:p-4 flex flex-col sm:flex-row sm:items-center gap-3"
            >
              <div className="flex-1 min-w-0">
                <span className="text-white text-sm font-medium truncate block">
                  {entry.item_name}
                </span>
                <span className="text-white/40 text-xs">ID: {entry.item_id}</span>
              </div>
              <div className="grid grid-cols-3 gap-2 sm:gap-3 sm:w-auto">
                <label className="flex flex-col gap-0.5">
                  <span className="text-white/50 text-[10px] uppercase">Шанс %</span>
                  <input
                    type="number"
                    value={entry.drop_chance}
                    onChange={(e) => handleEntryChange(entry.item_id, 'drop_chance', e.target.value)}
                    min={0}
                    max={100}
                    step={0.1}
                    className="input-underline !text-sm w-full"
                  />
                </label>
                <label className="flex flex-col gap-0.5">
                  <span className="text-white/50 text-[10px] uppercase">Мин</span>
                  <input
                    type="number"
                    value={entry.min_quantity}
                    onChange={(e) => handleEntryChange(entry.item_id, 'min_quantity', e.target.value)}
                    min={1}
                    className="input-underline !text-sm w-full"
                  />
                </label>
                <label className="flex flex-col gap-0.5">
                  <span className="text-white/50 text-[10px] uppercase">Макс</span>
                  <input
                    type="number"
                    value={entry.max_quantity}
                    onChange={(e) => handleEntryChange(entry.item_id, 'max_quantity', e.target.value)}
                    min={1}
                    className="input-underline !text-sm w-full"
                  />
                </label>
              </div>
              <button
                onClick={() => handleRemoveEntry(entry.item_id)}
                className="text-sm text-site-red hover:text-white transition-colors self-start sm:self-center"
              >
                Удалить
              </button>
            </div>
          ))}
        </div>
      )}

      {entries.length === 0 && (
        <p className="text-white/50 text-sm">Лут-таблица пуста. Добавьте предметы через поиск ниже.</p>
      )}

      {/* Item search */}
      <div>
        <h4 className="text-white/70 text-xs font-medium uppercase tracking-[0.06em] mb-2">
          Добавить предмет
        </h4>
        <input
          className="input-underline max-w-[320px] mb-2"
          placeholder="Поиск предмета..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        {searchLoading && (
          <div className="flex items-center gap-2 text-white/50 text-sm">
            <div className="w-4 h-4 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
            Поиск...
          </div>
        )}
        {searchResults.length > 0 && (
          <div className="flex flex-col gap-1 max-h-[200px] overflow-y-auto gold-scrollbar">
            {searchResults.map((item) => {
              const isAdded = entries.some((e) => e.item_id === item.id);
              return (
                <button
                  key={item.id}
                  onClick={() => handleAddItem(item)}
                  disabled={isAdded}
                  className={`flex items-center gap-2 px-3 py-2 rounded text-left transition-colors ${
                    isAdded
                      ? 'opacity-50 cursor-not-allowed'
                      : 'hover:bg-white/[0.07]'
                  }`}
                >
                  <span className="text-white text-sm">{item.name}</span>
                  <span className="text-white/40 text-xs">ID: {item.id}</span>
                  {isAdded && <span className="text-white/30 text-xs ml-auto">Добавлен</span>}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Save */}
      <div className="pt-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="btn-blue !text-base !px-8 !py-2 disabled:opacity-50"
        >
          {saving ? 'Сохранение...' : 'Сохранить лут-таблицу'}
        </button>
      </div>
    </div>
  );
};

export default AdminMobLoot;
