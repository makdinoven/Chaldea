import { Flame, LibraryBig, Trophy } from 'lucide-react';
import { HOUSE_BUFF_KIND_LABEL, percentText, type HouseBuff } from '../../../api/houses';
import { parseServerDate } from '../../../utils/serverDate';

/*
  FEAT-180 stage 6b — the acting character's running house blessings (library,
  shrine) and the trophy hall bonus, as compact chips.
*/

/** «29.10 02:37» in the player's own timezone. */
export const formatDayTime = (iso: string | null | undefined): string => {
  const d = parseServerDate(iso ?? null);
  if (!d) return '';
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
};

/** «Библиотека: +3 % ко всему опыту до 29.10 02:37». */
export const buffText = (buff: HouseBuff): string => {
  const until = formatDayTime(buff.expires_at);
  const what = HOUSE_BUFF_KIND_LABEL[buff.kind] ?? buff.kind;
  const head = buff.source === 'library' ? 'Библиотека' : 'Святилище';
  const value = buff.kind === 'character_xp' ? `+${percentText(buff.value)} % ко всему опыту` : `${what} +${percentText(buff.value)} %`;
  return `${head}: ${value}${until ? ` до ${until}` : ''}`;
};

const CHIP = 'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] leading-tight max-w-full';

interface HouseBuffChipsProps {
  buffs: HouseBuff[];
  /** Battle XP bonus from the home's trophy halls (fraction). */
  trophyBonus?: number;
  className?: string;
}

/** Chips of running house buffs; nothing when there are none. */
const HouseBuffChips = ({ buffs, trophyBonus = 0, className = '' }: HouseBuffChipsProps) => {
  if (buffs.length === 0 && trophyBonus <= 0) return null;
  return (
    <div className={`flex flex-wrap items-center gap-1.5 ${className}`}>
      {buffs.map((b) => {
        const Icon = b.source === 'library' ? LibraryBig : Flame;
        return (
          <span key={`${b.source}-${b.kind}`} className={`${CHIP} border-gold-dark/50 text-gold-light bg-gold/[0.06]`}>
            <Icon size={12} className="shrink-0" />
            <span className="break-words">{buffText(b)}</span>
          </span>
        );
      })}
      {trophyBonus > 0 && (
        <span className={`${CHIP} border-site-blue/40 text-site-blue bg-site-blue/[0.06]`}>
          <Trophy size={12} className="shrink-0" />
          <span className="break-words">Трофеи: +{percentText(trophyBonus)} % опыта за бои</span>
        </span>
      )}
    </div>
  );
};

export default HouseBuffChips;
