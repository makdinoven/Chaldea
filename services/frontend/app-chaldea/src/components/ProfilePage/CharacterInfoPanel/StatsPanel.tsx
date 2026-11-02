import { Heart, Droplet, Zap, Wind } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useAppSelector } from '../../../redux/store';
import {
  selectAttributes,
  selectProfile,
  selectRaceInfo,
} from '../../../redux/slices/profileSlice';
import type { CharacterAttributes } from '../../../redux/slices/profileSlice';
import { RESOURCE_BARS, STAT_LABELS } from '../constants';
import { RESOURCE_BASE, resourceStatPart } from '../../CommonComponents/CharacterPassport';
import { levelResourceRate } from '../../../utils/resourceGrowth';
import type { GrowthResource } from '../../../utils/resourceGrowth';

// FEAT-149: vitals use icon-only labels (no text next to icons — user decision).
// Icons come from lucide-react (already a project dependency), colored with the
// existing stat-* design tokens; the Russian label survives as a tooltip (a11y).
const VITAL_ICONS: Record<string, LucideIcon> = {
  health: Heart,
  mana: Droplet,
  energy: Zap,
  stamina: Wind,
};

const VITAL_ICON_COLOR: Record<string, string> = {
  health: 'text-stat-hp',
  mana: 'text-stat-mana',
  energy: 'text-stat-energy',
  stamina: 'text-stat-stamina',
};

const signed = (value: number): string => (value >= 0 ? `+ ${value}` : `− ${Math.abs(value)}`);

/**
 * FEAT-196 — where the maximum comes from: base + level growth + the resource
 * stat (points, gear, food — after the FEAT-195 cap). The stored max is the
 * truth; any gap is shown as «прочее», never hidden.
 */
const buildMaxBreakdown = (
  resource: GrowthResource,
  storedMax: number,
  attributes: CharacterAttributes | null | undefined,
  level: number | null | undefined,
  classId: number | null | undefined,
): string | null => {
  if (!attributes) return null;
  const base = RESOURCE_BASE[resource];
  const statPart = resourceStatPart(resource, attributes[resource]);
  const rate = levelResourceRate(resource, classId);
  const lvl = typeof level === 'number' && level >= 1 ? Math.floor(level) : 0;
  const levelPart = lvl * rate;
  const parts = [`база ${base}`];
  if (levelPart > 0) parts.push(`за уровень ${lvl}×${rate} = ${levelPart}`);
  parts.push(`от очков и снаряжения ${statPart}`);
  let text = parts.join(' + ');
  const rest = Math.round(storedMax) - (base + levelPart + statPart);
  if (rest !== 0) text += ` ${signed(rest)} прочее`;
  return `Максимум: ${text} = ${Math.round(storedMax)}`;
};

export default function StatsPanel() {
  const attributes = useAppSelector(selectAttributes);
  const profile = useAppSelector(selectProfile);
  const raceInfo = useAppSelector(selectRaceInfo);
  const level = profile?.level ?? raceInfo?.level;
  const classId = raceInfo?.id_class;

  if (!attributes && !profile) {
    return (
      <div className="flex flex-col gap-4 w-full">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="flex flex-col gap-[7px]">
            <div className="flex justify-between items-center">
              <span className="w-4 h-4 rounded-full bg-white/10 animate-pulse" />
              <span className="w-16 h-4 rounded bg-white/10 animate-pulse" />
            </div>
            <div className="stat-bar" />
          </div>
        ))}
      </div>
    );
  }

  // Use attributes for current/max values (they're more detailed),
  // but fall back to profile.attributes if attributes are not loaded yet
  const resourceData = {
    current_health: attributes?.current_health ?? profile?.attributes?.current_health ?? 0,
    max_health: attributes?.max_health ?? profile?.attributes?.max_health ?? 1,
    current_mana: attributes?.current_mana ?? profile?.attributes?.current_mana ?? 0,
    max_mana: attributes?.max_mana ?? profile?.attributes?.max_mana ?? 1,
    current_energy: attributes?.current_energy ?? profile?.attributes?.current_energy ?? 0,
    max_energy: attributes?.max_energy ?? profile?.attributes?.max_energy ?? 1,
    current_stamina: attributes?.current_stamina ?? profile?.attributes?.current_stamina ?? 0,
    max_stamina: attributes?.max_stamina ?? profile?.attributes?.max_stamina ?? 1,
  };

  return (
    <div className="flex flex-col gap-4 w-full">
      {RESOURCE_BARS.map(({ key, label, colorClass }) => {
        const currentKey = `current_${key}` as keyof typeof resourceData;
        const maxKey = `max_${key}` as keyof typeof resourceData;
        const current = resourceData[currentKey];
        const max = resourceData[maxKey];
        const percent = max > 0 ? Math.min((current / max) * 100, 100) : 0;
        const Icon = VITAL_ICONS[key];
        const tooltip = STAT_LABELS[key] ?? label;
        const breakdown = buildMaxBreakdown(key, max, attributes, level, classId);
        const title = breakdown ? `${tooltip}
${breakdown}` : tooltip;

        return (
          <div key={key} className="flex flex-col gap-[7px]" title={title}>
            <div className="flex justify-between items-center">
              <span
                className={`flex ${VITAL_ICON_COLOR[key] ?? 'text-white'}`}
                role="img"
                aria-label={tooltip}
              >
                {Icon && <Icon size={16} strokeWidth={2} />}
              </span>
              <span className="gold-text text-sm font-medium uppercase text-right">
                {Math.round(current)}/{Math.round(max)}
              </span>
            </div>
            <div className="stat-bar">
              <div
                className={`stat-bar-fill ${colorClass}`}
                style={{ width: `${percent}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
