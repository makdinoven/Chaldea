// ItemXpBuffsEditor — «Ускорение опыта» for books and scrolls (FEAT-168 §3.9-bis E).
//
// Replaces the old single buff select: an item may accelerate several XP sources
// at once, up to one row per type. A type already used in another row is
// disabled in the remaining selects, because the backend rejects duplicates.
//
// The percent input is the admin's unit (25) — the payload carries the share
// (0.25), converted here so the form state already matches the API shape.
import {
  MAX_XP_BUFF_DURATION_MINUTES,
  MAX_XP_BUFF_ROWS,
  MAX_XP_BUFF_VALUE,
  XP_BUFF_CHARACTER_ALL,
  XP_BUFF_TYPE_GROUPS,
  type ItemXpBuff,
} from "../../utils/itemEffects";
import { firstFreeXpBuffType, newXpBuff } from "./itemFormRules";

const inputClass =
  "bg-black/50 border border-white/15 rounded-sm px-2 py-1 text-white text-sm w-full min-w-0 focus:outline-none focus:border-gold/60";
const labelClass = "text-white/60 text-[11px]";
const fieldClass = "flex flex-col gap-1 flex-1 min-w-[130px]";
const optionClass = "bg-site-dark text-white";

export interface ItemXpBuffsEditorProps {
  rows: ItemXpBuff[];
  onChange: (rows: ItemXpBuff[]) => void;
}

const ItemXpBuffsEditor = ({ rows, onChange }: ItemXpBuffsEditorProps) => {
  const nextType = firstFreeXpBuffType(rows);
  const full = rows.length >= MAX_XP_BUFF_ROWS || nextType === null;

  const patch = (index: number, p: Partial<ItemXpBuff>) =>
    onChange(rows.map((row, i) => (i === index ? { ...row, ...p } : row)));

  const remove = (index: number) => onChange(rows.filter((_, i) => i !== index));

  const usesUmbrella = rows.some((r) => r.buff_type === XP_BUFF_CHARACTER_ALL);
  const usesGranular = rows.some(
    (r) => r.buff_type.startsWith("character_xp_") && r.buff_type !== XP_BUFF_CHARACTER_ALL,
  );

  return (
    <div className="flex flex-col gap-2 min-w-0">
      <div className="flex items-center justify-between gap-2">
        <p className="text-white/50 text-xs">
          Предмет может ускорять сразу несколько видов опыта — по одной строке на вид.
        </p>
        <button
          type="button"
          disabled={full}
          onClick={() => nextType && onChange([...rows, newXpBuff(nextType)])}
          className="text-xs text-gold hover:text-gold/80 transition-colors disabled:opacity-40 shrink-0"
        >
          + Добавить строку
        </button>
      </div>

      {full && rows.length > 0 && (
        <p className="text-gold text-[11px]">Все {MAX_XP_BUFF_ROWS} видов опыта уже добавлены.</p>
      )}

      {rows.length === 0 && (
        <p className="text-white/40 text-[11px] italic">
          Нет строк — предмет не ускоряет опыт.
        </p>
      )}

      {rows.map((row, index) => (
        <div
          key={row.id ?? `xp-${index}`}
          className="rounded-card border border-white/10 bg-black/40 p-2 sm:p-3 flex flex-wrap gap-2 items-end"
        >
          <label className={fieldClass}>
            <span className={labelClass}>Что ускоряет:</span>
            <select
              value={row.buff_type}
              onChange={(e) => patch(index, { buff_type: e.target.value })}
              className={inputClass}
            >
              {XP_BUFF_TYPE_GROUPS.map((group) => {
                const options = group.options.map((o) => (
                  <option
                    key={o.value}
                    value={o.value}
                    // The backend rejects duplicates, so a type taken by another
                    // row cannot be picked here.
                    disabled={
                      o.value !== row.buff_type &&
                      rows.some((r) => r.buff_type === o.value)
                    }
                    className={optionClass}
                  >
                    {o.label}
                  </option>
                ));
                return group.label ? (
                  <optgroup key={group.label} label={group.label} className={optionClass}>
                    {options}
                  </optgroup>
                ) : (
                  options
                );
              })}
            </select>
          </label>

          <label className={fieldClass}>
            <span className={labelClass}>Прибавка, %:</span>
            <input
              type="number"
              min={1}
              max={MAX_XP_BUFF_VALUE * 100}
              step={1}
              value={row.value == null ? "" : Math.round(Number(row.value) * 100)}
              onChange={(e) =>
                patch(index, {
                  value: e.target.value === "" ? 0 : Number(e.target.value) / 100,
                })
              }
              className={inputClass}
            />
          </label>

          <label className={fieldClass}>
            <span className={labelClass}>Длительность, мин:</span>
            <input
              type="number"
              min={1}
              max={MAX_XP_BUFF_DURATION_MINUTES}
              step={1}
              value={row.duration_minutes ?? ""}
              onChange={(e) =>
                patch(index, {
                  duration_minutes: e.target.value === "" ? 0 : Number(e.target.value),
                })
              }
              className={inputClass}
            />
          </label>

          <button
            type="button"
            onClick={() => remove(index)}
            className="text-xs text-site-red hover:text-site-red/80 underline self-center shrink-0"
          >
            Удалить
          </button>
        </div>
      ))}

      {usesUmbrella && usesGranular && (
        <p className="text-white/50 text-[11px] italic">
          «Весь опыт персонажа» складывается с точечными строками: +25% за задания и +10% на весь
          опыт дадут ×1.35 на заданиях.
        </p>
      )}
      <p className="text-white/40 text-[11px]">
        Максимум {MAX_XP_BUFF_VALUE * 100}% и {MAX_XP_BUFF_DURATION_MINUTES} минут (7 дней) на
        строку. Опыт очков навыка книгами не ускоряется.
      </p>
    </div>
  );
};

export default ItemXpBuffsEditor;
