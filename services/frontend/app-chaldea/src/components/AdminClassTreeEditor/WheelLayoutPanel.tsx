import toast from 'react-hot-toast';
import { RotateCcw, Copy } from 'react-feather';
import {
  DEFAULT_WHEEL_LAYOUT,
  type WheelLayoutConfig,
} from '../SkillTreeView/utils/combineTrees';

/**
 * Live controls for the wheel's shape.
 *
 * These only affect this browser — they are kept in localStorage, not on the
 * server, so players still see the values baked into DEFAULT_WHEEL_LAYOUT. The
 * panel is for finding numbers that look right; "Скопировать" puts them on the
 * clipboard so they can be committed as the new defaults.
 */

interface WheelLayoutPanelProps {
  config: WheelLayoutConfig;
  onChange: (config: WheelLayoutConfig) => void;
}

interface SliderSpec {
  key: keyof Omit<WheelLayoutConfig, 'spread'>;
  label: string;
  min: number;
  max: number;
  step: number;
  unit: string;
}

const SLIDERS: SliderSpec[] = [
  { key: 'innerRadius', label: 'Радиус центра', min: 0, max: 500, step: 10, unit: 'px' },
  { key: 'ringSpacing', label: 'Шаг между кольцами', min: 40, max: 400, step: 10, unit: 'px' },
  { key: 'arcSpacing', label: 'Зазор в кольце', min: 40, max: 400, step: 10, unit: 'px' },
  { key: 'sectorFill', label: 'Ширина сектора', min: 0.2, max: 1, step: 0.05, unit: '' },
  { key: 'startAngleDeg', label: 'Поворот колеса', min: -180, max: 180, step: 5, unit: '°' },
];

const WheelLayoutPanel = ({ config, onChange }: WheelLayoutPanelProps) => {
  const set = <K extends keyof WheelLayoutConfig>(key: K, value: WheelLayoutConfig[K]) =>
    onChange({ ...config, [key]: value });

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(config, null, 2));
      toast.success('Значения скопированы');
    } catch {
      toast.error('Не удалось скопировать — буфер обмена недоступен');
    }
  };

  return (
    <div className="w-full flex flex-col gap-3 p-3 bg-black/20 border-b border-white/10">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-white/60 text-xs font-medium uppercase tracking-wider">
          Вид колеса
        </span>

        {/* Spread mode */}
        <div className="flex gap-1 rounded-card bg-white/[0.04] p-1">
          {([
            ['fill', 'Кольцами'],
            ['arc', 'Клином'],
          ] as const).map(([value, label]) => (
            <button
              key={value}
              onClick={() => set('spread', value)}
              className={`px-2.5 py-1 rounded-card text-[11px] uppercase tracking-wide transition-colors duration-200 ${
                config.spread === value ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <button
          onClick={() => onChange(DEFAULT_WHEEL_LAYOUT)}
          className="btn-line flex items-center gap-1.5 text-xs !py-1 !px-2.5"
        >
          <RotateCcw size={12} />
          Сбросить
        </button>
        <button
          onClick={handleCopy}
          className="btn-line flex items-center gap-1.5 text-xs !py-1 !px-2.5"
        >
          <Copy size={12} />
          Скопировать
        </button>

        <span className="text-white/30 text-[11px] ml-auto hidden xl:block">
          Только в этом браузере. Чтобы увидели игроки — пришлите скопированные значения.
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-x-4 gap-y-2">
        {SLIDERS.map((slider) => {
          // "Зазор в кольце" only does anything in wedge mode.
          const disabled = slider.key === 'arcSpacing' && config.spread === 'fill';
          const value = config[slider.key];
          return (
            <label key={slider.key} className={`flex flex-col gap-0.5 ${disabled ? 'opacity-40' : ''}`}>
              <span className="flex justify-between text-[11px]">
                <span className="text-white/50">{slider.label}</span>
                <span className="text-white/80 tabular-nums">
                  {slider.step < 1 ? value.toFixed(2) : value}
                  {slider.unit}
                </span>
              </span>
              <input
                type="range"
                min={slider.min}
                max={slider.max}
                step={slider.step}
                value={value}
                disabled={disabled}
                onChange={(e) => set(slider.key, Number(e.target.value))}
                className="w-full accent-gold"
              />
            </label>
          );
        })}
      </div>
    </div>
  );
};

export default WheelLayoutPanel;
