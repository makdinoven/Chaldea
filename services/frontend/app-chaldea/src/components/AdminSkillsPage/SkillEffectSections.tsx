// SkillEffectSections — 5-section editor for skill damage + effects (FEAT-125 follow-up)
// Restores the old UX (5 distinct sections) while writing to the new flat perk data model.
// Used both by SkillBaseEditor (base damage/effects) and PerkPoolEditor (per-perk arrays).
//
// Sections:
//   1. Колич. урон         — damage rows (DamageEntry)
//   2. Бафф / Дебафф       — effect_name = "Buff: <type>" / "Debuff: <type>"
//   3. Резисты             — effect_name = "Resist: <type>" / "Vulnerability: <type>"
//   4. Стат-модификаторы   — effect_name = "StatModifier", attribute_key = <stat>
//   5. Сложн. эффекты      — freeform complex effects (Bleeding, Poison, ...)
//
// All effect composition logic mirrors the deleted utils/preparePayload.jsx from commit 4d50ce6^.
import { useMemo } from 'react';
import {
  DAMAGE_TYPES,
  WEAPON_SLOTS,
  STAT_MODIFIERS,
  COMPLEX_EFFECTS,
} from './skillConstants';
import type { DamageEntry, EffectEntry } from '../SkillTreeView/types';

// ---- Effect name composition (verbatim from old preparePayload.jsx) ----

// Battle engine (services/battle-service/app/buffs.py) only recognizes
// "Buff:" and "Resist:" prefixes. Production convention: positive magnitude = buff/resist,
// negative magnitude = debuff/vulnerability. Legacy "Debuff:" / "Vulnerability:" rows
// are read-only tolerated (for backward compat) and rewritten on save.
export const composeBuffName = (damageType: string): string => `Buff: ${damageType}`;

export const composeResistName = (damageType: string): string => `Resist: ${damageType}`;

export const STAT_MODIFIER_NAME = 'StatModifier';

// Parse back effect_name to figure out which section a row belongs to
type EffectCategory = 'buff' | 'resist' | 'stat' | 'complex';

const categorizeEffect = (e: EffectEntry): EffectCategory => {
  const name = e.effect_name ?? '';
  if (name === STAT_MODIFIER_NAME) return 'stat';
  if (name.startsWith('Buff: ') || name.startsWith('Debuff: ')) return 'buff';
  if (name.startsWith('Resist: ') || name.startsWith('Vulnerability: '))
    return 'resist';
  return 'complex';
};

// Read-side only: tolerate legacy "Debuff:" / "Vulnerability:" prefixes so old
// rows still show up in the right section. New/edited rows always get rewritten
// to "Buff:" / "Resist:" via compose*Name.
const parseBuffDamageType = (name: string): string => {
  if (name.startsWith('Debuff: ')) return name.slice(8);
  if (name.startsWith('Buff: ')) return name.slice(6);
  return 'fire';
};

const parseResistDamageType = (name: string): string => {
  if (name.startsWith('Vulnerability: ')) return name.slice(15);
  if (name.startsWith('Resist: ')) return name.slice(8);
  return 'all';
};

// ---- Async handler types ----
// Each handler returns a Promise so SkillBaseEditor can hit the API,
// and PerkPoolEditor can just mutate a local array synchronously.
export interface EffectSectionsHandlers {
  onAddDamage: (d: DamageEntry) => Promise<void>;
  onUpdateDamage: (d: DamageEntry) => Promise<void>;
  onDeleteDamage: (d: DamageEntry) => Promise<void>;
  onAddEffect: (e: EffectEntry) => Promise<void>;
  onUpdateEffect: (e: EffectEntry) => Promise<void>;
  onDeleteEffect: (e: EffectEntry) => Promise<void>;
}

interface SkillEffectSectionsProps extends EffectSectionsHandlers {
  damageEntries: DamageEntry[];
  effects: EffectEntry[];
  /** Optional confirm prompt for delete (remote mode should pass window.confirm) */
  confirmDelete?: boolean;
}

// ---- Shared styling helpers ----
const rowClass =
  'rounded-card border border-white/10 bg-black/40 p-2 sm:p-3 flex flex-wrap gap-2 items-end';
const sectionClass =
  'rounded-card border border-white/10 gray-bg p-3 sm:p-4 space-y-2';
const inputClass =
  'bg-black/50 border border-white/15 rounded-sm px-2 py-1 text-white text-sm w-full min-w-0 focus:outline-none focus:border-gold/60';
const labelClass = 'text-white/60 text-[11px]';
const fieldClass = 'flex flex-col gap-1 flex-1 min-w-[110px]';
const addBtnClass = 'text-xs text-gold hover:text-gold/80';
const delBtnClass =
  'text-xs text-red-400 hover:text-red-300 underline self-center shrink-0';

// ---- Target-side toggle (per-row) ----
const TargetSideToggle = ({
  side,
  onChange,
}: {
  side: string | null;
  onChange: (s: 'self' | 'enemy') => void;
}) => {
  const current = side === 'self' ? 'self' : 'enemy';
  return (
    <div className="flex flex-col gap-1 shrink-0">
      <span className={labelClass}>Цель:</span>
      <div className="inline-flex rounded-sm overflow-hidden border border-white/15">
        {(['self', 'enemy'] as const).map((s) => {
          const active = current === s;
          return (
            <button
              key={s}
              type="button"
              onClick={() => onChange(s)}
              className={`px-2 py-1 text-[11px] transition-colors ${
                active
                  ? 'bg-gold/20 text-gold'
                  : 'bg-white/[0.03] text-white/60 hover:bg-white/[0.08]'
              }`}
            >
              {s === 'self' ? 'На себя' : 'На врага'}
            </button>
          );
        })}
      </div>
    </div>
  );
};

// ============================================================
// Section 1 — Колич. урон (damage rows, not effects)
// ============================================================
const DamageQuantitySection = ({
  rows,
  onAdd,
  onUpdate,
  onDelete,
  confirmDelete,
}: {
  rows: DamageEntry[];
  onAdd: (d: DamageEntry) => Promise<void>;
  onUpdate: (d: DamageEntry) => Promise<void>;
  onDelete: (d: DamageEntry) => Promise<void>;
  confirmDelete: boolean;
}) => {
  const handleAdd = async () => {
    try {
      await onAdd({
        damage_type: 'all',
        amount: 0,
        chance: 100,
        target_side: 'enemy',
        weapon_slot: 'main_weapon',
        description: '',
      });
    } catch {
      /* toast handled by caller */
    }
  };

  const patch = async (row: DamageEntry, patchObj: Partial<DamageEntry>) => {
    try {
      await onUpdate({ ...row, ...patchObj });
    } catch {
      /* handled */
    }
  };

  const del = async (row: DamageEntry) => {
    if (confirmDelete && !window.confirm('Удалить запись урона?')) return;
    try {
      await onDelete(row);
    } catch {
      /* handled */
    }
  };

  return (
    <div className={sectionClass}>
      <div className="flex items-center justify-between">
        <h4 className="gold-text text-xs sm:text-sm font-medium">Колич. урон</h4>
        <button type="button" onClick={handleAdd} className={addBtnClass}>
          + Добавить
        </button>
      </div>
      {rows.length === 0 && (
        <p className="text-white/40 text-[11px] italic">Нет записей</p>
      )}
      {rows.map((row, idx) => (
        <div key={row.id ?? `new-${idx}`} className={rowClass}>
          <TargetSideToggle
            side={row.target_side}
            onChange={(s) => patch(row, { target_side: s })}
          />
          <div className={fieldClass}>
            <label className={labelClass}>Тип:</label>
            <select
              value={row.damage_type || 'all'}
              onChange={(e) => patch(row, { damage_type: e.target.value })}
              className={inputClass}
            >
              {DAMAGE_TYPES.map((dt) => (
                <option key={dt.value} value={dt.value}>
                  {dt.label}
                </option>
              ))}
            </select>
          </div>
          <div className={fieldClass}>
            <label className={labelClass}>Оружие:</label>
            <select
              value={row.weapon_slot || 'main_weapon'}
              onChange={(e) => patch(row, { weapon_slot: e.target.value })}
              className={inputClass}
            >
              {WEAPON_SLOTS.map((ws) => (
                <option key={ws.value} value={ws.value}>
                  {ws.label}
                </option>
              ))}
            </select>
          </div>
          <div className={fieldClass}>
            <label className={labelClass}>Значение:</label>
            <input
              type="number"
              value={typeof row.amount === 'number' ? row.amount : Number(row.amount) || 0}
              onChange={(e) => patch(row, { amount: Number(e.target.value) })}
              className={inputClass}
            />
          </div>
          <div className={fieldClass}>
            <label className={labelClass}>Шанс(%):</label>
            <input
              type="number"
              value={row.chance ?? 100}
              onChange={(e) => patch(row, { chance: Number(e.target.value) })}
              className={inputClass}
            />
          </div>
          <button type="button" onClick={() => del(row)} className={delBtnClass}>
            Удалить
          </button>
        </div>
      ))}
    </div>
  );
};

// ============================================================
// Section 2 — Бафф / Дебафф (effect_name = "Buff: <type>" / "Debuff: <type>")
// ============================================================
const BuffDebuffSection = ({
  rows,
  onAdd,
  onUpdate,
  onDelete,
  confirmDelete,
}: {
  rows: EffectEntry[];
  onAdd: (e: EffectEntry) => Promise<void>;
  onUpdate: (e: EffectEntry) => Promise<void>;
  onDelete: (e: EffectEntry) => Promise<void>;
  confirmDelete: boolean;
}) => {
  const handleAdd = async () => {
    try {
      await onAdd({
        target_side: 'enemy',
        effect_name: composeBuffName('fire'),
        description: '',
        chance: 100,
        duration: 3,
        magnitude: 0,
        attribute_key: null,
      });
    } catch {
      /* handled */
    }
  };

  const del = async (row: EffectEntry) => {
    if (confirmDelete && !window.confirm('Удалить эффект?')) return;
    try {
      await onDelete(row);
    } catch {
      /* handled */
    }
  };

  return (
    <div className={sectionClass}>
      <div className="flex items-center justify-between">
        <h4 className="gold-text text-xs sm:text-sm font-medium">Бафф / Дебафф</h4>
        <button type="button" onClick={handleAdd} className={addBtnClass}>
          + Добавить
        </button>
      </div>
      <p className="text-white/50 text-[11px] italic">
        Положительное значение — бафф, отрицательное — дебафф
      </p>
      {rows.length === 0 && (
        <p className="text-white/40 text-[11px] italic">Нет записей</p>
      )}
      {rows.map((row, idx) => {
        const damageType = parseBuffDamageType(row.effect_name);
        const patch = (p: Partial<EffectEntry>) => onUpdate({ ...row, ...p }).catch(() => {});
        return (
          <div key={row.id ?? `new-${idx}`} className={rowClass}>
            <TargetSideToggle
              side={row.target_side}
              onChange={(s) => patch({ target_side: s })}
            />
            <div className={fieldClass}>
              <label className={labelClass}>Тип:</label>
              <select
                value={damageType}
                onChange={(e) =>
                  patch({ effect_name: composeBuffName(e.target.value) })
                }
                className={inputClass}
              >
                {DAMAGE_TYPES.map((dt) => (
                  <option key={dt.value} value={dt.value}>
                    {dt.label}
                  </option>
                ))}
              </select>
            </div>
            <div className={fieldClass}>
              <label className={labelClass}>Процент(%):</label>
              <input
                type="number"
                value={row.magnitude ?? 0}
                onChange={(e) => patch({ magnitude: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
            <div className={fieldClass}>
              <label className={labelClass}>Длит.(ходы):</label>
              <input
                type="number"
                value={row.duration ?? 0}
                onChange={(e) => patch({ duration: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
            <div className={fieldClass}>
              <label className={labelClass}>Шанс(%):</label>
              <input
                type="number"
                value={row.chance ?? 100}
                onChange={(e) => patch({ chance: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
            <button type="button" onClick={() => del(row)} className={delBtnClass}>
              Удалить
            </button>
          </div>
        );
      })}
    </div>
  );
};

// ============================================================
// Section 3 — Резисты / Уязвимости
// ============================================================
const ResistSection = ({
  rows,
  onAdd,
  onUpdate,
  onDelete,
  confirmDelete,
}: {
  rows: EffectEntry[];
  onAdd: (e: EffectEntry) => Promise<void>;
  onUpdate: (e: EffectEntry) => Promise<void>;
  onDelete: (e: EffectEntry) => Promise<void>;
  confirmDelete: boolean;
}) => {
  const handleAdd = async () => {
    try {
      await onAdd({
        target_side: 'self',
        effect_name: composeResistName('all'),
        description: '',
        chance: 100,
        duration: 3,
        magnitude: 0,
        attribute_key: null,
      });
    } catch {
      /* handled */
    }
  };

  const del = async (row: EffectEntry) => {
    if (confirmDelete && !window.confirm('Удалить эффект?')) return;
    try {
      await onDelete(row);
    } catch {
      /* handled */
    }
  };

  return (
    <div className={sectionClass}>
      <div className="flex items-center justify-between">
        <h4 className="gold-text text-xs sm:text-sm font-medium">Резисты / Уязвимости</h4>
        <button type="button" onClick={handleAdd} className={addBtnClass}>
          + Добавить
        </button>
      </div>
      <p className="text-white/50 text-[11px] italic">
        Положительное значение — резист, отрицательное — уязвимость
      </p>
      {rows.length === 0 && (
        <p className="text-white/40 text-[11px] italic">Нет записей</p>
      )}
      {rows.map((row, idx) => {
        const damageType = parseResistDamageType(row.effect_name);
        const patch = (p: Partial<EffectEntry>) => onUpdate({ ...row, ...p }).catch(() => {});
        return (
          <div key={row.id ?? `new-${idx}`} className={rowClass}>
            <TargetSideToggle
              side={row.target_side}
              onChange={(s) => patch({ target_side: s })}
            />
            <div className={fieldClass}>
              <label className={labelClass}>Тип:</label>
              <select
                value={damageType}
                onChange={(e) =>
                  patch({ effect_name: composeResistName(e.target.value) })
                }
                className={inputClass}
              >
                {DAMAGE_TYPES.map((dt) => (
                  <option key={dt.value} value={dt.value}>
                    {dt.label}
                  </option>
                ))}
              </select>
            </div>
            <div className={fieldClass}>
              <label className={labelClass}>Процент(%):</label>
              <input
                type="number"
                value={row.magnitude ?? 0}
                onChange={(e) => patch({ magnitude: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
            <div className={fieldClass}>
              <label className={labelClass}>Длит.(ходы):</label>
              <input
                type="number"
                value={row.duration ?? 0}
                onChange={(e) => patch({ duration: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
            <div className={fieldClass}>
              <label className={labelClass}>Шанс(%):</label>
              <input
                type="number"
                value={row.chance ?? 100}
                onChange={(e) => patch({ chance: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
            <button type="button" onClick={() => del(row)} className={delBtnClass}>
              Удалить
            </button>
          </div>
        );
      })}
    </div>
  );
};

// ============================================================
// Section 4 — Стат-модификаторы
// ============================================================
const StatModifierSection = ({
  rows,
  onAdd,
  onUpdate,
  onDelete,
  confirmDelete,
}: {
  rows: EffectEntry[];
  onAdd: (e: EffectEntry) => Promise<void>;
  onUpdate: (e: EffectEntry) => Promise<void>;
  onDelete: (e: EffectEntry) => Promise<void>;
  confirmDelete: boolean;
}) => {
  const handleAdd = async () => {
    try {
      await onAdd({
        target_side: 'self',
        effect_name: STAT_MODIFIER_NAME,
        description: '',
        chance: 100,
        duration: 1,
        magnitude: 0,
        attribute_key: STAT_MODIFIERS[0].key,
      });
    } catch {
      /* handled */
    }
  };

  const del = async (row: EffectEntry) => {
    if (confirmDelete && !window.confirm('Удалить стат-модификатор?')) return;
    try {
      await onDelete(row);
    } catch {
      /* handled */
    }
  };

  return (
    <div className={sectionClass}>
      <div className="flex items-center justify-between">
        <h4 className="gold-text text-xs sm:text-sm font-medium">Стат-модификаторы</h4>
        <button type="button" onClick={handleAdd} className={addBtnClass}>
          + Добавить
        </button>
      </div>
      {rows.length === 0 && (
        <p className="text-white/40 text-[11px] italic">Нет записей</p>
      )}
      {rows.map((row, idx) => {
        const patch = (p: Partial<EffectEntry>) => onUpdate({ ...row, ...p }).catch(() => {});
        return (
          <div key={row.id ?? `new-${idx}`} className={rowClass}>
            <TargetSideToggle
              side={row.target_side}
              onChange={(s) => patch({ target_side: s })}
            />
            <div className={fieldClass}>
              <label className={labelClass}>Параметр:</label>
              <select
                value={row.attribute_key ?? STAT_MODIFIERS[0].key}
                onChange={(e) => patch({ attribute_key: e.target.value })}
                className={inputClass}
              >
                {STAT_MODIFIERS.map((m) => (
                  <option key={m.key} value={m.key}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
            <div className={fieldClass}>
              <label className={labelClass}>Значение (±):</label>
              <input
                type="number"
                value={row.magnitude ?? 0}
                onChange={(e) => patch({ magnitude: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
            <div className={fieldClass}>
              <label className={labelClass}>Длит.(ходы):</label>
              <input
                type="number"
                value={row.duration ?? 0}
                onChange={(e) => patch({ duration: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
            <div className={fieldClass}>
              <label className={labelClass}>Шанс(%):</label>
              <input
                type="number"
                value={row.chance ?? 100}
                onChange={(e) => patch({ chance: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
            <button type="button" onClick={() => del(row)} className={delBtnClass}>
              Удалить
            </button>
          </div>
        );
      })}
    </div>
  );
};

// ============================================================
// Section 5 — Сложн. эффекты (Bleeding, Poison, Stun, ...)
// ============================================================
const ComplexEffectsSection = ({
  rows,
  onAdd,
  onUpdate,
  onDelete,
  confirmDelete,
}: {
  rows: EffectEntry[];
  onAdd: (e: EffectEntry) => Promise<void>;
  onUpdate: (e: EffectEntry) => Promise<void>;
  onDelete: (e: EffectEntry) => Promise<void>;
  confirmDelete: boolean;
}) => {
  const handleAdd = async () => {
    const first = COMPLEX_EFFECTS[0];
    try {
      await onAdd({
        target_side: 'enemy',
        effect_name: first.value,
        description: '',
        chance: 100,
        duration: first.fixedDuration ?? 1,
        magnitude: 0,
        attribute_key:
          first.hasAttributeKey && first.attributeKeyOptions
            ? first.attributeKeyOptions[0].value
            : null,
      });
    } catch {
      /* handled */
    }
  };

  const del = async (row: EffectEntry) => {
    if (confirmDelete && !window.confirm('Удалить эффект?')) return;
    try {
      await onDelete(row);
    } catch {
      /* handled */
    }
  };

  return (
    <div className={sectionClass}>
      <div className="flex items-center justify-between">
        <h4 className="gold-text text-xs sm:text-sm font-medium">Сложн. эффекты</h4>
        <button type="button" onClick={handleAdd} className={addBtnClass}>
          + Добавить
        </button>
      </div>
      {rows.length === 0 && (
        <p className="text-white/40 text-[11px] italic">Нет записей</p>
      )}
      {rows.map((row, idx) => {
        const side = row.target_side === 'self' ? 'self' : 'enemy';
        const availableEffects = COMPLEX_EFFECTS.filter(
          (ef) => !ef.allowedSides || ef.allowedSides.includes(side)
        );
        const def =
          COMPLEX_EFFECTS.find((ef) => ef.value === row.effect_name) ??
          availableEffects[0];
        const isFixedDuration = def && def.fixedDuration !== null;
        const showAttributeKey =
          def && def.hasAttributeKey && def.attributeKeyOptions;

        const patch = (p: Partial<EffectEntry>) => onUpdate({ ...row, ...p }).catch(() => {});

        const handleEffectChange = (newValue: string) => {
          const newDef = COMPLEX_EFFECTS.find((ef) => ef.value === newValue);
          if (!newDef) return;
          const p: Partial<EffectEntry> = { effect_name: newValue };
          if (newDef.fixedDuration !== null) p.duration = newDef.fixedDuration;
          if (newDef.hasAttributeKey && newDef.attributeKeyOptions) {
            p.attribute_key = newDef.attributeKeyOptions[0].value;
          } else {
            p.attribute_key = null;
          }
          if (newDef.value === 'Stun') p.magnitude = 0;
          patch(p);
        };

        return (
          <div
            key={row.id ?? `new-${idx}`}
            className={`${rowClass} flex-col items-stretch`}
          >
            {def?.description && (
              <div className="text-[11px] text-white/50 italic">{def.description}</div>
            )}
            <div className="flex flex-wrap gap-2 items-end">
              <TargetSideToggle
                side={row.target_side}
                onChange={(s) => patch({ target_side: s })}
              />
              <div className={fieldClass}>
                <label className={labelClass}>Эффект:</label>
                <select
                  value={row.effect_name || availableEffects[0]?.value || ''}
                  onChange={(e) => handleEffectChange(e.target.value)}
                  className={inputClass}
                >
                  {availableEffects.map((cf) => (
                    <option key={cf.value} value={cf.value}>
                      {cf.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className={fieldClass}>
                <label className={labelClass}>Шанс(%):</label>
                <input
                  type="number"
                  value={row.chance ?? 100}
                  onChange={(e) => patch({ chance: Number(e.target.value) })}
                  className={inputClass}
                />
              </div>
              <div className={fieldClass}>
                <label className={labelClass}>Длит.(ходы):</label>
                <input
                  type="number"
                  value={
                    isFixedDuration && def ? (def.fixedDuration ?? 0) : (row.duration ?? 0)
                  }
                  disabled={!!isFixedDuration}
                  onChange={(e) => patch({ duration: Number(e.target.value) })}
                  className={`${inputClass} ${isFixedDuration ? 'opacity-50' : ''}`}
                />
              </div>
              <div className={fieldClass}>
                <label className={labelClass}>Мощность:</label>
                <input
                  type="number"
                  value={row.magnitude ?? 0}
                  onChange={(e) => patch({ magnitude: Number(e.target.value) })}
                  className={inputClass}
                />
              </div>
              {showAttributeKey && def?.attributeKeyOptions && (
                <div className={fieldClass}>
                  <label className={labelClass}>
                    {row.effect_name === 'Poison'
                      ? 'Подтип:'
                      : row.effect_name === 'MagicImpact'
                      ? 'Атрибут:'
                      : 'Тип навыка:'}
                  </label>
                  <select
                    value={row.attribute_key ?? def.attributeKeyOptions[0].value}
                    onChange={(e) => patch({ attribute_key: e.target.value })}
                    className={inputClass}
                  >
                    {def.attributeKeyOptions.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <button type="button" onClick={() => del(row)} className={delBtnClass}>
                Удалить
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
};

// ============================================================
// Main component — splits effects into 4 categories by effect_name prefix
// ============================================================
const SkillEffectSections = ({
  damageEntries,
  effects,
  onAddDamage,
  onUpdateDamage,
  onDeleteDamage,
  onAddEffect,
  onUpdateEffect,
  onDeleteEffect,
  confirmDelete = false,
}: SkillEffectSectionsProps) => {
  const categorized = useMemo(() => {
    const buff: EffectEntry[] = [];
    const resist: EffectEntry[] = [];
    const stat: EffectEntry[] = [];
    const complex: EffectEntry[] = [];
    for (const e of effects) {
      const cat = categorizeEffect(e);
      if (cat === 'buff') buff.push(e);
      else if (cat === 'resist') resist.push(e);
      else if (cat === 'stat') stat.push(e);
      else complex.push(e);
    }
    return { buff, resist, stat, complex };
  }, [effects]);

  return (
    <div className="space-y-3">
      <DamageQuantitySection
        rows={damageEntries}
        onAdd={onAddDamage}
        onUpdate={onUpdateDamage}
        onDelete={onDeleteDamage}
        confirmDelete={confirmDelete}
      />
      <BuffDebuffSection
        rows={categorized.buff}
        onAdd={onAddEffect}
        onUpdate={onUpdateEffect}
        onDelete={onDeleteEffect}
        confirmDelete={confirmDelete}
      />
      <ResistSection
        rows={categorized.resist}
        onAdd={onAddEffect}
        onUpdate={onUpdateEffect}
        onDelete={onDeleteEffect}
        confirmDelete={confirmDelete}
      />
      <StatModifierSection
        rows={categorized.stat}
        onAdd={onAddEffect}
        onUpdate={onUpdateEffect}
        onDelete={onDeleteEffect}
        confirmDelete={confirmDelete}
      />
      <ComplexEffectsSection
        rows={categorized.complex}
        onAdd={onAddEffect}
        onUpdate={onUpdateEffect}
        onDelete={onDeleteEffect}
        confirmDelete={confirmDelete}
      />
    </div>
  );
};

export default SkillEffectSections;
