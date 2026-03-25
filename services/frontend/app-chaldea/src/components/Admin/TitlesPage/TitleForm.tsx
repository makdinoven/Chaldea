import React, { useEffect, useState } from "react";
import { createTitle, updateTitle, fetchTitle } from "../../../api/titles";
import toast from "react-hot-toast";
import type { TitleCondition } from "../../../types/titles";

/* ── Dictionaries ── */

const RARITIES = ["common", "rare", "legendary"] as const;

const RARITY_LABELS: Record<string, string> = {
  common: "Обычный",
  rare: "Редкий",
  legendary: "Легендарный",
};

const CONDITION_TYPES = [
  "cumulative_stat",
  "character_level",
  "attribute",
  "admin_grant",
] as const;

const CONDITION_TYPE_LABELS: Record<string, string> = {
  cumulative_stat: "Кумулятивная стат.",
  character_level: "Уровень персонажа",
  attribute: "Атрибут",
  admin_grant: "Ручная выдача",
};

const OPERATORS = [">=", "<=", "==", ">"] as const;

const CUMULATIVE_STAT_OPTIONS: { value: string; label: string }[] = [
  { value: "total_damage_dealt", label: "Урон нанесён (всего)" },
  { value: "total_damage_received", label: "Урон получен (всего)" },
  { value: "pve_kills", label: "Мобов убито" },
  { value: "pvp_wins", label: "PvP побед" },
  { value: "pvp_losses", label: "PvP поражений" },
  { value: "total_battles", label: "Боёв всего" },
  { value: "max_damage_single_battle", label: "Макс. урон за бой" },
  { value: "max_win_streak", label: "Макс. серия побед" },
  { value: "current_win_streak", label: "Текущая серия побед" },
  { value: "total_rounds_survived", label: "Раундов пережито" },
  { value: "low_hp_wins", label: "Побед с HP < 10%" },
  { value: "total_gold_earned", label: "Золота заработано" },
  { value: "total_gold_spent", label: "Золота потрачено" },
  { value: "items_bought", label: "Предметов куплено" },
  { value: "items_sold", label: "Предметов продано" },
  { value: "locations_visited", label: "Локаций посещено" },
  { value: "total_transitions", label: "Переходов между локациями" },
  { value: "skills_used", label: "Навыков использовано" },
  { value: "items_equipped", label: "Предметов экипировано" },
];

const ATTRIBUTE_STAT_OPTIONS: { value: string; label: string }[] = [
  { value: "strength", label: "Сила" },
  { value: "agility", label: "Ловкость" },
  { value: "intelligence", label: "Интеллект" },
  { value: "endurance", label: "Выносливость" },
  { value: "charisma", label: "Харизма" },
  { value: "luck", label: "Удача" },
  { value: "damage", label: "Урон" },
  { value: "dodge", label: "Уклонение" },
  { value: "critical_hit_chance", label: "Шанс крита" },
  { value: "critical_damage", label: "Крит. урон" },
  { value: "res_physical", label: "Сопр. физическому" },
  { value: "res_fire", label: "Сопр. огню" },
  { value: "res_ice", label: "Сопр. льду" },
  { value: "res_magic", label: "Сопр. магии" },
  { value: "res_electricity", label: "Сопр. электричеству" },
  { value: "res_wind", label: "Сопр. ветру" },
];

/* ── Form state ── */

interface TitleFormState {
  name: string;
  description: string;
  rarity: string;
  icon: string;
  sort_order: number;
  is_active: boolean;
  conditions: TitleCondition[];
  reward_passive_exp: number;
  reward_active_exp: number;
}

const INITIAL_STATE: TitleFormState = {
  name: "",
  description: "",
  rarity: "common",
  icon: "",
  sort_order: 0,
  is_active: true,
  conditions: [],
  reward_passive_exp: 0,
  reward_active_exp: 0,
};

/* ── Props ── */

interface TitleFormProps {
  selected?: number;
  onSuccess: () => void;
  onCancel: () => void;
}

/* ── Component ── */

const TitleForm = ({ selected, onSuccess, onCancel }: TitleFormProps) => {
  const [form, setForm] = useState<TitleFormState>(INITIAL_STATE);
  const editMode = Boolean(selected);

  useEffect(() => {
    if (selected) {
      fetchTitle(selected)
        .then((t) =>
          setForm({
            name: t.name,
            description: t.description ?? "",
            rarity: t.rarity,
            icon: t.icon ?? "",
            sort_order: t.sort_order,
            is_active: t.is_active,
            conditions: t.conditions ?? [],
            reward_passive_exp: t.reward_passive_exp ?? 0,
            reward_active_exp: t.reward_active_exp ?? 0,
          }),
        )
        .catch((e: Error) =>
          toast.error(e.message || "Не удалось загрузить титул"),
        );
    }
  }, [selected]);

  const handleChange = (
    e: React.ChangeEvent<
      HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
    >,
  ) => {
    const target = e.target;
    const name = target.name;
    const value =
      target instanceof HTMLInputElement && target.type === "checkbox"
        ? target.checked
        : target.value;
    setForm((st) => ({ ...st, [name]: value }));
  };

  /* ── Conditions ── */

  const addCondition = () => {
    setForm((st) => ({
      ...st,
      conditions: [
        ...st.conditions,
        { type: "cumulative_stat", stat: "", operator: ">=", value: 0 },
      ],
    }));
  };

  const updateCondition = (
    idx: number,
    field: string,
    value: string | number,
  ) => {
    setForm((st) => {
      const conditions = [...st.conditions];
      conditions[idx] = { ...conditions[idx], [field]: value };
      return { ...st, conditions };
    });
  };

  const removeCondition = (idx: number) => {
    setForm((st) => ({
      ...st,
      conditions: st.conditions.filter((_, i) => i !== idx),
    }));
  };

  /* ── Submit ── */

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!form.name.trim()) {
      toast.error("Название титула обязательно");
      return;
    }

    const cleanConditions = form.conditions.map((c) => ({
      ...c,
      stat: c.stat || undefined,
      value: Number(c.value) || 0,
    }));

    const sortOrder = parseInt(String(form.sort_order), 10);

    const base = {
      name: form.name.trim(),
      description: form.description.trim(),
      rarity: form.rarity as "common" | "rare" | "legendary",
      icon: form.icon.trim() || null,
      sort_order: Number.isNaN(sortOrder) ? 0 : sortOrder,
      conditions: cleanConditions,
      reward_passive_exp: Number(form.reward_passive_exp) || 0,
      reward_active_exp: Number(form.reward_active_exp) || 0,
    };

    try {
      if (editMode) {
        await updateTitle(selected!, { ...base, is_active: form.is_active });
        toast.success("Титул сохранён");
      } else {
        await createTitle(base);
        toast.success("Титул создан");
      }
      onSuccess();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка при сохранении";
      toast.error(msg);
    }
  };

  /* ── Render helpers ── */

  const renderConditions = () => (
    <fieldset className="col-span-full border border-white/10 rounded-card p-4 bg-white/[0.03]">
      <legend className="text-white/50 text-xs font-medium uppercase tracking-[0.06em] px-2">
        Условия открытия
      </legend>
      <div className="flex flex-col gap-3 mt-2">
        {form.conditions.map((cond, idx) => (
          <div
            key={idx}
            className="flex flex-col sm:flex-row items-start sm:items-center gap-2 bg-white/[0.03] p-3 rounded-card"
          >
            <select
              value={cond.type}
              onChange={(e) => updateCondition(idx, "type", e.target.value)}
              className="input-underline text-sm flex-1 min-w-0"
            >
              {CONDITION_TYPES.map((t) => (
                <option key={t} value={t} className="bg-site-dark text-white">
                  {CONDITION_TYPE_LABELS[t]}
                </option>
              ))}
            </select>

            {cond.type === "cumulative_stat" && (
              <select
                value={cond.stat ?? ""}
                onChange={(e) => updateCondition(idx, "stat", e.target.value)}
                className="input-underline text-sm flex-1 min-w-0"
              >
                <option value="" disabled className="bg-site-dark text-white">
                  — Выберите показатель —
                </option>
                {CUMULATIVE_STAT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value} className="bg-site-dark text-white">
                    {o.label} ({o.value})
                  </option>
                ))}
              </select>
            )}

            {cond.type === "attribute" && (
              <select
                value={cond.stat ?? ""}
                onChange={(e) => updateCondition(idx, "stat", e.target.value)}
                className="input-underline text-sm flex-1 min-w-0"
              >
                <option value="" disabled className="bg-site-dark text-white">
                  — Выберите атрибут —
                </option>
                {ATTRIBUTE_STAT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value} className="bg-site-dark text-white">
                    {o.label} ({o.value})
                  </option>
                ))}
              </select>
            )}

            <select
              value={cond.operator}
              onChange={(e) => updateCondition(idx, "operator", e.target.value)}
              className="input-underline text-sm w-20"
            >
              {OPERATORS.map((op) => (
                <option key={op} value={op} className="bg-site-dark text-white">
                  {op}
                </option>
              ))}
            </select>

            <input
              type="number"
              value={cond.value}
              onChange={(e) =>
                updateCondition(idx, "value", Number(e.target.value))
              }
              className="input-underline text-sm w-24"
            />

            <button
              type="button"
              onClick={() => removeCondition(idx)}
              className="text-sm text-site-red hover:text-white transition-colors duration-200"
            >
              Убрать
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={addCondition}
          className="text-sm text-site-blue hover:text-white transition-colors duration-200 self-start"
        >
          + Добавить условие
        </button>
      </div>
    </fieldset>
  );

  return (
    <form className="gray-bg p-6 flex flex-col gap-6" onSubmit={handleSubmit}>
      <h2 className="gold-text text-2xl font-medium uppercase tracking-[0.06em]">
        {editMode ? "Редактирование титула" : "Создание титула"}
      </h2>

      {/* Base fields */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {/* Name */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Название
          </span>
          <input
            name="name"
            value={form.name}
            onChange={handleChange}
            required
            className="input-underline"
          />
        </label>

        {/* Rarity */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Редкость
          </span>
          <select
            name="rarity"
            value={form.rarity}
            onChange={handleChange}
            className="input-underline"
          >
            {RARITIES.map((r) => (
              <option key={r} value={r} className="bg-site-dark text-white">
                {RARITY_LABELS[r]}
              </option>
            ))}
          </select>
        </label>

        {/* Icon */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Иконка (файл)
          </span>
          <input
            name="icon"
            value={form.icon}
            onChange={handleChange}
            placeholder="dragon_slayer.png"
            className="input-underline"
          />
        </label>

        {/* Sort order */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Порядок сортировки
          </span>
          <input
            type="number"
            name="sort_order"
            value={form.sort_order}
            onChange={handleChange}
            min={0}
            className="input-underline"
          />
        </label>

        {/* Active checkbox */}
        <label className="flex items-center gap-3 self-end pb-2">
          <input
            type="checkbox"
            name="is_active"
            checked={form.is_active}
            onChange={handleChange}
            className="w-5 h-5 accent-site-blue"
          />
          <span className="text-sm text-white">Активен</span>
        </label>

        {/* Description */}
        <label className="flex flex-col gap-1 col-span-full">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Описание
          </span>
          <textarea
            name="description"
            value={form.description}
            onChange={handleChange}
            rows={3}
            className="textarea-bordered"
          />
        </label>
      </div>

      {/* Conditions */}
      {renderConditions()}

      {/* XP Rewards */}
      <fieldset className="col-span-full border border-white/10 rounded-card p-4 bg-white/[0.03]">
        <legend className="text-white/50 text-xs font-medium uppercase tracking-[0.06em] px-2">
          Награда опытом
        </legend>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 mt-2">
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Пассивный опыт
            </span>
            <input
              type="number"
              name="reward_passive_exp"
              value={form.reward_passive_exp}
              onChange={handleChange}
              min={0}
              className="input-underline"
              placeholder="0"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Активный опыт
            </span>
            <input
              type="number"
              name="reward_active_exp"
              value={form.reward_active_exp}
              onChange={handleChange}
              min={0}
              className="input-underline"
              placeholder="0"
            />
          </label>
        </div>
      </fieldset>

      {/* Buttons */}
      <div className="flex gap-4 pt-2">
        <button type="submit" className="btn-blue !text-base !px-8 !py-2">
          {editMode ? "Сохранить" : "Создать"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="btn-line !w-auto !px-8"
        >
          Отмена
        </button>
      </div>
    </form>
  );
};

export default TitleForm;
