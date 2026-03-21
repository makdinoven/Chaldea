import { useAppSelector } from '../../../redux/store';
import { selectProfile } from '../../../redux/slices/profileSlice';
import AvatarEquipmentGrid from './AvatarEquipmentGrid';
import FastSlots from '../EquipmentPanel/FastSlots';

const CenterColumn = () => {
  const profile = useAppSelector(selectProfile);

  return (
    <div className="flex flex-col items-center gap-4 flex-1 min-w-0 w-full order-1 lg:order-2">
      {/* Avatar with equipment slots */}
      <AvatarEquipmentGrid />

      {/* Level / XP progress bar */}
      {profile && (
        <div className="w-full max-w-[280px] flex flex-col gap-[10px]">
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
          {/* Stat Points */}
          <div className="flex items-center justify-center gap-2">
            <span className="gold-text text-sm font-medium uppercase">
              Очки прокачки
            </span>
            <div className="flex items-center gap-1">
              <div className="skill-point-dot" />
              <span className="text-site-blue text-sm font-medium">
                {profile.stat_points}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Fast slots in horizontal layout */}
      <div className="w-full flex justify-center">
        <FastSlots />
      </div>
    </div>
  );
};

export default CenterColumn;
