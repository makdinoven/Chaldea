// Player-facing resolved skill info card (FEAT-125).
// Displays cost / damage / effects / selected perks from a ResolvedSkillRead
// payload, fully localized to Russian. Also rendered by the battle page
// SkillPicker. FEAT-166: design-system tokens and shared profile primitives.
import {
  Zap,
  Droplet,
  Clock,
  TrendingUp,
  ArrowUp,
  Shield,
  BarChart3,
  Skull,
  Check,
  Info,
} from 'lucide-react';
import type {
  ResolvedSkill,
  SkillWithPerks,
  DamageEntry,
  EffectEntry,
} from '../../SkillTreeView/types';
import {
  ruDamageType,
  ruTargetSideCard,
  ruSkillType,
  parseEffectName,
  pluralizeTurns,
  type EffectCategory,
  type ParsedEffect,
} from '../../SkillTreeView/skillLabels';
import ProfileCard from '../shared/ProfileCard';
import GoldIconFrame from '../shared/GoldIconFrame';
import SectionHeader from '../shared/SectionHeader';

interface ResolvedSkillCardProps {
  resolved: ResolvedSkill;
  skill: SkillWithPerks | null;
}

const SKILL_TYPE_BADGE: Record<string, string> = {
  attack: 'bg-stat-hp/15 text-stat-hp border-stat-hp/30',
  defense: 'bg-site-blue/15 text-site-blue border-site-blue/30',
  support: 'bg-stat-energy/15 text-stat-energy border-stat-energy/30',
};

const CATEGORY_ORDER: EffectCategory[] = ['buff', 'resist', 'stat', 'complex'];

const CATEGORY_META: Record<
  EffectCategory,
  { Icon: typeof ArrowUp; color: string; title: string }
> = {
  buff: { Icon: ArrowUp, color: 'text-gold', title: 'Баффы' },
  resist: { Icon: Shield, color: 'text-site-blue', title: 'Резисты' },
  stat: { Icon: BarChart3, color: 'text-rarity-epic', title: 'Характеристики' },
  complex: { Icon: Skull, color: 'text-site-red', title: 'Особые эффекты' },
};

const formatSigned = (n: number): string => (n > 0 ? `+${n}` : `${n}`);

const sumByTarget = (entries: DamageEntry[]): Map<string, DamageEntry[]> => {
  const map = new Map<string, DamageEntry[]>();
  entries.forEach((e) => {
    const key = e.target_side ?? 'enemy';
    const arr = map.get(key) ?? [];
    arr.push(e);
    map.set(key, arr);
  });
  return map;
};

const toNumber = (v: number | string | null | undefined): number => {
  if (typeof v === 'number') return v;
  if (typeof v === 'string') {
    const parsed = Number.parseFloat(v);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};

const DamageGroup = ({
  targetSide,
  entries,
}: {
  targetSide: string;
  entries: DamageEntry[];
}) => {
  const total = entries.reduce((acc, e) => acc + toNumber(e.amount), 0);
  const isSelf = targetSide === 'self';
  const label = isSelf ? 'Эффект на себя' : `Урон ${targetSide === 'enemy' ? 'по врагу' : ruTargetSideCard(targetSide).toLowerCase()}`;
  const sumText = isSelf && total > 0 ? `+${total}` : `${total}`;

  // Per-type breakdown (collapse dupes by damage_type).
  const byType = new Map<string, number>();
  entries.forEach((e) => {
    const key = e.damage_type;
    byType.set(key, (byType.get(key) ?? 0) + toNumber(e.amount));
  });
  const breakdown = Array.from(byType.entries())
    .map(([type, amount]) => `${amount} ${ruDamageType(type)}`)
    .join(' + ');

  return (
    <ProfileCard className="px-3 py-2">
      <div className="flex items-baseline justify-between gap-2 flex-wrap">
        <span className="text-white/70 text-sm">{label}:</span>
        <span className="text-white font-semibold text-base font-mono tabular-nums">{sumText}</span>
      </div>
      {byType.size > 1 && (
        <div className="text-white/40 text-xs mt-1">{breakdown}</div>
      )}
    </ProfileCard>
  );
};

const EffectRow = ({
  effect,
  parsed,
}: {
  effect: EffectEntry;
  parsed: ParsedEffect;
}) => {
  const { Icon, color } = CATEGORY_META[parsed.category];
  const magnitude = effect.magnitude ?? 0;
  const hasMagnitude = magnitude !== 0;
  const unit = parsed.isPercent ? '%' : '';
  const magText = hasMagnitude ? `${formatSigned(magnitude)}${unit}` : '';

  const parts: string[] = [];
  if (magText) parts.push(magText);
  if (effect.duration && effect.duration > 0) parts.push(pluralizeTurns(effect.duration));

  // Show target only when informative.
  const targetSide = effect.target_side;
  const isBuffOnSelf = parsed.category === 'buff' && targetSide === 'self';
  const isStatOnSelf = parsed.category === 'stat' && targetSide === 'self';
  const isResistOnSelf = parsed.category === 'resist' && targetSide === 'self';
  if (targetSide && !isBuffOnSelf && !isStatOnSelf && !isResistOnSelf) {
    parts.push(ruTargetSideCard(targetSide));
  }

  if (effect.chance !== null && effect.chance !== undefined && effect.chance < 100) {
    parts.push(`шанс ${effect.chance}%`);
  }

  return (
    <div className="flex items-start gap-2 text-sm">
      <Icon size={16} className={`${color} mt-0.5 flex-shrink-0`} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-1.5 flex-wrap text-white/85">
          <span className="font-medium">{parsed.friendlyName}</span>
          {parts.length > 0 && (
            <span className="text-white/60">{parts.join(' · ')}</span>
          )}
          {effect.description && (
            <span
              title={effect.description}
              className="inline-flex items-center text-white/40 hover:text-white/70 cursor-help"
            >
              <Info size={12} />
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

const ResolvedSkillCard = ({ resolved, skill }: ResolvedSkillCardProps) => {
  const skillType = resolved.skill_type || skill?.skill_type || '';
  const typeLabel = ruSkillType(skillType);
  const typeBadge = SKILL_TYPE_BADGE[skillType] ?? 'bg-white/10 text-white/70 border-white/20';

  const skillName = skill?.name ?? `Навык #${resolved.skill_id}`;
  const skillImage = skill?.skill_image ?? null;
  const skillDescription = skill?.description ?? null;

  const damageByTarget = sumByTarget(resolved.damage_entries);

  // Group effects by category.
  const grouped = new Map<EffectCategory, { effect: EffectEntry; parsed: ParsedEffect }[]>();
  resolved.effects.forEach((effect) => {
    const parsed = parseEffectName(effect.effect_name, effect.attribute_key);
    const arr = grouped.get(parsed.category) ?? [];
    arr.push({ effect, parsed });
    grouped.set(parsed.category, arr);
  });

  // Resolve selected perks from the full skill payload.
  const selectedPerks = skill
    ? skill.perks.filter((p) => resolved.selected_perk_ids.includes(p.id))
    : [];

  return (
    <div className="flex flex-col gap-5 min-w-0">
      {/* Header */}
      <div className="flex items-start gap-3">
        <GoldIconFrame
          size={52}
          src={skillImage}
          alt={skillName}
          fallback={<Zap size={20} strokeWidth={1.6} className="text-gold/70" />}
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="gold-text text-lg sm:text-xl font-medium uppercase tracking-[0.04em] break-words min-w-0">
              {skillName}
            </h3>
            {typeLabel && (
              <span
                className={`text-[10px] uppercase tracking-wide font-medium px-2 py-0.5 rounded-full border ${typeBadge}`}
              >
                {typeLabel}
              </span>
            )}
          </div>
          {skillDescription && (
            <p className="text-white/50 text-xs mt-1 leading-snug">{skillDescription}</p>
          )}
        </div>
      </div>

      {/* Cost row */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-white/70 border-y border-white/10 py-3">
        <span className="flex items-center gap-1">
          <Zap size={14} className="text-gold" />
          {resolved.cost_energy} энергии
        </span>
        <span className="text-white/20">·</span>
        <span className="flex items-center gap-1">
          <Droplet size={14} className="text-site-blue" />
          {resolved.cost_mana} маны
        </span>
        <span className="text-white/20">·</span>
        <span className="flex items-center gap-1">
          <Clock size={14} className="text-white/50" />
          КД {resolved.cooldown}
        </span>
        <span className="text-white/20">·</span>
        <span className="flex items-center gap-1">
          <TrendingUp size={14} className="text-stat-energy" />
          ур. {resolved.level_requirement}
        </span>
      </div>

      {/* Damage section */}
      {resolved.damage_entries.length > 0 && (
        <div className="flex flex-col gap-2.5">
          <SectionHeader title="Урон" />
          <div className="space-y-2">
            {Array.from(damageByTarget.entries()).map(([targetSide, entries]) => (
              <DamageGroup key={targetSide} targetSide={targetSide} entries={entries} />
            ))}
          </div>
        </div>
      )}

      {/* Effects section */}
      {resolved.effects.length > 0 && (
        <div className="flex flex-col gap-2.5">
          <SectionHeader title="Эффекты" />
          <div className="space-y-3">
            {CATEGORY_ORDER.map((category) => {
              const items = grouped.get(category);
              if (!items || items.length === 0) return null;
              return (
                <div key={category} className="space-y-1.5">
                  <div className="text-white/40 text-[11px] uppercase tracking-wide">
                    {CATEGORY_META[category].title}
                  </div>
                  <div className="space-y-1">
                    {items.map((item, i) => (
                      <EffectRow key={i} effect={item.effect} parsed={item.parsed} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Perks section */}
      {selectedPerks.length > 0 && (
        <div className="flex flex-col gap-2.5">
          <SectionHeader title="Перки" />
          <div className="space-y-2">
            {selectedPerks.map((perk) => (
              <ProfileCard key={perk.id} className="flex items-start gap-2 px-3 py-2">
                <Check size={16} className="text-stat-energy mt-0.5 flex-shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="gold-text text-sm font-medium">{perk.name}</div>
                  {perk.description && (
                    <div className="text-white/50 text-xs mt-0.5 leading-snug">
                      {perk.description}
                    </div>
                  )}
                </div>
              </ProfileCard>
            ))}
          </div>
        </div>
      )}

      {resolved.selected_perk_ids.length > 0 && selectedPerks.length === 0 && (
        <div className="text-white/40 text-xs italic">
          Перки выбраны ({resolved.selected_perk_ids.length}), но их описания недоступны.
        </div>
      )}
    </div>
  );
};

export default ResolvedSkillCard;
