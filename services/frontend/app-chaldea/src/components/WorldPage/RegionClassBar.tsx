import type { RegionCardClasses, RegionClassAmount } from '../../api/regionEconomy';

/**
 * FEAT-194 (3.11): three-colour bar of the region's residents — poor / middling / rich.
 * The player card only gets coarse words per class («мало / средне / много»), the widths here are drawn
 * from a fixed word→weight map, so no real share ever reaches the page.
 * `ClassMixBar` is the plain drawing (also used by the admin with real shares).
 */

export type ClassKey = 'poor' | 'middling' | 'rich';

export const CLASS_KEYS: ClassKey[] = ['poor', 'middling', 'rich'];

export const CLASS_NAMES: Record<ClassKey, string> = {
  poor: 'бедные',
  middling: 'зажиточные',
  rich: 'богатые',
};

/** Segment colours: poor muted, middling blue, rich gold. */
export const CLASS_BAR_COLOR: Record<ClassKey, string> = {
  poor: 'bg-white/25',
  middling: 'bg-site-blue/70',
  rich: 'bg-gold/80',
};

/** Legend dot colours (same hues, a bit stronger for a small dot). */
const CLASS_DOT_COLOR: Record<ClassKey, string> = {
  poor: 'bg-white/40',
  middling: 'bg-site-blue',
  rich: 'bg-gold',
};

/** Bar weights per word. The rich are naturally few, so their scale is smaller (3.11). */
const WORD_WEIGHT: Record<ClassKey, Record<RegionClassAmount, number>> = {
  poor: { few: 20, some: 35, many: 55 },
  middling: { few: 20, some: 35, many: 55 },
  rich: { few: 6, some: 14, many: 24 },
};

const WORD_TEXT: Record<RegionClassAmount, string> = {
  few: 'мало',
  some: 'средне',
  many: 'много',
};

interface ClassMixBarProps {
  /** Any non-negative weights; the bar normalises them to 100 %. */
  poor: number;
  middling: number;
  rich: number;
  /** Tailwind height class, e.g. `h-2` */
  heightClass?: string;
  title?: string;
}

export const ClassMixBar = ({ poor, middling, rich, heightClass = 'h-2', title }: ClassMixBarProps) => {
  const values: Record<ClassKey, number> = {
    poor: Math.max(0, poor),
    middling: Math.max(0, middling),
    rich: Math.max(0, rich),
  };
  const total = values.poor + values.middling + values.rich;
  return (
    <div
      className={`flex w-full overflow-hidden rounded-full bg-white/5 ${heightClass}`}
      title={title}
      role="img"
      aria-label={title ?? 'Состав жителей'}
    >
      {total > 0 &&
        CLASS_KEYS.map((key) => (
          <div
            key={key}
            className={`${CLASS_BAR_COLOR[key]} h-full transition-[width] duration-300`}
            style={{ width: `${(values[key] / total) * 100}%` }}
          />
        ))}
    </div>
  );
};

interface RegionClassBarProps {
  classes: RegionCardClasses;
}

/** Player card: bar from words + legend «бедные — много · зажиточные — средне · богатые — мало». */
const RegionClassBar = ({ classes }: RegionClassBarProps) => {
  const word = (key: ClassKey): RegionClassAmount => {
    const w = classes.bar?.[key];
    return w === 'few' || w === 'some' || w === 'many' ? w : 'some';
  };
  const legend = CLASS_KEYS.map((key) => `${CLASS_NAMES[key]} — ${WORD_TEXT[word(key)]}`).join(', ');
  return (
    <div className="mx-auto mt-2 w-full max-w-sm">
      <ClassMixBar
        poor={WORD_WEIGHT.poor[word('poor')]}
        middling={WORD_WEIGHT.middling[word('middling')]}
        rich={WORD_WEIGHT.rich[word('rich')]}
        title={`Жители: ${legend}`}
      />
      <ul className="mt-1.5 flex flex-wrap justify-center gap-x-3 gap-y-0.5 text-[11px] text-white/60">
        {CLASS_KEYS.map((key) => (
          <li key={key} className="flex items-center gap-1 whitespace-nowrap">
            <span className={`inline-block h-2 w-2 rounded-full ${CLASS_DOT_COLOR[key]}`} aria-hidden="true" />
            {CLASS_NAMES[key]} — {WORD_TEXT[word(key)]}
          </li>
        ))}
      </ul>
    </div>
  );
};

export default RegionClassBar;
