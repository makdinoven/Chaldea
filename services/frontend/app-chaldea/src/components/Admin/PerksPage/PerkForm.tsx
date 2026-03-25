import React, { useEffect, useState } from "react";
import { createPerk, updatePerk, fetchPerk } from "../../../api/perks";
import toast from "react-hot-toast";
import type { PerkCondition, PerkBonuses } from "../../../types/perks";

/* ── Dictionaries ── */

const CATEGORIES = [
  "combat",
  "trade",
  "exploration",
  "progression",
  "usage",
] as const;

const CATEGORY_LABELS: Record<string, string> = {
  combat: "Боевой",
  trade: "Торговый",
  exploration: "Исследование",
  progression: "Прогрессия",
  usage: "Использование",
};

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
  "quest",
  "admin_grant",
] as const;

const CONDITION_TYPE_LABELS: Record<string, string> = {
  cumulative_stat: "Кумулятивная стат.",
  character_level: "Уровень персонажа",
  attribute: "Атрибут",
  quest: "Квест",
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

const BONUS_SECTIONS = ["flat", "percent", "contextual", "passive"] as const;

const BONUS_SECTION_LABELS: Record<string, string> = {
  flat: "Плоские бонусы (+N к атрибуту)",
  percent: "Процентные бонусы (+N% к атрибуту)",
  contextual: "Контекстные бонусы (ситуативные)",
  passive: "Пассивные эффекты (в бою)",
};

const BONUS_SECTION_DESCRIPTIONS: Record<string, string> = {
  flat: "Постоянная прибавка к атрибуту при открытии перка",
  percent: "Процентный множитель атрибута (применяется в бою, Phase 2)",
  contextual: "Бонусы в определённых ситуациях (Phase 2)",
  passive: "Автоматические эффекты каждый ход в бою (Phase 2)",
};

interface BonusOption { value: string; label: string; group?: string }

/** Flat & percent share the same attribute keys */
const ATTRIBUTE_BONUS_OPTIONS: BonusOption[] = [
  { value: "health", label: "Здоровье", group: "Ресурсы" },
  { value: "mana", label: "Мана", group: "Ресурсы" },
  { value: "energy", label: "Энергия", group: "Ресурсы" },
  { value: "stamina", label: "Выносливость (ресурс)", group: "Ресурсы" },
  { value: "strength", label: "Сила", group: "Основные" },
  { value: "agility", label: "Ловкость", group: "Основные" },
  { value: "intelligence", label: "Интеллект", group: "Основные" },
  { value: "endurance", label: "Живучесть", group: "Основные" },
  { value: "charisma", label: "Харизма", group: "Основные" },
  { value: "luck", label: "Удача", group: "Основные" },
  { value: "damage", label: "Урон", group: "Боевые" },
  { value: "dodge", label: "Уклонение", group: "Боевые" },
  { value: "critical_hit_chance", label: "Шанс крита", group: "Боевые" },
  { value: "critical_damage", label: "Крит. урон", group: "Боевые" },
  { value: "res_physical", label: "Сопр. физическому", group: "Сопротивления" },
  { value: "res_catting", label: "Сопр. режущему", group: "Сопротивления" },
  { value: "res_crushing", label: "Сопр. дробящему", group: "Сопротивления" },
  { value: "res_piercing", label: "Сопр. колющему", group: "Сопротивления" },
  { value: "res_magic", label: "Сопр. магии", group: "Сопротивления" },
  { value: "res_fire", label: "Сопр. огню", group: "Сопротивления" },
  { value: "res_ice", label: "Сопр. льду", group: "Сопротивления" },
  { value: "res_watering", label: "Сопр. воде", group: "Сопротивления" },
  { value: "res_electricity", label: "Сопр. электричеству", group: "Сопротивления" },
  { value: "res_wind", label: "Сопр. ветру", group: "Сопротивления" },
  { value: "res_sainting", label: "Сопр. святому", group: "Сопротивления" },
  { value: "res_damning", label: "Сопр. проклятию", group: "Сопротивления" },
  { value: "res_effects", label: "Сопр. эффектам", group: "Сопротивления" },
  { value: "vul_physical", label: "Уязв. физическому", group: "Уязвимости" },
  { value: "vul_catting", label: "Уязв. режущему", group: "Уязвимости" },
  { value: "vul_crushing", label: "Уязв. дробящему", group: "Уязвимости" },
  { value: "vul_piercing", label: "Уязв. колющему", group: "Уязвимости" },
  { value: "vul_magic", label: "Уязв. магии", group: "Уязвимости" },
  { value: "vul_fire", label: "Уязв. огню", group: "Уязвимости" },
  { value: "vul_ice", label: "Уязв. льду", group: "Уязвимости" },
  { value: "vul_watering", label: "Уязв. воде", group: "Уязвимости" },
  { value: "vul_electricity", label: "Уязв. электричеству", group: "Уязвимости" },
  { value: "vul_wind", label: "Уязв. ветру", group: "Уязвимости" },
  { value: "vul_sainting", label: "Уязв. святому", group: "Уязвимости" },
  { value: "vul_damning", label: "Уязв. проклятию", group: "Уязвимости" },
  { value: "vul_effects", label: "Уязв. эффектам", group: "Уязвимости" },
];

const CONTEXTUAL_BONUS_OPTIONS: BonusOption[] = [
  { value: "damage_vs_pve", label: "+% урона по мобам" },
  { value: "damage_vs_pvp", label: "+% урона по игрокам" },
  { value: "crit_with_sword", label: "+% крита мечом" },
  { value: "crit_with_axe", label: "+% крита топором" },
  { value: "crit_with_bow", label: "+% крита луком" },
  { value: "crit_with_staff", label: "+% крита посохом" },
  { value: "crit_with_dagger", label: "+% крита кинжалом" },
];

const PASSIVE_BONUS_OPTIONS: BonusOption[] = [
  { value: "regen_hp_per_turn", label: "Регенерация HP за ход" },
  { value: "regen_mana_per_turn", label: "Регенерация маны за ход" },
  { value: "regen_energy_per_turn", label: "Регенерация энергии за ход" },
  { value: "dodge_bonus", label: "Бонус уклонения" },
  { value: "reflect_damage", label: "Отражение урона (%)" },
  { value: "thorns_damage", label: "Урон шипами (фиксированный)" },
];

const BONUS_OPTIONS_MAP: Record<string, BonusOption[]> = {
  flat: ATTRIBUTE_BONUS_OPTIONS,
  percent: ATTRIBUTE_BONUS_OPTIONS,
  contextual: CONTEXTUAL_BONUS_OPTIONS,
  passive: PASSIVE_BONUS_OPTIONS,
};

/* ── Form state ── */

interface PerkFormState {
  name: string;
  description: string;
  category: string;
  rarity: string;
  icon: string;
  sort_order: number;
  is_active: boolean;
  conditions: PerkCondition[];
  bonuses: PerkBonuses;
}

const EMPTY_BONUSES: PerkBonuses = {
  flat: {},
  percent: {},
  contextual: {},
  passive: {},
};

const INITIAL_STATE: PerkFormState = {
  name: "",
  description: "",
  category: "combat",
  rarity: "common",
  icon: "",
  sort_order: 0,
  is_active: true,
  conditions: [],
  bonuses: { ...EMPTY_BONUSES },
};

/* ── Props ── */

interface PerkFormProps {
  selected?: number;
  onSuccess: () => void;
  onCancel: () => void;
}

/* ── Component ── */

const PerkForm = ({ selected, onSuccess, onCancel }: PerkFormProps) => {
  const [form, setForm] = useState<PerkFormState>(INITIAL_STATE);
  const editMode = Boolean(selected);

  useEffect(() => {
    if (selected) {
      fetchPerk(selected)
        .then((p) =>
          setForm({
            name: p.name,
            description: p.description ?? "",
            category: p.category,
            rarity: p.rarity,
            icon: p.icon ?? "",
            sort_order: p.sort_order,
            is_active: p.is_active,
            conditions: p.conditions ?? [],
            bonuses: {
              flat: p.bonuses?.flat ?? {},
              percent: p.bonuses?.percent ?? {},
              contextual: p.bonuses?.contextual ?? {},
              passive: p.bonuses?.passive ?? {},
            },
          }),
        )
        .catch((e: Error) =>
          toast.error(e.message || "Не удалось загрузить перк"),
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

  /* ── Bonuses ── */

  const addBonusEntry = (section: keyof PerkBonuses) => {
    setForm((st) => ({
      ...st,
      bonuses: {
        ...st.bonuses,
        [section]: { ...st.bonuses[section], "": 0 },
      },
    }));
  };

  const updateBonusKey = (
    section: keyof PerkBonuses,
    oldKey: string,
    newKey: string,
  ) => {
    setForm((st) => {
      const entries = Object.entries(st.bonuses[section]);
      const updated = Object.fromEntries(
        entries.map(([k, v]) => (k === oldKey ? [newKey, v] : [k, v])),
      );
      return { ...st, bonuses: { ...st.bonuses, [section]: updated } };
    });
  };

  const updateBonusValue = (
    section: keyof PerkBonuses,
    key: string,
    value: number,
  ) => {
    setForm((st) => ({
      ...st,
      bonuses: {
        ...st.bonuses,
        [section]: { ...st.bonuses[section], [key]: value },
      },
    }));
  };

  const removeBonusEntry = (section: keyof PerkBonuses, key: string) => {
    setForm((st) => {
      const copy = { ...st.bonuses[section] };
      delete copy[key];
      return { ...st, bonuses: { ...st.bonuses, [section]: copy } };
    });
  };

  /* ── Submit ── */

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!form.name.trim()) {
      toast.error("Название перка обязательно");
      return;
    }

    // Clean bonuses: remove entries with empty keys, ensure numeric values
    const cleanBonuses = (section: Record<string, number>) => {
      const cleaned: Record<string, number> = {};
      for (const [k, v] of Object.entries(section)) {
        if (k.trim()) cleaned[k.trim()] = Number(v) || 0;
      }
      return cleaned;
    };

    // Clean conditions: ensure value is a number
    const cleanConditions = form.conditions.map((c) => ({
      ...c,
      stat: c.stat || undefined,
      value: Number(c.value) || 0,
    }));

    const sortOrder = parseInt(String(form.sort_order), 10);

    const base = {
      name: form.name.trim(),
      description: form.description.trim(),
      category: form.category,
      rarity: form.rarity as "common" | "rare" | "legendary",
      icon: form.icon.trim() || null,
      sort_order: Number.isNaN(sortOrder) ? 0 : sortOrder,
      conditions: cleanConditions,
      bonuses: {
        flat: cleanBonuses(form.bonuses.flat),
        percent: cleanBonuses(form.bonuses.percent),
        contextual: cleanBonuses(form.bonuses.contextual),
        passive: cleanBonuses(form.bonuses.passive),
      },
    };

    try {
      if (editMode) {
        await updatePerk(selected!, { ...base, is_active: form.is_active });
        toast.success("Перк сохранён");
      } else {
        await createPerk(base);
        toast.success("Перк создан");
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

  const renderBonusSection = (section: keyof PerkBonuses) => {
    const entries = Object.entries(form.bonuses[section]);
    const options = BONUS_OPTIONS_MAP[section] ?? [];

    // Group options by group field (for optgroup)
    const groups = new Map<string, BonusOption[]>();
    for (const opt of options) {
      const g = opt.group ?? "";
      const arr = groups.get(g) ?? [];
      arr.push(opt);
      groups.set(g, arr);
    }

    // Keys already used in this section (to disable in dropdown)
    const usedKeys = new Set(entries.map(([k]) => k));

    const renderOptions = () => {
      const result: React.ReactNode[] = [];
      for (const [group, opts] of groups) {
        const available = opts.filter((o) => !usedKeys.has(o.value));
        if (available.length === 0) continue;
        if (group) {
          result.push(
            <optgroup key={group} label={group}>
              {available.map((o) => (
                <option key={o.value} value={o.value} className="bg-site-dark text-white">
                  {o.label}
                </option>
              ))}
            </optgroup>
          );
        } else {
          available.forEach((o) =>
            result.push(
              <option key={o.value} value={o.value} className="bg-site-dark text-white">
                {o.label}
              </option>
            )
          );
        }
      }
      return result;
    };

    // Find label for a key
    const getLabel = (key: string) => options.find((o) => o.value === key)?.label ?? key;

    return (
      <fieldset
        key={section}
        className="border border-white/10 rounded-card p-4 bg-white/[0.03]"
      >
        <legend className="text-white/50 text-xs font-medium uppercase tracking-[0.06em] px-2">
          {BONUS_SECTION_LABELS[section]}
        </legend>
        <p className="text-white/25 text-[11px] mt-1 mb-3">
          {BONUS_SECTION_DESCRIPTIONS[section]}
        </p>
        <div className="flex flex-col gap-2">
          {entries.map(([key, val], idx) => (
            <div key={idx} className="flex flex-col sm:flex-row items-start sm:items-center gap-2 bg-white/[0.03] p-2.5 rounded-card">
              {/* Attribute select */}
              <select
                value={key}
                onChange={(e) => updateBonusKey(section, key, e.target.value)}
                className="input-underline text-sm flex-1 min-w-0"
              >
                {key && (
                  <option value={key} className="bg-site-dark text-white">
                    {getLabel(key)}
                  </option>
                )}
                {!key && (
                  <option value="" disabled className="bg-site-dark text-white">
                    — Выберите атрибут —
                  </option>
                )}
                {renderOptions()}
              </select>

              {/* Value input */}
              <div className="flex items-center gap-1.5">
                <span className="text-white/30 text-xs">
                  {section === "percent" || section === "contextual" ? "%" : "+"}
                </span>
                <input
                  type="number"
                  value={val}
                  onChange={(e) =>
                    updateBonusValue(section, key, Number(e.target.value))
                  }
                  className="input-underline text-sm w-20"
                  placeholder="0"
                />
              </div>

              <button
                type="button"
                onClick={() => removeBonusEntry(section, key)}
                className="text-sm text-site-red hover:text-white transition-colors duration-200"
              >
                Убрать
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => addBonusEntry(section)}
            className="text-sm text-site-blue hover:text-white transition-colors duration-200 self-start"
          >
            + Добавить бонус
          </button>
        </div>
      </fieldset>
    );
  };

  return (
    <form className="gray-bg p-6 flex flex-col gap-6" onSubmit={handleSubmit}>
      <h2 className="gold-text text-2xl font-medium uppercase tracking-[0.06em]">
        {editMode ? "Редактирование перка" : "Создание перка"}
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

        {/* Category */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Категория
          </span>
          <select
            name="category"
            value={form.category}
            onChange={handleChange}
            className="input-underline"
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c} className="bg-site-dark text-white">
                {CATEGORY_LABELS[c]}
              </option>
            ))}
          </select>
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
            placeholder="first_blood.png"
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

      {/* Bonuses */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {BONUS_SECTIONS.map((s) => renderBonusSection(s))}
      </div>

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

export default PerkForm;
