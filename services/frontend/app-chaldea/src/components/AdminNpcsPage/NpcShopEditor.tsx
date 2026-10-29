import { useEffect, useMemo, useState, useCallback, type ReactNode } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../api/api';
import { apiErrorMessage } from '../../api/errors';
import { fetchEconomyGoodsGroups } from '../../api/economyAdmin';
import { merchantReasonText } from '../Admin/EconomyPage/economyLabels';
import type { EconMerchantReason } from '../../types/economy';
import useDebounce from '../../hooks/useDebounce';
import { useCurrency } from '../../hooks/useCurrency';
import { useAppSelector } from '../../redux/store';
import { selectPermissions } from '../../redux/slices/userSlice';
import { hasPermission } from '../../utils/permissions';
import { shownRarity } from '../../constants/items';

/* ── Types ── */

/** Row of `GET /locations/admin/npc-shop/{npc_id}/items` (FEAT-183, `NpcShopItemAdminRead`). */
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
  restock_target: number;
  origin: string;
  updated_at: string | null;
  group: string | null;
  off_market: boolean;
  market: boolean;
  ask: number | null;
  bid: number | null;
}


/** `GET /locations/admin/npc-shop/{npc_id}/market` (FEAT-183). */
interface MerchantMarket {
  npc_id: number;
  living: boolean;
  reason: EconMerchantReason | string | null;
  region_id: number | null;
  region_name: string | null;
  location_id: number | null;
  tax_rate: number | null;
  cash: number;
  buys_groups: { code: string; name: string }[];
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

/** Numeric fields are kept as strings so the admin can clear an input while typing. */
interface RowForm {
  buy_price: string;
  sell_price: string;
  stock: string; // '' = null (unlimited, legacy merchants only)
  restock_target: string;
}

interface ParsedRow {
  buy_price: number;
  sell_price: number;
  stock: number | null;
  restock_target: number;
}

/* ── Constants (mirror locations-service schemas, FEAT-183 3.7) ── */

const MAX_PRICE = 1_000_000_000;
const MAX_STOCK = 100_000;
const DEFAULT_RESTOCK_TARGET = 10;
const DEFAULT_BUY_PRICE = 100;
/** Prefill of the sell price = floor(price × 0.5) (3.8). */
const SELL_PREFILL_SHARE = 0.5;

const ORIGIN_PLAYER = 'player';

const INITIAL_ADD_FORM: RowForm = {
  buy_price: String(DEFAULT_BUY_PRICE),
  sell_price: String(Math.floor(DEFAULT_BUY_PRICE * SELL_PREFILL_SHARE)),
  stock: '',
  restock_target: String(DEFAULT_RESTOCK_TARGET),
};

const toForm = (si: ShopItem): RowForm => ({
  buy_price: String(si.buy_price),
  sell_price: String(si.sell_price),
  stock: si.stock === null ? '' : String(si.stock),
  restock_target: String(si.restock_target),
});

const parseIntIn = (raw: string, min: number, max: number): number | null => {
  const trimmed = raw.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const n = Number(trimmed);
  return n >= min && n <= max ? n : null;
};

const fmtInt = (n: number) => n.toLocaleString('ru-RU');

/** Client-side check of the backend bounds; returns a Russian error or the parsed row. */
const validateRow = (form: RowForm): { error: string } | { row: ParsedRow } => {
  const buy = parseIntIn(form.buy_price, 1, MAX_PRICE);
  if (buy === null) return { error: `Цена покупки — целое число от 1 до ${fmtInt(MAX_PRICE)}` };
  const sell = parseIntIn(form.sell_price, 0, MAX_PRICE);
  if (sell === null) return { error: `Цена продажи — целое число от 0 до ${fmtInt(MAX_PRICE)}` };
  let stock: number | null = null;
  if (form.stock.trim() !== '') {
    stock = parseIntIn(form.stock, 0, MAX_STOCK);
    if (stock === null) return { error: `Запас — пусто или целое число от 0 до ${fmtInt(MAX_STOCK)}` };
  }
  const restock = parseIntIn(form.restock_target, 0, MAX_STOCK);
  if (restock === null) return { error: `Норма склада — целое число от 0 до ${fmtInt(MAX_STOCK)}` };
  return { row: { buy_price: buy, sell_price: sell, stock, restock_target: restock } };
};

/** Backend 422 messages are English (pydantic) — replace them with our own Russian text. */
const saveErrorMessage = (err: unknown, fallback: string): string => {
  if (axios.isAxiosError(err) && err.response?.status === 422) {
    return `Сервер отклонил значения: цены от 1 (продажа от 0) до ${fmtInt(MAX_PRICE)}, запас и норма склада от 0 до ${fmtInt(MAX_STOCK)}`;
  }
  return apiErrorMessage(err, fallback);
};

/* ── Small presentational pieces ── */

const LABEL_CLS = 'text-white/50 text-xs font-medium uppercase tracking-[0.06em]';
const CELL_INPUT_CLS =
  'w-full min-w-0 bg-black/30 border border-white/20 rounded px-2 py-1 text-white text-sm focus:border-gold/50 outline-none';

const Badge = ({ children, tone, title }: { children: ReactNode; tone: 'gray' | 'amber' | 'blue'; title?: string }) => {
  const toneCls = {
    gray: 'border-white/15 text-white/50',
    amber: 'border-amber-400/40 text-amber-300',
    blue: 'border-site-blue/40 text-site-blue',
  }[tone];
  return (
    <span title={title} className={`inline-block text-[10px] leading-4 px-1.5 rounded-full border whitespace-nowrap ${toneCls}`}>
      {children}
    </span>
  );
};

const StatusPill = ({ active }: { active: boolean }) => (
  <span className={`text-[10px] sm:text-xs px-2 py-0.5 rounded-full whitespace-nowrap ${active ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'}`}>
    {active ? 'Активен' : 'Неактивен'}
  </span>
);

/* ── Component ── */

const NpcShopEditor = ({ npcId, npcName, onClose }: NpcShopEditorProps) => {
  const { format } = useCurrency();
  const permissions = useAppSelector(selectPermissions);
  const canReadEconomy = hasPermission(permissions, 'economy:read');

  const [shopItems, setShopItems] = useState<ShopItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [market, setMarket] = useState<MerchantMarket | null>(null);
  const [marketError, setMarketError] = useState<string | null>(null);
  const [groupNames, setGroupNames] = useState<Record<string, string>>({});

  const [addFormOpen, setAddFormOpen] = useState(false);
  const [addForm, setAddForm] = useState<RowForm>(INITIAL_ADD_FORM);
  const [saving, setSaving] = useState(false);

  // Item search
  const [itemSearch, setItemSearch] = useState('');
  const debouncedSearch = useDebounce(itemSearch);
  const [searchResults, setSearchResults] = useState<GameItem[]>([]);
  const [selectedItem, setSelectedItem] = useState<GameItem | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);

  // Editing
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<RowForm>(INITIAL_ADD_FORM);
  const [editActive, setEditActive] = useState(true);

  const fetchShopItems = useCallback(async () => {
    try {
      const res = await axios.get<ShopItem[]>(`${BASE_URL}/locations/admin/npc-shop/${npcId}/items`);
      setShopItems(res.data);
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Не удалось загрузить товары магазина'));
    }
  }, [npcId]);

  const fetchMarket = useCallback(async () => {
    try {
      const res = await axios.get<MerchantMarket>(`${BASE_URL}/locations/admin/npc-shop/${npcId}/market`);
      setMarket(res.data);
      setMarketError(null);
    } catch (err) {
      const msg = apiErrorMessage(err, 'Не удалось загрузить состояние торговца');
      setMarketError(msg);
      toast.error(msg);
    }
  }, [npcId]);

  /** Rows and the market header change together (buys_groups depends on the rows). */
  const reloadAll = useCallback(async () => {
    await Promise.all([fetchShopItems(), fetchMarket()]);
  }, [fetchShopItems, fetchMarket]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    reloadAll().finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [reloadAll]);

  // Goods group names for row badges — the dictionary lives in the economy admin (economy:read).
  useEffect(() => {
    if (!canReadEconomy) return;
    let cancelled = false;
    fetchEconomyGoodsGroups()
      .then((groups) => {
        if (!cancelled) setGroupNames(Object.fromEntries(groups.map((g) => [g.code, g.name])));
      })
      .catch((err) => {
        if (!cancelled) toast.error(apiErrorMessage(err, 'Не удалось загрузить названия групп товаров'));
      });
    return () => {
      cancelled = true;
    };
  }, [canReadEconomy]);

  const groupLabel = useMemo(() => {
    const names: Record<string, string> = { ...groupNames };
    market?.buys_groups.forEach((g) => {
      names[g.code] = g.name;
    });
    return (code: string) => names[code] ?? code;
  }, [groupNames, market]);

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
      } catch (err) {
        toast.error(apiErrorMessage(err, 'Не удалось найти предметы'));
      } finally {
        setSearchLoading(false);
      }
    };
    search();
  }, [debouncedSearch]);

  const handleSelectItem = (item: GameItem) => {
    const price = Math.min(Math.max(item.price || DEFAULT_BUY_PRICE, 1), MAX_PRICE);
    setSelectedItem(item);
    setAddForm((prev) => ({
      ...prev,
      buy_price: String(price),
      sell_price: String(Math.floor(price * SELL_PREFILL_SHARE)),
    }));
    setItemSearch('');
    setSearchResults([]);
  };

  const openAddForm = () => {
    setAddFormOpen(true);
    setSelectedItem(null);
    setAddForm(INITIAL_ADD_FORM);
  };

  const handleAddItem = async () => {
    if (!selectedItem) {
      toast.error('Выберите предмет');
      return;
    }
    const checked = validateRow(addForm);
    if ('error' in checked) {
      toast.error(checked.error);
      return;
    }
    setSaving(true);
    try {
      await axios.post(`${BASE_URL}/locations/admin/npc-shop/${npcId}/items`, {
        item_id: selectedItem.id,
        ...checked.row,
      });
      toast.success('Товар добавлен в магазин');
      setAddFormOpen(false);
      setAddForm(INITIAL_ADD_FORM);
      setSelectedItem(null);
      reloadAll();
    } catch (err) {
      // 409 «Этот предмет уже есть в магазине» comes as a Russian `detail`.
      toast.error(saveErrorMessage(err, 'Не удалось добавить товар'));
    } finally {
      setSaving(false);
    }
  };

  const handleStartEdit = (si: ShopItem) => {
    setEditingId(si.id);
    setEditForm(toForm(si));
    setEditActive(si.is_active);
  };

  const handleSaveEdit = async () => {
    if (editingId === null) return;
    const checked = validateRow(editForm);
    if ('error' in checked) {
      toast.error(checked.error);
      return;
    }
    setSaving(true);
    try {
      await axios.put(`${BASE_URL}/locations/admin/npc-shop/items/${editingId}`, {
        ...checked.row,
        is_active: editActive,
      });
      toast.success('Товар обновлён');
      setEditingId(null);
      reloadAll();
    } catch (err) {
      toast.error(saveErrorMessage(err, 'Не удалось обновить товар'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Удалить товар из магазина?')) return;
    try {
      await axios.delete(`${BASE_URL}/locations/admin/npc-shop/items/${id}`);
      toast.success('Товар удалён из магазина');
      if (editingId === id) setEditingId(null);
      reloadAll();
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Не удалось удалить товар'));
    }
  };

  const living = market?.living ?? false;

  const stockText = (stock: number | null) => {
    if (stock !== null) return fmtInt(stock);
    // NULL = unlimited only for a legacy merchant; a living one treats it as 0 (docs «Торговцы НПС»).
    return living ? '0 (не задан)' : 'без лимита';
  };

  /* ── Row pieces ── */

  const rowBadges = (si: ShopItem) => (
    <div className="flex flex-wrap gap-1">
      {si.off_market ? (
        <Badge tone="gray" title="Предмет не относится ни к одной группе товаров — цена не зависит от рынка">
          вне рынка
        </Badge>
      ) : si.group ? (
        <Badge tone="blue" title="Группа товаров">{groupLabel(si.group)}</Badge>
      ) : null}
      {si.origin === ORIGIN_PLAYER && (
        <Badge tone="amber" title="Скуплено у игроков — только перепродаётся, не докупается">
          скуплено у игроков
        </Badge>
      )}
    </div>
  );

  const priceCell = (base: number, current: number | null, si: ShopItem, isSell: boolean) => {
    if (isSell && base === 0) return <span className="text-white/40">не покупает</span>;
    const showCurrent = si.market && current !== null;
    return (
      <div className="flex flex-col">
        <span className={isSell ? 'text-white/70' : 'text-gold'}>{format(base, true)}</span>
        {showCurrent && (
          <span className="text-white/45 text-[11px] whitespace-nowrap">
            сейчас: <span className="text-white/80">{current === 0 ? '—' : format(current, true)}</span>
          </span>
        )}
      </div>
    );
  };

  const itemCell = (si: ShopItem, imgCls: string) => (
    <div className="flex items-center gap-2 min-w-0">
      {si.item_image && <img src={si.item_image} alt="" className={`${imgCls} rounded object-contain shrink-0`} />}
      <div className="flex flex-col gap-0.5 min-w-0">
        <span className="text-white text-sm truncate">{si.item_name ?? `#${si.item_id}`}</span>
        {shownRarity(si.item_type, si.item_rarity) && (
          <span className="text-white/40 text-[10px]">{si.item_rarity}</span>
        )}
        {rowBadges(si)}
      </div>
    </div>
  );

  const editFields = (labelCls: string) => (
    <>
      <label className="flex flex-col gap-0.5">
        <span className={labelCls}>Покупка</span>
        <input
          type="number"
          inputMode="numeric"
          min={1}
          max={MAX_PRICE}
          value={editForm.buy_price}
          onChange={(e) => setEditForm((p) => ({ ...p, buy_price: e.target.value }))}
          className={CELL_INPUT_CLS}
        />
      </label>
      <label className="flex flex-col gap-0.5">
        <span className={labelCls}>Продажа</span>
        <input
          type="number"
          inputMode="numeric"
          min={0}
          max={MAX_PRICE}
          value={editForm.sell_price}
          onChange={(e) => setEditForm((p) => ({ ...p, sell_price: e.target.value }))}
          className={CELL_INPUT_CLS}
        />
      </label>
      <label className="flex flex-col gap-0.5">
        <span className={labelCls}>Запас</span>
        <input
          type="number"
          inputMode="numeric"
          min={0}
          max={MAX_STOCK}
          value={editForm.stock}
          onChange={(e) => setEditForm((p) => ({ ...p, stock: e.target.value }))}
          placeholder={living ? '0' : 'Безлимит'}
          className={CELL_INPUT_CLS}
        />
      </label>
      <label className="flex flex-col gap-0.5">
        <span className={labelCls}>Норма склада</span>
        <input
          type="number"
          inputMode="numeric"
          min={0}
          max={MAX_STOCK}
          value={editForm.restock_target}
          onChange={(e) => setEditForm((p) => ({ ...p, restock_target: e.target.value }))}
          className={CELL_INPUT_CLS}
        />
      </label>
    </>
  );

  const actionButtons = (si: ShopItem, editing: boolean, alignEnd: boolean) => (
    <div className={`flex gap-3 ${alignEnd ? 'flex-col items-end gap-1' : 'flex-wrap'}`}>
      {editing ? (
        <>
          <button onClick={handleSaveEdit} disabled={saving} className="text-sm text-green-400 hover:text-green-300 transition-colors disabled:opacity-50">
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
          <button onClick={() => setEditingId(null)} className="text-sm text-white/50 hover:text-white transition-colors">
            Отмена
          </button>
        </>
      ) : (
        <>
          <button onClick={() => handleStartEdit(si)} className="text-sm text-white hover:text-site-blue transition-colors">
            Редактировать
          </button>
          <button onClick={() => handleDelete(si.id)} className="text-sm text-site-red hover:text-white transition-colors">
            Удалить
          </button>
        </>
      )}
    </div>
  );

  const editActiveToggle = (
    <button
      onClick={() => setEditActive((v) => !v)}
      className={`text-xs px-2 py-0.5 rounded-full whitespace-nowrap ${editActive ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'}`}
    >
      {editActive ? 'Активен' : 'Неактивен'}
    </button>
  );

  /* ── Market header ── */

  const marketHeader = () => {
    if (marketError && !market) {
      return <p className="text-site-red text-sm">{marketError}</p>;
    }
    if (!market) return null;
    const regionText = market.region_name ?? (market.region_id !== null ? `#${market.region_id}` : null);
    return (
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {market.living ? (
            <span className="text-xs px-2 py-0.5 rounded-full bg-green-900/40 text-green-400">Живой рынок</span>
          ) : market.reason === 'dead' ? (
            <span className="text-xs px-2 py-0.5 rounded-full bg-site-red/20 text-site-red">Лавка закрыта</span>
          ) : (
            <span className="text-xs px-2 py-0.5 rounded-full bg-white/10 text-white/60">Обычный магазин</span>
          )}
          <span className="text-white text-sm break-words">
            {market.living
              ? `Торгует в экономике региона «${regionText ?? '—'}»: цены по рынку региона, своя касса, склад пополняется при пересчёте региона`
              : market.reason === 'dead'
                ? 'НПС мёртв: игроки не могут у него покупать и продавать, пока он не оживёт'
                : `Цены и запас — как задано ниже. Причина: ${merchantReasonText(market.reason)}${regionText ? ` (регион «${regionText}»)` : ''}`}
          </span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
          <div className="flex flex-col gap-0.5">
            <span className={LABEL_CLS}>Касса торговца</span>
            <span className="text-gold">{format(market.cash)}</span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className={LABEL_CLS}>Налог региона</span>
            <span className="text-white/80">
              {market.tax_rate === null ? '—' : `${Math.round(market.tax_rate * 10000) / 100}%`}
            </span>
          </div>
          {market.living && (
            <div className="flex flex-col gap-0.5 min-w-0">
              <span className={LABEL_CLS}>Скупает у игроков группы</span>
              <span className="text-white/80 break-words">
                {market.buys_groups.length > 0
                  ? market.buys_groups.map((g) => g.name).join(', ')
                  : 'только товары из списка'}
              </span>
            </div>
          )}
        </div>
      </div>
    );
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
        <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase tracking-[0.06em] break-words">
          Магазин: {npcName}
        </h2>
        <button onClick={openAddForm} className="btn-blue !text-sm !px-5 !py-1.5 sm:ml-auto">
          Добавить товар
        </button>
      </div>

      {/* Market state */}
      {!loading && <div className="gray-bg p-4 sm:p-6">{marketHeader()}</div>}

      {/* Add form */}
      {addFormOpen && (
        <div className="gray-bg p-4 sm:p-6 flex flex-col gap-4">
          <h3 className="gold-text text-lg font-medium uppercase">Добавить товар</h3>

          {/* Item search */}
          <div className="relative">
            <label className="flex flex-col gap-1">
              <span className={LABEL_CLS}>Поиск предмета</span>
              <input
                value={itemSearch}
                onChange={(e) => setItemSearch(e.target.value)}
                placeholder="Введите название предмета..."
                className="input-underline"
              />
            </label>

            {searchResults.length > 0 && (
              <div className="absolute top-full left-0 right-0 z-20 mt-1 dropdown-menu max-h-60 overflow-y-auto gold-scrollbar">
                {searchResults.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => handleSelectItem(item)}
                    className="dropdown-item w-full text-left flex items-center gap-2"
                  >
                    {item.image && <img src={item.image} alt="" className="w-6 h-6 rounded object-contain" />}
                    <span className="truncate">{item.name}</span>
                    <span className="text-white/40 text-xs ml-auto shrink-0">{shownRarity(item.item_type, item.item_rarity)}</span>
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

          {selectedItem && (
            <div className="flex items-center gap-3 bg-white/[0.05] rounded-card p-3">
              {selectedItem.image && <img src={selectedItem.image} alt="" className="w-10 h-10 rounded object-contain" />}
              <div className="flex flex-col min-w-0">
                <span className="text-white text-sm font-medium truncate">{selectedItem.name}</span>
                <span className="text-white/40 text-xs">
                  ID: {selectedItem.id}
                  {shownRarity(selectedItem.item_type, selectedItem.item_rarity) ? ` | ${selectedItem.item_rarity}` : ''} | {selectedItem.item_type}
                </span>
              </div>
            </div>
          )}

          {/* Price / stock fields */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <label className="flex flex-col gap-1">
              <span className={LABEL_CLS}>Цена покупки (база)</span>
              <input
                type="number"
                inputMode="numeric"
                value={addForm.buy_price}
                onChange={(e) => setAddForm((p) => ({ ...p, buy_price: e.target.value }))}
                min={1}
                max={MAX_PRICE}
                className="input-underline"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className={LABEL_CLS}>Цена продажи (0 = не покупает)</span>
              <input
                type="number"
                inputMode="numeric"
                value={addForm.sell_price}
                onChange={(e) => setAddForm((p) => ({ ...p, sell_price: e.target.value }))}
                min={0}
                max={MAX_PRICE}
                className="input-underline"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className={LABEL_CLS}>{living ? 'Запас (пусто = 0)' : 'Запас (пусто = безлимит)'}</span>
              <input
                type="number"
                inputMode="numeric"
                value={addForm.stock}
                onChange={(e) => setAddForm((p) => ({ ...p, stock: e.target.value }))}
                min={0}
                max={MAX_STOCK}
                placeholder={living ? '0' : 'Безлимит'}
                className="input-underline"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className={LABEL_CLS}>Норма склада</span>
              <input
                type="number"
                inputMode="numeric"
                value={addForm.restock_target}
                onChange={(e) => setAddForm((p) => ({ ...p, restock_target: e.target.value }))}
                min={0}
                max={MAX_STOCK}
                className="input-underline"
              />
            </label>
          </div>
          <p className="text-white/40 text-xs">
            Цены — базовые (при множителе региона 1). У живого торговца итоговая цена зависит от рынка региона, а склад
            пополняется до нормы при пересчёте региона.
          </p>

          <div className="flex flex-col sm:flex-row gap-3 pt-2">
            <button
              onClick={handleAddItem}
              disabled={saving || !selectedItem}
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

      {/* Shop items */}
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
            <div className="hidden md:block overflow-x-auto gold-scrollbar">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    {['Предмет', 'Покупка', 'Продажа', 'Запас', 'Норма склада', 'Статус'].map((h) => (
                      <th key={h} className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-3 py-3 whitespace-nowrap">
                        {h}
                      </th>
                    ))}
                    <th className="text-right text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-3 py-3">Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {shopItems.map((si) => {
                    const editing = editingId === si.id;
                    return (
                      <tr key={si.id} className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200 align-top">
                        <td className="px-3 py-3 max-w-[260px]">{itemCell(si, 'w-8 h-8')}</td>
                        {editing ? (
                          <>
                            <td colSpan={4} className="px-3 py-3">
                              <div className="grid grid-cols-4 gap-2">{editFields('text-white/40 text-[10px]')}</div>
                            </td>
                            <td className="px-3 py-3">{editActiveToggle}</td>
                          </>
                        ) : (
                          <>
                            <td className="px-3 py-3 text-sm">{priceCell(si.buy_price, si.ask, si, false)}</td>
                            <td className="px-3 py-3 text-sm">{priceCell(si.sell_price, si.bid, si, true)}</td>
                            <td className="px-3 py-3 text-sm text-white/70 whitespace-nowrap">{stockText(si.stock)}</td>
                            <td className="px-3 py-3 text-sm text-white/70">{fmtInt(si.restock_target)}</td>
                            <td className="px-3 py-3"><StatusPill active={si.is_active} /></td>
                          </>
                        )}
                        <td className="px-3 py-3">{actionButtons(si, editing, true)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="md:hidden flex flex-col gap-3 p-3">
              {shopItems.map((si) => {
                const editing = editingId === si.id;
                return (
                  <div key={si.id} className="bg-white/[0.03] rounded-card p-4 flex flex-col gap-3">
                    <div className="flex items-start gap-3">
                      <div className="flex-1 min-w-0">{itemCell(si, 'w-10 h-10')}</div>
                      {editing ? editActiveToggle : <StatusPill active={si.is_active} />}
                    </div>

                    {editing ? (
                      <div className="grid grid-cols-2 gap-2">{editFields('text-white/40 text-[10px]')}</div>
                    ) : (
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div className="flex flex-col gap-0.5">
                          <span className="text-white/40">Покупка</span>
                          {priceCell(si.buy_price, si.ask, si, false)}
                        </div>
                        <div className="flex flex-col gap-0.5">
                          <span className="text-white/40">Продажа</span>
                          {priceCell(si.sell_price, si.bid, si, true)}
                        </div>
                        <div className="flex flex-col gap-0.5">
                          <span className="text-white/40">Запас</span>
                          <span className="text-white/70">{stockText(si.stock)}</span>
                        </div>
                        <div className="flex flex-col gap-0.5">
                          <span className="text-white/40">Норма склада</span>
                          <span className="text-white/70">{fmtInt(si.restock_target)}</span>
                        </div>
                      </div>
                    )}
                    {actionButtons(si, editing, false)}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default NpcShopEditor;
