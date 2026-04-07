// PerkPoolEditor — admin editor for a skill's base stats + flat perk pool (FEAT-125)
import { useState, useEffect } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import DamageEditor from './DamageEditor';
import EffectEditor from './EffectEditor';
import type {
  SkillWithPerks,
  SkillPerkRead,
  DamageEntry,
  EffectEntry,
} from '../SkillTreeView/types';

interface PerkPoolEditorProps {
  skill: SkillWithPerks;
  onRefresh: () => void;
}

const emptyDamage = (): DamageEntry => ({
  damage_type: '',
  amount: 0,
  chance: 100,
  target_side: 'enemy',
  weapon_slot: null,
  description: '',
});

const emptyEffect = (): EffectEntry => ({
  target_side: 'enemy',
  effect_name: '',
  description: '',
  chance: 100,
  duration: 0,
  magnitude: 0,
  attribute_key: null,
});

const emptyPerk = (): SkillPerkRead => ({
  id: 0,
  name: 'Новый перк',
  description: '',
  perk_image: null,
  delta_cost_energy: null,
  delta_cost_mana: null,
  delta_cooldown: null,
  delta_level_requirement: null,
  sort_order: 0,
  damage_entries: [],
  effects: [],
});

const extractError = (err: unknown, fallback: string): string => {
  const e = err as { response?: { data?: { detail?: string } }; message?: string };
  return e.response?.data?.detail || e.message || fallback;
};

interface PerkRowProps {
  perk: SkillPerkRead;
  skillId: number;
  isNew: boolean;
  onSaved: () => void;
  onRemoveLocal: () => void;
}

const PerkRow = ({ perk, skillId, isNew, onSaved, onRemoveLocal }: PerkRowProps) => {
  const [draft, setDraft] = useState<SkillPerkRead>(perk);
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState(isNew);

  useEffect(() => {
    setDraft(perk);
  }, [perk]);

  const patch = <K extends keyof SkillPerkRead>(field: K, value: SkillPerkRead[K]) => {
    setDraft((d) => ({ ...d, [field]: value }));
  };

  const numOrNull = (v: string): number | null => (v.trim() === '' ? null : Number(v));

  const handleSave = async () => {
    if (!draft.name.trim()) {
      toast.error('Введите название перка');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        name: draft.name,
        description: draft.description,
        perk_image: draft.perk_image,
        delta_cost_energy: draft.delta_cost_energy,
        delta_cost_mana: draft.delta_cost_mana,
        delta_cooldown: draft.delta_cooldown,
        delta_level_requirement: draft.delta_level_requirement,
        sort_order: draft.sort_order ?? 0,
        damage_entries: draft.damage_entries,
        effects: draft.effects,
      };
      if (isNew) {
        await axios.post(`/skills/admin/skills/${skillId}/perks`, payload);
        toast.success('Перк создан');
      } else {
        await axios.put(`/skills/admin/skill_perks/${draft.id}`, payload);
        toast.success('Перк обновлён');
      }
      onSaved();
    } catch (err) {
      toast.error(extractError(err, 'Ошибка сохранения перка'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (isNew) {
      onRemoveLocal();
      return;
    }
    if (!window.confirm(`Удалить перк "${draft.name}"?`)) return;
    try {
      await axios.delete(`/skills/admin/skill_perks/${draft.id}`);
      toast.success('Перк удалён');
      onSaved();
    } catch (err) {
      toast.error(extractError(err, 'Ошибка удаления перка'));
    }
  };

  return (
    <div className="rounded-card border border-white/15 bg-white/[0.02] p-3 sm:p-4">
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-left flex-1 gold-text text-sm sm:text-base font-medium truncate"
        >
          {expanded ? '▾' : '▸'} {draft.name || '(без названия)'}
        </button>
        <button
          type="button"
          onClick={handleDelete}
          className="text-xs text-red-400 hover:text-red-300 underline"
        >
          Удалить
        </button>
      </div>

      {expanded && (
        <div className="mt-3 space-y-3">
          <div className="flex flex-col gap-1">
            <label className="text-white/60 text-[11px]">Название:</label>
            <input
              type="text"
              value={draft.name}
              onChange={(e) => patch('name', e.target.value)}
              className="gray-bg rounded-sm px-2 py-1 text-white text-sm"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-white/60 text-[11px]">Описание:</label>
            <textarea
              value={draft.description ?? ''}
              onChange={(e) => patch('description', e.target.value)}
              rows={2}
              className="gray-bg rounded-sm px-2 py-1 text-white text-sm"
            />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {([
              ['delta_cost_energy', 'Δ Энергия'],
              ['delta_cost_mana', 'Δ Мана'],
              ['delta_cooldown', 'Δ КД'],
              ['delta_level_requirement', 'Δ Уровень'],
            ] as const).map(([key, label]) => (
              <div key={key} className="flex flex-col gap-1">
                <label className="text-white/60 text-[11px]">{label}:</label>
                <input
                  type="number"
                  value={draft[key] ?? ''}
                  onChange={(e) => patch(key, numOrNull(e.target.value))}
                  className="gray-bg rounded-sm px-2 py-1 text-white text-sm"
                />
              </div>
            ))}
          </div>

          {/* Damage entries */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <h5 className="text-white/70 text-xs uppercase">Доп. урон</h5>
              <button
                type="button"
                onClick={() => patch('damage_entries', [...draft.damage_entries, emptyDamage()])}
                className="text-xs text-gold hover:text-gold/80"
              >
                + добавить
              </button>
            </div>
            <div className="space-y-2">
              {draft.damage_entries.map((d, i) => (
                <DamageEditor
                  key={i}
                  damage={d}
                  onChange={(nd) => {
                    const copy = [...draft.damage_entries];
                    copy[i] = nd;
                    patch('damage_entries', copy);
                  }}
                  onDelete={() => {
                    const copy = draft.damage_entries.filter((_, j) => j !== i);
                    patch('damage_entries', copy);
                  }}
                />
              ))}
            </div>
          </div>

          {/* Effects */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <h5 className="text-white/70 text-xs uppercase">Доп. эффекты</h5>
              <button
                type="button"
                onClick={() => patch('effects', [...draft.effects, emptyEffect()])}
                className="text-xs text-gold hover:text-gold/80"
              >
                + добавить
              </button>
            </div>
            <div className="space-y-2">
              {draft.effects.map((e, i) => (
                <EffectEditor
                  key={i}
                  effect={e}
                  onChange={(ne) => {
                    const copy = [...draft.effects];
                    copy[i] = ne;
                    patch('effects', copy);
                  }}
                  onDelete={() => {
                    const copy = draft.effects.filter((_, j) => j !== i);
                    patch('effects', copy);
                  }}
                />
              ))}
            </div>
          </div>

          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="btn-blue px-4 py-1.5 text-sm disabled:opacity-40"
          >
            {saving ? 'Сохранение...' : 'Сохранить перк'}
          </button>
        </div>
      )}
    </div>
  );
};

const PerkPoolEditor = ({ skill, onRefresh }: PerkPoolEditorProps) => {
  const [newPerks, setNewPerks] = useState<SkillPerkRead[]>([]);

  const handleAddPerk = () => {
    setNewPerks((prev) => [...prev, { ...emptyPerk(), id: -Date.now() }]);
  };

  const handleNewSaved = () => {
    setNewPerks([]);
    onRefresh();
  };

  const total = skill.perks.length;
  const belowMin = total < 4;

  return (
    <div className="space-y-4">
      {/* Base stats (read-only summary) */}
      <div className="rounded-card border border-white/10 bg-white/[0.03] p-3 sm:p-4">
        <h3 className="gold-text text-sm sm:text-base font-medium mb-2">Базовые характеристики</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs sm:text-sm text-white/80">
          <div>Энергия: {skill.base.cost_energy}</div>
          <div>Мана: {skill.base.cost_mana}</div>
          <div>КД: {skill.base.cooldown}</div>
          <div>Треб. уровень: {skill.base.level_requirement}</div>
        </div>
        <p className="text-white/40 text-[10px] mt-2">
          Базовые поля, урон и эффекты редактируются через PATCH навыка. Здесь отображение для контекста.
        </p>
      </div>

      {/* Perk pool */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="gold-text text-sm sm:text-base font-medium">
            Пул перков ({total})
          </h3>
          <button
            type="button"
            onClick={handleAddPerk}
            className="btn-blue px-3 py-1.5 text-xs sm:text-sm"
          >
            + Добавить перк
          </button>
        </div>

        {belowMin && (
          <p className="text-amber-400/80 text-xs mb-2">
            Минимум 4 перка в пуле. Сейчас: {total}. Добавьте ещё {Math.max(0, 4 - total)}.
          </p>
        )}

        <div className="space-y-3">
          {skill.perks.map((p) => (
            <PerkRow
              key={p.id}
              perk={p}
              skillId={skill.id}
              isNew={false}
              onSaved={onRefresh}
              onRemoveLocal={() => {}}
            />
          ))}
          {newPerks.map((p) => (
            <PerkRow
              key={p.id}
              perk={p}
              skillId={skill.id}
              isNew
              onSaved={handleNewSaved}
              onRemoveLocal={() =>
                setNewPerks((prev) => prev.filter((np) => np.id !== p.id))
              }
            />
          ))}
        </div>
      </div>
    </div>
  );
};

export default PerkPoolEditor;
