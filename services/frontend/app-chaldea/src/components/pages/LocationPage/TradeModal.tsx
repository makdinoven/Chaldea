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
  const mySide = trade?.initiator.character_id === currentCharacterId
    ? trade?.initiator
    : trade?.target;
  const theirSide = trade?.initiator.character_id === currentCharacterId
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
    // Only set initial values if we haven't started editing
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
        className="modal-content gold-outline gold-outline-thick relative w-full max-w-3xl mx-3 sm:mx-4 max-h-[90vh] overflow-y-auto gold-scrollbar-wide"
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
            {/* Two-column layout: stacked on mobile, side by side on md+ */}
            <div className="flex flex-col md:flex-row gap-4 sm:gap-6">
              {/* My side */}
              <div className="flex-1 min-w-0">
                <h3 className="text-white font-medium text-sm sm:text-base mb-3 uppercase tracking-wide">
                  Ваше предложение
                  {mySide?.confirmed && (
                    <span className="ml-2 text-green-400 text-xs normal-case">
                      (подтверждено)
                    </span>
                  )}
                </h3>

                {/* Item selector */}
                <TradeItemSelector
                  characterId={currentCharacterId}
                  selectedItems={selectedItems}
                  onItemsChange={setSelectedItems}
                />

                {/* Gold input */}
                <div className="flex items-center gap-2 mt-3">
                  <img src={goldCoinsIcon} alt="Золото" className="w-5 h-5" />
                  <input
                    type="number"
                    min="0"
                    value={goldInput}
                    onChange={(e) => setGoldInput(e.target.value)}
                    className="input-underline w-24 text-sm"
                    placeholder="0"
                  />
                  <span className="text-white/50 text-xs">золота</span>
                </div>

                {/* Update offer button */}
                <button
                  onClick={handleUpdateOffer}
                  disabled={updating || isCompleteOrClosed}
                  className="btn-line text-xs sm:text-sm mt-3 w-full disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {updating ? 'Обновление...' : 'Обновить предложение'}
                </button>

                {/* Confirm button */}
                <button
                  onClick={handleConfirm}
                  disabled={confirming || mySide?.confirmed || isCompleteOrClosed}
                  className="btn-blue text-xs sm:text-sm mt-2 w-full disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {confirming
                    ? 'Подтверждение...'
                    : mySide?.confirmed
                      ? 'Подтверждено'
                      : 'Подтвердить'}
                </button>
              </div>

              {/* Divider */}
              <div className="hidden md:block w-px bg-gradient-to-b from-transparent via-white/20 to-transparent" />
              <div className="md:hidden h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />

              {/* Their side */}
              <div className="flex-1 min-w-0">
                <h3 className="text-white font-medium text-sm sm:text-base mb-3 uppercase tracking-wide">
                  Предложение {theirSide?.character_name || targetCharacterName}
                  {theirSide?.confirmed && (
                    <span className="ml-2 text-green-400 text-xs normal-case">
                      (подтверждено)
                    </span>
                  )}
                </h3>

                {/* Their items display */}
                {theirSide && theirSide.items.length > 0 ? (
                  <div className="gold-scrollbar-wide overflow-y-auto max-h-[240px] sm:max-h-[300px]">
                    <div className="grid grid-cols-4 sm:grid-cols-5 gap-2">
                      {theirSide.items.map((item) => (
                        <TradeItemDisplay key={item.item_id} item={item} />
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="text-white/40 text-sm text-center py-6">
                    Пока ничего не предложено
                  </p>
                )}

                {/* Their gold */}
                {theirSide && theirSide.gold > 0 && (
                  <div className="flex items-center gap-2 mt-3">
                    <img src={goldCoinsIcon} alt="Золото" className="w-5 h-5" />
                    <span className="text-gold text-sm font-medium">
                      {theirSide.gold}
                    </span>
                    <span className="text-white/50 text-xs">золота</span>
                  </div>
                )}

                {/* Status indicator for their side */}
                {theirSide && !theirSide.confirmed && theirSide.items.length === 0 && theirSide.gold === 0 && (
                  <p className="text-white/30 text-xs text-center mt-2">
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

// --- Sub-component: display a single trade item from the other side ---

const TradeItemDisplay = ({ item }: { item: TradeItem }) => {
  const iconSrc = ITEM_TYPE_ICONS[item.rarity || ''] || null;

  return (
    <div className="flex flex-col items-center gap-1">
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
      <span className="text-[10px] text-white/70 text-center truncate w-full max-w-[60px]">
        {item.item_name}
      </span>
      {item.quantity > 1 && (
        <span className="text-[9px] text-white/40">x{item.quantity}</span>
      )}
    </div>
  );
};

export default TradeModal;
