import { useEffect } from 'react';
import { motion } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchBestiary,
  selectBestiaryLoading,
  selectBestiaryError,
  selectBestiaryEntries,
} from '../../redux/slices/bestiarySlice';
import ScrollBestiary from './ScrollBestiary';

const titleFont = "'MedievalSharp', 'Georgia', serif";
const scriptFont = "'Marck Script', 'Georgia', cursive";

const BestiaryPage = () => {
  const dispatch = useAppDispatch();
  const loading = useAppSelector(selectBestiaryLoading);
  const error = useAppSelector(selectBestiaryError);
  const entries = useAppSelector(selectBestiaryEntries);

  const characterId = useAppSelector(
    (state) => state.user.character?.id as number | undefined,
  );

  useEffect(() => {
    dispatch(fetchBestiary(characterId));
  }, [dispatch, characterId]);

  if (loading) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
        className="flex flex-col items-center justify-center py-20 gap-4"
      >
        <div className="w-10 h-10 border-4 border-white/20 border-t-gold rounded-full animate-spin" />
        <p className="text-white/50 text-sm" style={{ fontFamily: scriptFont }}>
          Свиток разворачивается...
        </p>
      </motion.div>
    );
  }

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

  if (entries.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
        className="flex flex-col items-center justify-center py-20 gap-4"
      >
        <p className="text-white/40 text-base" style={{ fontFamily: scriptFont }}>
          Свиток пуст — монстры ещё не добавлены
        </p>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="py-6 sm:py-8 md:py-10"
    >
      <ScrollBestiary />
    </motion.div>
  );
};

export default BestiaryPage;
