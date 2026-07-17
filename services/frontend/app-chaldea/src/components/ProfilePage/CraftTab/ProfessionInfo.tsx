// FEAT-151 — CraftTab profession info card (mock 955-970): 54px gold-framed
// icon, name, «Ранг N · {rankName}», XP bar with xp/next text and the
// rank-pills row (passed = dim gold, current = highlighted, future = dimmed).
// Profession switching moved to ProfessionRail.
import type { CharacterProfession } from '../../../types/professions';

interface ProfessionInfoProps {
  characterProfession: CharacterProfession;
}

const ProfessionInfo = ({ characterProfession }: ProfessionInfoProps) => {
  const prof = characterProfession?.profession;

  if (!prof) {
    return null;
  }

  // XP progress calculations
  const currentXp = characterProfession.experience;
  const currentRank = characterProfession.current_rank;
  const sortedRanks = [...(prof.ranks || [])].sort(
    (a, b) => a.rank_number - b.rank_number,
  );
  const nextRank = sortedRanks.find((r) => r.rank_number === currentRank + 1);
  const isMaxRank = !nextRank;
  const xpThreshold = nextRank?.required_experience ?? 0;
  const progressPercent = isMaxRank
    ? 100
    : xpThreshold > 0
      ? Math.min(100, Math.round((currentXp / xpThreshold) * 100))
      : 100;

  const rankPillClass = (rankNumber: number): string => {
    if (rankNumber < currentRank) {
      // passed
      return 'text-gold/60 bg-gold/[0.06] border-gold/25';
    }
    if (rankNumber === currentRank) {
      // current
      return 'text-gold bg-gold/15 border-gold/50';
    }
    // future
    return 'text-white/35 bg-white/[0.03] border-white/10';
  };

  return (
    <div className="relative rounded-card border border-gold/[0.16] bg-black/30 shadow-card p-4 sm:p-5 flex flex-wrap items-center gap-4">
      {/* 54px icon in gold-gradient frame */}
      <div className="w-[54px] h-[54px] shrink-0 rounded-[13px] p-[2px] bg-gradient-to-b from-gold-light to-gold-dark shadow-[0_0_14px_rgba(240,217,92,0.35)]">
        <div className="w-full h-full rounded-[11px] bg-site-dark flex items-center justify-center overflow-hidden">
          {prof.icon ? (
            <img src={prof.icon} alt={prof.name} className="w-full h-full object-cover" />
          ) : (
            <span className="text-gold text-lg">{prof.name.charAt(0)}</span>
          )}
        </div>
      </div>

      {/* Name + rank */}
      <div className="flex flex-col gap-1 min-w-0">
        <span className="text-white text-[17px] font-medium leading-tight">{prof.name}</span>
        <span className="text-xs text-white/60">
          Ранг {currentRank} · <span className="text-gold">{characterProfession.rank_name}</span>
        </span>
      </div>

      {/* XP progress bar */}
      <div className="flex flex-col gap-1.5 flex-1 min-w-[180px]">
        <div className="h-[9px] rounded-full bg-white/10 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-gold-dark to-gold-light transition-all duration-500 ease-out"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
        <span className="font-mono tabular-nums text-[11px] text-white/55 text-right">
          {isMaxRank ? (
            <>Макс. ранг &middot; {currentXp} XP</>
          ) : (
            <>{currentXp} / {xpThreshold} XP</>
          )}
        </span>
      </div>

      {/* Rank pills */}
      {sortedRanks.length > 0 && (
        <div className="flex gap-1.5 flex-wrap w-full xl:w-auto">
          {sortedRanks.map((rank) => (
            <span
              key={rank.id}
              className={`text-[10px] font-medium tracking-[0.03em] px-2 py-1 rounded-md border ${rankPillClass(rank.rank_number)}`}
            >
              {rank.name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

export default ProfessionInfo;
