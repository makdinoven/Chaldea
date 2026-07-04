import { CharacterAttributes } from '../../../redux/slices/profileSlice';
import { DERIVED_STATS, STAT_LABELS, PERCENTAGE_STATS, CLASS_MAIN_ATTRIBUTE } from '../constants';

interface DerivedStatsSectionProps {
  attributes: CharacterAttributes;
  classId: number | null;
  mainWeaponDamageModifier: number;
}

const STAT_ICONS: Record<string, string> = {
  damage: '\u2694\uFE0F',
  dodge: '\uD83D\uDCA8',
  res_effects: '\uD83D\uDEE1\uFE0F',
  res_physical: '\uD83E\uDDBE',
  res_catting: '\uD83D\uDD2A',
  res_crushing: '\uD83D\uDD28',
  res_piercing: '\uD83C\uDFF9',
  res_magic: '\u2728',
  res_fire: '\uD83D\uDD25',
  res_ice: '\u2744\uFE0F',
  res_watering: '\uD83D\uDCA7',
  res_electricity: '\u26A1',
  res_wind: '\uD83C\uDF2C\uFE0F',
  res_sainting: '\u2600\uFE0F',
  res_damning: '\uD83C\uDF11',
  critical_hit_chance: '\uD83C\uDFAF',
  critical_damage: '\uD83D\uDCA5',
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
  const initiativeText =
    initiative % 1 === 0 ? String(initiative) : initiative.toFixed(2);

  return (
    <div>
      <h3 className="gold-text text-xl font-medium uppercase mb-4">
        Боевые характеристики
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-2">
        {DERIVED_STATS.map((stat) => {
          const rawValue = attributes[stat as keyof CharacterAttributes] ?? 0;
          const value = stat === 'damage' ? getDisplayDamage() : rawValue;
          const isPercent = PERCENTAGE_STATS.has(stat);
          const displayValue = isPercent
            ? `${typeof value === 'number' ? value.toFixed(1) : value}%`
            : String(value);

          return (
            <div
              key={stat}
              className="flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-white/5 transition-colors duration-200"
            >
              <span className="text-base w-6 text-center flex-shrink-0">
                {STAT_ICONS[stat] ?? '\u25C6'}
              </span>
              <span className="text-white/70 text-sm flex-1 min-w-0 truncate">
                {STAT_LABELS[stat] ?? stat}
              </span>
              <span className="text-white text-sm font-medium font-mono flex-shrink-0">
                {displayValue}
              </span>
            </div>
          );
        })}
      </div>

      {/* Initiative — highlighted, drives the battle turn order (FEAT-143) */}
      <div className="mt-3 flex items-center gap-2 py-2 px-3 rounded-lg bg-gold/5 border border-gold/20">
        <span className="text-base w-6 text-center flex-shrink-0">{'🏃'}</span>
        <span className="text-gold/90 text-sm flex-1 min-w-0 truncate font-medium">
          Инициатива
        </span>
        <span
          className="text-gold text-sm font-medium font-mono flex-shrink-0"
          title="Ловкость ×1.0 + (Сила + Интеллект) ×0.75 — определяет очередь хода в бою"
        >
          {initiativeText}
        </span>
      </div>
    </div>
  );
};

export default DerivedStatsSection;
