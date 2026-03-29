import { useState, useMemo } from 'react';
import type { BPMission } from '../../../types/battlePass';
import MissionCard from './MissionCard';

interface MissionsPanelProps {
  missions: BPMission[];
  currentWeek: number;
  onComplete: (missionId: number) => void;
}

const MissionsPanel = ({ missions, currentWeek, onComplete }: MissionsPanelProps) => {
  const [completingId, setCompletingId] = useState<number | null>(null);

  // Group missions by week
  const weekGroups = useMemo(() => {
    const groups: Record<number, BPMission[]> = {};
    for (const m of missions) {
      if (!groups[m.week_number]) groups[m.week_number] = [];
      groups[m.week_number].push(m);
    }
    return groups;
  }, [missions]);

  const weekNumbers = Object.keys(weekGroups).map(Number).sort((a, b) => a - b);

  // Current week expanded by default, past weeks collapsed
  const [expandedWeeks, setExpandedWeeks] = useState<Set<number>>(() => new Set([currentWeek]));

  const toggleWeek = (week: number) => {
    setExpandedWeeks((prev) => {
      const next = new Set(prev);
      if (next.has(week)) {
        next.delete(week);
      } else {
        next.add(week);
      }
      return next;
    });
  };

  const handleComplete = async (missionId: number) => {
    setCompletingId(missionId);
    try {
      await onComplete(missionId);
    } finally {
      setCompletingId(null);
    }
  };

  if (missions.length === 0) {
    return (
      <div className="text-white/40 text-sm text-center py-6">
        Нет доступных заданий
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase">
        Задания
      </h2>

      {weekNumbers.map((week) => {
        const isExpanded = expandedWeeks.has(week);
        const weekMissions = weekGroups[week];
        const completedCount = weekMissions.filter((m) => m.is_completed).length;
        const isCurrent = week === currentWeek;

        return (
          <div key={week} className="rounded-card border border-white/10 overflow-hidden">
            <button
              onClick={() => toggleWeek(week)}
              className="w-full flex items-center justify-between p-3 sm:p-4 bg-white/[0.04] hover:bg-white/[0.07] transition-colors duration-200 ease-site text-left"
            >
              <div className="flex items-center gap-2">
                <span className="text-white text-sm sm:text-base font-medium">
                  Неделя {week}
                </span>
                {isCurrent && (
                  <span className="text-[10px] bg-site-blue/20 text-site-blue px-2 py-0.5 rounded-full uppercase tracking-wider font-medium">
                    Текущая
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-white/40">
                  {completedCount}/{weekMissions.length}
                </span>
                <span
                  className={`text-white/40 text-sm transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
                >
                  &#9660;
                </span>
              </div>
            </button>

            {isExpanded && (
              <div className="flex flex-col gap-2 p-2 sm:p-3">
                {weekMissions.map((mission) => (
                  <MissionCard
                    key={mission.id}
                    mission={mission}
                    onComplete={handleComplete}
                    completing={completingId === mission.id}
                  />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default MissionsPanel;
