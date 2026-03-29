import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { motion } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { fetchSeason, fetchProgress } from '../../redux/actions/battlePassActions';
import {
  selectBattlePassSeason,
  selectBattlePassProgress,
  selectBattlePassLoading,
  selectBattlePassError,
  clearBattlePassError,
} from '../../redux/slices/battlePassSlice';

const EventsPage = () => {
  const dispatch = useAppDispatch();
  const season = useAppSelector(selectBattlePassSeason);
  const progress = useAppSelector(selectBattlePassProgress);
  const loading = useAppSelector(selectBattlePassLoading);
  const error = useAppSelector(selectBattlePassError);

  useEffect(() => {
    dispatch(fetchSeason());
    dispatch(fetchProgress());
  }, [dispatch]);

  useEffect(() => {
    if (error) {
      toast.error(error);
      dispatch(clearBattlePassError());
    }
  }, [error, dispatch]);

  const currentLevel = progress?.current_level ?? 0;
  const currentXp = progress?.current_xp ?? 0;
  const xpToNext = progress?.xp_to_next_level ?? 1;
  const xpPercent = xpToNext > 0 ? Math.min((currentXp / xpToNext) * 100, 100) : 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex flex-col gap-6 sm:gap-8 py-6 sm:py-10"
    >
      <h1 className="gold-text text-3xl sm:text-4xl font-medium uppercase">
        События
      </h1>

      {loading && !season && (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin-slow w-8 h-8 border-2 border-gold border-t-transparent rounded-full" />
        </div>
      )}

      {/* Battle Pass card */}
      {season && (
        <Link
          to="/events/battle-pass"
          className="group block"
        >
          <div className="gold-outline hover-gold-overlay relative rounded-card gray-bg p-5 sm:p-6 transition-shadow duration-200 ease-site shadow-card hover:shadow-hover">
            <div className="relative z-10 flex flex-col gap-3">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase">
                  {season.name}
                </h2>
                {season.status === 'grace' ? (
                  <span className="text-site-red text-sm">
                    Осталось {season.days_remaining} дней для получения наград
                  </span>
                ) : season.status === 'ended' ? (
                  <span className="text-white/40 text-sm">
                    Сезон завершён
                  </span>
                ) : (
                  <span className="text-white/60 text-sm">
                    Осталось {season.days_remaining} дней
                  </span>
                )}
              </div>

              {/* Progress */}
              <div className="flex items-center gap-3">
                <span className="text-white text-sm">Уровень</span>
                <span className="gold-text text-lg font-medium">{currentLevel}</span>
                <span className="text-white/30 text-sm">/ 30</span>

                <div className="stat-bar flex-1 max-w-xs">
                  <div
                    className="stat-bar-fill stat-bar-stamina"
                    style={{ width: `${xpPercent}%` }}
                  />
                </div>
              </div>

              <span className="text-site-blue text-sm group-hover:underline">
                Открыть батл пасс &rarr;
              </span>
            </div>
          </div>
        </Link>
      )}

      {!loading && !season && (
        <div className="text-white/40 text-center py-12">
          Нет активных событий
        </div>
      )}
    </motion.div>
  );
};

export default EventsPage;
