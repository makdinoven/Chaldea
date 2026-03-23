import { useEffect, useState, useCallback, useRef } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import axios from 'axios';
import {
  getTradeState,
  updateTradeItems,
  confirmTrade,
  cancelTrade,
} from '../../../api/trade';
import type { TradeState, TradeItem } from '../../../api/trade';
import TradeItemSelector from './TradeItemSelector';
import goldCoinsIcon from '../../../assets/icons/gold-coins.svg';
import { ITEM_TYPE_ICONS } from '../../ProfilePage/constants';

interface TradeModalProps {
  tradeId: number;
  currentCharacterId: number;
  targetCharacterName: string;
  onClose: () => void;
}

const POLL_INTERVAL = 3000;
const MIN_DISPLAY_CELLS = 8;

const getRarityClass = (rarity: string | undefined): string => {
  if (!rarity || rarity === 'common') return '';
  const map: Record<string, string> = {
    rare: 'rarity-rare',
    epic: 'rarity-epic',
    mythical: 'rarity-mythical',
    legendary: 'rarity-legendary',
  };
  return map[rarity] || '';
};

const cellVariants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0 },
};

const TradeModal = ({
  tradeId,
  currentCharacterId,
  targetCharacterName,
  onClose,
}: TradeModalProps) => {
  const [trade, setTrade] = useState<TradeState | null>(null);
  const [goldInput, setGoldInput] = useState('0');
  const [selectedItems, setSelectedItems] = useState<{ item_id: number; quantity: number }[]>([]);
  const [updating, setUpdating] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [completed, setCompleted] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Determine which side is "mine" and which is "theirs"
  const mySide = trade?.initiator?.character_id === currentCharacterId
    ? trade?.initiator
    : trade?.target;
  const theirSide = trade?.initiator?.character_id === currentCharacterId
    ? trade?.target
    : trade?.initiator;

  // Poll trade state
  const fetchState = useCallback(async () => {
    try {
      const state = await getTradeState(tradeId);
      setTrade(state);

      if (state.status === 'completed') {
        setCompleted(true);
        toast.success('Обмен завершён успешно!');
      } else if (state.status === 'cancelled' || state.status === 'expired') {
        toast.error(state.status === 'cancelled' ? 'Обмен отменён.' : 'Обмен истёк.');
        onClose();
      }
    } catch {
      // Silently ignore poll errors
    }
  }, [tradeId, onClose]);

  useEffect(() => {
    fetchState();
    pollRef.current = setInterval(fetchState, POLL_INTERVAL);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchState]);

  // Auto-close after completed message
  useEffect(() => {
    if (!completed) return;
    const timer = setTimeout(onClose, 2500);
    return () => clearTimeout(timer);
  }, [completed, onClose]);

  // Sync local state from fetched trade state (only on first load)
  useEffect(() => {
    if (!mySide) return;
    if (selectedItems.length === 0 && mySide.items.length > 0) {
      setSelectedItems(mySide.items.map((i) => ({ item_id: i.item_id, quantity: i.quantity })));
    }
    if (goldInput === '0' && mySide.gold > 0) {
      setGoldInput(String(mySide.gold));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mySide?.character_id]);

  const handleUpdateOffer = async () => {
    const gold = Math.max(0, parseInt(goldInput, 10) || 0);
    setUpdating(true);
    try {
      const state = await updateTradeItems(tradeId, currentCharacterId, selectedItems, gold);
      setTrade(state);
      toast.success('Предложение обновлено');
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось обновить предложение';
      toast.error(message);
    } finally {
      setUpdating(false);
    }
  };

  const handleConfirm = async () => {
    setConfirming(true);
    try {
      const state = await confirmTrade(tradeId, currentCharacterId);
      setTrade(state);
      if (state.status === 'completed') {
        setCompleted(true);
        toast.success('Обмен завершён успешно!');
      } else {
        toast.success('Вы подтвердили обмен. Ожидание второй стороны...');
      }
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось подтвердить обмен';
      toast.error(message);
    } finally {
      setConfirming(false);
    }
  };

  const handleCancel = async () => {
    setCancelling(true);
    try {
      await cancelTrade(tradeId);
      toast('Обмен отменён.');
      onClose();
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось отменить обмен';
      toast.error(message);
    } finally {
      setCancelling(false);
    }
  };

  const isCompleteOrClosed = completed || trade?.status === 'completed' || trade?.status === 'cancelled';

  return (
    <div className="modal-overlay" onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="modal-content gold-outline gold-outline-thick relative w-full max-w-4xl mx-3 sm:mx-4 max-h-[90vh] overflow-y-auto gold-scrollbar-wide"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase text-center mb-4 sm:mb-6">
          Обмен с {targetCharacterName}
        </h2>

        {/* Completed state */}
        {completed && (
          <div className="text-center py-8">
            <p className="text-xl text-green-400 font-medium mb-2">Обмен завершён!</p>
            <p className="text-white/60 text-sm">Окно закроется автоматически...</p>
          </div>
        )}

        {/* Loading state */}
        {!trade && !completed && (
          <div className="flex items-center justify-center py-12">
            <div className="w-6 h-6 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          </div>
        )}

        {/* Trade content */}
        {trade && !completed && (
          <>
            {/* Two-column layout */}
            <div className="flex flex-col md:flex-row gap-4 sm:gap-6">
              {/* My side */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">
                    Ваше предложение
                  </h3>
                  {mySide?.confirmed && (
                    <span className="text-green-400 text-xs bg-green-400/10 px-2 py-0.5 rounded-full border border-green-400/20">
                      подтверждено
                    </span>
                  )}
                </div>

                {/* Item selector (inventory grid) */}
                <TradeItemSelector
                  characterId={currentCharacterId}
                  selectedItems={selectedItems}
                  onItemsChange={setSelectedItems}
                />

                {/* Gold input */}
                <div className="flex items-center gap-2 mt-3 px-1.5">
                  <img src={goldCoinsIcon} alt="Золото" className="w-5 h-5 flex-shrink-0" />
                  <input
                    type="number"
                    min="0"
                    value={goldInput}
                    onChange={(e) => setGoldInput(e.target.value)}
                    className="input-underline w-20 sm:w-24 text-sm"
                    placeholder="0"
                  />
                  <span className="text-white/50 text-xs">золота</span>
                </div>

                {/* Action buttons */}
                <div className="flex flex-col gap-2 mt-3">
                  <button
                    onClick={handleUpdateOffer}
                    disabled={updating || isCompleteOrClosed}
                    className="btn-line text-xs sm:text-sm w-full disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {updating ? 'Обновление...' : 'Обновить предложение'}
                  </button>
                  <button
                    onClick={handleConfirm}
                    disabled={confirming || mySide?.confirmed || isCompleteOrClosed}
                    className="btn-blue text-xs sm:text-sm w-full disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {confirming
                      ? 'Подтверждение...'
                      : mySide?.confirmed
                        ? 'Подтверждено'
                        : 'Подтвердить'}
                  </button>
                </div>
              </div>

              {/* Divider */}
              <div className="hidden md:block w-px bg-gradient-to-b from-transparent via-white/20 to-transparent" />
              <div className="md:hidden h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />

              {/* Their side */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">
                    Предложение {theirSide?.character_name || targetCharacterName}
                  </h3>
                  {theirSide?.confirmed && (
                    <span className="text-green-400 text-xs bg-green-400/10 px-2 py-0.5 rounded-full border border-green-400/20">
                      подтверждено
                    </span>
                  )}
                </div>

                {/* Their items grid */}
                <TheirItemsGrid items={theirSide?.items || []} />

                {/* Their gold */}
                {theirSide && theirSide.gold > 0 && (
                  <div className="flex items-center gap-2 mt-3 px-1.5">
                    <img src={goldCoinsIcon} alt="Золото" className="w-5 h-5 flex-shrink-0" />
                    <span className="text-gold text-sm font-medium">
                      {theirSide.gold}
                    </span>
                    <span className="text-white/50 text-xs">золота</span>
                  </div>
                )}

                {/* Status indicator */}
                {theirSide && !theirSide.confirmed && theirSide.items.length === 0 && theirSide.gold === 0 && (
                  <p className="text-white/30 text-xs text-center mt-3">
                    Ожидание предложения...
                  </p>
                )}
              </div>
            </div>

            {/* Cancel button */}
            <div className="mt-6 flex justify-center">
              <button
                onClick={handleCancel}
                disabled={cancelling || isCompleteOrClosed}
                className="text-site-red hover:text-site-red/80 text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {cancelling ? 'Отмена...' : 'Отменить обмен'}
              </button>
            </div>
          </>
        )}
      </motion.div>
    </div>
  );
};

// --- Sub-component: other player's items displayed as inventory grid ---

const TheirItemsGrid = ({ items }: { items: TradeItem[] }) => {
  const emptyCellsCount = Math.max(0, MIN_DISPLAY_CELLS - items.length);

  if (items.length === 0) {
    return (
      <div className="gold-scrollbar-wide overflow-y-auto max-h-[240px] sm:max-h-[300px] pr-1 rounded-lg">
        <div className="grid grid-cols-4 gap-1.5 p-1.5">
          {Array.from({ length: MIN_DISPLAY_CELLS }).map((_, idx) => (
            <motion.div
              key={`empty-${idx}`}
              variants={cellVariants}
              initial="hidden"
              animate="visible"
            >
              <div className="item-cell item-cell-empty" />
            </motion.div>
          ))}
        </div>
        <p className="text-white/40 text-xs text-center py-2">
          Пока ничего не предложено
        </p>
      </div>
    );
  }

  return (
    <motion.div
      className="gold-scrollbar-wide overflow-y-auto max-h-[240px] sm:max-h-[300px] pr-1 rounded-lg"
      initial="hidden"
      animate="visible"
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: 0.03 } },
      }}
    >
      <div className="grid grid-cols-4 gap-1.5 p-1.5">
        {items.map((item) => {
          const iconSrc = ITEM_TYPE_ICONS[item.rarity || ''] || null;

          return (
            <motion.div key={item.item_id} variants={cellVariants} className="relative">
              <div className={`item-cell ${getRarityClass(item.rarity)}`}>
                {item.item_image ? (
                  <img
                    src={item.item_image}
                    alt={item.item_name}
                    className="w-full h-full object-cover"
                    draggable={false}
                  />
                ) : iconSrc ? (
                  <img
                    src={iconSrc}
                    alt={item.item_name}
                    className="w-10 h-10 opacity-70"
                    draggable={false}
                  />
                ) : null}
              </div>

              {/* Quantity badge */}
              {item.quantity > 1 && (
                <span
                  className="
                    absolute -bottom-1 -right-1 z-10 min-w-[20px] h-[20px]
                    flex items-center justify-center
                    text-[10px] font-medium text-white
                    bg-site-bg rounded-full
                    border border-white/30 px-1
                  "
                >
                  {item.quantity}
                </span>
              )}
            </motion.div>
          );
        })}

        {/* Empty placeholder cells */}
        {Array.from({ length: emptyCellsCount }).map((_, idx) => (
          <motion.div key={`empty-${idx}`} variants={cellVariants}>
            <div className="item-cell item-cell-empty" />
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
};

export default TradeModal;
