import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchListings,
} from '../../redux/slices/auctionSlice';
import AuctionBrowseTab from './AuctionBrowseTab';
import AuctionMyListingsTab from './AuctionMyListingsTab';
import AuctionStorageTab from './AuctionStorageTab';

type AuctionTab = 'browse' | 'my_listings' | 'storage';

const TABS: { key: AuctionTab; label: string }[] = [
  { key: 'browse', label: 'Все лоты' },
  { key: 'my_listings', label: 'Мои лоты' },
  { key: 'storage', label: 'Склад' },
];

const AuctionPage = () => {
  const dispatch = useAppDispatch();
  const character = useAppSelector((state) => state.user.character);

  const [activeTab, setActiveTab] = useState<AuctionTab>('browse');

  const characterId = character?.id as number | undefined;

  // Fetch initial listings on mount
  useEffect(() => {
    if (characterId) {
      dispatch(fetchListings({}));
    }
  }, [dispatch, characterId]);

  if (!character || !characterId) {
    return (
      <div className="text-center py-20">
        <p className="text-white/50 text-lg">
          Выберите персонажа для доступа к аукциону
        </p>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="mt-8 mb-20"
    >
      <div className="rounded-card border border-white/10 bg-black/50 p-3 sm:p-5">
        {/* Title */}
        <div className="mb-5">
          <h1 className="gold-text text-3xl sm:text-4xl font-medium uppercase">
            Аукцион
          </h1>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-5 border-b border-white/10 overflow-x-auto">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={
                'px-4 py-2.5 text-sm font-medium uppercase tracking-wide whitespace-nowrap transition-colors duration-200 ease-site relative ' +
                (activeTab === tab.key
                  ? 'text-white'
                  : 'text-white/40 hover:text-white/70')
              }
            >
              {tab.label}
              {activeTab === tab.key && (
                <motion.div
                  layoutId="auction-tab-indicator"
                  className="absolute bottom-0 left-0 right-0 h-[2px] bg-gradient-to-r from-gold-light to-gold-dark"
                  transition={{ type: 'spring', bounce: 0.2, duration: 0.4 }}
                />
              )}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div>
          {activeTab === 'browse' && (
            <AuctionBrowseTab characterId={characterId} />
          )}
          {activeTab === 'my_listings' && (
            <AuctionMyListingsTab characterId={characterId} />
          )}
          {activeTab === 'storage' && (
            <AuctionStorageTab characterId={characterId} />
          )}
        </div>
      </div>
    </motion.div>
  );
};

export default AuctionPage;
