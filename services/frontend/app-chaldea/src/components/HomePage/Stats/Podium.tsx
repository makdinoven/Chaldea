import type { LeaderboardEntry } from '../../../api/homeStats';
import { formatValue, LeaderAvatar } from './common';

interface PodiumSlotConfig {
  /** Avatar size classes (smaller below 420px so three slots fit at 360px). */
  avatar: string;
  /** Gold ring for rank 1; silver/bronze medal rings for ranks 2/3. */
  ring: string;
  glow: string;
  /** Pedestal heights per reference: 132 / 96 / 76 px. */
  pedestal: string;
  /** Medal-colored rank numeral (gold / silver / bronze — podium semantics). */
  medal: string;
}

const SLOT_BY_RANK: Record<number, PodiumSlotConfig> = {
  1: {
    avatar: 'w-[88px] h-[88px] min-[420px]:w-[104px] min-[420px]:h-[104px]',
    ring: 'bg-gradient-to-b from-gold-light to-gold-dark',
    glow: 'shadow-[0_0_26px_rgba(240,217,92,0.5)]',
    pedestal: 'h-[132px]',
    medal: 'text-gold',
  },
  2: {
    avatar: 'w-[72px] h-[72px] min-[420px]:w-[82px] min-[420px]:h-[82px]',
    ring: 'bg-gradient-to-b from-[#cfcfcf] to-[#8f8f8f]',
    glow: '',
    pedestal: 'h-[96px]',
    medal: 'text-[#cfcfcf]',
  },
  3: {
    avatar: 'w-[68px] h-[68px] min-[420px]:w-[76px] min-[420px]:h-[76px]',
    ring: 'bg-gradient-to-b from-[#c9915a] to-[#8a5a2b]',
    glow: '',
    pedestal: 'h-[76px]',
    medal: 'text-[#c9915a]',
  },
};

const CrownIcon = () => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M3 7l4 4 5-7 5 7 4-4-2 12H5L3 7z" />
  </svg>
);

const PodiumSlot = ({ entry, rank }: { entry: LeaderboardEntry; rank: number }) => {
  const cfg = SLOT_BY_RANK[rank];
  return (
    <div className="flex min-w-0 flex-1 max-w-[220px] flex-col items-center">
      <div className="flex h-[26px] items-end text-gold">{rank === 1 && <CrownIcon />}</div>
      <div className={`rounded-full p-[3px] ${cfg.ring} ${cfg.glow}`}>
        <LeaderAvatar
          src={entry.avatar}
          alt={entry.name}
          className={`${cfg.avatar} rounded-full object-cover bg-site-dark`}
        />
      </div>
      <span className="mt-3 w-full truncate text-center text-[15px] font-medium text-white">
        {entry.name}
      </span>
      <span className="mt-0.5 gold-text text-[15px] font-medium tabular-nums">
        {formatValue(entry.value)}
      </span>
      <div
        className={`mt-3.5 flex w-full items-start justify-center rounded-t-xl border border-b-0 border-gold/25 bg-gradient-to-b from-gold/15 to-gold/[0.02] pt-3 ${cfg.pedestal}`}
      >
        <span className={`text-3xl sm:text-[38px] font-medium tabular-nums ${cfg.medal}`}>
          {rank}
        </span>
      </div>
    </div>
  );
};

/**
 * Podium for the top-3: visual order is rank 2 · rank 1 (center, larger) · rank 3.
 * Handles partial boards (1-2 entries) by rendering only the existing slots.
 */
const Podium = ({ entries }: { entries: LeaderboardEntry[] }) => {
  const slots = [
    { entry: entries[1], rank: 2 },
    { entry: entries[0], rank: 1 },
    { entry: entries[2], rank: 3 },
  ].filter((s): s is { entry: LeaderboardEntry; rank: number } => Boolean(s.entry));

  return (
    <div className="mx-auto flex w-full max-w-[760px] items-end justify-center gap-2 px-1.5 pb-2 pt-7 md:gap-[22px] md:px-[30px] md:pt-10">
      {slots.map((slot) => (
        <PodiumSlot key={slot.entry.character_id} entry={slot.entry} rank={slot.rank} />
      ))}
    </div>
  );
};

export default Podium;
