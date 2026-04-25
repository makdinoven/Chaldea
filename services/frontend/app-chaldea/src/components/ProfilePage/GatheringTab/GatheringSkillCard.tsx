/**
 * Per-skill card for the "Сбор" profile tab.
 * Renders the skill name, current rank, XP progress bar, current bonuses
 * and (when not at max rank) a preview of the next-rank bonuses.
 */
import type { GatheringSkill } from '../../../types/gathering';

interface GatheringSkillCardProps {
  skill: GatheringSkill;
}

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

  return (
    <div className="gray-bg p-5 flex flex-col gap-4 rounded-card">
      {/* Header: name + rank */}
      <div className="flex items-start justify-between gap-3">
        <h4 className="gold-text text-lg font-medium uppercase tracking-[0.04em] truncate">
          {skill.name}
        </h4>
        <span className="text-white/70 text-xs font-medium uppercase tracking-[0.06em] shrink-0">
          Ранг&nbsp;
          <span className="gold-text text-base">{skill.current_rank}</span>
          <span className="text-white/40">&nbsp;/&nbsp;5</span>
        </span>
      </div>

      {/* XP progress bar */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-white/50 uppercase tracking-[0.06em]">
            {skill.is_max_rank ? 'Опыт' : 'Опыт до след. ранга'}
          </span>
          <span className="text-white/70">
            {skill.is_max_rank
              ? 'Макс.'
              : `${skill.experience} / ${requiredXp} опыта`}
          </span>
        </div>
        <div className="h-2 w-full bg-white/10 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-[width] duration-500 ease-out ${
              skill.is_max_rank ? 'bg-gold' : 'bg-site-blue'
            }`}
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      {/* Current bonuses */}
      <div className="flex flex-col gap-1 text-sm">
        <div className="text-white/50 text-xs uppercase tracking-[0.06em] mb-0.5">
          Текущие бонусы
        </div>
        <div className="flex items-center justify-between">
          <span className="text-white/70">Шанс дубля</span>
          <span className="text-white">+{fmt(cur.double_chance_bonus)}%</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-white/70">Скорость сбора</span>
          <span className="text-white">+{fmt(cur.speed_bonus_pct)}%</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-white/70">Экономия стамины</span>
          <span className="text-white">+{fmt(cur.stamina_bonus_pct)}%</span>
        </div>
      </div>

      {/* Next-rank preview / max badge */}
      {skill.is_max_rank ? (
        <div className="text-center py-2 border-t border-white/10">
          <span className="gold-text text-sm uppercase tracking-[0.06em]">
            Максимальный ранг
          </span>
        </div>
      ) : next ? (
        <div className="border-t border-white/10 pt-3">
          <div className="text-white/50 text-xs uppercase tracking-[0.06em] mb-1">
            Следующий ранг
            {skill.next_rank ? ` (${skill.next_rank.rank_number})` : ''}
          </div>
          <div className="text-sm text-white/80">
            +{fmt(next.double_chance_bonus)}% / +{fmt(next.speed_bonus_pct)}% / +
            {fmt(next.stamina_bonus_pct)}%
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default GatheringSkillCard;
