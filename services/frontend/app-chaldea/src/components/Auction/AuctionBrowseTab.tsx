import { useEffect } from 'react';
import { motion } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchListings,
  setListingsPage,
  setSelectedListingId,
  selectListings,
  selectListingsLoading,
  selectListingsError,
  selectListingsTotal,
  selectListingsPage,
  selectListingsPerPage,
  selectFilters,
  selectSelectedListingId,
} from '../../redux/slices/auctionSlice';
import type { AuctionSortOption } from '../../types/auction';
import AuctionFilters from './AuctionFilters';
import AuctionListingCard from './AuctionListingCard';
import AuctionListingDetail from './AuctionListingDetail';

interface AuctionBrowseTabProps {
  characterId: number;
}

const AuctionBrowseTab = ({ characterId }: AuctionBrowseTabProps) => {
  const dispatch = useAppDispatch();
  const listings = useAppSelector(selectListings);
  const loading = useAppSelector(selectListingsLoading);
  const error = useAppSelector(selectListingsError);
  const total = useAppSelector(selectListingsTotal);
  const page = useAppSelector(selectListingsPage);
  const perPage = useAppSelector(selectListingsPerPage);
  const filters = useAppSelector(selectFilters);
  const selectedListingId = useAppSelector(selectSelectedListingId);

  const totalPages = Math.max(1, Math.ceil(total / perPage));

  // Fetch listings when filters or page change
  useEffect(() => {
    dispatch(
      fetchListings({
        page,
        per_page: perPage,
        item_type: filters.itemType,
        rarity: filters.rarity,
        sort: filters.sort as AuctionSortOption,
        search: filters.search || null,
      }),
    );
  }, [dispatch, page, perPage, filters]);

  const handleCardClick = (id: number) => {
    dispatch(setSelectedListingId(id));
  };

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      dispatch(setListingsPage(newPage));
    }
  };

  return (
    <div>
      {/* Filters */}
      <div className="mb-5">
        <AuctionFilters />
      </div>

      {/* Error */}
      {error && (
        <div className="text-center py-8">
          <p className="text-site-red">{error}</p>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && listings.length === 0 && (
        <div className="text-center py-12">
          <p className="text-white/50 text-lg">Нет активных лотов</p>
          <p className="text-white/30 text-sm mt-2">Попробуйте изменить фильтры</p>
        </div>
      )}

      {/* Listing grid */}
      {!loading && listings.length > 0 && (
        <motion.div
          initial="hidden"
          animate="visible"
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.05 } },
          }}
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
        >
          {listings.map((listing) => (
            <AuctionListingCard
              key={listing.id}
              listing={listing}
              onClick={handleCardClick}
            />
          ))}
        </motion.div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-6">
          <button
            onClick={() => handlePageChange(page - 1)}
            disabled={page <= 1}
            className="text-white/50 hover:text-white disabled:text-white/20 transition-colors px-3 py-1"
          >
            &larr;
          </button>

          {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
            let pageNum: number;
            if (totalPages <= 7) {
              pageNum = i + 1;
            } else if (page <= 4) {
              pageNum = i + 1;
            } else if (page >= totalPages - 3) {
              pageNum = totalPages - 6 + i;
            } else {
              pageNum = page - 3 + i;
            }
            return (
              <button
                key={pageNum}
                onClick={() => handlePageChange(pageNum)}
                className={
                  'px-3 py-1 rounded-card text-sm transition-colors duration-200 ease-site ' +
                  (pageNum === page
                    ? 'gold-text bg-white/10 font-medium'
                    : 'text-white/50 hover:text-white')
                }
              >
                {pageNum}
              </button>
            );
          })}

          <button
            onClick={() => handlePageChange(page + 1)}
            disabled={page >= totalPages}
            className="text-white/50 hover:text-white disabled:text-white/20 transition-colors px-3 py-1"
          >
            &rarr;
          </button>

          <span className="text-white/30 text-xs ml-2">
            {total} {total === 1 ? 'лот' : total < 5 ? 'лота' : 'лотов'}
          </span>
        </div>
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

export default AuctionBrowseTab;
