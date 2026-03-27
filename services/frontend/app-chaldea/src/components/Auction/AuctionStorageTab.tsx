import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchStorage,
  createListing,
  fetchMyListings,
  fetchListings,
  selectStorageItems,
  selectStorageTotalGold,
  selectStorageLoading,
  selectStorageError,
  selectActionLoading,
} from '../../redux/slices/auctionSlice';
import { RARITY_COLOR_MAP } from './AuctionListingCard';
import type { AuctionStorageItemResponse } from '../../types/auction';

interface AuctionStorageTabProps {
  characterId: number;
}

const SOURCE_LABELS: Record<string, string> = {
  purchase: 'Покупка',
  expired: 'Истёкший лот',
  cancelled: 'Отмена',
  sale_proceeds: 'Выручка',
  deposit: 'Размещено',
};

/* -- Create Listing Inline Form -- */

const CreateListingForm = ({
  storageItem,
  characterId,
  onClose,
  onSuccess,
}: {
  storageItem: AuctionStorageItemResponse;
  characterId: number;
  onClose: () => void;
  onSuccess: () => void;
}) => {
  const dispatch = useAppDispatch();
  const actionLoading = useAppSelector(selectActionLoading);

  const [startPrice, setStartPrice] = useState('');
  const [buyoutPrice, setBuyoutPrice] = useState('');

  const handleSubmit = async () => {
    const start = parseInt(startPrice, 10);
    if (isNaN(start) || start <= 0) {
      toast.error('Начальная цена должна быть больше 0');
      return;
    }
    const buyout = buyoutPrice ? parseInt(buyoutPrice, 10) : undefined;
    if (buyout !== undefined && (isNaN(buyout) || buyout <= start)) {
      toast.error('Цена выкупа должна быть больше начальной цены');
      return;
    }

    try {
      await dispatch(
        createListing({
          character_id: characterId,
          storage_id: storageItem.id,
          start_price: start,
          buyout_price: buyout ?? null,
        }),
      ).unwrap();
      toast.success('Предмет выставлен на аукцион');
      dispatch(fetchMyListings(characterId));
      dispatch(fetchListings({}));
      onSuccess();
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось выставить лот');
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className="overflow-hidden"
    >
      <div className="p-3 mt-2 rounded-card bg-white/5 border border-white/10 space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-white text-sm font-medium">
            Выставить: {storageItem.item?.name ?? 'Предмет'}
            {storageItem.quantity > 1 && ` x${storageItem.quantity}`}
          </p>
          <button
            onClick={onClose}
            className="text-white/40 hover:text-white text-sm transition-colors"
          >
            &times;
          </button>
        </div>

        <div className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1">
            <label className="text-white/60 text-xs block mb-1">Начальная цена (зол.)</label>
            <input
              type="number"
              value={startPrice}
              onChange={(e) => setStartPrice(e.target.value)}
              placeholder="100"
              min={1}
              className="input-underline text-sm w-full"
            />
          </div>
          <div className="flex-1">
            <label className="text-white/60 text-xs block mb-1">Цена выкупа (необязательно)</label>
            <input
              type="number"
              value={buyoutPrice}
              onChange={(e) => setBuyoutPrice(e.target.value)}
              placeholder="500"
              min={1}
              className="input-underline text-sm w-full"
            />
          </div>
        </div>

        <p className="text-white/30 text-xs">
          Если указана цена выкупа, покупатель сможет выкупить сразу по этой цене
        </p>

        <button
          onClick={handleSubmit}
          disabled={actionLoading || !startPrice}
          className="btn-blue w-full !text-sm disabled:opacity-50"
        >
          {actionLoading ? 'Создание...' : 'Выставить на аукцион'}
        </button>
      </div>
    </motion.div>
  );
};

/* -- Storage Row -- */

const StorageRow = ({
  item,
  characterId,
  listingFormId,
  onOpenListingForm,
  onCloseListingForm,
  onListingSuccess,
}: {
  item: AuctionStorageItemResponse;
  characterId: number;
  listingFormId: number | null;
  onOpenListingForm: (id: number) => void;
  onCloseListingForm: () => void;
  onListingSuccess: () => void;
}) => {
  const rarityColor = item.item
    ? (RARITY_COLOR_MAP[item.item.item_rarity] ?? 'text-white')
    : 'text-gold';

  const isGold = item.gold_amount > 0 && !item.item;
  const isFormOpen = listingFormId === item.id;

  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: 10 },
        visible: { opacity: 1, y: 0 },
      }}
    >
      <div className="flex items-center gap-3 p-3 rounded-card bg-white/5 transition-colors duration-200 ease-site">
        {/* Image / Icon */}
        <div className="w-10 h-10 rounded-full bg-white/5 flex-shrink-0 flex items-center justify-center overflow-hidden">
          {isGold ? (
            <span className="gold-text text-lg font-medium">$</span>
          ) : item.item?.image ? (
            <img src={item.item.image} alt={item.item.name} className="w-full h-full object-cover" />
          ) : (
            <span className="text-white/30 text-lg">?</span>
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <p className={`${rarityColor} text-sm font-medium truncate`}>
            {isGold
              ? `${item.gold_amount.toLocaleString('ru-RU')} золота`
              : item.item?.name ?? 'Неизвестный предмет'}
          </p>
          <p className="text-white/40 text-xs">
            {SOURCE_LABELS[item.source] ?? item.source}
            {!isGold && item.quantity > 1 && ` x${item.quantity}`}
          </p>
        </div>

        {/* Action button for items (not gold) */}
        {!isGold && item.item && (
          <button
            onClick={() => isFormOpen ? onCloseListingForm() : onOpenListingForm(item.id)}
            className={
              'text-xs font-medium px-3 py-1.5 rounded-card transition-all duration-200 flex-shrink-0 ' +
              (isFormOpen
                ? 'bg-white/10 text-white/60'
                : 'bg-gradient-to-r from-[#2e353e] to-[#537895] text-white hover:shadow-hover')
            }
          >
            {isFormOpen ? 'Отмена' : 'Выставить'}
          </button>
        )}
      </div>

      {/* Inline listing form */}
      <AnimatePresence>
        {isFormOpen && !isGold && (
          <CreateListingForm
            storageItem={item}
            characterId={characterId}
            onClose={onCloseListingForm}
            onSuccess={onListingSuccess}
          />
        )}
      </AnimatePresence>
    </motion.div>
  );
};

/* -- Main Component -- */

const AuctionStorageTab = ({ characterId }: AuctionStorageTabProps) => {
  const dispatch = useAppDispatch();
  const storageItems = useAppSelector(selectStorageItems);
  const totalGold = useAppSelector(selectStorageTotalGold);
  const loading = useAppSelector(selectStorageLoading);
  const error = useAppSelector(selectStorageError);

  const [listingFormId, setListingFormId] = useState<number | null>(null);

  useEffect(() => {
    dispatch(fetchStorage(characterId));
  }, [dispatch, characterId]);

  const handleListingSuccess = () => {
    setListingFormId(null);
    dispatch(fetchStorage(characterId));
  };

  return (
    <div>
      {/* Info message */}
      <div className="mb-4 p-3 rounded-card bg-white/5 border border-white/10">
        <p className="text-white/50 text-sm text-center">
          Для забора предметов и золота подойдите к НПС-Аукционисту
        </p>
      </div>

      {/* Gold summary */}
      {totalGold > 0 && (
        <div className="mb-4 p-3 rounded-card bg-white/5 flex items-center justify-between">
          <p className="text-white/60 text-sm">
            Всего золота на складе: <span className="gold-text font-medium">{totalGold.toLocaleString('ru-RU')}</span>
          </p>
        </div>
      )}

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

      {/* Empty state */}
      {!loading && !error && storageItems.length === 0 && (
        <div className="text-center py-12">
          <p className="text-white/50 text-lg">Склад пуст</p>
          <p className="text-white/30 text-sm mt-2">
            Положите предметы на склад через НПС-Аукциониста, чтобы выставить их на аукцион
          </p>
        </div>
      )}

      {/* Items */}
      {!loading && storageItems.length > 0 && (
        <motion.div
          initial="hidden"
          animate="visible"
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.04 } },
          }}
          className="space-y-2"
        >
          {storageItems.map((item) => (
            <StorageRow
              key={item.id}
              item={item}
              characterId={characterId}
              listingFormId={listingFormId}
              onOpenListingForm={setListingFormId}
              onCloseListingForm={() => setListingFormId(null)}
              onListingSuccess={handleListingSuccess}
            />
          ))}
        </motion.div>
      )}
    </div>
  );
};

export default AuctionStorageTab;
