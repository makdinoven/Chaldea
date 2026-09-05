import { useState } from 'react';
import { Save, PlusCircle, ChevronDown, RefreshCw } from 'react-feather';
import { LEVEL_RING_OPTIONS } from './types';

/** One class tree shown in the wheel, as far as the toolbar cares. */
export interface WheelToolbarTree {
  treeId: number;
  classId: number;
  label: string;
  accent: string;
  dirty: boolean;
}

interface WheelToolbarProps {
  trees: WheelToolbarTree[];
  onAddNode: (treeId: number, levelRing: number) => void;
  onSave: () => void;
  onReload: () => void;
  isSaving: boolean;
  isDirty: boolean;
}

const WheelToolbar = ({
  trees,
  onAddNode,
  onSave,
  onReload,
  isSaving,
  isDirty,
}: WheelToolbarProps) => {
  /** treeId whose ring menu is open, or null. */
  const [openMenuTreeId, setOpenMenuTreeId] = useState<number | null>(null);

  return (
    <div className="flex flex-wrap items-center gap-2 p-3 bg-black/30 backdrop-blur-sm border-b border-white/10 relative z-10">
      <button
        onClick={onSave}
        disabled={isSaving || !isDirty}
        className={`btn-blue flex items-center gap-1.5 text-sm !py-1.5 !px-3 ${
          !isDirty ? 'opacity-50 cursor-not-allowed' : ''
        }`}
      >
        <Save size={14} />
        {isSaving ? 'Сохранение...' : 'Сохранить'}
      </button>

      <button
        onClick={onReload}
        disabled={isSaving}
        className="btn-line flex items-center gap-1.5 text-sm !py-1.5 !px-3"
        title="Перечитать деревья с сервера"
      >
        <RefreshCw size={14} />
        Обновить
      </button>

      {/* One "add node" menu per class — a node always belongs to one tree */}
      {trees.map((tree) => (
        <div key={tree.treeId} className="relative">
          <button
            onClick={() => setOpenMenuTreeId(openMenuTreeId === tree.treeId ? null : tree.treeId)}
            className="btn-line flex items-center gap-1.5 text-sm !py-1.5 !px-3"
            style={{ borderColor: `${tree.accent}66`, color: tree.accent }}
          >
            <PlusCircle size={14} />
            {tree.label}
            {tree.dirty && <span className="text-gold text-xs">•</span>}
            <ChevronDown size={12} />
          </button>

          {openMenuTreeId === tree.treeId && (
            <div className="dropdown-menu absolute top-full left-0 mt-1 z-50 min-w-[180px]">
              {LEVEL_RING_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => {
                    onAddNode(tree.treeId, opt.value);
                    setOpenMenuTreeId(null);
                  }}
                  className="dropdown-item w-full text-left"
                >
                  Кольцо {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}

      <span className="text-white/35 text-xs ml-auto hidden lg:block">
        Позиции считаются из кольца — узлы не перетаскиваются. Порядок в кольце — поле «Порядок».
      </span>

      {isDirty && (
        <span className="text-gold text-xs font-medium">(есть несохранённые изменения)</span>
      )}
    </div>
  );
};

export default WheelToolbar;
