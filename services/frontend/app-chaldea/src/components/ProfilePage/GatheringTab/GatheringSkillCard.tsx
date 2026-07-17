/**
 * Per-skill card for the "Сбор" profile tab — restyled per Claude Design
 * mock (FEAT-151). Renders a 52px category icon in a gold-gradient frame,
 * the skill name, current rank, XP progress bar (gold gradient fill),
 * current bonuses and (when not at max rank) a next-rank preview footer.
 */
import { Pickaxe, Sprout, Axe } from 'lucide-react';
import type { GatheringCategory, GatheringSkill } from '../../../types/gathering';

interface GatheringSkillCardProps {
  skill: GatheringSkill;
}

const MAX_RANK = 5;

/** Category → lucide icon (verified present in lucide-react v1.7.0). */
const CATEGORY_ICON: Record<GatheringCategory, typeof Pickaxe> = {
  ore: Pickaxe,
  herb: Sprout,
  wood: Axe,
};

/** Format a numeric bonus value, dropping the trailing ".0" when it's an integer. */
const fmt = (n: number): string => {
  if (Number.isInteger(n)) return n.toFixed(0);
  return n.toFixed(1).replace(/\.0$/, '');
};

const GatheringSkillCard = ({ skill }: GatheringSkillCardProps) => {
  // Required XP for the next rank = current bucket + remaining
  const requiredXp =
    skill.experience_to_next != null
      ? skill.experience + skill.experience_to_next
      : 0;

  const progressPct =
    skill.is_max_rank || requiredXp <= 0
      ? 100
      : Math.min(100, Math.max(0, (skill.experience / requiredXp) * 100));

  const cur = skill.current_rank_bonuses;
  const next = skill.next_rank_bonuses;
  const CategoryIcon = CATEGORY_ICON[skill.category] ?? Pickaxe;

  const bonusRows: Array<{ label: string; value: string }> = [
    { label: 'Шанс дубля', value: `+${fmt(cur.double_chance_bonus)}%` },
    { label: 'Скорость сбора', value: `+${fmt(cur.speed_bonus_pct)}%` },
    { label: 'Экономия стамины', value: `+${fmt(cur.stamina_bonus_pct)}%` },
  ];

  return (
    <div className="relative rounded-card bg-black/30 border border-gold/[0.16] shadow-card p-5 flex flex-col gap-4 h-full">
      {/* Header: 52px icon frame + name + rank */}
      <div className="flex items-center gap-3.5">
        <div className="w-[52px] h-[52px] shrink-0 rounded-[13px] p-[2px] bg-gradient-to-b from-gold-light to-gold-dark">
          <div className="w-full h-full rounded-[11px] bg-site-dark flex items-center justify-center">
            <CategoryIcon size={24} strokeWidth={1.6} className="text-gold/70" />
          </div>
        </div>
        <div className="flex flex-col gap-0.5 flex-1 min-w-0">
          <span className="text-white text-[15px] font-medium leading-tight truncate">
            {skill.name}
          </span>
          <span className="text-xs text-white/60">
            Ранг{' '}
            <span className="font-mono tabular-nums font-medium text-gold">
              {skill.current_rank}
            </span>
            <span className="font-mono tabular-nums text-white/40">/{MAX_RANK}</span>
          </span>
        </div>
      </div>

      {/* XP progress bar (gold gradient fill) */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <span className="text-[10.5px] uppercase tracking-[0.05em] text-white/50">
            {skill.is_max_rank ? 'Опыт' : 'Опыт до след. ранга'}
          </span>
          <span className="font-mono tabular-nums text-[11px] text-white/70">
            {skill.is_max_rank ? 'Макс.' : `${skill.experience} / ${requiredXp}`}
          </span>
        </div>
        <div className="stat-bar">
          <div
            className="stat-bar-fill bg-gradient-to-r from-gold-dark to-gold-light"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      {/* Current bonuses */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[10.5px] uppercase tracking-[0.06em] text-white/45">
          Текущие бонусы
        </span>
        {bonusRows.map((row) => (
          <div key={row.label} className="flex items-center justify-between">
            <span className="text-[12.5px] text-white/70">{row.label}</span>
            <span className="font-mono tabular-nums text-[12.5px] font-medium text-white">
              {row.value}
            </span>
          </div>
        ))}
      </div>

      {/* Next-rank preview / max badge (bordered-top footer) */}
      {skill.is_max_rank ? (
        <div className="mt-auto pt-3 border-t border-white/[0.08] text-center">
          <span className="gold-text text-xs font-medium uppercase tracking-[0.06em]">
            Максимальный ранг
          </span>
        </div>
      ) : next ? (
        <div className="mt-auto pt-3 border-t border-white/[0.08]">
          <span className="text-[10.5px] uppercase tracking-[0.06em] text-white/45">
            След. ранг{skill.next_rank ? ` (${skill.next_rank.rank_number})` : ''}
          </span>
          <div className="font-mono tabular-nums text-[13px] text-white/80 mt-1">
            +{fmt(next.double_chance_bonus)}% / +{fmt(next.speed_bonus_pct)}% / +
            {fmt(next.stamina_bonus_pct)}%
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default GatheringSkillCard;
