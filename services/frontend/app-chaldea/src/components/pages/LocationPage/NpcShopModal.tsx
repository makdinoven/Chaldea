import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useSelector, useDispatch } from 'react-redux';
import { BASE_URL } from '../../../api/api';
import { fetchInventory, fetchProfile, selectInventory, selectProfile } from '../../../redux/slices/profileSlice';
import type { InventoryItem } from '../../../redux/slices/profileSlice';
import type { AppDispatch, RootState } from '../../../redux/store';
import { ITEM_TYPE_ICONS } from '../../ProfilePage/constants';
import goldCoinsIcon from '../../../assets/icons/gold-coins.svg';

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

interface ShopTransactionResponse {
  success: boolean;
  message: string;
  new_balance: number | null;
  item_name: string | null;
  quantity: number;
  total_price: number;
}

interface NpcShopModalProps {
  npcId: number;
  npcName: string;
  npcAvatar: string | null;
  onClose: () => void;
}

type ShopTab = 'buy' | 'sell';

/* ── Helpers ── */

const getRarityClass = (rarity: string | null): string => {
  if (!rarity) return '';
  const map: Record<string, string> = {
    common: 'rarity-common',
    rare: 'rarity-rare',
    epic: 'rarity-epic',
    mythical: 'rarity-mythical',
    legendary: 'rarity-legendary',
  };
  return map[rarity] || '';
};

const getItemIcon = (type: string | null, image: string | null): string | null => {
  if (image) return image;
  if (type && ITEM_TYPE_ICONS[type]) return ITEM_TYPE_ICONS[type];
  return null;
};

/* ── Component ── */

const NpcShopModal = ({ npcId, npcName, npcAvatar, onClose }: NpcShopModalProps) => {
  const dispatch = useDispatch<AppDispatch>();
  const character = useSelector(selectProfile);
  const inventory = useSelector(selectInventory);
  const characterId = useSelector((s: RootState) => s.user.character?.id ?? null);

  const [tab, setTab] = useState<ShopTab>('buy');
  const [shopItems, setShopItems] = useState<ShopItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  const [sellQuantities, setSellQuantities] = useState<Record<number, number>>({});
  const [processing, setProcessing] = useState(false);

  const fetchShop = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get<ShopItem[]>(`${BASE_URL}/locations/npcs/${npcId}/shop`);
      setShopItems(res.data.filter((i) => i.is_active));
    } catch {
      toast.error('Не удалось загрузить товары магазина');
    } finally {
      setLoading(false);
    }
  }, [npcId]);

  useEffect(() => {
    fetchShop();
  }, [fetchShop]);

  // Load player inventory if not loaded
  useEffect(() => {
    if (characterId && inventory.length === 0) {
      dispatch(fetchInventory(characterId));
    }
    if (characterId && !character) {
      dispatch(fetchProfile(characterId));
    }
  }, [characterId, inventory.length, character, dispatch]);

  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose();
  };

  const getQuantity = (id: number): number => quantities[id] ?? 1;
  const getSellQuantity = (id: number): number => sellQuantities[id] ?? 1;

  const handleBuy = async (shopItem: ShopItem) => {
    if (!characterId || processing) return;
    const qty = getQuantity(shopItem.id);
    const totalPrice = shopItem.buy_price * qty;

    if (character && totalPrice > character.currency_balance) {
      toast.error('Недостаточно золота');
      return;
    }

    setProcessing(true);
    try {
      const res = await axios.post<ShopTransactionResponse>(
        `${BASE_URL}/locations/npcs/${npcId}/shop/buy`,
        { character_id: characterId, shop_item_id: shopItem.id, quantity: qty },
      );
      if (res.data.success) {
        toast.success(`Предмет куплен: ${res.data.item_name ?? shopItem.item_name} x${res.data.quantity}`);
        // Refresh data
        dispatch(fetchInventory(characterId));
        dispatch(fetchProfile(characterId));
        fetchShop();
        setQuantities((prev) => ({ ...prev, [shopItem.id]: 1 }));
      } else {
        toast.error(res.data.message || 'Ошибка покупки');
      }
    } catch (err) {
      const msg = axios.isAxiosError(err) && err.response?.data?.detail
        ? err.response.data.detail
        : 'Не удалось купить предмет';
      toast.error(msg);
    } finally {
      setProcessing(false);
    }
  };

  const handleSell = async (invItem: InventoryItem) => {
    if (!characterId || processing) return;
    const qty = getSellQuantity(invItem.item_id);

    setProcessing(true);
    try {
      const res = await axios.post<ShopTransactionResponse>(
        `${BASE_URL}/locations/npcs/${npcId}/shop/sell`,
        { character_id: characterId, item_id: invItem.item_id, quantity: qty },
      );
      if (res.data.success) {
        toast.success(`Предмет продан: ${res.data.item_name ?? invItem.item.name} x${res.data.quantity}`);
        dispatch(fetchInventory(characterId));
        dispatch(fetchProfile(characterId));
        setSellQuantities((prev) => ({ ...prev, [invItem.item_id]: 1 }));
      } else {
        toast.error(res.data.message || 'Ошибка продажи');
      }
    } catch (err) {
      const msg = axios.isAxiosError(err) && err.response?.data?.detail
        ? err.response.data.detail
        : 'Не удалось продать предмет';
      toast.error(msg);
    } finally {
      setProcessing(false);
    }
  };

  // Build sell price map from shop items
  const sellPriceMap = new Map<number, number>();
  shopItems.forEach((si) => {
    if (si.sell_price > 0) sellPriceMap.set(si.item_id, si.sell_price);
  });

  const sellableInventory = inventory.filter((inv) => sellPriceMap.has(inv.item_id));

  const balance = character?.currency_balance ?? 0;

  return (
    <div className="modal-overlay !bg-black/80" onClick={handleOverlayClick}>
      <div className="modal-content gold-outline gold-outline-thick relative max-w-2xl w-full mx-3 sm:mx-4 max-h-[90vh] flex flex-col overflow-hidden">
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

        {/* Header: NPC + Shop title + Balance */}
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
            <span className="text-white/50 text-xs uppercase tracking-wide">Торговля</span>
          </div>
          {/* Balance */}
          <div className="ml-auto flex items-center gap-1.5 bg-black/30 rounded-card px-3 py-1.5 shrink-0">
            <img src={goldCoinsIcon} alt="" className="w-5 h-5" />
            <span className="text-gold font-medium text-sm sm:text-base">{balance.toLocaleString()}</span>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-white/10 mb-4">
          <button
            onClick={() => setTab('buy')}
            className={`
              flex-1 pb-2 text-sm sm:text-base font-medium uppercase tracking-wide
              transition-colors duration-200 border-b-2
              ${tab === 'buy'
                ? 'text-gold border-gold'
                : 'text-white/50 border-transparent hover:text-white/80'
              }
            `}
          >
            Купить
          </button>
          <button
            onClick={() => setTab('sell')}
            className={`
              flex-1 pb-2 text-sm sm:text-base font-medium uppercase tracking-wide
              transition-colors duration-200 border-b-2
              ${tab === 'sell'
                ? 'text-gold border-gold'
                : 'text-white/50 border-transparent hover:text-white/80'
              }
            `}
          >
            Продать
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto gold-scrollbar pr-1 min-h-0">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
            </div>
          ) : tab === 'buy' ? (
            /* ── Buy Tab ── */
            shopItems.length === 0 ? (
              <p className="text-center text-white/50 text-sm py-8">У торговца нет товаров</p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {shopItems.map((si) => {
                  const qty = getQuantity(si.id);
                  const totalPrice = si.buy_price * qty;
                  const canAfford = totalPrice <= balance;
                  const inStock = si.stock === null || si.stock >= qty;
                  const icon = getItemIcon(si.item_type, si.item_image);

                  return (
                    <div
                      key={si.id}
                      className="flex gap-3 bg-white/[0.03] rounded-card p-3 border border-white/5 hover:border-white/10 transition-colors"
                    >
                      {/* Item icon */}
                      <div className={`item-cell !w-14 !h-14 sm:!w-16 sm:!h-16 shrink-0 ${getRarityClass(si.item_rarity)}`}>
                        {icon ? (
                          <img src={icon} alt={si.item_name ?? ''} className="w-8 h-8 sm:w-10 sm:h-10 object-contain" />
                        ) : (
                          <span className="text-white/30 text-xs">?</span>
                        )}
                      </div>

                      {/* Item info */}
                      <div className="flex flex-col flex-1 min-w-0 gap-1">
                        <span className="text-white text-sm font-medium truncate">
                          {si.item_name ?? `Предмет #${si.item_id}`}
                        </span>

                        {/* Price per unit */}
                        <div className="flex items-center gap-1">
                          <img src={goldCoinsIcon} alt="" className="w-4 h-4" />
                          <span className="text-gold text-xs">{si.buy_price.toLocaleString()}</span>
                        </div>

                        {/* Stock */}
                        {si.stock !== null && (
                          <span className="text-white/40 text-[10px]">
                            В наличии: {si.stock}
                          </span>
                        )}

                        {/* Quantity + total + buy button */}
                        <div className="flex items-center gap-2 mt-1">
                          <input
                            type="number"
                            min={1}
                            max={si.stock ?? 999}
                            value={qty}
                            onChange={(e) => {
                              const v = Math.max(1, parseInt(e.target.value) || 1);
                              setQuantities((prev) => ({ ...prev, [si.id]: v }));
                            }}
                            className="w-12 sm:w-14 bg-black/30 border border-white/20 rounded px-1.5 py-0.5 text-white text-xs text-center focus:border-gold/50 outline-none"
                          />
                          {qty > 1 && (
                            <span className="text-white/40 text-[10px] flex items-center gap-0.5">
                              = <img src={goldCoinsIcon} alt="" className="w-3 h-3 inline" />
                              {totalPrice.toLocaleString()}
                            </span>
                          )}
                          <button
                            onClick={() => handleBuy(si)}
                            disabled={processing || !canAfford || !inStock}
                            className="
                              ml-auto px-3 py-1 rounded text-xs font-medium uppercase
                              bg-gradient-to-r from-[#2e353e] to-[#537895] text-white
                              hover:shadow-hover disabled:opacity-40 disabled:cursor-not-allowed
                              transition-all duration-200
                            "
                          >
                            Купить
                          </button>
                        </div>
                        {!canAfford && (
                          <span className="text-site-red text-[10px]">Недостаточно золота</span>
                        )}
                        {!inStock && si.stock !== null && (
                          <span className="text-site-red text-[10px]">Нет в наличии</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )
          ) : (
            /* ── Sell Tab ── */
            sellableInventory.length === 0 ? (
              <p className="text-center text-white/50 text-sm py-8">
                {inventory.length === 0
                  ? 'Ваш инвентарь пуст'
                  : 'Торговец не покупает ваши предметы'}
              </p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {sellableInventory.map((inv) => {
                  const sellPrice = sellPriceMap.get(inv.item_id) ?? 0;
                  const qty = getSellQuantity(inv.item_id);
                  const totalSell = sellPrice * qty;
                  const icon = getItemIcon(inv.item.item_type, inv.item.image);

                  return (
                    <div
                      key={inv.id}
                      className="flex gap-3 bg-white/[0.03] rounded-card p-3 border border-white/5 hover:border-white/10 transition-colors"
                    >
                      {/* Item icon */}
                      <div className={`item-cell !w-14 !h-14 sm:!w-16 sm:!h-16 shrink-0 ${getRarityClass(inv.item.item_rarity)}`}>
                        {icon ? (
                          <img src={icon} alt={inv.item.name} className="w-8 h-8 sm:w-10 sm:h-10 object-contain" />
                        ) : (
                          <span className="text-white/30 text-xs">?</span>
                        )}
                      </div>

                      {/* Item info */}
                      <div className="flex flex-col flex-1 min-w-0 gap-1">
                        <span className="text-white text-sm font-medium truncate">{inv.item.name}</span>

                        <div className="flex items-center gap-1">
                          <img src={goldCoinsIcon} alt="" className="w-4 h-4" />
                          <span className="text-gold text-xs">{sellPrice.toLocaleString()} / шт.</span>
                        </div>

                        <span className="text-white/40 text-[10px]">
                          В инвентаре: {inv.quantity}
                        </span>

                        <div className="flex items-center gap-2 mt-1">
                          <input
                            type="number"
                            min={1}
                            max={inv.quantity}
                            value={qty}
                            onChange={(e) => {
                              const v = Math.max(1, Math.min(inv.quantity, parseInt(e.target.value) || 1));
                              setSellQuantities((prev) => ({ ...prev, [inv.item_id]: v }));
                            }}
                            className="w-12 sm:w-14 bg-black/30 border border-white/20 rounded px-1.5 py-0.5 text-white text-xs text-center focus:border-gold/50 outline-none"
                          />
                          {qty > 1 && (
                            <span className="text-white/40 text-[10px] flex items-center gap-0.5">
                              = <img src={goldCoinsIcon} alt="" className="w-3 h-3 inline" />
                              {totalSell.toLocaleString()}
                            </span>
                          )}
                          <button
                            onClick={() => handleSell(inv)}
                            disabled={processing || qty > inv.quantity}
                            className="
                              ml-auto px-3 py-1 rounded text-xs font-medium uppercase
                              border border-white/30 text-white/80
                              hover:bg-white/10 hover:border-white/50 hover:text-white
                              disabled:opacity-40 disabled:cursor-not-allowed
                              transition-all duration-200
                            "
                          >
                            Продать
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
};

export default NpcShopModal;
