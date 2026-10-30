import { Plus, Trash2 } from 'lucide-react';
import type { EconEventEffect, EconEventEffectType, EconGoodsGroup } from '../../../types/economy';
import {
  ALL_GROUPS,
  EFFECT_SPECS,
  EFFECT_TYPES,
  MAX_EFFECTS,
  MAX_EFFECT_GROUPS,
  PERCENT_FIELDS,
} from './eventLabels';
import { formatDecimal } from './economyLabels';
import { FieldHint } from './ParamHint';

/** One editable effect row; `value` is in UI units (percent for share / pct). */
export interface EffectDraft {
  key: number;
  type: EconEventEffectType;
  groups: string[];
  value: string;
}

const PERCENT = 100;
let nextKey = 1;
const newKey = () => nextKey++;

const isPercent = (type: EconEventEffectType): boolean => {
  const field = EFFECT_SPECS[type].field;
  return field !== null && PERCENT_FIELDS.includes(field);
};

/** Rounds away float noise: 0.15 * 100 → 15, not 15.000000000000002. */
const tidy = (n: number): number => Math.round(n * 1e6) / 1e6;

export const effectToDraft = (effect: EconEventEffect): EffectDraft => {
  const spec = EFFECT_SPECS[effect.type] ?? EFFECT_SPECS.production;
  const raw = spec.field ? effect[spec.field] : null;
  const value = raw == null ? '' : String(tidy(isPercent(effect.type) ? raw * PERCENT : raw));
  return { key: newKey(), type: effect.type, groups: effect.groups ?? [], value };
};

export const newEffectDraft = (type: EconEventEffectType = 'production'): EffectDraft => {
  const spec = EFFECT_SPECS[type];
  return {
    key: newKey(),
    type,
    groups: [],
    value: spec.field ? String(tidy(isPercent(type) ? spec.initial * PERCENT : spec.initial)) : '',
  };
};

/** Russian message for an out-of-bounds value, or null. Mirrors `schemas.EventEffectIn` (feature file 3.8). */
const valueError = (d: EffectDraft): string | null => {
  const spec = EFFECT_SPECS[d.type];
  if (!spec.field) return null;
  const pct = isPercent(d.type);
  const min = pct ? spec.min * PERCENT : spec.min;
  const max = pct ? spec.max * PERCENT : spec.max;
  const n = Number(d.value);
  if (d.value.trim() === '' || !Number.isFinite(n) || n < min || n > max) {
    return `Значение от ${formatDecimal(min)} до ${formatDecimal(max)}${pct ? ' %' : ''}`;
  }
  return null;
};

/** Russian message for an invalid row, or null. */
export const effectDraftError = (d: EffectDraft): string | null => {
  const spec = EFFECT_SPECS[d.type];
  if (spec.groups && d.groups.length === 0) return 'Выберите хотя бы одну группу товаров';
  if (spec.groups && d.groups.length > MAX_EFFECT_GROUPS) return `Не больше ${MAX_EFFECT_GROUPS} групп`;
  return valueError(d);
};

/** API shape: only the fields of the type (the backend rejects extra fields). */
export const draftToEffect = (d: EffectDraft): EconEventEffect => {
  const spec = EFFECT_SPECS[d.type];
  const effect: EconEventEffect = { type: d.type };
  if (spec.groups) effect.groups = d.groups.includes(ALL_GROUPS) ? [ALL_GROUPS] : d.groups;
  if (spec.field) {
    const n = Number(d.value);
    effect[spec.field] = isPercent(d.type) ? tidy(n / PERCENT) : n;
  }
  return effect;
};

const UNIT_PREFIX: Record<string, string> = { mult: '×', delta: '±', share: '%', pct: '±%' };

interface EventEffectsBuilderProps {
  effects: EffectDraft[];
  groups: EconGoodsGroup[];
  canEdit: boolean;
  onChange: (effects: EffectDraft[]) => void;
}

/** Effects of an event template: type select → only its fields (feature file 3.10). */
const EventEffectsBuilder = ({ effects, groups, canEdit, onChange }: EventEffectsBuilderProps) => {
  const update = (key: number, patch: Partial<EffectDraft>) =>
    onChange(effects.map((e) => (e.key === key ? { ...e, ...patch } : e)));

  const changeType = (row: EffectDraft, type: EconEventEffectType) => {
    // A new type gets its own default value; chosen groups survive when the new type takes groups too.
    const fresh = newEffectDraft(type);
    update(row.key, { type, value: fresh.value, groups: EFFECT_SPECS[type].groups ? row.groups : [] });
  };

  const toggleGroup = (row: EffectDraft, code: string) => {
    if (code === ALL_GROUPS) {
      update(row.key, { groups: row.groups.includes(ALL_GROUPS) ? [] : [ALL_GROUPS] });
      return;
    }
    const without = row.groups.filter((g) => g !== ALL_GROUPS);
    update(row.key, {
      groups: without.includes(code) ? without.filter((g) => g !== code) : [...without, code],
    });
  };

  return (
    <div className="flex flex-col gap-3">
      {effects.length === 0 && <p className="text-site-red text-xs">Добавьте хотя бы один эффект.</p>}
      <ul className="flex flex-col gap-3">
        {effects.map((row, index) => {
          const spec = EFFECT_SPECS[row.type];
          const error = effectDraftError(row);
          const pct = isPercent(row.type);
          const inputId = `econ-ev-effect-${row.key}`;
          return (
            <li key={row.key} className="rounded-card border border-white/[0.07] bg-white/[0.03] p-3 flex flex-col gap-2.5 min-w-0">
              <div className="flex flex-col sm:flex-row sm:items-end gap-3">
                <div className="flex flex-col gap-1 min-w-0 flex-1">
                  <span className="flex items-center gap-1">
                    <label htmlFor={`${inputId}-type`} className="text-white/60 text-xs uppercase tracking-[0.06em]">
                      Эффект {index + 1}
                    </label>
                    <FieldHint field={`event_effect_${row.type}`} label={spec.label} />
                  </span>
                  <select
                    id={`${inputId}-type`}
                    className="input-underline w-full"
                    value={row.type}
                    disabled={!canEdit}
                    onChange={(e) => changeType(row, e.target.value as EconEventEffectType)}
                  >
                    {EFFECT_TYPES.map((t) => (
                      <option key={t} value={t} className="bg-site-dark text-white">
                        {EFFECT_SPECS[t].label}
                        {EFFECT_SPECS[t].oneShot ? ' (разово)' : ''}
                      </option>
                    ))}
                  </select>
                </div>
                {spec.field && (
                  <div className="flex flex-col gap-1 sm:w-36 min-w-0">
                    <label htmlFor={inputId} className="text-white/60 text-xs uppercase tracking-[0.06em]">
                      {spec.field === 'mult' ? 'Множитель ×' : spec.field === 'delta' ? 'За пересчёт ±' : pct ? 'Процент, %' : 'Значение'}
                    </label>
                    <input
                      id={inputId}
                      type="number"
                      inputMode="decimal"
                      step={pct || spec.field === 'delta' ? 0.5 : 0.05}
                      min={pct ? spec.min * PERCENT : spec.min}
                      max={pct ? spec.max * PERCENT : spec.max}
                      className={`input-underline w-full ${valueError(row) ? '!border-site-red' : ''}`}
                      value={row.value}
                      disabled={!canEdit}
                      aria-describedby={`${inputId}-help`}
                      placeholder={UNIT_PREFIX[spec.field]}
                      onChange={(e) => update(row.key, { value: e.target.value })}
                    />
                  </div>
                )}
                {canEdit && (
                  <button
                    type="button"
                    onClick={() => onChange(effects.filter((e) => e.key !== row.key))}
                    className="self-end sm:self-auto sm:mb-1 inline-flex items-center gap-1 text-xs text-white/50 hover:text-site-red transition-colors duration-200 ease-site"
                    aria-label={`Убрать эффект ${index + 1}`}
                  >
                    <Trash2 size={14} />
                    <span className="sm:hidden">Убрать</span>
                  </button>
                )}
              </div>
              <p id={`${inputId}-help`} className="text-white/45 text-xs break-words">
                {spec.help}
              </p>
              {spec.groups && (
                <div className="flex flex-wrap gap-1.5" role="group" aria-label="Группы товаров">
                  {[{ code: ALL_GROUPS, name: 'Все группы' }, ...groups].map((g) => {
                    const on = row.groups.includes(g.code);
                    return (
                      <button
                        key={g.code}
                        type="button"
                        disabled={!canEdit}
                        aria-pressed={on}
                        onClick={() => toggleGroup(row, g.code)}
                        className={`chip-outline rounded-full px-2.5 py-1 text-[11px] font-medium ${on ? 'chip-outline-active' : ''}`}
                      >
                        {g.name}
                      </button>
                    );
                  })}
                </div>
              )}
              {error && <p className="text-site-red text-xs">{error}</p>}
            </li>
          );
        })}
      </ul>
      {canEdit && (
        <button
          type="button"
          className="btn-line w-full sm:w-auto sm:self-start !text-xs !py-2 !px-5 inline-flex items-center justify-center gap-1.5"
          disabled={effects.length >= MAX_EFFECTS}
          onClick={() => onChange([...effects, newEffectDraft()])}
        >
          <Plus size={14} />
          Добавить эффект
        </button>
      )}
      {effects.length >= MAX_EFFECTS && <p className="text-white/40 text-xs">Не больше {MAX_EFFECTS} эффектов.</p>}
    </div>
  );
};

export default EventEffectsBuilder;
