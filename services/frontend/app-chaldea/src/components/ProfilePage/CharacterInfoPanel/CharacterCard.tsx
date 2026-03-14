import { useAppSelector } from '../../../redux/store';
import { selectProfile, selectRaceInfo } from '../../../redux/slices/profileSlice';
import { RACE_NAMES, CLASS_NAMES } from '../constants';
import goldCoinsIcon from '../../../assets/icons/gold-coins.svg';

export default function CharacterCard() {
  const profile = useAppSelector(selectProfile);
  const raceInfo = useAppSelector(selectRaceInfo);

  if (!profile) {
    return (
      <div className="flex flex-col items-center gap-3 p-4">
        <div className="w-[180px] h-[220px] rounded-card bg-white/5 animate-pulse" />
        <div className="h-6 w-32 bg-white/5 rounded animate-pulse" />
      </div>
    );
  }

  const raceName = raceInfo ? (RACE_NAMES[raceInfo.id_race] ?? 'Неизвестная раса') : '—';
  const className = raceInfo ? (CLASS_NAMES[raceInfo.id_class] ?? 'Неизвестный класс') : '—';

  return (
    <div className="flex flex-col items-center gap-3 p-4">
      {/* Portrait / Avatar */}
      <div className="gold-outline relative rounded-card w-[180px] h-[220px] overflow-hidden bg-black/30">
        {profile.avatar ? (
          <img
            src={profile.avatar}
            alt={profile.name}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-white/20">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-20 h-20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
          </div>
        )}
      </div>

      {/* Name */}
      <h3 className="gold-text text-xl font-medium uppercase text-center">
        {profile.name}
      </h3>

      {/* Active Title */}
      {profile.active_title && (
        <span className="text-site-blue text-sm italic text-center">
          {profile.active_title}
        </span>
      )}

      {/* Race / Class */}
      <div className="flex items-center gap-2 text-sm text-white/80">
        <span>{raceName}</span>
        <span className="text-white/30">|</span>
        <span>{className}</span>
      </div>

      {/* Level + Progress Bar */}
      <div className="w-[210px] flex flex-col gap-[10px]">
        <div className="flex justify-between items-end">
          <span className="gold-text text-base font-medium uppercase">
            LVL {profile.level}
          </span>
          <span className="text-white text-sm font-medium uppercase text-right">
            {Math.round(profile.level_progress?.current_exp_in_level ?? 0)}
            /{Math.round(profile.level_progress?.exp_to_next_level ?? 0)}
          </span>
        </div>
        <div className="stat-bar">
          <div
            className="stat-bar-fill"
            style={{
              width: `${Math.min((profile.level_progress?.progress_fraction ?? 0) * 100, 100)}%`,
              background: 'linear-gradient(176.46deg, #FFF9B8 2.91%, #BCAB4C 237.31%)',
            }}
          />
        </div>
      </div>

      {/* Stat Points */}
      <div className="flex items-center gap-2">
        <span className="gold-text text-base font-medium uppercase">
          Очки прокачки
        </span>
        <div className="flex items-center gap-1">
          <div className="skill-point-dot" />
          <span className="text-site-blue text-sm font-medium">
            {profile.stat_points}
          </span>
        </div>
      </div>

      {/* Currency */}
      <div className="flex items-center gap-2 mt-1">
        <img src={goldCoinsIcon} alt="" className="w-5 h-5" />
        <span className="gold-text text-sm font-medium">
          {profile.currency_balance.toLocaleString('ru-RU')}
        </span>
      </div>
    </div>
  );
}
