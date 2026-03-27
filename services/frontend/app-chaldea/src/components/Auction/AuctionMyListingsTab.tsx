import { useEffect } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchMyListings,
  cancelListing,
  setSelectedListingId,
  selectMyActiveListings,
  selectMyCompletedListings,
  selectMyListingsLoading,
  selectMyListingsError,
  selectActionLoading,
  selectSelectedListingId,
} from '../../redux/slices/auctionSlice';
import { formatTimeRemaining, RARITY_COLOR_MAP } from './AuctionListingCard';
import AuctionListingDetail from './AuctionListingDetail';
import type { AuctionListingResponse } from '../../types/auction';

interface AuctionMyListingsTabProps {
  characterId: number;
}

const STATUS_LABELS: Record<string, string> = {
  active: 'Активен',
  sold: 'Продано',
  expired: 'Истёк',
  cancelled: 'Отменён',
};

const STATUS_COLORS: Record<string, string> = {
  active: 'text-green-400',
  sold: 'text-gold',
  expired: 'text-white/40',
  cancelled: 'text-site-red',
};

const ListingRow = ({
  listing,
  onClick,
  onCancel,
  canCancel,
  actionLoading,
}: {
  listing: AuctionListingResponse;
  onClick: (id: number) => void;
  onCancel?: (id: number) => void;
  canCancel: boolean;
  actionLoading: boolean;
}) => {
  const rarityColor = RARITY_COLOR_MAP[listing.item.item_rarity] ?? 'text-white';
  const statusColor = STATUS_COLORS[listing.status] ?? 'text-white/50';

  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: 10 },
        visible: { opacity: 1, y: 0 },
      }}
      className="flex items-center gap-3 p-3 rounded-card bg-white/5 hover:bg-white/[0.07] transition-colors duration-200 ease-site cursor-pointer"
      onClick={() => onClick(listing.id)}
    >
      {/* Image */}
      <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-white/5 flex-shrink-0 flex items-center justify-center overflow-hidden">
        {listing.item.image ? (
          <img src={listing.item.image} alt={listing.item.name} className="w-full h-full object-cover" />
        ) : (
          <span className="text-white/30 text-lg">?</span>
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className={`${rarityColor} text-sm font-medium truncate`}>{listing.item.name}</p>
        <p className="text-white/40 text-xs">
          {listing.current_bid > 0
            ? `Ставка: ${listing.current_bid.toLocaleString('ru-RU')} зол.`
            : `Старт: ${listing.start_price.toLocaleString('ru-RU')} зол.`}
          {listing.bid_count > 0 && ` (${listing.bid_count} ст.)`}
        </p>
      </div>

      {/* Status + time */}
      <div className="flex flex-col items-end gap-1 flex-shrink-0">
        <span className={`${statusColor} text-xs`}>{STATUS_LABELS[listing.status] ?? listing.status}</span>
        {listing.status === 'active' && (
          <span className="text-white/30 text-xs">{formatTimeRemaining(listing.time_remaining_seconds)}</span>
        )}
      </div>

      {/* Cancel button (only for active + at NPC) */}
      {listing.status === 'active' && canCancel && onCancel && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onCancel(listing.id);
          }}
          disabled={actionLoading}
          className="text-site-red/70 hover:text-site-red text-xs transition-colors disabled:opacity-50 flex-shrink-0"
        >
          Отменить
        </button>
      )}
    </motion.div>
  );
};

const AuctionMyListingsTab = ({ characterId }: AuctionMyListingsTabProps) => {
  const dispatch = useAppDispatch();
  const activeListings = useAppSelector(selectMyActiveListings);
  const completedListings = useAppSelector(selectMyCompletedListings);
  const loading = useAppSelector(selectMyListingsLoading);
  const error = useAppSelector(selectMyListingsError);
  const actionLoading = useAppSelector(selectActionLoading);
  const selectedListingId = useAppSelector(selectSelectedListingId);

  useEffect(() => {
    dispatch(fetchMyListings(characterId));
  }, [dispatch, characterId]);

  const handleCancel = async (listingId: number) => {
    try {
      await dispatch(cancelListing({ listingId, payload: { character_id: characterId } })).unwrap();
      toast.success('Лот отменён');
      dispatch(fetchMyListings(characterId));
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось отменить лот');
    }
  };

  const handleClick = (id: number) => {
    dispatch(setSelectedListingId(id));
  };

  const handleCancelClick = (listingId: number) => {
    handleCancel(listingId);
  };

  return (
    <div>
      {/* Info */}
      <div className="flex flex-col gap-3 mb-5">
        <div className="flex items-center justify-between">
          <p className="text-white/50 text-sm">
            Активных лотов: {activeListings.length}/5
          </p>
        </div>
        <div className="p-3 rounded-card bg-white/5 border border-white/10">
          <p className="text-white/50 text-sm text-center">
            Выставить предметы можно через вкладку &laquo;Склад&raquo;. При отмене лот возвращается на склад (забрать у НПС).
          </p>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="text-center py-4">
          <p className="text-site-red">{error}</p>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {!loading && (
        <>
          {/* Active listings */}
          <div className="mb-6">
            <h3 className="gold-text text-lg font-medium uppercase mb-3">Активные</h3>
            {activeListings.length === 0 ? (
              <p className="text-white/30 text-sm">Нет активных лотов</p>
            ) : (
              <motion.div
                initial="hidden"
                animate="visible"
                variants={{
                  hidden: {},
                  visible: { transition: { staggerChildren: 0.04 } },
                }}
                className="space-y-2"
              >
                {activeListings.map((listing) => (
                  <ListingRow
                    key={listing.id}
                    listing={listing}
                    onClick={handleClick}
                    onCancel={handleCancelClick}
                    canCancel={true}
                    actionLoading={actionLoading}
                  />
                ))}
              </motion.div>
            )}
          </div>

          {/* Completed listings */}
          <div>
            <h3 className="gold-text text-lg font-medium uppercase mb-3">Завершённые</h3>
            {completedListings.length === 0 ? (
              <p className="text-white/30 text-sm">Нет завершённых лотов</p>
            ) : (
              <motion.div
                initial="hidden"
                animate="visible"
                variants={{
                  hidden: {},
                  visible: { transition: { staggerChildren: 0.04 } },
                }}
                className="space-y-2"
              >
                {completedListings.map((listing) => (
                  <ListingRow
                    key={listing.id}
                    listing={listing}
                    onClick={handleClick}
                    canCancel={false}
                    actionLoading={false}
                  />
                ))}
              </motion.div>
            )}
          </div>
        </>
      )}

      {/* Detail modal */}
      {selectedListingId !== null && (
        <AuctionListingDetail
          listingId={selectedListingId}
          characterId={characterId}
        />
      )}
    </div>
  );
};

export default AuctionMyListingsTab;
