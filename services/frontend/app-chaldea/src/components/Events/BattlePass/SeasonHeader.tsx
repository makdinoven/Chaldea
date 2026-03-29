import type { BPSeason, BPUserProgress } from '../../../types/battlePass';

interface SeasonHeaderProps {
  season: BPSeason;
  progress: BPUserProgress | null;
}

const SeasonHeader = ({ season, progress }: SeasonHeaderProps) => {
  const currentLevel = progress?.current_level ?? 0;
  const currentXp = progress?.current_xp ?? 0;
  const xpToNext = progress?.xp_to_next_level ?? 1;
  const xpPercent = xpToNext > 0 ? Math.min((currentXp / xpToNext) * 100, 100) : 0;

  const statusLabel = () => {
    if (season.status === 'grace') {
      return `Осталось ${season.days_remaining} дней для получения наград`;
    }
    if (season.status === 'ended') {
      return 'Сезон завершён, ожидайте новый';
    }
    if (season.days_remaining <= 0) {
      return 'Сезон завершён';
    }
    return `Осталось ${season.days_remaining} дней`;
  };

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex flex-col gap-1">
        <h1 className="gold-text text-2xl sm:text-3xl font-medium uppercase">
          {season.name}
        </h1>
        <p className={`text-sm ${season.status === 'grace' ? 'text-site-red' : 'text-white/60'}`}>
          {statusLabel()}
        </p>
      </div>

      <div className="flex flex-col items-start sm:items-end gap-1">
        <div className="flex items-center gap-2">
          <span className="text-white text-sm">Уровень</span>
          <span className="gold-text text-xl font-medium">{currentLevel}</span>
          <span className="text-white/40 text-sm">/ 30</span>
        </div>

        {currentLevel < 30 && (
          <div className="flex items-center gap-2 w-full sm:w-48">
            <div className="stat-bar flex-1">
              <div
                className="stat-bar-fill stat-bar-stamina"
                style={{ width: `${xpPercent}%` }}
              />
            </div>
            <span className="text-xs text-white/50 tabular-nums shrink-0">
              {currentXp}/{xpToNext}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

export default SeasonHeader;
