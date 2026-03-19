import type { StatPreset } from '../../../redux/slices/racesSlice';

const STAT_FIELDS: { key: keyof StatPreset; label: string }[] = [
  { key: 'strength', label: 'Сила' },
  { key: 'agility', label: 'Ловкость' },
  { key: 'intelligence', label: 'Интеллект' },
  { key: 'endurance', label: 'Живучесть' },
  { key: 'health', label: 'Здоровье' },
  { key: 'energy', label: 'Энергия' },
  { key: 'mana', label: 'Мана' },
  { key: 'stamina', label: 'Выносливость' },
  { key: 'charisma', label: 'Харизма' },
  { key: 'luck', label: 'Удача' },
];

const DEFAULT_PRESET: StatPreset = {
  strength: 10,
  agility: 10,
  intelligence: 10,
  endurance: 10,
  health: 10,
  energy: 10,
  mana: 10,
  stamina: 10,
  charisma: 10,
  luck: 10,
};

interface StatPresetEditorProps {
  value: StatPreset;
  onChange: (preset: StatPreset) => void;
}

const StatPresetEditor = ({ value, onChange }: StatPresetEditorProps) => {
  const preset = value || DEFAULT_PRESET;
  const sum = Object.values(preset).reduce((acc, v) => acc + (v || 0), 0);
  const isValid = sum === 100;

  const handleChange = (key: keyof StatPreset, rawValue: string) => {
    const numValue = parseInt(rawValue, 10);
    const newValue = isNaN(numValue) ? 0 : Math.max(0, numValue);
    onChange({ ...preset, [key]: newValue });
  };

  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
        {STAT_FIELDS.map(({ key, label }) => (
          <div key={key} className="flex flex-col gap-1">
            <label className="text-white/60 text-xs font-medium uppercase tracking-wide">
              {label}
            </label>
            <input
              type="number"
              min={0}
              value={preset[key] ?? 0}
              onChange={(e) => handleChange(key, e.target.value)}
              className="w-full p-2 bg-black/30 border border-white/10 rounded text-white text-sm
                focus:border-site-blue/50 focus:outline-none transition-colors"
            />
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-2">
        <span className="text-white/60 text-sm">Итого:</span>
        <span
          className={`text-sm font-medium ${
            isValid ? 'text-green-400' : 'text-site-red'
          }`}
        >
          {sum} / 100
        </span>
        {!isValid && (
          <span className="text-site-red text-xs">
            {sum < 100
              ? `(нужно ещё ${100 - sum})`
              : `(лишних ${sum - 100})`}
          </span>
        )}
      </div>
    </div>
  );
};

export default StatPresetEditor;
export { DEFAULT_PRESET, STAT_FIELDS };
