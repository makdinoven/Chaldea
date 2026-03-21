import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../api/api';
import useDebounce from '../../hooks/useDebounce';

/* ── Types ── */

interface ShopItem {
  id: number;
  npc_id: number;
  item_id: number;
  buy_price: number;
  sell_price: number;
  stock: number | null;
  is_active: boolean;
  item_name: string | null;
  item_image: string | null;
  item_rarity: string | null;
  item_type: string | null;
}

interface GameItem {
  id: number;
  name: string;
  image: string | null;
  item_rarity: string;
  item_type: string;
  price: number;
}

interface NpcShopEditorProps {
  npcId: number;
  npcName: string;
  onClose: () => void;
}

interface AddFormData {
  item_id: number | null;
  buy_price: number;
  sell_price: number;
  stock: number | null;
}

const INITIAL_ADD_FORM: AddFormData = {
  item_id: null,
  buy_price: 100,
  sell_price: 50,
  stock: null,
};

/* ── Component ── */

const NpcShopEditor = ({ npcId, npcName, onClose }: NpcShopEditorProps) => {
  const [shopItems, setShopItems] = useState<ShopItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [addFormOpen, setAddFormOpen] = useState(false);
  const [addForm, setAddForm] = useState<AddFormData>(INITIAL_ADD_FORM);
  const [saving, setSaving] = useState(false);

  // Item search
  const [itemSearch, setItemSearch] = useState('');
  const debouncedSearch = useDebounce(itemSearch);
  const [searchResults, setSearchResults] = useState<GameItem[]>([]);
  const [selectedItem, setSelectedItem] = useState<GameItem | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);

  // Editing
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<{ buy_price: number; sell_price: number; stock: number | null; is_active: boolean }>({
    buy_price: 0, sell_price: 0, stock: null, is_active: true,
  });

  const fetchShopItems = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get<ShopItem[]>(`${BASE_URL}/locations/admin/npc-shop/${npcId}/items`);
      setShopItems(res.data);
    } catch {
      toast.error('Не удалось загрузить товары магазина');
    } finally {
      setLoading(false);
    }
  }, [npcId]);

  useEffect(() => {
    fetchShopItems();
  }, [fetchShopItems]);

  // Search items
  useEffect(() => {
    if (!debouncedSearch || debouncedSearch.length < 2) {
      setSearchResults([]);
      return;
    }
    const search = async () => {
      setSearchLoading(true);
      try {
        const res = await axios.get<GameItem[]>(`${BASE_URL}/inventory/items`, {
          params: { q: debouncedSearch, page_size: 20 },
        });
        setSearchResults(res.data);
      } catch {
        toast.error('Не удалось найти предметы');
      } finally {
        setSearchLoading(false);
      }
    };
    search();
  }, [debouncedSearch]);

  const handleSelectItem = (item: GameItem) => {
    setSelectedItem(item);
    setAddForm((prev) => ({
      ...prev,
      item_id: item.id,
      buy_price: item.price || 100,
      sell_price: Math.floor((item.price || 100) * 0.5),
    }));
    setItemSearch('');
    setSearchResults([]);
  };

  const handleAddItem = async () => {
    if (!addForm.item_id) {
      toast.error('Выберите предмет');
      return;
    }
    setSaving(true);
    try {
      await axios.post(`${BASE_URL}/locations/admin/npc-shop/${npcId}/items`, {
        item_id: addForm.item_id,
        buy_price: addForm.buy_price,
        sell_price: addForm.sell_price,
        stock: addForm.stock,
      });
      toast.success('Товар добавлен в магазин');
      setAddFormOpen(false);
      setAddForm(INITIAL_ADD_FORM);
      setSelectedItem(null);
      fetchShopItems();
    } catch (err) {
      const msg = axios.isAxiosError(err) && err.response?.data?.detail
        ? err.response.data.detail
        : 'Не удалось добавить товар';
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleStartEdit = (si: ShopItem) => {
    setEditingId(si.id);
    setEditForm({
      buy_price: si.buy_price,
      sell_price: si.sell_price,
      stock: si.stock,
      is_active: si.is_active,
    });
  };

  const handleSaveEdit = async () => {
    if (editingId === null) return;
    setSaving(true);
    try {
      await axios.put(`${BASE_URL}/locations/admin/npc-shop/items/${editingId}`, editForm);
      toast.success('Товар обновлён');
      setEditingId(null);
      fetchShopItems();
    } catch (err) {
      const msg = axios.isAxiosError(err) && err.response?.data?.detail
        ? err.response.data.detail
        : 'Не удалось обновить товар';
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Удалить товар из магазина?')) return;
    try {
      await axios.delete(`${BASE_URL}/locations/admin/npc-shop/items/${id}`);
      toast.success('Товар удалён из магазина');
      setShopItems((prev) => prev.filter((i) => i.id !== id));
      if (editingId === id) setEditingId(null);
    } catch {
      toast.error('Не удалось удалить товар');
    }
  };

  return (
    <div className="w-full flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        <button
          onClick={onClose}
          className="text-sm text-white/50 hover:text-white transition-colors flex items-center gap-1"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          Назад к НПС
        </button>
        <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase tracking-[0.06em]">
          Магазин: {npcName}
        </h2>
        <button
          onClick={() => { setAddFormOpen(true); setSelectedItem(null); setAddForm(INITIAL_ADD_FORM); }}
          className="btn-blue !text-sm !px-5 !py-1.5 sm:ml-auto"
        >
          Добавить товар
        </button>
      </div>

      {/* Add form */}
      {addFormOpen && (
        <div className="gray-bg p-4 sm:p-6 flex flex-col gap-4">
          <h3 className="gold-text text-lg font-medium uppercase">Добавить товар</h3>

          {/* Item search */}
          <div className="relative">
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Поиск предмета</span>
              <input
                value={itemSearch}
                onChange={(e) => setItemSearch(e.target.value)}
                placeholder="Введите название предмета..."
                className="input-underline"
              />
            </label>

            {/* Search results dropdown */}
            {searchResults.length > 0 && (
              <div className="absolute top-full left-0 right-0 z-20 mt-1 dropdown-menu max-h-60 overflow-y-auto gold-scrollbar">
                {searchResults.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => handleSelectItem(item)}
                    className="dropdown-item w-full text-left flex items-center gap-2"
                  >
                    {item.image && (
                      <img src={item.image} alt="" className="w-6 h-6 rounded object-contain" />
                    )}
                    <span className="truncate">{item.name}</span>
                    <span className="text-white/40 text-xs ml-auto shrink-0">{item.item_rarity}</span>
                  </button>
                ))}
              </div>
            )}
            {searchLoading && (
              <div className="absolute top-full left-0 right-0 z-20 mt-1 dropdown-menu p-4 text-center">
                <div className="w-5 h-5 border-2 border-white/30 border-t-gold rounded-full animate-spin mx-auto" />
              </div>
            )}
          </div>

          {/* Selected item display */}
          {selectedItem && (
            <div className="flex items-center gap-3 bg-white/[0.05] rounded-card p-3">
              {selectedItem.image && (
                <img src={selectedItem.image} alt="" className="w-10 h-10 rounded object-contain" />
              )}
              <div className="flex flex-col min-w-0">
                <span className="text-white text-sm font-medium truncate">{selectedItem.name}</span>
                <span className="text-white/40 text-xs">ID: {selectedItem.id} | {selectedItem.item_rarity} | {selectedItem.item_type}</span>
              </div>
            </div>
          )}

          {/* Price fields */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Цена покупки</span>
              <input
                type="number"
                value={addForm.buy_price}
                onChange={(e) => setAddForm((p) => ({ ...p, buy_price: Number(e.target.value) || 0 }))}
                min={0}
                className="input-underline"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Цена продажи</span>
              <input
                type="number"
                value={addForm.sell_price}
                onChange={(e) => setAddForm((p) => ({ ...p, sell_price: Number(e.target.value) || 0 }))}
                min={0}
                className="input-underline"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Запас (пусто = безлимит)</span>
              <input
                type="number"
                value={addForm.stock ?? ''}
                onChange={(e) => setAddForm((p) => ({ ...p, stock: e.target.value === '' ? null : Number(e.target.value) }))}
                min={0}
                placeholder="Безлимит"
                className="input-underline"
              />
            </label>
          </div>

          <div className="flex flex-col sm:flex-row gap-3 pt-2">
            <button
              onClick={handleAddItem}
              disabled={saving || !addForm.item_id}
              className="btn-blue !text-sm !px-6 !py-2 disabled:opacity-50"
            >
              {saving ? 'Сохранение...' : 'Добавить'}
            </button>
            <button
              onClick={() => { setAddFormOpen(false); setSelectedItem(null); }}
              className="btn-line !w-auto !px-6"
            >
              Отмена
            </button>
          </div>
        </div>
      )}

      {/* Shop items table */}
      <div className="gray-bg overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
          </div>
        ) : shopItems.length === 0 ? (
          <p className="text-center text-white/50 text-sm py-8">Магазин пуст</p>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden sm:block">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Предмет</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Покупка</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Продажа</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Запас</th>
                    <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Статус</th>
                    <th className="text-right text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {shopItems.map((si) => (
                    <tr key={si.id} className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {si.item_image && (
                            <img src={si.item_image} alt="" className="w-8 h-8 rounded object-contain" />
                          )}
                          <div className="flex flex-col min-w-0">
                            <span className="text-white text-sm truncate">{si.item_name ?? `#${si.item_id}`}</span>
                            {si.item_rarity && (
                              <span className="text-white/40 text-[10px]">{si.item_rarity}</span>
                            )}
                          </div>
                        </div>
                      </td>
                      {editingId === si.id ? (
                        <>
                          <td className="px-4 py-3">
                            <input
                              type="number"
                              value={editForm.buy_price}
                              onChange={(e) => setEditForm((p) => ({ ...p, buy_price: Number(e.target.value) || 0 }))}
                              className="w-20 bg-black/30 border border-white/20 rounded px-2 py-1 text-white text-sm focus:border-gold/50 outline-none"
                            />
                          </td>
                          <td className="px-4 py-3">
                            <input
                              type="number"
                              value={editForm.sell_price}
                              onChange={(e) => setEditForm((p) => ({ ...p, sell_price: Number(e.target.value) || 0 }))}
                              className="w-20 bg-black/30 border border-white/20 rounded px-2 py-1 text-white text-sm focus:border-gold/50 outline-none"
                            />
                          </td>
                          <td className="px-4 py-3">
                            <input
                              type="number"
                              value={editForm.stock ?? ''}
                              onChange={(e) => setEditForm((p) => ({ ...p, stock: e.target.value === '' ? null : Number(e.target.value) }))}
                              placeholder="---"
                              className="w-20 bg-black/30 border border-white/20 rounded px-2 py-1 text-white text-sm focus:border-gold/50 outline-none"
                            />
                          </td>
                          <td className="px-4 py-3">
                            <button
                              onClick={() => setEditForm((p) => ({ ...p, is_active: !p.is_active }))}
                              className={`text-xs px-2 py-0.5 rounded-full ${editForm.is_active ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'}`}
                            >
                              {editForm.is_active ? 'Активен' : 'Неактивен'}
                            </button>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex flex-col items-end gap-1">
                              <button
                                onClick={handleSaveEdit}
                                disabled={saving}
                                className="text-sm text-green-400 hover:text-green-300 transition-colors"
                              >
                                Сохранить
                              </button>
                              <button
                                onClick={() => setEditingId(null)}
                                className="text-sm text-white/50 hover:text-white transition-colors"
                              >
                                Отмена
                              </button>
                            </div>
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="px-4 py-3 text-sm text-gold">{si.buy_price.toLocaleString()}</td>
                          <td className="px-4 py-3 text-sm text-white/70">{si.sell_price.toLocaleString()}</td>
                          <td className="px-4 py-3 text-sm text-white/70">{si.stock ?? '---'}</td>
                          <td className="px-4 py-3">
                            <span className={`text-xs px-2 py-0.5 rounded-full ${si.is_active ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'}`}>
                              {si.is_active ? 'Активен' : 'Неактивен'}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex flex-col items-end gap-1">
                              <button
                                onClick={() => handleStartEdit(si)}
                                className="text-sm text-white hover:text-site-blue transition-colors"
                              >
                                Редактировать
                              </button>
                              <button
                                onClick={() => handleDelete(si.id)}
                                className="text-sm text-site-red hover:text-white transition-colors"
                              >
                                Удалить
                              </button>
                            </div>
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="sm:hidden flex flex-col gap-3 p-3">
              {shopItems.map((si) => (
                <div key={si.id} className="bg-white/[0.03] rounded-card p-4 flex flex-col gap-3">
                  <div className="flex items-center gap-3">
                    {si.item_image && (
                      <img src={si.item_image} alt="" className="w-10 h-10 rounded object-contain shrink-0" />
                    )}
                    <div className="flex flex-col min-w-0 flex-1">
                      <span className="text-white text-sm font-medium truncate">
                        {si.item_name ?? `#${si.item_id}`}
                      </span>
                      {si.item_rarity && (
                        <span className="text-white/40 text-[10px]">{si.item_rarity}</span>
                      )}
                    </div>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full shrink-0 ${si.is_active ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'}`}>
                      {si.is_active ? 'Активен' : 'Неактивен'}
                    </span>
                  </div>

                  {editingId === si.id ? (
                    <div className="flex flex-col gap-2">
                      <div className="grid grid-cols-3 gap-2">
                        <label className="flex flex-col gap-0.5">
                          <span className="text-white/40 text-[10px]">Покупка</span>
                          <input
                            type="number"
                            value={editForm.buy_price}
                            onChange={(e) => setEditForm((p) => ({ ...p, buy_price: Number(e.target.value) || 0 }))}
                            className="bg-black/30 border border-white/20 rounded px-2 py-1 text-white text-xs focus:border-gold/50 outline-none"
                          />
                        </label>
                        <label className="flex flex-col gap-0.5">
                          <span className="text-white/40 text-[10px]">Продажа</span>
                          <input
                            type="number"
                            value={editForm.sell_price}
                            onChange={(e) => setEditForm((p) => ({ ...p, sell_price: Number(e.target.value) || 0 }))}
                            className="bg-black/30 border border-white/20 rounded px-2 py-1 text-white text-xs focus:border-gold/50 outline-none"
                          />
                        </label>
                        <label className="flex flex-col gap-0.5">
                          <span className="text-white/40 text-[10px]">Запас</span>
                          <input
                            type="number"
                            value={editForm.stock ?? ''}
                            onChange={(e) => setEditForm((p) => ({ ...p, stock: e.target.value === '' ? null : Number(e.target.value) }))}
                            placeholder="---"
                            className="bg-black/30 border border-white/20 rounded px-2 py-1 text-white text-xs focus:border-gold/50 outline-none"
                          />
                        </label>
                      </div>
                      <div className="flex gap-3">
                        <button
                          onClick={() => setEditForm((p) => ({ ...p, is_active: !p.is_active }))}
                          className={`text-xs px-2 py-0.5 rounded-full ${editForm.is_active ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'}`}
                        >
                          {editForm.is_active ? 'Активен' : 'Неактивен'}
                        </button>
                      </div>
                      <div className="flex gap-3">
                        <button onClick={handleSaveEdit} disabled={saving} className="text-sm text-green-400 hover:text-green-300 transition-colors">
                          Сохранить
                        </button>
                        <button onClick={() => setEditingId(null)} className="text-sm text-white/50 hover:text-white transition-colors">
                          Отмена
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="grid grid-cols-3 gap-2 text-xs">
                        <div className="flex flex-col gap-0.5">
                          <span className="text-white/40">Покупка</span>
                          <span className="text-gold">{si.buy_price.toLocaleString()}</span>
                        </div>
                        <div className="flex flex-col gap-0.5">
                          <span className="text-white/40">Продажа</span>
                          <span className="text-white/70">{si.sell_price.toLocaleString()}</span>
                        </div>
                        <div className="flex flex-col gap-0.5">
                          <span className="text-white/40">Запас</span>
                          <span className="text-white/70">{si.stock ?? '---'}</span>
                        </div>
                      </div>
                      <div className="flex gap-3">
                        <button onClick={() => handleStartEdit(si)} className="text-sm text-white hover:text-site-blue transition-colors">
                          Редактировать
                        </button>
                        <button onClick={() => handleDelete(si.id)} className="text-sm text-site-red hover:text-white transition-colors">
                          Удалить
                        </button>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default NpcShopEditor;
