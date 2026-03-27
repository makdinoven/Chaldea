import { motion } from 'motion/react';
import type { AuctionListingResponse } from '../../types/auction';

const RARITY_COLOR_MAP: Record<string, string> = {
  common: 'text-rarity-common',
  rare: 'text-rarity-rare',
  epic: 'text-rarity-epic',
  mythical: 'text-rarity-mythical',
  legendary: 'text-rarity-legendary',
  divine: 'text-gold',
  demonic: 'text-site-red',
};

const RARITY_BORDER_MAP: Record<string, string> = {
  common: 'border-rarity-common/30',
  rare: 'border-rarity-rare/40',
  epic: 'border-rarity-epic/40',
  mythical: 'border-rarity-mythical/40',
  legendary: 'border-rarity-legendary/40',
  divine: 'border-gold/40',
  demonic: 'border-site-red/40',
};

const formatTimeRemaining = (seconds: number): string => {
  if (seconds <= 0) return 'Завершён';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours >= 24) {
    const days = Math.floor(hours / 24);
    const remainingHours = hours % 24;
    return `${days}д ${remainingHours}ч`;
  }
  if (hours > 0) return `${hours}ч ${minutes}м`;
  return `${minutes}м`;
};

interface AuctionListingCardProps {
  listing: AuctionListingResponse;
  onClick: (id: number) => void;
}

const AuctionListingCard = ({ listing, onClick }: AuctionListingCardProps) => {
  const rarityColor = RARITY_COLOR_MAP[listing.item.item_rarity] ?? 'text-white';
  const rarityBorder = RARITY_BORDER_MAP[listing.item.item_rarity] ?? 'border-white/10';

  const displayPrice = listing.current_bid > 0 ? listing.current_bid : listing.start_price;

  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: 10 },
        visible: { opacity: 1, y: 0 },
      }}
      whileHover={{ scale: 1.02 }}
      transition={{ duration: 0.2 }}
      onClick={() => onClick(listing.id)}
      className={
        `gray-bg p-4 rounded-card shadow-card cursor-pointer ` +
        `border border-transparent ${rarityBorder} ` +
        `hover:shadow-hover transition-shadow duration-200 ease-site`
      }
    >
      {/* Item image + info */}
      <div className="flex items-start gap-3">
        {/* Image */}
        <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-full bg-white/5 flex-shrink-0 flex items-center justify-center overflow-hidden">
          {listing.item.image ? (
            <img
              src={listing.item.image}
              alt={listing.item.name}
              className="w-full h-full object-cover"
            />
          ) : (
            <span className="text-white/30 text-2xl">?</span>
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <h3 className={`${rarityColor} font-medium text-sm sm:text-base truncate`}>
            {listing.item.name}
          </h3>
          {listing.quantity > 1 && (
            <span className="text-white/60 text-xs">x{listing.quantity}</span>
          )}
          <p className="text-white/50 text-xs mt-0.5 truncate">
            {listing.seller_name}
          </p>
        </div>
      </div>

      {/* Price + time */}
      <div className="mt-3 flex items-end justify-between gap-2">
        <div className="min-w-0">
          <p className="text-white/50 text-xs">
            {listing.current_bid > 0 ? 'Текущая ставка' : 'Начальная цена'}
          </p>
          <p className="gold-text text-base sm:text-lg font-medium">
            {displayPrice.toLocaleString('ru-RU')} зол.
          </p>
          {listing.buyout_price && (
            <p className="text-site-blue text-xs mt-0.5">
              Выкуп: {listing.buyout_price.toLocaleString('ru-RU')} зол.
            </p>
          )}
        </div>

        <div className="flex flex-col items-end flex-shrink-0">
          <span className="text-white/40 text-xs">
            {formatTimeRemaining(listing.time_remaining_seconds)}
          </span>
          {listing.bid_count > 0 && (
            <span className="text-white/30 text-xs mt-0.5">
              {listing.bid_count} {listing.bid_count === 1 ? 'ставка' : listing.bid_count < 5 ? 'ставки' : 'ставок'}
            </span>
          )}
        </div>
      </div>
    </motion.div>
  );
};

export { formatTimeRemaining, RARITY_COLOR_MAP };
export default AuctionListingCard;
