import { useState } from 'react';
import type { Node } from 'reactflow';
import type { TreeNodeInTreeResponse, TreeNodeSkillRead, Subclass } from './types';
import { LEVEL_RING_OPTIONS, NODE_TYPE_OPTIONS } from './types';
import TreeSkillPicker from './TreeSkillPicker';
import { X, Plus, Trash2 } from 'react-feather';

interface TreeNodeInspectorProps {
  node: Node | null;
  subclasses: Subclass[];
  onUpdateField: (nodeId: string, field: string, value: unknown) => void;
  onRemoveNode: (nodeId: string) => void;
  onAddSkill: (nodeId: string, skill: { skill_id: number; skill_name: string; skill_type: string; skill_image: string | null }) => void;
  onRemoveSkill: (nodeId: string, skillId: number) => void;
  onClose: () => void;
}

const TreeNodeInspector = ({
  node,
  subclasses,
  onUpdateField,
  onRemoveNode,
  onAddSkill,
  onRemoveSkill,
  onClose,
}: TreeNodeInspectorProps) => {
  const [showSkillPicker, setShowSkillPicker] = useState(false);

  if (!node) return null;

  const data = node.data as TreeNodeInTreeResponse;
  const skills: TreeNodeSkillRead[] = data.skills ?? [];

  // Picking a subclass is the link (subclass_key) AND autofills name/description
  // straight from the registry, so the player preview always matches.
  const handleSubclassChange = (key: string) => {
    const sub = subclasses.find((s) => s.key === key);
    onUpdateField(node.id, 'subclass_key', key || null);
    if (sub) {
      onUpdateField(node.id, 'name', sub.name);
      onUpdateField(node.id, 'description', sub.description);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="gold-text text-lg font-medium uppercase">
          Свойства узла
        </h3>
        <button
          onClick={onClose}
          className="text-white/50 hover:text-site-blue transition-colors"
        >
          <X size={18} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto gold-scrollbar space-y-4">
        {/* Name */}
        <div>
          <label className="text-white/60 text-xs font-medium uppercase tracking-wider mb-1 block">
            Название
          </label>
          <input
            type="text"
            value={data.name}
            onChange={(e) => onUpdateField(node.id, 'name', e.target.value)}
            className="input-underline w-full"
            placeholder="Название узла"
          />
        </div>

        {/* Description */}
        <div>
          <label className="text-white/60 text-xs font-medium uppercase tracking-wider mb-1 block">
            Описание
          </label>
          <textarea
            value={data.description ?? ''}
            onChange={(e) => onUpdateField(node.id, 'description', e.target.value || null)}
            className="textarea-bordered w-full"
            rows={3}
            placeholder="Описание узла"
          />
        </div>

        {/* Level ring */}
        <div>
          <label className="text-white/60 text-xs font-medium uppercase tracking-wider mb-1 block">
            Кольцо уровня
          </label>
          <select
            value={data.level_ring}
            onChange={(e) => onUpdateField(node.id, 'level_ring', Number(e.target.value))}
            className="input-underline w-full bg-transparent"
          >
            {LEVEL_RING_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value} className="bg-site-dark text-white">
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Node type */}
        <div>
          <label className="text-white/60 text-xs font-medium uppercase tracking-wider mb-1 block">
            Тип узла
          </label>
          <select
            value={data.node_type}
            onChange={(e) => onUpdateField(node.id, 'node_type', e.target.value)}
            className="input-underline w-full bg-transparent"
          >
            {NODE_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value} className="bg-site-dark text-white">
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Subclass picker — only for subclass_choice nodes */}
        {data.node_type === 'subclass_choice' && (
          <div>
            <label className="text-white/60 text-xs font-medium uppercase tracking-wider mb-1 block">
              Подкласс
            </label>
            <select
              value={data.subclass_key ?? ''}
              onChange={(e) => handleSubclassChange(e.target.value)}
              className="input-underline w-full bg-transparent"
            >
              <option value="" className="bg-site-dark text-white">
                — выберите подкласс —
              </option>
              {subclasses.map((s) => (
                <option key={s.key} value={s.key} className="bg-site-dark text-white">
                  {s.name}
                </option>
              ))}
            </select>
            {!data.subclass_key && (
              <p className="text-site-red/70 text-xs mt-1">
                Узел выбора подкласса должен ссылаться на подкласс.
              </p>
            )}
            {subclasses.length === 0 && (
              <p className="text-white/30 text-xs mt-1 italic">
                Нет подклассов для этого класса.
              </p>
            )}
          </div>
        )}

        {/* Sort order */}
        <div>
          <label className="text-white/60 text-xs font-medium uppercase tracking-wider mb-1 block">
            Порядок сортировки
          </label>
          <input
            type="number"
            value={data.sort_order ?? 0}
            onChange={(e) => onUpdateField(node.id, 'sort_order', Number(e.target.value))}
            className="input-underline w-full"
          />
        </div>

        {/* Divider */}
        <div className="border-t border-white/10 pt-4">
          <div className="flex items-center justify-between mb-2">
            <label className="text-white/60 text-xs font-medium uppercase tracking-wider">
              Навыки ({skills.length})
            </label>
            <button
              onClick={() => setShowSkillPicker(true)}
              className="flex items-center gap-1 text-site-blue text-xs hover:text-white transition-colors"
            >
              <Plus size={14} />
              Добавить
            </button>
          </div>

          {skills.length === 0 && (
            <p className="text-white/30 text-sm italic">Нет назначенных навыков</p>
          )}

          <div className="space-y-2">
            {skills.map((skill) => (
              <div
                key={skill.skill_id}
                className="flex items-center gap-2 bg-white/5 rounded-card p-2"
              >
                {skill.skill_image ? (
                  <img
                    src={skill.skill_image}
                    alt={skill.skill_name ?? ''}
                    className="w-8 h-8 rounded object-cover flex-shrink-0"
                  />
                ) : (
                  <div className="w-8 h-8 rounded bg-white/10 flex-shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm truncate">
                    {skill.skill_name ?? `ID: ${skill.skill_id}`}
                  </p>
                  <p className="text-white/40 text-xs">{skill.skill_type ?? ''}</p>
                </div>
                <button
                  onClick={() => onRemoveSkill(node.id, skill.skill_id)}
                  className="text-white/30 hover:text-site-red transition-colors flex-shrink-0"
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Delete node */}
        <div className="pt-4 border-t border-white/10">
          <button
            onClick={() => {
              if (window.confirm('Удалить этот узел?')) {
                onRemoveNode(node.id);
              }
            }}
            className="flex items-center gap-2 text-site-red/80 text-sm hover:text-site-red transition-colors"
          >
            <Trash2 size={14} />
            Удалить узел
          </button>
        </div>
      </div>

      {/* Skill Picker Modal */}
      {showSkillPicker && (
        <TreeSkillPicker
          onSelect={(skill) => {
            onAddSkill(node.id, skill);
            setShowSkillPicker(false);
          }}
          onClose={() => setShowSkillPicker(false)}
          excludeSkillIds={skills.map((s) => s.skill_id)}
        />
      )}
    </div>
  );
};

export default TreeNodeInspector;
