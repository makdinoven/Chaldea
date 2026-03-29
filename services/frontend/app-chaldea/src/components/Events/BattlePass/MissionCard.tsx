import type { BPMission } from '../../../types/battlePass';

const STUB_TYPES = ['quest_complete', 'dungeon_run', 'resource_gather'];

interface MissionCardProps {
  mission: BPMission;
  onComplete: (missionId: number) => void;
  completing: boolean;
}

const MissionCard = ({ mission, onComplete, completing }: MissionCardProps) => {
  const isStub = STUB_TYPES.includes(mission.mission_type);
  const progress = Math.min(mission.current_count, mission.target_count);
  const progressPercent = mission.target_count > 0
    ? Math.min((progress / mission.target_count) * 100, 100)
    : 0;
  const canComplete = !mission.is_completed && progress >= mission.target_count && !isStub;

  return (
    <div className="flex flex-col gap-2 p-3 sm:p-4 rounded-card bg-white/[0.07] border border-white/10">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-white text-sm sm:text-base font-medium">
            {mission.description}
          </p>
          <p className="text-white/50 text-xs mt-0.5">
            +{mission.xp_reward} XP батл пасса
          </p>
        </div>

        {isStub && (
          <span className="shrink-0 text-[10px] sm:text-xs bg-white/10 text-white/60 px-2 py-0.5 rounded-full uppercase tracking-wider font-medium">
            Скоро
          </span>
        )}

        {mission.is_completed && (
          <span className="shrink-0 text-[10px] sm:text-xs text-gold uppercase tracking-wider font-medium">
            Выполнено
          </span>
        )}

        {canComplete && (
          <button
            onClick={() => onComplete(mission.id)}
            disabled={completing}
            className="btn-blue text-xs px-3 py-1 shrink-0"
          >
            {completing ? '...' : 'Завершить'}
          </button>
        )}
      </div>

      {!isStub && (
        <div className="flex items-center gap-2">
          <div className="stat-bar flex-1">
            <div
              className={`stat-bar-fill ${mission.is_completed ? 'stat-bar-energy' : 'stat-bar-mana'}`}
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <span className="text-xs text-white/60 shrink-0 tabular-nums">
            {progress}/{mission.target_count}
          </span>
        </div>
      )}
    </div>
  );
};

export default MissionCard;
