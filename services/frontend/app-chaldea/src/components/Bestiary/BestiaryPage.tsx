import { useEffect } from 'react';
import { motion } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchBestiary,
  selectBestiaryLoading,
  selectBestiaryError,
  selectBestiaryEntries,
} from '../../redux/slices/bestiarySlice';
import GrimoireBook from './GrimoireBook';

const BestiaryPage = () => {
  const dispatch = useAppDispatch();
  const loading = useAppSelector(selectBestiaryLoading);
  const error = useAppSelector(selectBestiaryError);
  const entries = useAppSelector(selectBestiaryEntries);

  // Get active character ID (may be null if not logged in or no character)
  const characterId = useAppSelector(
    (state) => state.user.character?.id as number | undefined,
  );

  useEffect(() => {
    dispatch(fetchBestiary(characterId));
  }, [dispatch, characterId]);

  // Loading state
  if (loading) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
        className="flex flex-col items-center justify-center py-20 gap-4"
      >
        <div className="w-10 h-10 border-4 border-white/20 border-t-gold rounded-full animate-spin" />
        <p className="text-white/50 text-sm">Загрузка гримуара...</p>
      </motion.div>
    );
  }

  // Error state
  if (error) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
        className="flex flex-col items-center justify-center py-20 gap-4"
      >
        <p className="text-site-red text-base">{error}</p>
        <button
          onClick={() => dispatch(fetchBestiary(characterId))}
          className="btn-blue text-sm px-5 py-2"
        >
          Повторить
        </button>
      </motion.div>
    );
  }

  // Empty state
  if (entries.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
        className="flex flex-col items-center justify-center py-20 gap-4"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="w-16 h-16 text-white/10"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={0.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
          />
        </svg>
        <p className="text-white/40 text-base">
          Гримуар пуст — монстры ещё не добавлены
        </p>
      </motion.div>
    );
  }

  // Loaded state
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="py-6 sm:py-8 md:py-10"
    >
      <GrimoireBook />
    </motion.div>
  );
};

export default BestiaryPage;
