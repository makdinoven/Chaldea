// Player-facing resolved skill info card (FEAT-125).
// Displays cost / damage / effects / selected perks from a ResolvedSkillRead
// payload, fully localized to Russian.
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

interface ResolvedSkillCardProps {
  resolved: ResolvedSkill;
  skill: SkillWithPerks | null;
}

const SKILL_TYPE_BADGE: Record<string, string> = {
  attack: 'bg-red-500/20 text-red-300 border-red-500/30',
  defense: 'bg-sky-500/20 text-sky-300 border-sky-500/30',
  support: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
};

const CATEGORY_ORDER: EffectCategory[] = ['buff', 'resist', 'stat', 'complex'];

const CATEGORY_META: Record<
  EffectCategory,
  { Icon: typeof ArrowUp; color: string; title: string }
> = {
  buff: { Icon: ArrowUp, color: 'text-amber-300', title: 'Баффы' },
  resist: { Icon: Shield, color: 'text-sky-300', title: 'Резисты' },
  stat: { Icon: BarChart3, color: 'text-purple-300', title: 'Характеристики' },
  complex: { Icon: Skull, color: 'text-red-300', title: 'Особые эффекты' },
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
    <div className="bg-white/5 rounded-lg px-3 py-2 border border-white/5">
      <div className="flex items-baseline justify-between gap-2 flex-wrap">
        <span className="text-white/70 text-sm">{label}:</span>
        <span className="text-white font-semibold text-base">{sumText}</span>
      </div>
      {byType.size > 1 && (
        <div className="text-white/40 text-xs mt-1">{breakdown}</div>
      )}
    </div>
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

const SectionHeader = ({ children }: { children: React.ReactNode }) => (
  <h4 className="gold-text uppercase tracking-wide text-xs font-medium pb-1 border-b border-white/10">
    {children}
  </h4>
);

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
    <div className="gray-bg rounded-card border border-white/10 p-4 space-y-4">
      {/* Header */}
      <div className="flex items-start gap-3">
        {skillImage ? (
          <img
            src={skillImage}
            alt={skillName}
            className="w-10 h-10 rounded-lg object-cover border border-white/10 flex-shrink-0"
          />
        ) : (
          <div className="w-10 h-10 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center flex-shrink-0">
            <Zap size={18} className="text-white/30" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="gold-text text-lg sm:text-xl font-bold truncate">{skillName}</h3>
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
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-white/70">
        <span className="flex items-center gap-1">
          <Zap size={14} className="text-amber-300" />
          {resolved.cost_energy} энергии
        </span>
        <span className="text-white/20">·</span>
        <span className="flex items-center gap-1">
          <Droplet size={14} className="text-sky-300" />
          {resolved.cost_mana} маны
        </span>
        <span className="text-white/20">·</span>
        <span className="flex items-center gap-1">
          <Clock size={14} className="text-white/50" />
          КД {resolved.cooldown}
        </span>
        <span className="text-white/20">·</span>
        <span className="flex items-center gap-1">
          <TrendingUp size={14} className="text-emerald-300" />
          ур. {resolved.level_requirement}
        </span>
      </div>

      {/* Damage section */}
      {resolved.damage_entries.length > 0 && (
        <div className="space-y-2">
          <SectionHeader>Урон</SectionHeader>
          <div className="space-y-2">
            {Array.from(damageByTarget.entries()).map(([targetSide, entries]) => (
              <DamageGroup key={targetSide} targetSide={targetSide} entries={entries} />
            ))}
          </div>
        </div>
      )}

      {/* Effects section */}
      {resolved.effects.length > 0 && (
        <div className="space-y-2">
          <SectionHeader>Эффекты</SectionHeader>
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
        <div className="space-y-2">
          <SectionHeader>Перки</SectionHeader>
          <div className="space-y-2">
            {selectedPerks.map((perk) => (
              <div
                key={perk.id}
                className="flex items-start gap-2 bg-white/5 rounded-lg px-3 py-2 border border-white/5"
              >
                <Check size={16} className="text-emerald-300 mt-0.5 flex-shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="gold-text text-sm font-medium">{perk.name}</div>
                  {perk.description && (
                    <div className="text-white/50 text-xs mt-0.5 leading-snug">
                      {perk.description}
                    </div>
                  )}
                </div>
              </div>
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
