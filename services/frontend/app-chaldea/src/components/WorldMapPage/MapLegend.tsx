import type { GraphStats } from '../../api/worldGraph';
import {
  COLOR_MODE_LABELS,
  COUNTRY_COLORS,
  ISOLATED_COLOR,
  MARKER_COLORS,
  MARKER_LABELS,
  levelColor,
  type ColorMode,
} from './theme';

export interface ComponentSummary {
  id: number;
  size: number;
  color: string;
}

interface MapLegendProps {
  colorMode: ColorMode;
  onColorModeChange: (mode: ColorMode) => void;
  stats: GraphStats;
  countries: Array<{ id: number; name: string }>;
  components: ComponentSummary[];
  componentCount: number;
  maxLevel: number;
}

const Swatch = ({ color, label, dashed = false }: { color: string; label: string; dashed?: boolean }) => (
  <div className="flex items-center gap-2">
    <span
      className="h-3 w-3 shrink-0 rounded-full"
      style={{
        background: color,
        border: dashed ? '1.5px dashed rgba(255,255,255,0.5)' : '1.5px solid rgba(255,255,255,0.25)',
      }}
    />
    <span className="truncate text-[11px] text-white/65">{label}</span>
  </div>
);

const MapLegend = ({
  colorMode,
  onColorModeChange,
  stats,
  countries,
  components,
  componentCount,
  maxLevel,
}: MapLegendProps) => (
  <div className="flex flex-col gap-3">
    <div>
      <span className="mb-1 block text-[10px] uppercase tracking-wide text-white/45">
        Раскраска
      </span>
      <div className="grid grid-cols-2 gap-1">
        {(Object.keys(COLOR_MODE_LABELS) as ColorMode[]).map((mode) => (
          <button
            key={mode}
            type="button"
            className={`rounded-lg border px-2 py-1.5 text-[11px] transition-colors ${
              colorMode === mode
                ? 'border-gold-dark/70 bg-gold-dark/25 text-gold-light'
                : 'border-white/10 text-white/50 hover:bg-white/5'
            }`}
            onClick={() => onColorModeChange(mode)}
          >
            {COLOR_MODE_LABELS[mode]}
          </button>
        ))}
      </div>
    </div>

    <div className="gold-scrollbar flex max-h-48 flex-col gap-1.5 overflow-y-auto pr-1">
      {colorMode === 'marker' &&
        (Object.keys(MARKER_COLORS) as Array<keyof typeof MARKER_COLORS>).map((marker) => (
          <Swatch key={marker} color={MARKER_COLORS[marker]} label={MARKER_LABELS[marker]} />
        ))}

      {colorMode === 'country' &&
        countries.map((country, index) => (
          <Swatch
            key={country.id}
            color={COUNTRY_COLORS[index % COUNTRY_COLORS.length]}
            label={country.name}
          />
        ))}

      {colorMode === 'component' && (
        <>
          {components.map((component, index) => (
            <Swatch
              key={component.id}
              color={component.color}
              label={`Материк ${index + 1} — ${component.size} лок.`}
            />
          ))}
          <Swatch color={ISOLATED_COLOR} label="Мелкие и изолированные" dashed />
        </>
      )}

      {colorMode === 'level' && (
        <>
          <div
            className="h-3 w-full rounded"
            style={{
              background: `linear-gradient(to right, ${levelColor(0, maxLevel)}, ${levelColor(
                maxLevel / 2,
                maxLevel,
              )}, ${levelColor(maxLevel, maxLevel)})`,
            }}
          />
          <div className="flex justify-between text-[10px] text-white/45">
            <span>ур. 0</span>
            <span>ур. {maxLevel}</span>
          </div>
        </>
      )}
    </div>

    <div className="gradient-line-border rounded-lg bg-black/30 p-2.5">
      <dl className="grid grid-cols-2 gap-y-1 text-[11px]">
        <dt className="text-white/45">Локаций</dt>
        <dd className="text-right text-white/80">{stats.locations}</dd>
        <dt className="text-white/45">Связей</dt>
        <dd className="text-right text-white/80">{stats.edges}</dd>
        <dt className="text-white/45">Изолированных</dt>
        <dd className="text-right text-site-red">{stats.isolated}</dd>
        <dt className="text-white/45">Несвязных частей</dt>
        <dd className="text-right text-site-red">{componentCount}</dd>
        {stats.one_way_edges > 0 && (
          <>
            <dt className="text-white/45">Односторонних</dt>
            <dd className="text-right text-gold">{stats.one_way_edges}</dd>
          </>
        )}
      </dl>
    </div>
  </div>
);

export default MapLegend;
