import { HexColorPicker } from 'react-colorful';

const PRESET_COLORS = [
  '#f0d95c',
  '#ff6347',
  '#76a6bd',
  '#c0c0c0',
  '#b875bd',
  '#88b332',
  '#ff9900',
  '#e94545',
  '#1a1a2e',
  '#ffffff',
];

interface ColorPickerProps {
  color: string;
  onChange: (color: string) => void;
}

const ColorPicker = ({ color, onChange }: ColorPickerProps) => {
  return (
    <div className="flex flex-col gap-3">
      <HexColorPicker color={color} onChange={onChange} style={{ width: '100%', height: 150 }} />
      <div className="flex flex-wrap gap-2">
        {PRESET_COLORS.map((preset) => (
          <button
            key={preset}
            type="button"
            onClick={() => onChange(preset)}
            className={`w-7 h-7 rounded-full border-2 transition-all duration-200 ${
              color.toLowerCase() === preset.toLowerCase()
                ? 'border-white scale-110'
                : 'border-white/20 hover:border-white/50'
            }`}
            style={{ backgroundColor: preset }}
            title={preset}
          />
        ))}
      </div>
    </div>
  );
};

export default ColorPicker;
