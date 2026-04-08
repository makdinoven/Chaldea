// EffectEditor — admin editor for a single effect entry (FEAT-125, Tailwind)
import { COMPLEX_EFFECTS } from './skillConstants';
import type { EffectEntry } from '../SkillTreeView/types';

interface EffectEditorProps {
  effect: EffectEntry;
  onChange: (e: EffectEntry) => void;
  onDelete: () => void;
}

const EffectEditor = ({ effect, onChange, onDelete }: EffectEditorProps) => {
  const handleField = <K extends keyof EffectEntry>(field: K, value: EffectEntry[K]) => {
    onChange({ ...effect, [field]: value });
  };

  return (
    <div className="rounded-card border border-white/10 bg-white/[0.03] p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h5 className="text-white/80 text-xs sm:text-sm font-medium">
          Эффект: {effect.effect_name || '(нет)'}
        </h5>
        <button
          type="button"
          onClick={onDelete}
          className="text-xs text-red-400 hover:text-red-300 underline"
        >
          Удалить
        </button>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-white/60 text-[11px]">Цель:</label>
        <div className="inline-flex rounded-sm overflow-hidden border border-white/15 w-fit">
          {(['self', 'enemy'] as const).map((side) => {
            const active = (effect.target_side ?? 'self') === side;
            return (
              <button
                key={side}
                type="button"
                onClick={() => handleField('target_side', side)}
                className={`px-3 py-1 text-xs transition-colors ${
                  active
                    ? 'bg-gold/20 text-gold'
                    : 'bg-white/[0.03] text-white/60 hover:bg-white/[0.08]'
                }`}
              >
                {side === 'self' ? 'На себя' : 'На врага'}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-white/60 text-[11px]">Тип эффекта:</label>
        <select
          value={effect.effect_name || ''}
          onChange={(e) => handleField('effect_name', e.target.value)}
          className="gray-bg rounded-sm px-2 py-1 text-white text-sm"
        >
          <option value="">(не выбрано)</option>
          {COMPLEX_EFFECTS.map((cf) => (
            <option key={cf.value} value={cf.value}>
              {cf.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-white/60 text-[11px]">Длительность (ходы):</label>
        <input
          type="number"
          min={0}
          value={effect.duration ?? 0}
          onChange={(e) => handleField('duration', Number(e.target.value))}
          className="gray-bg rounded-sm px-2 py-1 text-white text-sm"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-white/60 text-[11px]">Магнитуда:</label>
        <input
          type="number"
          value={effect.magnitude ?? 0}
          onChange={(e) => handleField('magnitude', Number(e.target.value))}
          className="gray-bg rounded-sm px-2 py-1 text-white text-sm"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-white/60 text-[11px]">Описание:</label>
        <input
          type="text"
          value={effect.description ?? ''}
          onChange={(e) => handleField('description', e.target.value)}
          className="gray-bg rounded-sm px-2 py-1 text-white text-sm"
        />
      </div>
    </div>
  );
};

export default EffectEditor;
