// ItemEffectSections — battle effect editor for consumables and scrolls (FEAT-168).
//
// Modelled on AdminSkillsPage/SkillEffectSections.tsx and importing its
// vocabulary (DAMAGE_TYPES, WEAPON_SLOTS, STAT_MODIFIERS, COMPLEX_EFFECTS,
// composeBuffName/composeResistName) so the two editors can never drift apart.
//
// Difference from the skill editor: rows live in the item form's local state and
// are sent with the item in one payload (replace-all), so every handler here is
// synchronous — there is no per-row API call and therefore no per-row error.
//
// Sections:
//   1. Урон              — item_damage_entries
//   2. Эффекты           — item_effects (stat / damage buff / resist / complex)
//   3. Очищение          — item_effects with effect_name = "Cleanse"
//   4. Яд на оружие      — consumable_action = "weapon_coating" + coating_*
import { useMemo } from "react";
import {
  COMPLEX_EFFECTS,
  DAMAGE_TYPES,
  STAT_MODIFIERS,
  WEAPON_SLOTS,
} from "../AdminSkillsPage/skillConstants";
import {
  STAT_MODIFIER_NAME,
  composeBuffName,
  composeResistName,
} from "../AdminSkillsPage/SkillEffectSections";
import {
  CLEANSE_EFFECT_NAME,
  CLEANSE_HINT,
  CLEANSE_SELECTORS,
} from "../pages/BattlePage/battleEffects";
import {
  CONSUMABLE_ACTION_OPTIONS,
  normalizeAction,
  type ConsumableAction,
  type ItemDamageEntry,
  type ItemEffect,
} from "../../utils/itemEffects";
import {
  DEFAULT_COATING_BONUS_DAMAGE,
  DEFAULT_COATING_TURNS,
  MAX_COATING_TURNS,
  MAX_ITEM_DAMAGE_ENTRIES,
  MAX_ITEM_EFFECTS,
  newCleanseEffect,
  newItemDamageEntry,
  newItemEffect,
} from "./itemFormRules";

/* ── Shared styling (same language as the skill editor) ── */

const sectionClass = "rounded-card border border-white/10 gray-bg p-3 sm:p-4 space-y-2";
const rowClass =
  "rounded-card border border-white/10 bg-black/40 p-2 sm:p-3 flex flex-wrap gap-2 items-end";
const inputClass =
  "bg-black/50 border border-white/15 rounded-sm px-2 py-1 text-white text-sm w-full min-w-0 focus:outline-none focus:border-gold/60";
const labelClass = "text-white/60 text-[11px]";
const fieldClass = "flex flex-col gap-1 flex-1 min-w-[110px]";
const addBtnClass = "text-xs text-gold hover:text-gold/80 transition-colors";
const delBtnClass =
  "text-xs text-site-red hover:text-site-red/80 underline self-center shrink-0";
const optionClass = "bg-site-dark text-white";

const EMPTY = <p className="text-white/40 text-[11px] italic">Нет записей</p>;

/* ── Effect row kinds ── */

type EffectKind = "stat" | "buff" | "resist" | "complex";

const EFFECT_KIND_OPTIONS: { value: EffectKind; label: string }[] = [
  { value: "stat", label: "Характеристика" },
  { value: "buff", label: "Изменение урона" },
  { value: "resist", label: "Изменение защиты" },
  { value: "complex", label: "Сложный эффект" },
];

export const isCleanseRow = (row: ItemEffect): boolean =>
  row.effect_name === CLEANSE_EFFECT_NAME;

const kindOf = (row: ItemEffect): EffectKind => {
  const name = row.effect_name ?? "";
  if (name === STAT_MODIFIER_NAME) return "stat";
  if (name.startsWith("Buff: ") || name.startsWith("Debuff: ")) return "buff";
  if (name.startsWith("Resist: ") || name.startsWith("Vulnerability: ")) return "resist";
  return "complex";
};

const parseTypeAfterPrefix = (name: string, fallback: string): string => {
  const idx = name.indexOf(": ");
  return idx >= 0 ? name.slice(idx + 2) : fallback;
};

/** Reset a row to sane defaults for its new kind. */
const applyKind = (row: ItemEffect, kind: EffectKind): ItemEffect => {
  if (kind === "stat")
    return { ...row, effect_name: STAT_MODIFIER_NAME, attribute_key: STAT_MODIFIERS[0].key };
  if (kind === "buff")
    return { ...row, effect_name: composeBuffName("fire"), attribute_key: null };
  if (kind === "resist")
    return { ...row, effect_name: composeResistName("all"), attribute_key: null };
  const first = COMPLEX_EFFECTS[0];
  return {
    ...row,
    effect_name: first.value,
    duration: first.fixedDuration ?? row.duration ?? 1,
    attribute_key:
      first.hasAttributeKey && first.attributeKeyOptions
        ? first.attributeKeyOptions[0].value
        : null,
  };
};

/* ── Target side toggle (mirrors the skill editor's) ── */

const TARGET_SIDES: { value: string; label: string }[] = [
  { value: "self", label: "На себя" },
  { value: "enemy", label: "На врага" },
  { value: "ally", label: "На союзника" },
  { value: "all_allies", label: "На команду" },
];

const TargetSideToggle = ({
  side,
  onChange,
  allowed = TARGET_SIDES,
}: {
  side: string | null | undefined;
  onChange: (side: string) => void;
  allowed?: { value: string; label: string }[];
}) => {
  const current = allowed.some((s) => s.value === side) ? side : allowed[0].value;
  return (
    <div className="flex flex-col gap-1 shrink-0">
      <span className={labelClass}>Цель:</span>
      <div className="inline-flex flex-wrap rounded-sm overflow-hidden border border-white/15 w-fit">
        {allowed.map((s) => (
          <button
            key={s.value}
            type="button"
            onClick={() => onChange(s.value)}
            className={`px-2 py-1 text-[11px] transition-colors ${
              current === s.value
                ? "bg-gold/20 text-gold"
                : "bg-white/[0.03] text-white/60 hover:bg-white/[0.08]"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
};

const NumberField = ({
  label,
  value,
  onChange,
  min,
  max,
  disabled,
}: {
  label: string;
  value: number | null | undefined;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  disabled?: boolean;
}) => (
  <label className={fieldClass}>
    <span className={labelClass}>{label}</span>
    <input
      type="number"
      min={min}
      max={max}
      disabled={disabled}
      value={value ?? 0}
      onChange={(e) => onChange(Number(e.target.value))}
      className={`${inputClass} ${disabled ? "opacity-50" : ""}`}
    />
  </label>
);

/* ── Props ── */

export interface ItemEffectSectionsProps {
  effects: ItemEffect[];
  damageEntries: ItemDamageEntry[];
  action: ConsumableAction;
  coatingTurns: number | null;
  coatingBonusDamage: number | null;
  /** Writes straight into the item form state by field name */
  onFieldChange: (name: string, value: unknown) => void;
}

const ItemEffectSections = ({
  effects,
  damageEntries,
  action,
  coatingTurns,
  coatingBonusDamage,
  onFieldChange,
}: ItemEffectSectionsProps) => {
  const normalizedAction = normalizeAction(action);

  // Both visible groups edit the same array, so rows carry their real index.
  const { effectRows, cleanseRows } = useMemo(() => {
    const withIndex = effects.map((row, index) => ({ row, index }));
    return {
      effectRows: withIndex.filter(({ row }) => !isCleanseRow(row)),
      cleanseRows: withIndex.filter(({ row }) => isCleanseRow(row)),
    };
  }, [effects]);

  const patchEffect = (index: number, patch: Partial<ItemEffect>) =>
    onFieldChange(
      "effects",
      effects.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );

  const replaceEffect = (index: number, next: ItemEffect) =>
    onFieldChange(
      "effects",
      effects.map((row, i) => (i === index ? next : row)),
    );

  const removeEffect = (index: number) =>
    onFieldChange(
      "effects",
      effects.filter((_, i) => i !== index),
    );

  const addEffect = (row: ItemEffect) => onFieldChange("effects", [...effects, row]);

  const patchDamage = (index: number, patch: Partial<ItemDamageEntry>) =>
    onFieldChange(
      "damage_entries",
      damageEntries.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );

  const removeDamage = (index: number) =>
    onFieldChange(
      "damage_entries",
      damageEntries.filter((_, i) => i !== index),
    );

  /**
   * Switching to «яд на оружие» must put real numbers into the state, not just
   * show them: the inputs used to fall back to 1 / 0 for display while the
   * state stayed null, and saving was then refused for a field the admin could
   * see filled in. Switching away clears them, because the server rejects
   * coating parameters on a non-coating item.
   */
  const handleActionChange = (next: ConsumableAction) => {
    onFieldChange("consumable_action", next);
    if (next === "weapon_coating") {
      onFieldChange("coating_turns", coatingTurns ?? DEFAULT_COATING_TURNS);
      onFieldChange("coating_bonus_damage", coatingBonusDamage ?? DEFAULT_COATING_BONUS_DAMAGE);
    } else {
      onFieldChange("coating_turns", null);
      onFieldChange("coating_bonus_damage", null);
    }
  };

  const effectsFull = effects.length >= MAX_ITEM_EFFECTS;
  const damageFull = damageEntries.length >= MAX_ITEM_DAMAGE_ENTRIES;

  return (
    <div className="space-y-3 min-w-0">
      <p className="text-white/50 text-xs">
        Эффекты действуют только в бою и заканчиваются вместе с ним. Предмет применяется из
        быстрого слота и не тратит ход, но за ход можно применить только один предмет.
      </p>

      {/* ── 1. Урон ── */}
      <div className={sectionClass}>
        <div className="flex items-center justify-between gap-2">
          <h4 className="gold-text text-xs sm:text-sm font-medium">Урон</h4>
          <button
            type="button"
            disabled={damageFull}
            onClick={() => onFieldChange("damage_entries", [...damageEntries, newItemDamageEntry()])}
            className={`${addBtnClass} disabled:opacity-40`}
          >
            + Добавить
          </button>
        </div>
        <p className="text-white/50 text-[11px] italic">
          Считается по обычной боевой формуле: криты, сопротивления, уклонение. «Без оружия» —
          урон только от характеристик, как у свитка. Шанс срабатывания здесь не проверяется:
          урон предмета применяется всегда, промахнуться можно только через уклонение цели.
        </p>
        {damageFull && (
          <p className="text-gold text-[11px]">
            Достигнут предел: {MAX_ITEM_DAMAGE_ENTRIES} записей урона.
          </p>
        )}
        {damageEntries.length === 0 && EMPTY}
        {damageEntries.map((row, index) => {
          const shape = row.aoe_shape ?? "single";
          return (
            <div key={row.id ?? `dmg-${index}`} className={rowClass}>
              <label className={fieldClass}>
                <span className={labelClass}>Тип:</span>
                <select
                  value={row.damage_type || "all"}
                  onChange={(e) => patchDamage(index, { damage_type: e.target.value })}
                  className={inputClass}
                >
                  {DAMAGE_TYPES.map((dt) => (
                    <option key={dt.value} value={dt.value} className={optionClass}>
                      {dt.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className={fieldClass}>
                <span className={labelClass}>Оружие:</span>
                <select
                  value={row.weapon_slot || "no_weapon"}
                  onChange={(e) => patchDamage(index, { weapon_slot: e.target.value })}
                  className={inputClass}
                >
                  {WEAPON_SLOTS.map((ws) => (
                    <option key={ws.value} value={ws.value} className={optionClass}>
                      {ws.label}
                    </option>
                  ))}
                </select>
              </label>
              <NumberField
                label="Значение:"
                value={Number(row.amount ?? 0)}
                onChange={(amount) => patchDamage(index, { amount })}
              />
              {/* No chance field on purpose: the engine does not roll `chance`
                  for item damage rows — the hit always lands (subject to the
                  usual dodge / resist rolls). Showing the input would lie. */}
              <div className="basis-full flex flex-col gap-1">
                <span className={labelClass}>Форма АоЕ:</span>
                <div className="inline-flex flex-wrap rounded-sm overflow-hidden border border-white/15 w-fit">
                  {(
                    [
                      ["single", "Одна цель"],
                      ["splash", "Соседи"],
                      ["cleave", "Пробой"],
                      ["all", "Все враги"],
                      ["random_n", "Случайные"],
                    ] as const
                  ).map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => patchDamage(index, { aoe_shape: value })}
                      className={`px-2 py-1 text-[11px] transition-colors ${
                        shape === value
                          ? "bg-gold/20 text-gold"
                          : "bg-white/[0.03] text-white/60 hover:bg-white/[0.08]"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                {shape !== "single" && (
                  <div className="flex flex-wrap gap-2 mt-1">
                    <NumberField
                      label="Урон соседям, %:"
                      min={0}
                      max={100}
                      value={row.aoe_falloff ?? 50}
                      onChange={(aoe_falloff) => patchDamage(index, { aoe_falloff })}
                    />
                    {shape === "random_n" && (
                      <NumberField
                        label="Всего целей:"
                        min={1}
                        max={10}
                        value={row.aoe_max_targets ?? 3}
                        onChange={(aoe_max_targets) => patchDamage(index, { aoe_max_targets })}
                      />
                    )}
                  </div>
                )}
              </div>
              <button type="button" onClick={() => removeDamage(index)} className={delBtnClass}>
                Удалить
              </button>
            </div>
          );
        })}
      </div>

      {/* ── 2. Эффекты ── */}
      <div className={sectionClass}>
        <div className="flex items-center justify-between gap-2">
          <h4 className="gold-text text-xs sm:text-sm font-medium">Эффекты</h4>
          <button
            type="button"
            disabled={effectsFull}
            onClick={() => addEffect(newItemEffect())}
            className={`${addBtnClass} disabled:opacity-40`}
          >
            + Добавить
          </button>
        </div>
        <p className="text-white/50 text-[11px] italic">
          Положительное значение — усиление, отрицательное — ослабление. Повторное применение
          обновляет длительность, эффекты не складываются.
        </p>
        {effectsFull && (
          <p className="text-gold text-[11px]">Достигнут предел: {MAX_ITEM_EFFECTS} эффектов.</p>
        )}
        {effectRows.length === 0 && EMPTY}
        {effectRows.map(({ row, index }) => {
          const kind = kindOf(row);
          const complexDef =
            kind === "complex"
              ? COMPLEX_EFFECTS.find((c) => c.value === row.effect_name) ?? COMPLEX_EFFECTS[0]
              : null;
          const fixedDuration = complexDef?.fixedDuration ?? null;
          return (
            <div key={row.id ?? `eff-${index}`} className={`${rowClass} flex-col items-stretch`}>
              {complexDef?.description && (
                <span className="text-[11px] text-white/50 italic">{complexDef.description}</span>
              )}
              <div className="flex flex-wrap gap-2 items-end">
                <TargetSideToggle
                  side={row.target_side}
                  onChange={(target_side) => patchEffect(index, { target_side })}
                />
                <label className={fieldClass}>
                  <span className={labelClass}>Вид:</span>
                  <select
                    value={kind}
                    onChange={(e) =>
                      replaceEffect(index, applyKind(row, e.target.value as EffectKind))
                    }
                    className={inputClass}
                  >
                    {EFFECT_KIND_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value} className={optionClass}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </label>

                {kind === "stat" && (
                  <label className={fieldClass}>
                    <span className={labelClass}>Параметр:</span>
                    <select
                      value={row.attribute_key ?? STAT_MODIFIERS[0].key}
                      onChange={(e) => patchEffect(index, { attribute_key: e.target.value })}
                      className={inputClass}
                    >
                      {STAT_MODIFIERS.map((m) => (
                        <option key={m.key} value={m.key} className={optionClass}>
                          {m.label}
                        </option>
                      ))}
                    </select>
                  </label>
                )}

                {(kind === "buff" || kind === "resist") && (
                  <label className={fieldClass}>
                    <span className={labelClass}>Тип урона:</span>
                    <select
                      value={parseTypeAfterPrefix(
                        row.effect_name ?? "",
                        kind === "buff" ? "fire" : "all",
                      )}
                      onChange={(e) =>
                        patchEffect(index, {
                          effect_name:
                            kind === "buff"
                              ? composeBuffName(e.target.value)
                              : composeResistName(e.target.value),
                        })
                      }
                      className={inputClass}
                    >
                      {DAMAGE_TYPES.map((dt) => (
                        <option key={dt.value} value={dt.value} className={optionClass}>
                          {dt.label}
                        </option>
                      ))}
                    </select>
                  </label>
                )}

                {kind === "complex" && complexDef && (
                  <>
                    <label className={fieldClass}>
                      <span className={labelClass}>Эффект:</span>
                      <select
                        value={complexDef.value}
                        onChange={(e) => {
                          const def = COMPLEX_EFFECTS.find((c) => c.value === e.target.value);
                          if (!def) return;
                          patchEffect(index, {
                            effect_name: def.value,
                            duration: def.fixedDuration ?? row.duration ?? 1,
                            magnitude: def.value === "Stun" ? 0 : row.magnitude ?? 0,
                            attribute_key:
                              def.hasAttributeKey && def.attributeKeyOptions
                                ? def.attributeKeyOptions[0].value
                                : null,
                          });
                        }}
                        className={inputClass}
                      >
                        {COMPLEX_EFFECTS.map((c) => (
                          <option key={c.value} value={c.value} className={optionClass}>
                            {c.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    {complexDef.hasAttributeKey && complexDef.attributeKeyOptions && (
                      <label className={fieldClass}>
                        <span className={labelClass}>
                          {complexDef.value === "Poison" ? "Подтип:" : "Атрибут:"}
                        </span>
                        <select
                          value={row.attribute_key ?? complexDef.attributeKeyOptions[0].value}
                          onChange={(e) => patchEffect(index, { attribute_key: e.target.value })}
                          className={inputClass}
                        >
                          {complexDef.attributeKeyOptions.map((o) => (
                            <option key={o.value} value={o.value} className={optionClass}>
                              {o.label}
                            </option>
                          ))}
                        </select>
                      </label>
                    )}
                  </>
                )}

                <NumberField
                  label="Значение:"
                  value={row.magnitude ?? 0}
                  onChange={(magnitude) => patchEffect(index, { magnitude })}
                />
                <NumberField
                  label="Длит.(ходы):"
                  min={0}
                  max={100}
                  disabled={fixedDuration !== null}
                  value={fixedDuration ?? row.duration ?? 0}
                  onChange={(duration) => patchEffect(index, { duration })}
                />
                <NumberField
                  label="Шанс(%):"
                  min={0}
                  max={100}
                  value={row.chance ?? 100}
                  onChange={(chance) => patchEffect(index, { chance })}
                />
                <button type="button" onClick={() => removeEffect(index)} className={delBtnClass}>
                  Удалить
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── 3. Очищение ── */}
      <div className={sectionClass}>
        <div className="flex items-center justify-between gap-2">
          <h4 className="gold-text text-xs sm:text-sm font-medium">Очищение / противоядие</h4>
          <button
            type="button"
            disabled={effectsFull}
            onClick={() => addEffect(newCleanseEffect())}
            className={`${addBtnClass} disabled:opacity-40`}
          >
            + Добавить
          </button>
        </div>
        <p className="text-white/50 text-[11px] italic">{CLEANSE_HINT}</p>
        {cleanseRows.length === 0 && EMPTY}
        {cleanseRows.map(({ row, index }) => (
          <div key={row.id ?? `cln-${index}`} className={rowClass}>
            <TargetSideToggle
              side={row.target_side}
              onChange={(target_side) => patchEffect(index, { target_side })}
              allowed={TARGET_SIDES.filter((s) => s.value !== "enemy")}
            />
            <label className={fieldClass}>
              <span className={labelClass}>Что снимает:</span>
              <select
                value={row.attribute_key ?? CLEANSE_SELECTORS[0].value}
                onChange={(e) => patchEffect(index, { attribute_key: e.target.value })}
                className={inputClass}
              >
                {CLEANSE_SELECTORS.map((s) => (
                  <option key={s.value} value={s.value} className={optionClass}>
                    {s.label}
                  </option>
                ))}
                {COMPLEX_EFFECTS.map((c) => (
                  <option key={c.value} value={c.value} className={optionClass}>
                    Только «{c.label}»
                  </option>
                ))}
              </select>
            </label>
            <NumberField
              label="Сколько (0 = все):"
              min={0}
              max={100}
              value={row.magnitude ?? 0}
              onChange={(magnitude) => patchEffect(index, { magnitude })}
            />
            <NumberField
              label="Шанс(%):"
              min={0}
              max={100}
              value={row.chance ?? 100}
              onChange={(chance) => patchEffect(index, { chance })}
            />
            <button type="button" onClick={() => removeEffect(index)} className={delBtnClass}>
              Удалить
            </button>
          </div>
        ))}
      </div>

      {/* ── 4. Способ применения / яд на оружие ── */}
      <div className={sectionClass}>
        <h4 className="gold-text text-xs sm:text-sm font-medium">Способ применения</h4>
        <div className="flex flex-wrap gap-2 items-end">
          <label className={fieldClass}>
            <span className={labelClass}>Как применяется:</span>
            <select
              value={normalizedAction}
              onChange={(e) => handleActionChange(e.target.value as ConsumableAction)}
              className={inputClass}
            >
              {CONSUMABLE_ACTION_OPTIONS.map((o) => (
                <option key={o.value} value={o.value} className={optionClass}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          {normalizedAction === "weapon_coating" && (
            <>
              <NumberField
                label="Ходов с ядом (вкл. текущий):"
                min={1}
                max={MAX_COATING_TURNS}
                value={coatingTurns ?? DEFAULT_COATING_TURNS}
                onChange={(value) => onFieldChange("coating_turns", value)}
              />
              <NumberField
                label="Прибавка к урону:"
                min={0}
                value={coatingBonusDamage ?? DEFAULT_COATING_BONUS_DAMAGE}
                onChange={(value) => onFieldChange("coating_bonus_damage", value)}
              />
            </>
          )}
        </div>
        {normalizedAction === "weapon_coating" && (
          <p className="text-white/50 text-[11px] italic">
            Яд наносится на оружие: пока он действует, новый нанести нельзя. Яд усиливает уже
            ту атаку, на которой его нанесли, — «4 хода» значит 4 усиленных атаки, считая
            текущую. Эффекты с целью «На врага» из списка выше накладываются на каждого, кого
            задело оружие.
          </p>
        )}
        {normalizedAction === "cleanse" && (
          <p className="text-white/50 text-[11px] italic">
            Что именно снимает предмет — настраивается в разделе «Очищение / противоядие».
          </p>
        )}
      </div>
    </div>
  );
};

export default ItemEffectSections;
