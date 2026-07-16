import type { LeaderboardEntry } from '../../../api/homeStats';
import { formatValue, LeaderAvatar } from './common';

/** List row for ranks below the podium (4+): rank, avatar, name, value. */
const RankRow = ({ entry, rank }: { entry: LeaderboardEntry; rank: number }) => (
  <div className="flex items-center gap-3 rounded-[10px] px-3 py-3 transition-colors duration-200 ease-site hover:bg-white/[0.05] sm:gap-4 sm:px-4">
    <span className="w-[22px] shrink-0 text-center text-[15px] font-medium text-white/40 tabular-nums">
      {rank}
    </span>
    <LeaderAvatar
      src={entry.avatar}
      alt={entry.name}
      className="h-[38px] w-[38px] shrink-0 rounded-full bg-white/5 object-cover"
    />
    <span className="min-w-0 flex-1 truncate text-[15px] text-white">{entry.name}</span>
    <span className="gold-text shrink-0 text-[15px] font-medium tabular-nums">
      {formatValue(entry.value)}
    </span>
  </div>
);

export default RankRow;
