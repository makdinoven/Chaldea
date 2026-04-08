// SkillBaseEditor — admin editor for skill's base characteristics (FEAT-125 follow-up)
// Uses SkillEffectSections (5-section UX) wired to REST admin endpoints:
//   POST/PUT/DELETE /skills/admin/skills/{id}/base_damage[/{id}]
//   POST/PUT/DELETE /skills/admin/skills/{id}/base_effects[/{id}]
import { useState, useEffect, useRef, useCallback, type ChangeEvent } from 'react';
import toast from 'react-hot-toast';
import SkillEffectSections from './SkillEffectSections';
import { useAppDispatch } from '../../redux/store';
import {
  updateSkillBase,
  createBaseDamage,
  updateBaseDamage,
  deleteBaseDamage,
  createBaseEffect,
  updateBaseEffect,
  deleteBaseEffect,
  uploadSkillImage,
  fetchSkills,
  fetchSkillAdmin,
} from '../../redux/actions/skillsAdminActions';
import type {
  SkillWithPerks,
  DamageEntry,
  EffectEntry,
} from '../SkillTreeView/types';
import { CLASS_OPTIONS } from './skillConstants';

// Parse comma-separated class IDs ("1,3") into a Set for quick lookup.
const parseIdList = (raw: string | null | undefined): Set<string> => {
  if (!raw) return new Set();
  return new Set(
    raw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
  );
};

// Serialize selected IDs back to the "1,3" shape the backend stores
// (matches FIND_IN_SET usage in character-service seeds).
const serializeIdList = (ids: Set<string>): string => {
  return Array.from(ids)
    .sort((a, b) => Number(a) - Number(b))
    .join(',');
};

interface SkillBaseEditorProps {
  skill: SkillWithPerks;
  onRefresh: () => void;
}

interface CoreFields {
  name: string;
  skill_type: string;
  purchase_cost: number;
  description: string;
  min_level: number;
  class_limitations: string;
  race_limitations: string;
  subrace_limitations: string;
}

interface Scalars {
  cost_energy: number;
  cost_mana: number;
  cooldown: number;
  level_requirement: number;
}

const SKILL_TYPES: Array<{ value: string; label: string }> = [
  { value: 'attack', label: 'Атакующий' },
  { value: 'defense', label: 'Защитный' },
  { value: 'support', label: 'Поддержка' },
];

const CARD_CLASS = 'rounded-card gray-bg border border-white/10 p-3 sm:p-4 space-y-3';

const DEBOUNCE_MS = 400;

const SkillBaseEditor = ({ skill, onRefresh }: SkillBaseEditorProps) => {
  const dispatch = useAppDispatch();

  const [core, setCore] = useState<CoreFields>({
    name: skill.name,
    skill_type: skill.skill_type,
    purchase_cost: skill.purchase_cost ?? 0,
    description: skill.description ?? '',
    min_level: skill.min_level ?? 1,
    class_limitations: skill.class_limitations ?? '',
    race_limitations: skill.race_limitations ?? '',
    subrace_limitations: skill.subrace_limitations ?? '',
  });
  const [scalars, setScalars] = useState<Scalars>({
    cost_energy: skill.base.cost_energy,
    cost_mana: skill.base.cost_mana,
    cooldown: skill.base.cooldown,
    level_requirement: skill.base.level_requirement,
  });
  const [savingScalars, setSavingScalars] = useState(false);
  const [uploadingImage, setUploadingImage] = useState(false);

  // Local mirror of server arrays so typing in inputs feels instant while
  // debounced API writes flush in the background.
  const [damageDraft, setDamageDraft] = useState<DamageEntry[]>(skill.base.damage_entries);
  const [effectsDraft, setEffectsDraft] = useState<EffectEntry[]>(skill.base.effects);

  useEffect(() => {
    setCore({
      name: skill.name,
      skill_type: skill.skill_type,
      purchase_cost: skill.purchase_cost ?? 0,
      description: skill.description ?? '',
      min_level: skill.min_level ?? 1,
      class_limitations: skill.class_limitations ?? '',
      race_limitations: skill.race_limitations ?? '',
      subrace_limitations: skill.subrace_limitations ?? '',
    });
    setScalars({
      cost_energy: skill.base.cost_energy,
      cost_mana: skill.base.cost_mana,
      cooldown: skill.base.cooldown,
      level_requirement: skill.base.level_requirement,
    });
    setDamageDraft(skill.base.damage_entries);
    setEffectsDraft(skill.base.effects);
  }, [skill]);

  const patchCore = <K extends keyof CoreFields>(k: K, v: CoreFields[K]) => {
    setCore((c) => ({ ...c, [k]: v }));
  };

  const handleImageUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingImage(true);
    try {
      await dispatch(uploadSkillImage({ skillId: skill.id, file })).unwrap();
      dispatch(fetchSkills());
      dispatch(fetchSkillAdmin(skill.id));
      toast.success('Изображение обновлено');
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Ошибка загрузки изображения');
    } finally {
      setUploadingImage(false);
    }
  };

  // Debounce timers keyed by row id
  const dmgTimers = useRef<Record<number, ReturnType<typeof setTimeout>>>({});
  const effTimers = useRef<Record<number, ReturnType<typeof setTimeout>>>({});

  useEffect(() => {
    const dt = dmgTimers.current;
    const et = effTimers.current;
    return () => {
      Object.values(dt).forEach((t) => clearTimeout(t));
      Object.values(et).forEach((t) => clearTimeout(t));
    };
  }, []);

  const patchScalar = (k: keyof Scalars, v: string) => {
    const n = Number(v);
    setScalars((s) => ({ ...s, [k]: Number.isFinite(n) ? n : 0 }));
  };

  const handleSaveScalars = async () => {
    if (!core.name.trim()) {
      toast.error('Имя навыка не может быть пустым');
      return;
    }
    setSavingScalars(true);
    try {
      await dispatch(
        updateSkillBase({
          skillId: skill.id,
          payload: {
            name: core.name.trim(),
            skill_type: core.skill_type,
            description: core.description || null,
            class_limitations: core.class_limitations.trim() || null,
            race_limitations: core.race_limitations.trim() || null,
            subrace_limitations: core.subrace_limitations.trim() || null,
            min_level: core.min_level,
            purchase_cost: core.purchase_cost,
            skill_image: skill.skill_image,
            cost_energy: scalars.cost_energy,
            cost_mana: scalars.cost_mana,
            cooldown: scalars.cooldown,
            level_requirement: scalars.level_requirement,
          },
        })
      ).unwrap();
      toast.success('Базовые характеристики сохранены');
      dispatch(fetchSkills());
      onRefresh();
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Ошибка сохранения базовых характеристик');
    } finally {
      setSavingScalars(false);
    }
  };

  // ---- Damage handlers ----

  const onAddDamage = useCallback(
    async (d: DamageEntry) => {
      try {
        const created = await dispatch(
          createBaseDamage({ skillId: skill.id, payload: d })
        ).unwrap();
        setDamageDraft((arr) => [...arr, created]);
        toast.success('Запись урона создана');
      } catch (err) {
        toast.error(typeof err === 'string' ? err : 'Ошибка создания урона');
        throw err;
      }
    },
    [dispatch, skill.id]
  );

  const onUpdateDamage = useCallback(
    async (d: DamageEntry) => {
      if (d.id === undefined) return;
      // Instant local update
      setDamageDraft((arr) => arr.map((x) => (x.id === d.id ? d : x)));
      // Debounced PUT
      const id = d.id;
      if (dmgTimers.current[id]) clearTimeout(dmgTimers.current[id]);
      dmgTimers.current[id] = setTimeout(() => {
        dispatch(updateBaseDamage({ skillId: skill.id, damageId: id, payload: d }))
          .unwrap()
          .catch((err: unknown) => {
            toast.error(typeof err === 'string' ? err : 'Ошибка обновления урона');
          });
      }, DEBOUNCE_MS);
    },
    [dispatch, skill.id]
  );

  const onDeleteDamage = useCallback(
    async (d: DamageEntry) => {
      if (d.id === undefined) return;
      try {
        await dispatch(deleteBaseDamage({ skillId: skill.id, damageId: d.id })).unwrap();
        setDamageDraft((arr) => arr.filter((x) => x.id !== d.id));
        toast.success('Запись урона удалена');
      } catch (err) {
        toast.error(typeof err === 'string' ? err : 'Ошибка удаления урона');
        throw err;
      }
    },
    [dispatch, skill.id]
  );

  // ---- Effect handlers ----

  const onAddEffect = useCallback(
    async (e: EffectEntry) => {
      try {
        const created = await dispatch(
          createBaseEffect({ skillId: skill.id, payload: e })
        ).unwrap();
        setEffectsDraft((arr) => [...arr, created]);
        toast.success('Эффект создан');
      } catch (err) {
        toast.error(typeof err === 'string' ? err : 'Ошибка создания эффекта');
        throw err;
      }
    },
    [dispatch, skill.id]
  );

  const onUpdateEffect = useCallback(
    async (e: EffectEntry) => {
      if (e.id === undefined) return;
      setEffectsDraft((arr) => arr.map((x) => (x.id === e.id ? e : x)));
      const id = e.id;
      if (effTimers.current[id]) clearTimeout(effTimers.current[id]);
      effTimers.current[id] = setTimeout(() => {
        dispatch(updateBaseEffect({ skillId: skill.id, effectId: id, payload: e }))
          .unwrap()
          .catch((err: unknown) => {
            toast.error(typeof err === 'string' ? err : 'Ошибка обновления эффекта');
          });
      }, DEBOUNCE_MS);
    },
    [dispatch, skill.id]
  );

  const onDeleteEffect = useCallback(
    async (e: EffectEntry) => {
      if (e.id === undefined) return;
      try {
        await dispatch(deleteBaseEffect({ skillId: skill.id, effectId: e.id })).unwrap();
        setEffectsDraft((arr) => arr.filter((x) => x.id !== e.id));
        toast.success('Эффект удалён');
      } catch (err) {
        toast.error(typeof err === 'string' ? err : 'Ошибка удаления эффекта');
        throw err;
      }
    },
    [dispatch, skill.id]
  );

  const inputBase =
    'bg-black/40 border border-white/15 rounded-sm px-2 py-1 text-white text-sm w-full min-w-0 focus:outline-none focus:border-gold/60';
  const labelBase = 'text-white/70 text-[11px]';

  return (
    <div className="space-y-4">
      {/* ===== Основные данные навыка ===== */}
      <div className={CARD_CLASS}>
        <h3 className="gold-text text-sm sm:text-base font-medium">Основные данные навыка</h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="flex flex-col gap-1 sm:col-span-2">
            <label className={labelBase}>Имя навыка:</label>
            <input
              type="text"
              value={core.name}
              onChange={(e) => patchCore('name', e.target.value)}
              className={inputBase}
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className={labelBase}>Тип навыка:</label>
            <select
              value={core.skill_type}
              onChange={(e) => patchCore('skill_type', e.target.value)}
              className={inputBase}
            >
              {SKILL_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label className={labelBase}>Цена покупки (опыт):</label>
            <input
              type="number"
              value={core.purchase_cost}
              onChange={(e) => patchCore('purchase_cost', Number(e.target.value) || 0)}
              className={inputBase}
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className={labelBase}>Мин. уровень персонажа:</label>
            <input
              type="number"
              value={core.min_level}
              onChange={(e) => patchCore('min_level', Number(e.target.value) || 1)}
              className={inputBase}
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className={labelBase}>Изображение навыка:</label>
            <div className="flex items-center gap-2">
              {skill.skill_image ? (
                <img
                  src={skill.skill_image}
                  alt=""
                  className="w-10 h-10 rounded-sm object-cover border border-white/15"
                />
              ) : (
                <div className="w-10 h-10 rounded-sm bg-white/10 border border-white/15" />
              )}
              <label className="btn-line px-3 py-1 text-xs cursor-pointer whitespace-nowrap">
                {uploadingImage ? 'Загрузка...' : 'Загрузить'}
                <input
                  type="file"
                  accept="image/*"
                  onChange={handleImageUpload}
                  disabled={uploadingImage}
                  className="hidden"
                />
              </label>
            </div>
          </div>

          <div className="flex flex-col gap-1 sm:col-span-2">
            <label className={labelBase}>Описание:</label>
            <textarea
              value={core.description}
              onChange={(e) => patchCore('description', e.target.value)}
              rows={3}
              className={inputBase}
            />
          </div>

          <div className="flex flex-col gap-1 sm:col-span-2">
            <label className={labelBase}>Доступно классам:</label>
            <div className="flex flex-wrap gap-2">
              {CLASS_OPTIONS.map((opt) => {
                const selected = parseIdList(core.class_limitations);
                const isChecked = selected.has(opt.value);
                return (
                  <label
                    key={opt.value}
                    className={`flex items-center gap-2 rounded-sm px-3 py-1.5 text-sm cursor-pointer border transition-colors ${
                      isChecked
                        ? 'border-amber-400/60 bg-amber-400/10 text-amber-200'
                        : 'border-white/15 bg-white/5 text-white/70 hover:border-white/30'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={(e) => {
                        const next = parseIdList(core.class_limitations);
                        if (e.target.checked) next.add(opt.value);
                        else next.delete(opt.value);
                        patchCore('class_limitations', serializeIdList(next));
                      }}
                      className="accent-amber-400"
                    />
                    <span>{opt.label}</span>
                  </label>
                );
              })}
            </div>
            <span className="text-white/40 text-[11px]">
              Пусто = навык доступен всем классам.
            </span>
          </div>

        </div>
      </div>

      {/* ===== Числовые скаляры ===== */}
      <div className={CARD_CLASS}>
        <h3 className="gold-text text-sm sm:text-base font-medium">Базовые характеристики</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {([
            ['cost_energy', 'Энергия'],
            ['cost_mana', 'Мана'],
            ['cooldown', 'КД'],
            ['level_requirement', 'Треб. уровень'],
          ] as const).map(([key, label]) => (
            <div key={key} className="flex flex-col gap-1">
              <label className={labelBase}>{label}:</label>
              <input
                type="number"
                value={scalars[key]}
                onChange={(e) => patchScalar(key, e.target.value)}
                className={inputBase}
              />
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={handleSaveScalars}
          disabled={savingScalars}
          className="btn-blue px-4 py-1.5 text-sm disabled:opacity-40"
        >
          {savingScalars ? 'Сохранение...' : 'Сохранить базовые характеристики'}
        </button>
      </div>

      {/* ===== 5-section editor for base damage + effects ===== */}
      <SkillEffectSections
        damageEntries={damageDraft}
        effects={effectsDraft}
        onAddDamage={onAddDamage}
        onUpdateDamage={onUpdateDamage}
        onDeleteDamage={onDeleteDamage}
        onAddEffect={onAddEffect}
        onUpdateEffect={onUpdateEffect}
        onDeleteEffect={onDeleteEffect}
        confirmDelete
      />
    </div>
  );
};

export default SkillBaseEditor;
