// FEAT-151 — CraftTab profession info card (mock 955-970): 54px gold-framed
// icon, name, «Ранг N · {rankName}», XP bar with xp/next text and the
// rank-pills row (passed = dim gold, current = highlighted, future = dimmed).
// Profession switching moved to ProfessionRail.
// FEAT-166: rendered as a section of the «Мастерская» panel (no own card).
import type { CharacterProfession } from '../../../types/professions';
import GoldIconFrame from '../shared/GoldIconFrame';
import ProgressBar from '../shared/ProgressBar';

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
    <div className="flex flex-col gap-3.5 min-w-0">
      {/* 52px icon in gold-gradient frame + name/rank */}
      <div className="flex items-center gap-3.5 min-w-0">
        <GoldIconFrame
          size={52}
          glow
          src={prof.icon}
          alt={prof.name}
          fallback={<span className="text-gold text-lg">{prof.name.charAt(0)}</span>}
        />
        <div className="flex flex-col gap-1 min-w-0">
          <span className="text-white text-[17px] font-medium leading-tight break-words">{prof.name}</span>
          <span className="text-xs text-white/60">
            Ранг {currentRank} · <span className="text-gold">{characterProfession.rank_name}</span>
          </span>
        </div>
      </div>

      {/* XP progress bar */}
      <div className="flex flex-col gap-1.5">
        <ProgressBar value={progressPercent} max={100} variant="gold" />
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
        <div className="flex gap-1.5 flex-wrap">
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
