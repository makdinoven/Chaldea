import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { ArrowDown, ArrowUp } from 'lucide-react';
import { useSelector, useDispatch } from 'react-redux';
import { BASE_URL } from '../../../api/api';
import { fetchInventory, fetchProfile, selectInventory, selectProfile } from '../../../redux/slices/profileSlice';
import type { AppDispatch, RootState } from '../../../redux/store';
import { ITEM_TYPE_ICONS } from '../../ProfilePage/constants';
import goldCoinsIcon from '../../../assets/icons/gold-coins.svg';
import { shownRarity } from '../../../constants/items';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import ConfirmationModal from '../../ui/ConfirmationModal';
import { getClientPrefs } from '../../../utils/clientPrefs';
import { useCurrency } from '../../../hooks/useCurrency';

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
  discounted_buy_price?: number | null;
  /* FEAT-183: current market prices, base prices from the admin, stock state. */
  base_buy_price?: number;
  base_sell_price?: number;
  in_stock?: boolean;
  market?: boolean;
  price_level?: PriceLevel;
  living?: boolean;
}

type PriceLevel = 'low' | 'normal' | 'high';

/** What of the bag this merchant buys right now (GET .../shop/sell-offers). */
interface SellOffer {
  item_id: number;
  item_name: string | null;
  item_image: string | null;
  unit_price: number;
  max_quantity: number;
}

interface ShopTransactionResponse {
  success: boolean;
  message: string;
  new_balance: number | null;
  item_name: string | null;
  quantity: number;
  total_price: number;
  discount_percent: number;
}

interface NpcShopModalProps {
  npcId: number;
  npcName: string;
  npcAvatar: string | null;
  onClose: () => void;
}

type ShopTab = 'buy' | 'sell';

/** Server-side bound of one buy/sell request (schemas.SHOP_MAX_QUANTITY). */
const MAX_DEAL_QUANTITY = 999;

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

const getEffectivePrice = (si: ShopItem): number =>
  si.discounted_buy_price != null && si.discounted_buy_price !== si.buy_price
    ? si.discounted_buy_price
    : si.buy_price;

const hasDiscount = (si: ShopItem): boolean =>
  si.discounted_buy_price != null && si.discounted_buy_price < si.buy_price;

const PRICE_LEVEL_BADGE: Record<PriceLevel, { label: string; className: string }> = {
  low: { label: 'дешевле обычного', className: 'text-green-400 border-green-500/30 bg-green-900/20' },
  normal: { label: 'обычная цена', className: 'text-white/50 border-white/15 bg-white/[0.03]' },
  high: { label: 'дороже обычного', className: 'text-site-red border-site-red/30 bg-site-red/10' },
};

const clampQuantity = (raw: string, max: number): number =>
  Math.max(1, Math.min(max, parseInt(raw, 10) || 1));

/** Russian error text from an axios failure: server `detail` string, otherwise the fallback. */
const errorText = (err: unknown, fallback: string): string => {
  if (axios.isAxiosError(err)) {
    const detail: unknown = err.response?.data?.detail;
    if (typeof detail === 'string' && detail) return detail;
    if (err.response?.status === 422) return 'Неверное количество';
    if (!err.response) return 'Нет связи с сервером';
  }
  return fallback;
};

/* ── Component ── */

const NpcShopModal = ({ npcId, npcName, npcAvatar, onClose }: NpcShopModalProps) => {
  const { format, forms } = useCurrency();
  const dispatch = useDispatch<AppDispatch>();
  const character = useSelector(selectProfile);
  const inventory = useSelector(selectInventory);
  const characterId = useSelector((s: RootState) => s.user.character?.id ?? null);

  const [tab, setTab] = useState<ShopTab>('buy');
  const [shopItems, setShopItems] = useState<ShopItem[]>([]);
  const [sellOffers, setSellOffers] = useState<SellOffer[]>([]);
  const [loading, setLoading] = useState(true);
  const [offersLoading, setOffersLoading] = useState(false);
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  const [sellQuantities, setSellQuantities] = useState<Record<number, number>>({});
  const [processing, setProcessing] = useState(false);

  const fetchShop = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, number> = {};
      if (characterId) params.character_id = characterId;
      const res = await axios.get<ShopItem[]>(`${BASE_URL}/locations/npcs/${npcId}/shop`, { params });
      setShopItems(res.data.filter((i) => i.is_active));
    } catch {
      toast.error('Не удалось загрузить товары магазина');
    } finally {
      setLoading(false);
    }
  }, [npcId, characterId]);

  const fetchSellOffers = useCallback(async () => {
    if (!characterId) return;
    setOffersLoading(true);
    try {
      const res = await axios.get<SellOffer[]>(
        `${BASE_URL}/locations/npcs/${npcId}/shop/sell-offers`,
        { params: { character_id: characterId } },
      );
      setSellOffers(res.data);
    } catch (err) {
      toast.error(errorText(err, 'Не удалось узнать, что купит торговец'));
    } finally {
      setOffersLoading(false);
    }
  }, [npcId, characterId]);

  useEffect(() => {
    fetchShop();
  }, [fetchShop]);

  useEffect(() => {
    fetchSellOffers();
  }, [fetchSellOffers]);

  /** After every deal: both lists, the bag and the balance. */
  const refreshAfterDeal = () => {
    if (!characterId) return;
    dispatch(fetchInventory(characterId));
    dispatch(fetchProfile(characterId));
    fetchShop();
    fetchSellOffers();
  };

  // Load player inventory if not loaded
  useEffect(() => {
    if (characterId && inventory.length === 0) {
      dispatch(fetchInventory(characterId));
    }
    if (characterId && !character) {
      dispatch(fetchProfile(characterId));
    }
  }, [characterId, inventory.length, character, dispatch]);

  const getQuantity = (id: number): number => quantities[id] ?? 1;
  const getSellQuantity = (id: number): number => sellQuantities[id] ?? 1;

  const handleBuy = async (shopItem: ShopItem) => {
    if (!characterId || processing) return;
    const qty = Math.min(
      getQuantity(shopItem.id),
      shopItem.stock === null ? MAX_DEAL_QUANTITY : Math.max(1, Math.min(shopItem.stock, MAX_DEAL_QUANTITY)),
    );
    const unitPrice = getEffectivePrice(shopItem);
    const totalPrice = unitPrice * qty;

    if (character && totalPrice > character.currency_balance) {
      toast.error(`Недостаточно ${forms.genitive}`);
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
        setQuantities((prev) => ({ ...prev, [shopItem.id]: 1 }));
      } else {
        toast.error(res.data.message || 'Ошибка покупки');
      }
      refreshAfterDeal();
    } catch (err) {
      toast.error(errorText(err, 'Не удалось купить предмет'));
      // Stock or price may have moved under us: show the fresh state.
      fetchShop();
    } finally {
      setProcessing(false);
    }
  };

  const [sellConfirm, setSellConfirm] = useState<SellOffer | null>(null);

  /** Selling can't be undone: ask first, unless confirmations are off in the settings. */
  const requestSell = (offer: SellOffer) => {
    if (getClientPrefs().confirmDangerous) setSellConfirm(offer);
    else void handleSell(offer);
  };

  const handleSell = async (offer: SellOffer) => {
    if (!characterId || processing) return;
    const qty = Math.min(getSellQuantity(offer.item_id), offer.max_quantity);

    setProcessing(true);
    try {
      const res = await axios.post<ShopTransactionResponse>(
        `${BASE_URL}/locations/npcs/${npcId}/shop/sell`,
        { character_id: characterId, item_id: offer.item_id, quantity: qty },
      );
      if (res.data.success) {
        toast.success(`Предмет продан: ${res.data.item_name ?? offer.item_name} x${res.data.quantity}`);
        setSellQuantities((prev) => ({ ...prev, [offer.item_id]: 1 }));
      } else {
        toast.error(res.data.message || 'Ошибка продажи');
      }
      refreshAfterDeal();
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        // The merchant's till is short: the refusal is the merchant's own words.
        toast.error(`${npcName}: «${errorText(err, 'У меня сейчас нет на это денег')}»`);
      } else {
        toast.error(errorText(err, 'Не удалось продать предмет'));
      }
      // The item may have been returned to the bag: show the fresh state.
      refreshAfterDeal();
    } finally {
      setProcessing(false);
    }
  };

  // Bag rows give the sell tab its type/rarity frame; offers themselves only carry name and image.
  const inventoryByItemId = new Map(inventory.map((inv) => [inv.item_id, inv]));

  // Compute discount percent from first item that has a discount
  const discountPercent = (() => {
    const discounted = shopItems.find(hasDiscount);
    if (!discounted || !discounted.discounted_buy_price) return 0;
    return Math.round((1 - discounted.discounted_buy_price / discounted.buy_price) * 100);
  })();

  const balance = character?.currency_balance ?? 0;

  return (
    <ModalShell
      open
      onClose={onClose}
      title={npcName}
      size="lg"
      icon={
        <div className="gold-outline relative w-9 h-9 rounded-full overflow-hidden bg-black/40 shrink-0">
          {npcAvatar ? (
            <img src={npcAvatar} alt={npcName} className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-white/20">
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
          )}
        </div>
      }
    >
      {/* Subtitle + balance + discount */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="text-white/50 text-xs uppercase tracking-wide">Торговля</span>
        <div className="ml-auto flex items-center gap-2 shrink-0">
          {discountPercent > 0 && (
            <span className="bg-green-900/40 border border-green-500/30 text-green-400 text-[10px] sm:text-xs font-medium px-2 py-1 rounded-card whitespace-nowrap">
              Скидка: {discountPercent}%
            </span>
          )}
          <div className="flex items-center gap-1.5 bg-black/30 rounded-card px-3 py-1.5">
            <img src={goldCoinsIcon} alt="" className="w-5 h-5" />
            <span className="text-gold font-medium text-sm sm:text-base">{balance.toLocaleString()}</span>
          </div>
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
              const maxQty = si.stock === null
                ? MAX_DEAL_QUANTITY
                : Math.max(1, Math.min(si.stock, MAX_DEAL_QUANTITY));
              const soldOut = si.in_stock === false || (si.stock !== null && si.stock <= 0);
              const qty = Math.min(getQuantity(si.id), maxQty);
              const unitPrice = getEffectivePrice(si);
              const totalPrice = unitPrice * qty;
              const canAfford = totalPrice <= balance;
              const icon = getItemIcon(si.item_type, si.item_image);
              const itemHasDiscount = hasDiscount(si);
              const basePrice = si.base_buy_price;
              const showBase = !!si.market && basePrice != null && basePrice !== si.buy_price;
              const badge = si.market && si.price_level ? PRICE_LEVEL_BADGE[si.price_level] : null;

              return (
                <div
                  key={si.id}
                  className="flex gap-3 bg-white/[0.03] rounded-card p-3 border border-white/5 hover:border-white/10 transition-colors"
                >
                  {/* Item icon */}
                  <div className={`item-cell !w-14 !h-14 sm:!w-16 sm:!h-16 shrink-0 ${getRarityClass(shownRarity(si.item_type, si.item_rarity))}`}>
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

                    {/* Price per unit: current (charisma-discounted) price, base price when the market moved it */}
                    <div className="flex items-center gap-1 flex-wrap">
                      <img src={goldCoinsIcon} alt="" className="w-4 h-4" />
                      {itemHasDiscount ? (
                        <>
                          <span className="text-white/40 text-xs line-through">{si.buy_price.toLocaleString()}</span>
                          <span className="text-green-400 text-xs font-medium">{unitPrice.toLocaleString()}</span>
                        </>
                      ) : (
                        <span className="text-gold text-xs">{si.buy_price.toLocaleString()}</span>
                      )}
                      {showBase && basePrice != null && (
                        <span className="text-white/35 text-[10px]" title="Обычная цена этого товара">
                          обычно <span className="line-through">{basePrice.toLocaleString()}</span>
                        </span>
                      )}
                    </div>

                    {badge && (
                      <span
                        className={`self-start inline-flex items-center gap-0.5 border rounded-full px-1.5 py-px text-[10px] leading-tight ${badge.className}`}
                      >
                        {si.price_level === 'low' && <ArrowDown className="w-3 h-3" aria-hidden />}
                        {si.price_level === 'high' && <ArrowUp className="w-3 h-3" aria-hidden />}
                        {badge.label}
                      </span>
                    )}

                    {/* Stock: nothing for an unlimited (legacy) row */}
                    {soldOut ? (
                      <span className="text-site-red text-[10px]">Нет в наличии</span>
                    ) : si.stock !== null ? (
                      <span className="text-white/40 text-[10px]">Осталось: {si.stock}</span>
                    ) : null}

                    {/* Quantity + total + buy button */}
                    <div className="flex items-center gap-2 mt-1">
                      <input
                        type="number"
                        min={1}
                        max={maxQty}
                        value={qty}
                        disabled={soldOut}
                        onChange={(e) => {
                          const v = clampQuantity(e.target.value, maxQty);
                          setQuantities((prev) => ({ ...prev, [si.id]: v }));
                        }}
                        aria-label="Количество"
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
                        disabled={processing || !canAfford || soldOut}
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
                    {!canAfford && !soldOut && (
                      <span className="text-site-red text-[10px]">Недостаточно {forms.genitive}</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )
      ) : (
        /* ── Sell Tab: what this merchant buys from the bag right now ── */
        offersLoading && sellOffers.length === 0 ? (
          <div className="flex items-center justify-center py-12">
            <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
          </div>
        ) : sellOffers.length === 0 ? (
          <p className="text-center text-white/50 text-sm py-8">
            {inventory.length === 0
              ? 'Ваш инвентарь пуст'
              : 'Торговец не покупает ваши предметы'}
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {sellOffers.map((offer) => {
              const inv = inventoryByItemId.get(offer.item_id);
              const maxQty = Math.max(1, Math.min(offer.max_quantity, MAX_DEAL_QUANTITY));
              const qty = Math.min(getSellQuantity(offer.item_id), maxQty);
              const totalSell = offer.unit_price * qty;
              const name = offer.item_name ?? inv?.item.name ?? `Предмет #${offer.item_id}`;
              const icon = getItemIcon(inv?.item.item_type ?? null, offer.item_image ?? inv?.item.image ?? null);
              const rarity = inv ? shownRarity(inv.item.item_type, inv.item.item_rarity) : null;

              return (
                <div
                  key={offer.item_id}
                  className="flex gap-3 bg-white/[0.03] rounded-card p-3 border border-white/5 hover:border-white/10 transition-colors"
                >
                  {/* Item icon */}
                  <div className={`item-cell !w-14 !h-14 sm:!w-16 sm:!h-16 shrink-0 ${getRarityClass(rarity)}`}>
                    {icon ? (
                      <img src={icon} alt={name} className="w-8 h-8 sm:w-10 sm:h-10 object-contain" />
                    ) : (
                      <span className="text-white/30 text-xs">?</span>
                    )}
                  </div>

                  {/* Item info */}
                  <div className="flex flex-col flex-1 min-w-0 gap-1">
                    <span className="text-white text-sm font-medium truncate">{name}</span>

                    <div className="flex items-center gap-1">
                      <img src={goldCoinsIcon} alt="" className="w-4 h-4" />
                      <span className="text-gold text-xs">{offer.unit_price.toLocaleString()} / шт.</span>
                    </div>

                    <span className="text-white/40 text-[10px]">
                      Можно продать: {offer.max_quantity}
                    </span>

                    <div className="flex items-center gap-2 mt-1">
                      <input
                        type="number"
                        min={1}
                        max={maxQty}
                        value={qty}
                        onChange={(e) => {
                          const v = clampQuantity(e.target.value, maxQty);
                          setSellQuantities((prev) => ({ ...prev, [offer.item_id]: v }));
                        }}
                        aria-label="Количество"
                        className="w-12 sm:w-14 bg-black/30 border border-white/20 rounded px-1.5 py-0.5 text-white text-xs text-center focus:border-gold/50 outline-none"
                      />
                      {qty > 1 && (
                        <span className="text-white/40 text-[10px] flex items-center gap-0.5">
                          = <img src={goldCoinsIcon} alt="" className="w-3 h-3 inline" />
                          {totalSell.toLocaleString()}
                        </span>
                      )}
                      <button
                        onClick={() => requestSell(offer)}
                        disabled={processing || offer.max_quantity < 1}
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

      <ConfirmationModal
        isOpen={sellConfirm !== null}
        title="Продать предмет?"
        message={
          sellConfirm
            ? (() => {
                const q = Math.min(getSellQuantity(sellConfirm.item_id), sellConfirm.max_quantity);
                const name = sellConfirm.item_name ?? `Предмет #${sellConfirm.item_id}`;
                return `«${name}» x${q} за ${format(sellConfirm.unit_price * q)}`;
              })()
            : ''
        }
        onCancel={() => setSellConfirm(null)}
        onConfirm={() => {
          const invItem = sellConfirm;
          setSellConfirm(null);
          if (invItem) void handleSell(invItem);
        }}
      />
    </ModalShell>
  );
};

export default NpcShopModal;
