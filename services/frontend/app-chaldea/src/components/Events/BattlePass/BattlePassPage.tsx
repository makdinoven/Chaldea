import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { motion } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchSeason,
  fetchProgress,
  fetchMissions,
  completeMission,
  claimReward,
} from '../../../redux/actions/battlePassActions';
import {
  selectBattlePassSeason,
  selectBattlePassProgress,
  selectBattlePassMissions,
  selectBattlePassCurrentWeek,
  selectBattlePassLoading,
  selectBattlePassError,
  clearBattlePassError,
} from '../../../redux/slices/battlePassSlice';
import { activatePremium } from '../../../api/battlePass';
import SeasonHeader from './SeasonHeader';
import LevelTrack from './LevelTrack';
import MissionsPanel from './MissionsPanel';

const BattlePassPage = () => {
  const dispatch = useAppDispatch();
  const season = useAppSelector(selectBattlePassSeason);
  const progress = useAppSelector(selectBattlePassProgress);
  const missions = useAppSelector(selectBattlePassMissions);
  const currentWeek = useAppSelector(selectBattlePassCurrentWeek);
  const loading = useAppSelector(selectBattlePassLoading);
  const error = useAppSelector(selectBattlePassError);

  useEffect(() => {
    dispatch(fetchSeason());
    dispatch(fetchProgress());
    dispatch(fetchMissions());
  }, [dispatch]);

  useEffect(() => {
    if (error) {
      toast.error(error);
      dispatch(clearBattlePassError());
    }
  }, [error, dispatch]);

  const handleClaim = async (levelNumber: number, track: 'free' | 'premium') => {
    try {
      const result = await dispatch(claimReward({ level_number: levelNumber, track })).unwrap();
      toast.success(
        `Награда получена! Выдано персонажу ${result.delivered_to_character_name}`,
      );
      // Refresh progress to update claimed list
      dispatch(fetchProgress());
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось забрать награду');
    }
  };

  const handleCompleteMission = async (missionId: number) => {
    try {
      const result = await dispatch(completeMission(missionId)).unwrap();
      if (result.leveled_up) {
        toast.success(`Задание выполнено! Новый уровень: ${result.new_level}`);
      } else {
        toast.success(`Задание выполнено! +${result.xp_awarded} XP`);
      }
      dispatch(fetchMissions());
      dispatch(fetchProgress());
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось завершить задание');
    }
  };

  const handleActivatePremium = async () => {
    try {
      await activatePremium();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || 'Покупка премиума временно недоступна');
    }
  };

  if (loading && !season) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin-slow w-8 h-8 border-2 border-gold border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!season) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
        className="flex flex-col items-center justify-center py-20 gap-4"
      >
        <p className="text-white/60 text-lg">Сезон завершён, ожидайте новый</p>
        <Link to="/events" className="site-link text-sm">
          &larr; К событиям
        </Link>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex flex-col gap-6 sm:gap-8 py-6 sm:py-10"
    >
      {/* Back link */}
      <Link to="/events" className="site-link text-sm self-start">
        &larr; События
      </Link>

      {/* Season header */}
      <SeasonHeader season={season} progress={progress} />

      {/* Level track */}
      <section className="gray-bg p-4 sm:p-6">
        <h2 className="gold-text text-xl font-medium uppercase mb-4">
          Награды
        </h2>
        <LevelTrack
          levels={season.levels}
          progress={progress}
          onClaim={handleClaim}
          onActivatePremium={handleActivatePremium}
        />
      </section>

      {/* Missions */}
      <section className="gray-bg p-4 sm:p-6">
        <MissionsPanel
          missions={missions}
          currentWeek={currentWeek}
          onComplete={handleCompleteMission}
        />
      </section>
    </motion.div>
  );
};

export default BattlePassPage;
