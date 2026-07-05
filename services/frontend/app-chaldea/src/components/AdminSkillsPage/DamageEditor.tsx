// DamageEditor — admin editor for a single damage entry (FEAT-125, Tailwind)
import { DAMAGE_TYPES } from './skillConstants';
import type { DamageEntry } from '../SkillTreeView/types';

interface DamageEditorProps {
  damage: DamageEntry;
  onChange: (d: DamageEntry) => void;
  onDelete: () => void;
}

const DamageEditor = ({ damage, onChange, onDelete }: DamageEditorProps) => {
  const handleField = <K extends keyof DamageEntry>(field: K, value: DamageEntry[K]) => {
    onChange({ ...damage, [field]: value });
  };

  return (
    <div className="rounded-card border border-white/10 bg-white/[0.03] p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h5 className="text-white/80 text-xs sm:text-sm font-medium">
          Урон: {damage.damage_type || '(тип)'}
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
            const active = (damage.target_side ?? 'enemy') === side;
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

      {(damage.target_side ?? 'enemy') === 'enemy' && (
        <div className="flex flex-col gap-1">
          <label className="text-white/60 text-[11px]">Форма АоЕ:</label>
          <div className="inline-flex flex-wrap rounded-sm overflow-hidden border border-white/15 w-fit">
            {([
              ['single', 'Одна цель'],
              ['splash', 'Соседи'],
              ['cleave', 'Пробой'],
              ['all', 'Все враги'],
              ['random_n', 'Случайные'],
            ] as const).map(([shape, label]) => {
              const active = (damage.aoe_shape ?? 'single') === shape;
              return (
                <button
                  key={shape}
                  type="button"
                  onClick={() => handleField('aoe_shape', shape)}
                  className={`px-3 py-1 text-xs transition-colors ${
                    active ? 'bg-gold/20 text-gold' : 'bg-white/[0.03] text-white/60 hover:bg-white/[0.08]'
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
          {(damage.aoe_shape ?? 'single') !== 'single' && (
            <div className="flex flex-wrap gap-3 mt-1">
              <label className="text-white/60 text-[11px] flex items-center gap-1">
                Урон соседям, %:
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={damage.aoe_falloff ?? 50}
                  onChange={(e) => handleField('aoe_falloff', Number(e.target.value))}
                  className="gray-bg rounded-sm px-2 py-1 text-white text-sm w-16"
                />
              </label>
              {(damage.aoe_shape ?? 'single') === 'random_n' && (
                <label className="text-white/60 text-[11px] flex items-center gap-1">
                  Всего целей:
                  <input
                    type="number"
                    min={1}
                    value={damage.aoe_max_targets ?? 3}
                    onChange={(e) => handleField('aoe_max_targets', Number(e.target.value))}
                    className="gray-bg rounded-sm px-2 py-1 text-white text-sm w-16"
                  />
                </label>
              )}
            </div>
          )}
        </div>
      )}

      <div className="flex flex-col gap-1">
        <label className="text-white/60 text-[11px]">Тип урона:</label>
        <select
          value={damage.damage_type || ''}
          onChange={(e) => handleField('damage_type', e.target.value)}
          className="gray-bg rounded-sm px-2 py-1 text-white text-sm"
        >
          <option value="">(не выбрано)</option>
          {DAMAGE_TYPES.map((dt) => (
            <option key={dt.value} value={dt.value}>
              {dt.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-white/60 text-[11px]">Количество:</label>
        <input
          type="text"
          value={String(damage.amount ?? '')}
          onChange={(e) => handleField('amount', e.target.value)}
          className="gray-bg rounded-sm px-2 py-1 text-white text-sm"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-white/60 text-[11px]">Описание:</label>
        <input
          type="text"
          value={damage.description ?? ''}
          onChange={(e) => handleField('description', e.target.value)}
          className="gray-bg rounded-sm px-2 py-1 text-white text-sm"
        />
      </div>
    </div>
  );
};

export default DamageEditor;
