// PerkCard — displays a single perk in the pool inside SkillUpgradeModal (FEAT-125)
import type { SkillPerkRead } from './types';
import { ruDamageType, ruEffectName, ruTargetSide } from './skillLabels';

export type PerkCardState = 'selected' | 'available' | 'locked' | 'unaffordable';

interface PerkCardProps {
  perk: SkillPerkRead;
  state: PerkCardState;
  onPick?: (perkId: number) => void;
}

const stateClasses: Record<PerkCardState, string> = {
  selected:
    'border border-gold/70 bg-gold/10 ring-1 ring-gold/40',
  available:
    'border border-white/15 bg-white/[0.04] hover:bg-white/[0.08] hover:border-gold/50 cursor-pointer',
  locked:
    'border border-white/10 bg-white/[0.02] opacity-60',
  unaffordable:
    'border border-white/10 bg-white/[0.02] opacity-40 cursor-not-allowed',
};

const formatDelta = (value: number | null, label: string): string | null => {
  if (value == null || value === 0) return null;
  const sign = value > 0 ? '+' : '';
  return `${label}: ${sign}${value}`;
};

const PerkCard = ({ perk, state, onPick }: PerkCardProps) => {
  const clickable = state === 'available' && typeof onPick === 'function';

  const deltas = [
    formatDelta(perk.delta_cost_energy, 'Энергия'),
    formatDelta(perk.delta_cost_mana, 'Мана'),
    formatDelta(perk.delta_cooldown, 'КД'),
    formatDelta(perk.delta_level_requirement, 'Треб. уровень'),
  ].filter((x): x is string => !!x);

  return (
    <button
      type="button"
      disabled={!clickable}
      onClick={clickable ? () => onPick!(perk.id) : undefined}
      className={`text-left w-full rounded-card p-3 sm:p-4 transition-all duration-200 ease-site ${stateClasses[state]}`}
    >
      <div className="flex items-start gap-2 sm:gap-3">
        {perk.perk_image && (
          <img
            src={perk.perk_image}
            alt={perk.name}
            className="w-10 h-10 sm:w-12 sm:h-12 rounded-sm object-cover flex-shrink-0"
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="gold-text text-sm sm:text-base font-medium truncate">
              {perk.name}
            </h4>
            {state === 'selected' && (
              <span className="text-[10px] uppercase text-gold/90 border border-gold/50 rounded-full px-2 py-0.5">
                Выбрано
              </span>
            )}
          </div>
          {perk.description && (
            <p className="text-white/60 text-xs sm:text-sm mt-1 whitespace-pre-line">
              {perk.description}
            </p>
          )}
        </div>
      </div>

      {deltas.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {deltas.map((d, i) => (
            <span
              key={i}
              className="text-[10px] sm:text-xs bg-white/10 rounded-sm px-2 py-0.5 text-white/80"
            >
              {d}
            </span>
          ))}
        </div>
      )}

      {perk.damage_entries.length > 0 && (
        <div className="mt-2 space-y-0.5">
          {perk.damage_entries.map((d, i) => (
            <div key={i} className="text-[10px] sm:text-xs text-red-300/90">
              +{d.amount} {ruDamageType(d.damage_type)}
              {d.target_side ? ` (${ruTargetSide(d.target_side)})` : ''}
            </div>
          ))}
        </div>
      )}

      {perk.effects.length > 0 && (
        <div className="mt-1 space-y-0.5">
          {perk.effects.map((e, i) => (
            <div key={i} className="text-[10px] sm:text-xs text-blue-300/90">
              {ruEffectName(e.effect_name, e.attribute_key)}
              {e.duration ? ` (${e.duration} ход.)` : ''}
            </div>
          ))}
        </div>
      )}
    </button>
  );
};

export default PerkCard;
