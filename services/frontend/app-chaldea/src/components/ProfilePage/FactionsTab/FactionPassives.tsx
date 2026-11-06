// FEAT-207 — rank passives (battle modifiers) and «вне закона» warnings, shared by the profile tab and the catalog.
import { ShieldAlert, Sparkles } from 'lucide-react';
import type { FactionModifiers, FactionOutlawRegion } from '../../../api/factions';
import { PERCENTAGE_STATS, STAT_LABELS } from '../constants';

/** «+5 Сила», «−3 % Уклонение». */
const modifierText = (key: string, value: number): string => {
  const sign = value > 0 ? '+' : '−';
  const unit = PERCENTAGE_STATS.has(key) ? ' %' : '';
  return `${sign}${Math.abs(value)}${unit} ${STAT_LABELS[key] ?? key}`;
};

/** Modifier chips; negative ones in red. */
export const ModifierList = ({ modifiers }: { modifiers: FactionModifiers }) => {
  const entries = Object.entries(modifiers ?? {}).filter(([, v]) => v !== 0);
  if (entries.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-1">
      {entries.map(([key, value]) => (
        <li
          key={key}
          className={`rounded-full border px-2 py-px text-[11px] whitespace-nowrap ${
            value > 0 ? 'border-stat-energy/30 text-stat-energy' : 'border-site-red/30 text-site-red'
          }`}
        >
          {modifierText(key, value)}
        </li>
      ))}
    </ul>
  );
};

/** One passive: name, description, modifiers. */
export const PassiveRow = ({
  name,
  description,
  modifiers,
  rankName,
}: {
  name: string;
  description: string | null;
  modifiers: FactionModifiers;
  rankName?: string;
}) => (
  <div className="flex flex-col gap-1 min-w-0">
    <p className="text-xs text-white/85 flex items-start gap-1.5 min-w-0">
      <Sparkles size={13} className="text-gold shrink-0 mt-px" />
      <span className="break-words min-w-0">
        <span className="text-gold-light">{name}</span>
        {rankName && <span className="text-white/40"> · звание «{rankName}»</span>}
      </span>
    </p>
    {description && <p className="text-white/55 text-xs break-words pl-5">{description}</p>}
    <div className="pl-5">
      <ModifierList modifiers={modifiers} />
    </div>
  </div>
);

/** «В крае «X» эта фракция вне закона (Y)» per region. */
export const OutlawWarnings = ({ regions, compact = false }: { regions: FactionOutlawRegion[] | undefined; compact?: boolean }) => {
  if (!regions || regions.length === 0) return null;
  return (
    <div className="rounded-card border border-site-red/30 bg-site-red/[0.06] px-3 py-2 flex flex-col gap-1">
      {regions.map((r) => (
        <p key={r.region_id} className="text-xs text-white/80 flex items-start gap-1.5 min-w-0">
          <ShieldAlert size={14} className="text-site-red shrink-0 mt-px" />
          <span className="break-words min-w-0">
            В крае «{r.region_name ?? `#${r.region_id}`}» эта фракция вне закона
            {r.level_name ? ` (${r.level_name})` : ''}
            {compact ? '' : ' — стража может оштрафовать или арестовать участника'}
          </span>
        </p>
      ))}
    </div>
  );
};
