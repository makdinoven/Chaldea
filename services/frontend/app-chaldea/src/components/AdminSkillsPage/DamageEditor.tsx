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
