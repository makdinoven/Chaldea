import { useState } from 'react';
import { Save, PlusCircle, Layout, Settings, ChevronDown } from 'react-feather';
import { LEVEL_RING_OPTIONS } from './types';

interface TreeToolbarProps {
  treeName: string;
  treeDescription: string;
  onTreeNameChange: (name: string) => void;
  onTreeDescriptionChange: (desc: string) => void;
  onSave: () => void;
  onAddNode: (levelRing: number) => void;
  onAutoLayout: () => void;
  isSaving: boolean;
  isDirty: boolean;
  hasTree: boolean;
}

const TreeToolbar = ({
  treeName,
  treeDescription,
  onTreeNameChange,
  onTreeDescriptionChange,
  onSave,
  onAddNode,
  onAutoLayout,
  isSaving,
  isDirty,
  hasTree,
}: TreeToolbarProps) => {
  const [showAddMenu, setShowAddMenu] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  if (!hasTree) return null;

  return (
    <div className="flex flex-wrap items-center gap-2 p-3 bg-black/30 backdrop-blur-sm border-b border-white/10 relative z-10">
      {/* Save */}
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

      {/* Add node dropdown */}
      <div className="relative">
        <button
          onClick={() => setShowAddMenu(!showAddMenu)}
          className="btn-line flex items-center gap-1.5 text-sm !py-1.5 !px-3"
        >
          <PlusCircle size={14} />
          Добавить узел
          <ChevronDown size={12} />
        </button>

        {showAddMenu && (
          <div className="dropdown-menu absolute top-full left-0 mt-1 z-50 min-w-[180px]">
            {LEVEL_RING_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => {
                  onAddNode(opt.value);
                  setShowAddMenu(false);
                }}
                className="dropdown-item w-full text-left"
              >
                Кольцо {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Auto-layout */}
      <button
        onClick={onAutoLayout}
        className="btn-line flex items-center gap-1.5 text-sm !py-1.5 !px-3"
      >
        <Layout size={14} />
        Авто-раскладка
      </button>

      {/* Settings toggle */}
      <button
        onClick={() => setShowSettings(!showSettings)}
        className="btn-line flex items-center gap-1.5 text-sm !py-1.5 !px-3 ml-auto"
      >
        <Settings size={14} />
        Настройки дерева
      </button>

      {/* Dirty indicator */}
      {isDirty && (
        <span className="text-gold text-xs font-medium ml-2">
          (есть несохранённые изменения)
        </span>
      )}

      {/* Settings panel */}
      {showSettings && (
        <div className="w-full flex flex-col sm:flex-row gap-3 pt-3 border-t border-white/10 mt-1">
          <div className="flex-1">
            <label className="text-white/60 text-xs font-medium uppercase tracking-wider mb-1 block">
              Название дерева
            </label>
            <input
              type="text"
              value={treeName}
              onChange={(e) => onTreeNameChange(e.target.value)}
              className="input-underline w-full"
              placeholder="Название дерева"
            />
          </div>
          <div className="flex-1">
            <label className="text-white/60 text-xs font-medium uppercase tracking-wider mb-1 block">
              Описание дерева
            </label>
            <input
              type="text"
              value={treeDescription}
              onChange={(e) => onTreeDescriptionChange(e.target.value)}
              className="input-underline w-full"
              placeholder="Описание (необязательно)"
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default TreeToolbar;
