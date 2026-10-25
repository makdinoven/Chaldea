import { useMemo } from 'react';
import { DUNGEON_THEMES, THEME_INFO, type DungeonTheme } from '../../DungeonBoard3D/dungeonThemes';
import { themeSwatch } from '../../DungeonBoard3D/themePaint';

/* The dungeon's look on the 3D miniature (FEAT-176): a card per look, with its wall over its floor. */

interface ThemePickerProps {
  value: DungeonTheme;
  onChange: (theme: DungeonTheme) => void;
}

const ThemePicker = ({ value, onChange }: ThemePickerProps) => {
  const swatches = useMemo(() => new Map(DUNGEON_THEMES.map((t) => [t, themeSwatch(t)])), []);
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3">
      {DUNGEON_THEMES.map((t) => {
        const chosen = t === value;
        return (
          <button
            key={t}
            type="button"
            onClick={() => onChange(t)}
            aria-pressed={chosen}
            className={`flex flex-col text-left rounded-card overflow-hidden border transition-colors ${
              chosen ? 'border-gold/70 bg-gold/10' : 'border-white/10 hover:border-white/30'
            }`}
          >
            <img src={swatches.get(t)} alt="" className="w-full aspect-[4/3] object-cover" draggable={false} />
            <span className="px-2 pt-1.5 text-xs sm:text-sm text-white leading-tight">{THEME_INFO[t].name}</span>
            <span className="px-2 pb-2 pt-0.5 text-[10px] sm:text-[11px] text-white/45 leading-snug">{THEME_INFO[t].about}</span>
          </button>
        );
      })}
    </div>
  );
};

export default ThemePicker;
