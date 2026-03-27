import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchListing,
  placeBid,
  buyoutListing,
  cancelListing,
  setSelectedListingId,
  selectSelectedListing,
  selectSelectedListingLoading,
  selectSelectedListingError,
  selectActionLoading,
} from '../../redux/slices/auctionSlice';
import { formatTimeRemaining, RARITY_COLOR_MAP } from './AuctionListingCard';
import { STAT_LABELS } from '../ProfilePage/constants';

interface AuctionListingDetailProps {
  listingId: number;
  characterId: number;
}

const AuctionListingDetail = ({ listingId, characterId }: AuctionListingDetailProps) => {
  const dispatch = useAppDispatch();
  const listing = useAppSelector(selectSelectedListing);
  const loading = useAppSelector(selectSelectedListingLoading);
  const error = useAppSelector(selectSelectedListingError);
  const actionLoading = useAppSelector(selectActionLoading);

  const [bidAmount, setBidAmount] = useState('');

  useEffect(() => {
    dispatch(fetchListing(listingId));
  }, [dispatch, listingId]);

  // Pre-fill bid amount with current_bid + 1 or start_price
  useEffect(() => {
    if (listing) {
      const minBid = listing.current_bid > 0 ? listing.current_bid + 1 : listing.start_price;
      setBidAmount(String(minBid));
    }
  }, [listing]);

  const handleClose = () => {
    dispatch(setSelectedListingId(null));
  };

  const handleBid = async () => {
    const amount = parseInt(bidAmount, 10);
    if (isNaN(amount) || amount <= 0) {
      toast.error('Введите корректную сумму ставки');
      return;
    }
    try {
      await dispatch(placeBid({ listingId, payload: { character_id: characterId, amount } })).unwrap();
      toast.success('Ставка принята');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось сделать ставку');
    }
  };

  const handleBuyout = async () => {
    try {
      await dispatch(buyoutListing({ listingId, payload: { character_id: characterId } })).unwrap();
      toast.success('Предмет выкуплен');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось выкупить лот');
    }
  };

  const handleCancel = async () => {
    try {
      await dispatch(cancelListing({ listingId, payload: { character_id: characterId } })).unwrap();
      toast.success('Лот отменён');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось отменить лот');
    }
  };

  const isSeller = listing?.seller_character_id === characterId;
  const rarityColor = RARITY_COLOR_MAP[listing?.item.item_rarity ?? ''] ?? 'text-white';

  return (
    <AnimatePresence>
      <div className="modal-overlay" onClick={handleClose}>
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          className="modal-content gold-outline gold-outline-thick max-w-lg mx-4 max-h-[90vh] overflow-y-auto gold-scrollbar"
          onClick={(e) => e.stopPropagation()}
        >
          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
            </div>
          )}

          {error && (
            <div className="text-center py-8">
              <p className="text-site-red">{error}</p>
              <button onClick={handleClose} className="text-site-blue mt-4 hover:text-white transition-colors">
                Закрыть
              </button>
            </div>
          )}

          {listing && !loading && (
            <>
              {/* Header */}
              <div className="flex items-start gap-4 mb-5">
                <div className="w-20 h-20 rounded-full bg-white/5 flex-shrink-0 flex items-center justify-center overflow-hidden">
                  {listing.item.image ? (
                    <img src={listing.item.image} alt={listing.item.name} className="w-full h-full object-cover" />
                  ) : (
                    <span className="text-white/30 text-3xl">?</span>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <h2 className={`${rarityColor} text-xl sm:text-2xl font-medium`}>
                    {listing.item.name}
                  </h2>
                  {listing.quantity > 1 && (
                    <p className="text-white/60 text-sm">Количество: {listing.quantity}</p>
                  )}
                  <p className="text-white/50 text-sm mt-1">
                    Продавец: <span className="text-white">{listing.seller_name}</span>
                  </p>
                  <p className="text-white/40 text-xs mt-1">
                    Ур. {listing.item.item_level} &middot; Осталось: {formatTimeRemaining(listing.time_remaining_seconds)}
                  </p>
                </div>
                <button
                  onClick={handleClose}
                  className="text-white/40 hover:text-white transition-colors text-xl flex-shrink-0"
                  aria-label="Закрыть"
                >
                  &times;
                </button>
              </div>

              {/* Enhancement data */}
              {listing.enhancement_data && (
                <div className="mb-4 p-3 rounded-card bg-white/5">
                  <p className="text-white/60 text-xs uppercase tracking-wide mb-2">Улучшения</p>
                  {listing.enhancement_data.enhancement_points_spent != null && listing.enhancement_data.enhancement_points_spent > 0 && (
                    <p className="text-white text-sm">
                      Очков улучшения: {listing.enhancement_data.enhancement_points_spent}
                    </p>
                  )}
                  {listing.enhancement_data.enhancement_bonuses &&
                    Object.entries(listing.enhancement_data.enhancement_bonuses).length > 0 && (
                      <div className="text-white/80 text-sm mt-1">
                        {Object.entries(listing.enhancement_data.enhancement_bonuses).map(([stat, val]) => {
                          const statKey = stat.replace('_modifier', '');
                          const label = STAT_LABELS[statKey] || statKey;
                          return (
                            <span key={stat} className="mr-3">
                              +{val} {label}
                            </span>
                          );
                        })}
                      </div>
                    )}
                  {listing.enhancement_data.current_durability != null && (
                    <p className="text-white/60 text-sm mt-1">
                      Прочность: {listing.enhancement_data.current_durability}
                    </p>
                  )}
                </div>
              )}

              {/* Pricing info */}
              <div className="grid grid-cols-2 gap-3 mb-5">
                <div className="p-3 rounded-card bg-white/5">
                  <p className="text-white/50 text-xs mb-1">Начальная цена</p>
                  <p className="gold-text text-lg font-medium">
                    {listing.start_price.toLocaleString('ru-RU')} зол.
                  </p>
                </div>
                <div className="p-3 rounded-card bg-white/5">
                  <p className="text-white/50 text-xs mb-1">Текущая ставка</p>
                  <p className="gold-text text-lg font-medium">
                    {listing.current_bid > 0
                      ? `${listing.current_bid.toLocaleString('ru-RU')} зол.`
                      : 'Нет ставок'}
                  </p>
                </div>
                {listing.buyout_price && (
                  <div className="p-3 rounded-card bg-white/5">
                    <p className="text-white/50 text-xs mb-1">Цена выкупа</p>
                    <p className="text-site-blue text-lg font-medium">
                      {listing.buyout_price.toLocaleString('ru-RU')} зол.
                    </p>
                  </div>
                )}
                <div className="p-3 rounded-card bg-white/5">
                  <p className="text-white/50 text-xs mb-1">Ставок</p>
                  <p className="text-white text-lg font-medium">{listing.bid_count}</p>
                </div>
              </div>

              {/* Current bidder */}
              {listing.current_bidder_name && (
                <p className="text-white/50 text-sm mb-4">
                  Лидирует: <span className="text-white">{listing.current_bidder_name}</span>
                </p>
              )}

              {/* Actions */}
              {!isSeller && listing.status === 'active' && (
                <div className="space-y-3">
                  {/* Bid */}
                  <div className="flex gap-2 items-end">
                    <div className="flex-1">
                      <label className="text-white/50 text-xs block mb-1">Ваша ставка</label>
                      <input
                        type="number"
                        value={bidAmount}
                        onChange={(e) => setBidAmount(e.target.value)}
                        min={listing.current_bid > 0 ? listing.current_bid + 1 : listing.start_price}
                        className="input-underline text-sm"
                        disabled={actionLoading}
                      />
                    </div>
                    <button
                      onClick={handleBid}
                      disabled={actionLoading}
                      className="btn-blue !px-5 !py-2.5 !text-sm whitespace-nowrap disabled:opacity-50"
                    >
                      {actionLoading ? '...' : 'Ставка'}
                    </button>
                  </div>

                  {/* Buyout */}
                  {listing.buyout_price && (
                    <button
                      onClick={handleBuyout}
                      disabled={actionLoading}
                      className="btn-blue w-full !text-sm disabled:opacity-50"
                    >
                      {actionLoading
                        ? 'Обработка...'
                        : `Выкупить за ${listing.buyout_price.toLocaleString('ru-RU')} зол.`}
                    </button>
                  )}
                </div>
              )}

              {/* Seller: cancel */}
              {isSeller && listing.status === 'active' && (
                <button
                  onClick={handleCancel}
                  disabled={actionLoading}
                  className="w-full py-2.5 rounded-card text-sm font-medium uppercase transition-colors duration-200 ease-site text-site-red border border-site-red/30 hover:bg-site-red/10 disabled:opacity-50"
                >
                  {actionLoading ? 'Отмена...' : 'Отменить лот'}
                </button>
              )}
            </>
          )}
        </motion.div>
      </div>
    </AnimatePresence>
  );
};

export default AuctionListingDetail;
