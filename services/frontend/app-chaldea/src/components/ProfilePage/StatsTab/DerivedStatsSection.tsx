import { CharacterAttributes } from '../../../redux/slices/profileSlice';
import { STAT_LABELS, PERCENTAGE_STATS, CLASS_MAIN_ATTRIBUTE } from '../constants';

interface DerivedStatsSectionProps {
  attributes: CharacterAttributes;
  classId: number | null;
  mainWeaponDamageModifier: number;
}

// FEAT-149: «В бою» — 2-column stat cards for the core combat values.
// Only REAL stats are rendered (mock's «Блок» does not exist and is dropped;
// «Инициатива» is kept — it is a real FEAT-143 computed value already shown here).
// Short labels fit the narrow panel; full names live in the `title` tooltip.
const COMBAT_CARD_LABELS: Record<string, string> = {
  damage: 'Урон',
  initiative: 'Инициатива',
  dodge: 'Уклонение',
  critical_hit_chance: 'Крит. шанс',
  critical_damage: 'Крит. урон',
};

// Resist chips (per mock): rounded pill with a colored dot + short label + value.
// Dot colors use existing palette tokens only.
const RESIST_CHIPS: { key: string; label: string; dotClass: string }[] = [
  { key: 'res_effects', label: 'Эфф.', dotClass: 'bg-white/70' },
  { key: 'res_physical', label: 'Физ.', dotClass: 'bg-white/70' },
  { key: 'res_catting', label: 'Реж.', dotClass: 'bg-white/50' },
  { key: 'res_crushing', label: 'Дроб.', dotClass: 'bg-white/50' },
  { key: 'res_piercing', label: 'Кол.', dotClass: 'bg-white/50' },
  { key: 'res_magic', label: 'Маг.', dotClass: 'bg-rarity-epic' },
  { key: 'res_fire', label: 'Огонь', dotClass: 'bg-site-red' },
  { key: 'res_ice', label: 'Лёд', dotClass: 'bg-site-blue' },
  { key: 'res_watering', label: 'Вода', dotClass: 'bg-stat-mana' },
  { key: 'res_electricity', label: 'Электр.', dotClass: 'bg-gold' },
  { key: 'res_wind', label: 'Ветер', dotClass: 'bg-stat-energy' },
  { key: 'res_sainting', label: 'Свет', dotClass: 'bg-gold-light' },
  { key: 'res_damning', label: 'Тьма', dotClass: 'bg-rarity-epic/60' },
];

const formatStatValue = (value: number | string, isPercent: boolean): string => {
  if (typeof value !== 'number') return String(value);
  const text = value % 1 === 0 ? String(value) : value.toFixed(1);
  return isPercent ? `${text}%` : text;
};

const DerivedStatsSection = ({ attributes, classId, mainWeaponDamageModifier }: DerivedStatsSectionProps) => {
  // Damage shown exactly as the battle engine computes the base: class main
  // attribute + the flat `damage` stat (where perk/item bonuses live) + weapon
  // modifier. Previously the flat `damage` was dropped, so perk damage bonuses
  // were invisible here while battle used them (FEAT-143).
  const getDisplayDamage = (): number => {
    const damageBonus = Number(attributes.damage ?? 0);
    const mainAttrKey =
      (classId != null && CLASS_MAIN_ATTRIBUTE[classId]) || "strength";
    const mainAttrValue = Number(
      attributes[mainAttrKey as keyof CharacterAttributes] ?? 0,
    );
    return mainAttrValue + damageBonus + mainWeaponDamageModifier;
  };

  // Initiative (FEAT-143): agility ×1.0 + (strength + intelligence) ×0.75.
  // Drives turn order in battle after the initiator.
  const agility = Number(attributes.agility ?? 0);
  const strength = Number(attributes.strength ?? 0);
  const intelligence = Number(attributes.intelligence ?? 0);
  const initiative = agility * 1.0 + (strength + intelligence) * 0.75;

  const combatCards: {
    key: string;
    value: number | string;
    isPercent: boolean;
    highlighted: boolean;
    tooltip?: string;
  }[] = [
    { key: 'damage', value: getDisplayDamage(), isPercent: false, highlighted: true },
    {
      key: 'initiative',
      value: initiative,
      isPercent: false,
      highlighted: true,
      tooltip: 'Ловкость ×1.0 + (Сила + Интеллект) ×0.75 — определяет очередь хода в бою',
    },
    {
      key: 'dodge',
      value: (attributes.dodge as number | undefined) ?? 0,
      isPercent: PERCENTAGE_STATS.has('dodge'),
      highlighted: false,
    },
    {
      key: 'critical_hit_chance',
      value: (attributes.critical_hit_chance as number | undefined) ?? 0,
      isPercent: PERCENTAGE_STATS.has('critical_hit_chance'),
      highlighted: false,
    },
    {
      key: 'critical_damage',
      value: (attributes.critical_damage as number | undefined) ?? 0,
      isPercent: PERCENTAGE_STATS.has('critical_damage'),
      highlighted: false,
    },
  ];

  return (
    <div>
      {/* FEAT-149: section title row with a fading gold rule (per mock) */}
      <div className="flex items-center gap-3 mb-3.5">
        <h3 className="gold-text text-xs font-medium uppercase tracking-[0.14em] shrink-0">
          В бою
        </h3>
        <span
          className="flex-1 h-px bg-gradient-to-r from-gold/40 to-transparent"
          aria-hidden="true"
        />
      </div>

      {/* Combat stat cards — 2 columns per mock */}
      <div className="grid grid-cols-2 gap-2">
        {combatCards.map(({ key, value, isPercent, highlighted, tooltip }) => (
          <div
            key={key}
            title={tooltip ?? STAT_LABELS[key] ?? COMBAT_CARD_LABELS[key]}
            className={`flex items-center justify-between gap-2 py-2 px-3 rounded-card border transition-colors duration-200 ease-site ${
              highlighted
                ? 'bg-gold/5 border-gold/20'
                : 'bg-white/[0.03] border-white/[0.07] hover:bg-white/5'
            }`}
          >
            <span
              className={`text-xs min-w-0 truncate ${highlighted ? 'text-gold/90 font-medium' : 'text-white/70'}`}
            >
              {COMBAT_CARD_LABELS[key] ?? STAT_LABELS[key] ?? key}
            </span>
            <span
              className={`text-sm font-medium font-mono shrink-0 ${highlighted ? 'text-gold' : 'text-white'}`}
            >
              {formatStatValue(value, isPercent)}
            </span>
          </div>
        ))}
      </div>

      {/* Resist chips */}
      <div className="flex flex-wrap gap-1.5 mt-3">
        {RESIST_CHIPS.map(({ key, label, dotClass }) => {
          const rawValue = attributes[key as keyof CharacterAttributes];
          const value = typeof rawValue === 'number' ? rawValue : Number(rawValue ?? 0);
          return (
            <span
              key={key}
              title={STAT_LABELS[key] ?? key}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/[0.04] border border-white/10 text-[11px] text-white/75"
            >
              <span
                className={`w-[7px] h-[7px] rounded-full shrink-0 ${dotClass}`}
                aria-hidden="true"
              />
              {label}
              <span className="text-white font-medium font-mono">
                {formatStatValue(value, PERCENTAGE_STATS.has(key))}
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
};

export default DerivedStatsSection;
