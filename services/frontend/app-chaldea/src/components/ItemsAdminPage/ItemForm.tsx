import React, { useCallback, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import {
  createItem,
  updateItem,
  uploadItemImage,
  recropItemImage,
  fetchItem,
  type ItemImageCrop,
} from "../../api/items";
import { fetchRefiningRules, putItemConversions } from "../../api/professions";
import type { RefiningRule } from "../../types/professions";
import ItemImageCropper from "./ItemImageCropper";
import ItemConversionsEditor, { type ConversionsDraft } from "./ItemConversionsEditor";
import {
  ARMOR_SUBCLASS_LABELS,
  DAMAGE_TYPE_LABELS,
  ITEM_CATEGORIES,
  ITEM_TYPE_LABELS,
  RARITY_LABELS,
  TOOL_CATEGORIES,
  TOOL_CATEGORY_LABELS,
  WEAPON_SUBCLASS_GROUPS,
  itemHasRarity,
} from "../../constants/items";
import {
  RESOURCE_SUBCATEGORY_GROUPS,
  RESOURCE_SUBCATEGORY_LABELS,
  RESOURCE_SUBCATEGORY_NONE_LABEL,
} from "../../constants/professions";
import {
  ATTR_MODS,
  DEFAULT_DURABILITY,
  DEFAULT_DURABILITY_TYPES,
  DEFAULT_TOOL_DURABILITY,
  FOOD_HINT,
  IDENTIFY_LEVEL_OPTIONS,
  RARITY_CAP_MESSAGE,
  RECOVERY_FIELDS,
  REPAIR_POWER_OPTIONS,
  RES_MODS,
  VUL_MODS,
  WHETSTONE_GROUP_OPTIONS,
  WHETSTONE_OPTIONS,
  allowedRaritiesFor,
  buildItemPayload,
  isRawSubcategory,
  isResourceSubcategory,
  rulesFor,
  validateBattleConfig,
  validateXpBuffs,
  type ModDef,
} from "./itemFormRules";
import ItemEffectSections from "./ItemEffectSections";
import ItemXpBuffsEditor from "./ItemXpBuffsEditor";
import {
  normalizeAction,
  resolveXpBuffs,
  type ItemBattleConfig,
  type ItemDamageEntry,
  type ItemEffect,
  type ItemXpBuff,
} from "../../utils/itemEffects";

/* ── State ── */

interface ItemFormState {
  name: string;
  item_type: string;
  item_rarity: string;
  item_level: number | string;
  price: number | string;
  max_stack_size: number | string;
  is_unique: boolean;
  is_food?: boolean;
  description: string;
  image?: string | null;
  full_image?: string | null;
  /** Inputs store raw strings; buildItemPayload normalises them */
  [key: string]: unknown;
}

const initialState = (itemType: string): ItemFormState => {
  const zeroes = Object.fromEntries(
    [...ATTR_MODS, ...RES_MODS, ...VUL_MODS, ...RECOVERY_FIELDS].map(({ key }) => [key, 0]),
  );
  return {
    ...zeroes,
    name: "",
    item_type: itemType,
    item_rarity: "common",
    item_level: 0,
    price: 0,
    max_stack_size: 1,
    is_unique: false,
    is_food: false,
    description: "",
    fast_slot_bonus: 0,
    socket_count: 0,
    max_durability: DEFAULT_DURABILITY_TYPES.includes(itemType) ? DEFAULT_DURABILITY : 0,
    armor_subclass: null,
    weapon_subclass: null,
    primary_damage_type: null,
    buff_type: null,
    buff_value: null,
    buff_duration_minutes: null,
    identify_level: null,
    repair_power: null,
    whetstone_level: null,
    whetstone_group: null,
    resource_subcategory: null,
    blueprint_recipe_id: null,
    tool_category: itemType === "gathering_tool" ? "pickaxe" : null,
    gather_double_chance_bonus: 0,
    gather_speed_bonus_pct: 0,
    gather_stamina_bonus_pct: 0,
    // Battle effects (FEAT-168): replace-all lists sent with the item
    effects: [] as ItemEffect[],
    damage_entries: [] as ItemDamageEntry[],
    xp_buffs: [] as ItemXpBuff[],
    consumable_action: null,
    coating_turns: null,
    coating_bonus_damage: null,
  };
};

/* ── Small presentational helpers ── */

const labelText = "text-white/50 text-xs font-medium uppercase tracking-[0.06em]";

const Field = ({ label, children, wide }: { label: string; children: React.ReactNode; wide?: boolean }) => (
  <label className={`flex flex-col gap-1 min-w-0 ${wide ? "col-span-full" : ""}`}>
    <span className={labelText}>{label}</span>
    {children}
  </label>
);

const Section = ({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) => (
  <fieldset className="border border-white/10 rounded-card p-4 bg-white/[0.03] min-w-0">
    <legend className={`${labelText} px-2`}>{title}</legend>
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 mt-2">{children}</div>
    {hint && <p className="text-white/40 text-xs mt-3">{hint}</p>}
  </fieldset>
);

const optionClass = "bg-site-dark text-white";

/**
 * Readable Russian text for a failed save. FastAPI sends `detail` as a string
 * (400) or as a list of {msg} (422); the inventory client already folds both
 * into Error.message, raw axios errors (image upload) still carry `detail`.
 */
const saveErrorMessage = (err: unknown): string => {
  const fallback = "Ошибка при сохранении";
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const text = detail
      .map((d) => (d && typeof d === "object" ? (d as { msg?: unknown }).msg : null))
      .filter((m): m is string => typeof m === "string" && m.length > 0)
      // Pydantic v1 prefixes custom validator messages; show only the message itself
      .map((m) => m.replace(/^Value error, /, ""))
      .join("; ");
    if (text) return text;
  }
  // Non-HTTP failures (network, timeout) come with English axios text
  if ((err as { isAxiosError?: boolean })?.isAxiosError) return `${fallback}: сервер недоступен`;
  if (err instanceof Error && err.message) return err.message.replace(/^Value error, /, "");
  return fallback;
};

/* ── Props ── */

interface ItemFormProps {
  selected?: number;
  /** Type preselected for a new item (from the category being browsed) */
  defaultType?: string;
  onSuccess: () => void;
  onCancel: () => void;
}

/* ── Component ── */

const ItemForm = ({ selected, defaultType = "head", onSuccess, onCancel }: ItemFormProps) => {
  const [item, setItem] = useState<ItemFormState>(() => initialState(defaultType));
  const [saving, setSaving] = useState(false);
  /** Id of an item created in this form whose refining config failed to save */
  const [createdId, setCreatedId] = useState<number | null>(null);
  const [conversionsDraft, setConversionsDraft] = useState<ConversionsDraft | null>(null);
  const [conversionsError, setConversionsError] = useState<string | null>(null);
  const [refiningRules, setRefiningRules] = useState<RefiningRule[] | null>(null);
  const [refiningRulesError, setRefiningRulesError] = useState<string | null>(null);

  const [imgFile, setImgFile] = useState<File | undefined>();
  const [imgFileUrl, setImgFileUrl] = useState<string | null>(null);
  const [crop, setCrop] = useState<ItemImageCrop | null>(null);
  /** Re-framing the icon of an already stored original */
  const [recropping, setRecropping] = useState(false);

  /** Shown when a type switch reset a rarity the new type cannot have */
  const [rarityNote, setRarityNote] = useState<string | null>(null);

  const targetId = selected ?? createdId ?? undefined;
  const editMode = Boolean(targetId);
  const rules = rulesFor(item.item_type, Boolean(item.is_food));
  const allowedRarities = allowedRaritiesFor(item.item_type);
  /** Recipes have no quality: no rarity field for them */
  const showRarity = itemHasRarity(item.item_type);
  const rarityAllowed = !showRarity || allowedRarities.includes(item.item_rarity);

  useEffect(() => {
    if (!selected) return;
    fetchItem(selected)
      .then((loaded: ItemFormState) =>
        // A payload from before FEAT-168 has no effect lists at all: fill them in
        // so the editor never reads an undefined array.
        setItem({
          ...initialState(String(loaded.item_type)),
          ...loaded,
          effects: Array.isArray(loaded.effects) ? loaded.effects : [],
          damage_entries: Array.isArray(loaded.damage_entries) ? loaded.damage_entries : [],
          // An item saved before §3.9-bis has no rows but may carry the legacy
          // single buff — show it as one row so editing it does not drop it.
          xp_buffs: resolveXpBuffs(loaded as ItemBattleConfig),
        }),
      )
      .catch((e: Error) => toast.error(e.message || "Не удалось загрузить предмет"));
  }, [selected]);

  // Object URL for previewing a freshly picked file; revoked when replaced
  useEffect(() => {
    if (!imgFile) {
      setImgFileUrl(null);
      return;
    }
    const url = URL.createObjectURL(imgFile);
    setImgFileUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [imgFile]);

  /* ── Handlers ── */

  const setField = (name: string, value: unknown) => setItem((st) => ({ ...st, [name]: value }));

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) => {
    const target = e.target;
    const value = target instanceof HTMLInputElement && target.type === "checkbox" ? target.checked : target.value;
    setField(target.name, value);
  };

  /** Empty select option means "not set" */
  const handleNullableSelect = (e: React.ChangeEvent<HTMLSelectElement>) =>
    setField(e.target.name, e.target.value === "" ? null : e.target.value);

  const handleTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const nextType = e.target.value;
    const resetRarity =
      itemHasRarity(nextType) && !allowedRaritiesFor(nextType).includes(item.item_rarity);
    setRarityNote(
      resetRarity
        ? `Редкость «${RARITY_LABELS[item.item_rarity] ?? item.item_rarity}» сброшена на «${RARITY_LABELS.common}»: ${RARITY_CAP_MESSAGE.toLowerCase()}.`
        : null,
    );
    setItem((st) => {
      const next: ItemFormState = { ...st, item_type: nextType };
      if (resetRarity) next.item_rarity = "common";
      if (nextType !== "consumable") next.is_food = false;
      if (DEFAULT_DURABILITY_TYPES.includes(nextType) && Number(st.max_durability) === 0) {
        next.max_durability = DEFAULT_DURABILITY;
      }
      if (nextType === "gathering_tool") {
        if (Number(st.max_durability) === 0) next.max_durability = DEFAULT_TOOL_DURABILITY;
        if (!st.tool_category) next.tool_category = "pickaxe";
      }
      return next;
    });
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setImgFile(e.target.files?.[0]);
    setCrop(null);
    setRecropping(false);
  };

  const cropperSrc = imgFileUrl ?? (recropping ? item.full_image ?? null : null);

  const handleConversionsChange = useCallback((draft: ConversionsDraft) => setConversionsDraft(draft), []);

  const subcategory = rules.resource ? ((item.resource_subcategory as string | null) ?? null) : null;
  // Refining rules decide which subcategories can be refined (loaded once for resources)
  const needsRefiningRules = rules.resource;
  useEffect(() => {
    if (!needsRefiningRules || refiningRules || refiningRulesError) return;
    fetchRefiningRules()
      .then((list) => setRefiningRules(Array.isArray(list) ? list : []))
      .catch((e: unknown) =>
        setRefiningRulesError(
          e instanceof Error && e.message ? e.message : "Не удалось загрузить правила переработки",
        ),
      );
  }, [needsRefiningRules, refiningRules, refiningRulesError]);

  const refinableSubcategories = useMemo(
    () => new Set((refiningRules ?? []).map((r) => r.source_subcategory as string)),
    [refiningRules],
  );
  // Editor for any rule's source subcategory; raw ones without a rule get the
  // "not refined yet" note from the editor
  const conversionsSubcategory =
    isResourceSubcategory(subcategory) &&
    (refinableSubcategories.has(subcategory) || isRawSubcategory(subcategory))
      ? subcategory
      : null;
  const showConversions = conversionsSubcategory !== null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rarityAllowed) {
      toast.error(RARITY_CAP_MESSAGE);
      return;
    }
    if (rules.battleEffects) {
      const battleError = validateBattleConfig(item);
      if (battleError) {
        toast.error(battleError);
        return;
      }
    }
    const xpError = validateXpBuffs(
      rules.buff ? ((item.xp_buffs as ItemXpBuff[] | undefined) ?? []) : [],
      item.item_type,
      Boolean(item.is_food),
    );
    if (xpError) {
      toast.error(xpError);
      return;
    }
    const draft = showConversions ? conversionsDraft : null;
    if (draft?.invalid) {
      toast.error(draft.invalid);
      return;
    }
    setSaving(true);
    setConversionsError(null);
    let saved: { id: number };
    try {
      const payload = buildItemPayload(item);
      saved = editMode ? await updateItem(targetId!, payload) : await createItem(payload);
      if (imgFile) {
        await uploadItemImage(saved.id, imgFile, crop);
      } else if (recropping && crop) {
        await recropItemImage(saved.id, crop);
      }
    } catch (err: unknown) {
      toast.error(saveErrorMessage(err));
      setSaving(false);
      return;
    }

    // Refining config is saved after the item (a new item needs its id first).
    // A retry after a failed save of a just-created item always sends the set.
    const mustSaveConversions = Boolean(
      draft && draft.ready && (draft.dirty || createdId !== null) && (Boolean(selected) || draft.conversions.length > 0),
    );
    if (draft && mustSaveConversions) {
      try {
        await putItemConversions(saved.id, { conversions: draft.conversions });
      } catch (err: unknown) {
        const msg = `Предмет сохранён, но настройки переработки — нет: ${saveErrorMessage(err)}`;
        setConversionsError(msg);
        toast.error(msg);
        if (!editMode) setCreatedId(saved.id);
        setSaving(false);
        return;
      }
    }

    toast.success(editMode ? "Предмет сохранён" : "Предмет создан");
    setSaving(false);
    onSuccess();
  };

  /* ── Type select: grouped by category; recipe items come from the recipe editor ── */

  const typeGroups = useMemo(
    () =>
      ITEM_CATEGORIES.map((cat) => ({
        ...cat,
        types: cat.types.filter((t) => t !== "recipe" || item.item_type === "recipe"),
      })),
    [item.item_type],
  );

  /* ── Render helpers ── */

  const numberInput = (name: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <input
      type="number"
      name={name}
      value={(item[name] as number | string | null) ?? ""}
      onChange={handleChange}
      className="input-underline"
      {...props}
    />
  );

  const renderModGroup = (title: string, mods: ModDef[]) => (
    <fieldset className="border border-white/10 rounded-card p-4 bg-white/[0.03] min-w-0">
      <legend className={`${labelText} px-2`}>{title}</legend>
      <div className="grid grid-cols-1 min-[420px]:grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-6 gap-y-3 mt-2">
        {mods.map(({ key, label, fractional }) => (
          <label key={key} className="flex items-center justify-between gap-2 min-w-0">
            <span className="text-sm text-white/70 truncate">{label}</span>
            <input
              name={key}
              type="number"
              step={fractional ? 0.1 : 1}
              value={(item[key] as number | string) ?? 0}
              onChange={handleChange}
              className="w-20 shrink-0 text-center bg-transparent border-b border-white/30 text-white text-sm outline-none focus:border-site-blue transition-colors"
            />
          </label>
        ))}
      </div>
    </fieldset>
  );

  return (
    <form className="gray-bg p-4 sm:p-6 flex flex-col gap-6" onSubmit={handleSubmit}>
      <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase tracking-[0.06em]">
        {editMode ? "Редактирование предмета" : "Создание предмета"}
      </h2>

      {/* ── Base ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        <Field label="Название">
          <input name="name" value={item.name} onChange={handleChange} required className="input-underline" />
        </Field>

        <Field label="Тип">
          <select
            name="item_type"
            value={item.item_type}
            onChange={handleTypeChange}
            disabled={item.item_type === "recipe"}
            className="input-underline"
          >
            {typeGroups.map((group) => (
              <optgroup key={group.key} label={group.label} className={optionClass}>
                {group.types.map((t) => (
                  <option key={t} value={t} className={optionClass}>
                    {ITEM_TYPE_LABELS[t]}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </Field>

        {showRarity && (
        <Field label="Редкость">
          <select
            name="item_rarity"
            value={item.item_rarity}
            onChange={(e) => {
              setRarityNote(null);
              handleChange(e);
            }}
            className="input-underline"
          >
            {/* A stored rarity this type may no longer have stays visible until changed */}
            {!rarityAllowed && (
              <option value={item.item_rarity} disabled className={optionClass}>
                {RARITY_LABELS[item.item_rarity] ?? item.item_rarity} (недоступна)
              </option>
            )}
            {allowedRarities.map((r) => (
              <option key={r} value={r} className={optionClass}>
                {RARITY_LABELS[r]}
              </option>
            ))}
          </select>
          {!rarityAllowed && (
            <span className="text-site-red text-xs">{RARITY_CAP_MESSAGE}. Выберите другую редкость.</span>
          )}
          {rarityAllowed && rarityNote && <span className="text-gold text-xs">{rarityNote}</span>}
        </Field>
        )}

        <Field label="Уровень предмета">{numberInput("item_level", { min: 0 })}</Field>
        <Field label="Цена">{numberInput("price", { min: 0 })}</Field>
        <Field label="Максимум в стаке">{numberInput("max_stack_size", { min: 1 })}</Field>

        <label className="flex items-center gap-3 self-end pb-2">
          <input
            type="checkbox"
            name="is_unique"
            checked={Boolean(item.is_unique)}
            onChange={handleChange}
            className="w-5 h-5 accent-site-blue"
          />
          <span className="text-sm text-white">Уникальный</span>
        </label>

        <Field label="Описание" wide>
          <textarea
            name="description"
            value={item.description ?? ""}
            onChange={handleChange}
            rows={3}
            className="textarea-bordered"
          />
        </Field>
      </div>

      {/* ── Recipe items are generated ── */}
      {rules.recipeAuto && (
        <p className="text-white/60 text-sm border border-white/10 rounded-card p-4 bg-white/[0.03]">
          Предмет-рецепт создаётся и удаляется автоматически вместе с рецептом в разделе профессий.
          Здесь можно поменять только название, описание и картинку.
        </p>
      )}

      {/* ── Equipment / weapon specifics ── */}
      {(rules.armorSubclass || rules.weaponFields || rules.durability || rules.sockets || rules.fastSlotBonus) &&
        !rules.gatheringTool && (
          <Section title="Экипировка">
            {rules.armorSubclass && (
              <Field label="Класс брони">
                <select
                  name="armor_subclass"
                  value={(item.armor_subclass as string) ?? ""}
                  onChange={handleNullableSelect}
                  className="input-underline"
                >
                  <option value="" className={optionClass}>—</option>
                  {Object.entries(ARMOR_SUBCLASS_LABELS).map(([value, label]) => (
                    <option key={value} value={value} className={optionClass}>{label}</option>
                  ))}
                </select>
              </Field>
            )}

            {rules.weaponFields && (
              <>
                <Field label="Вид оружия">
                  <select
                    name="weapon_subclass"
                    value={(item.weapon_subclass as string) ?? ""}
                    onChange={handleNullableSelect}
                    className="input-underline"
                  >
                    <option value="" className={optionClass}>—</option>
                    {WEAPON_SUBCLASS_GROUPS.map((group) => (
                      <optgroup key={group.key} label={group.label} className={optionClass}>
                        {Object.entries(group.options).map(([value, label]) => (
                          <option key={value} value={value} className={optionClass}>{label}</option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </Field>
                <Field label="Основной тип урона">
                  <select
                    name="primary_damage_type"
                    value={(item.primary_damage_type as string) ?? ""}
                    onChange={handleNullableSelect}
                    className="input-underline"
                  >
                    <option value="" className={optionClass}>—</option>
                    {Object.entries(DAMAGE_TYPE_LABELS).map(([value, label]) => (
                      <option key={value} value={value} className={optionClass}>{label}</option>
                    ))}
                  </select>
                </Field>
              </>
            )}

            {rules.durability && (
              <Field label="Макс. прочность">{numberInput("max_durability", { min: 0, placeholder: "0 = без прочности" })}</Field>
            )}
            {rules.sockets && (
              <Field label={rules.sockets === "gems" ? "Слоты под камни" : "Слоты под руны"}>
                {numberInput("socket_count", { min: 0, max: 10 })}
              </Field>
            )}
            {rules.fastSlotBonus && <Field label="Бонус быстрых слотов">{numberInput("fast_slot_bonus", { min: 0 })}</Field>}
          </Section>
        )}

      {/* ── Food (satiety) ── */}
      {rules.food && (
        <fieldset className="border border-white/10 rounded-card p-4 bg-white/[0.03] min-w-0">
          <legend className={`${labelText} px-2`}>Еда</legend>
          <label className="flex items-center gap-3 mt-2">
            <input
              type="checkbox"
              name="is_food"
              checked={Boolean(item.is_food)}
              onChange={handleChange}
              className="w-5 h-5 accent-site-blue shrink-0"
            />
            <span className="text-sm text-white">Еда (даёт сытость)</span>
          </label>
          {Boolean(item.is_food) && <p className="text-white/40 text-xs mt-3">{FOOD_HINT}</p>}
        </fieldset>
      )}

      {/* ── Consumables & scrolls ── */}
      {rules.recovery && (
        <Section
          title="Восстановление"
          hint={item.item_type === "scroll" ? "Срабатывает, если свиток лежит в быстром слоте." : undefined}
        >
          {RECOVERY_FIELDS.map(({ key, label }) => (
            <Field key={key} label={label}>{numberInput(key, { min: 0 })}</Field>
          ))}
        </Section>
      )}

      {/* ── Battle effects (FEAT-168) ── */}
      {rules.battleEffects && (
        <fieldset className="border border-white/10 rounded-card p-4 bg-white/[0.03] min-w-0">
          <legend className={`${labelText} px-2`}>Боевые эффекты</legend>
          <div className="mt-2">
            <ItemEffectSections
              effects={(item.effects as ItemEffect[] | undefined) ?? []}
              damageEntries={(item.damage_entries as ItemDamageEntry[] | undefined) ?? []}
              action={normalizeAction(item.consumable_action as string | null)}
              coatingTurns={item.coating_turns == null ? null : Number(item.coating_turns)}
              coatingBonusDamage={
                item.coating_bonus_damage == null ? null : Number(item.coating_bonus_damage)
              }
              onFieldChange={setField}
            />
          </div>
        </fieldset>
      )}

      {rules.buff && (
        <fieldset className="border border-white/10 rounded-card p-4 bg-white/[0.03] min-w-0">
          <legend className={`${labelText} px-2`}>Ускорение опыта</legend>
          <div className="mt-2">
            <ItemXpBuffsEditor
              rows={(item.xp_buffs as ItemXpBuff[] | undefined) ?? []}
              onChange={(rows) => setField("xp_buffs", rows)}
            />
          </div>
        </fieldset>
      )}

      {rules.identify && (
        <Section title="Опознание" hint="Опознаёт предметы до указанной редкости. Пустое значение — свиток не опознаёт.">
          <Field label="Уровень опознания">
            <select
              name="identify_level"
              value={(item.identify_level as number | null) ?? ""}
              onChange={handleNullableSelect}
              className="input-underline"
            >
              <option value="" className={optionClass}>—</option>
              {IDENTIFY_LEVEL_OPTIONS.map(({ value, label }) => (
                <option key={value} value={value} className={optionClass}>{label}</option>
              ))}
            </select>
          </Field>
        </Section>
      )}

      {/* ── Resources ── */}
      {rules.resource && (
        <Section title="Ресурс">
          <Field label="Подкатегория">
            <select
              name="resource_subcategory"
              value={subcategory ?? ""}
              onChange={handleNullableSelect}
              className="input-underline"
            >
              <option value="" className={optionClass}>{RESOURCE_SUBCATEGORY_NONE_LABEL}</option>
              {RESOURCE_SUBCATEGORY_GROUPS.map((group) => (
                <optgroup key={group.label} label={group.label} className={optionClass}>
                  {group.items.map((value) => (
                    <option key={value} value={value} className={optionClass}>
                      {RESOURCE_SUBCATEGORY_LABELS[value]}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </Field>

          {subcategory === "repair_kit" && (
            <Field label="Сила ремонта">
              <select
                name="repair_power"
                value={(item.repair_power as number | null) ?? ""}
                onChange={handleNullableSelect}
                required
                className="input-underline"
              >
                <option value="" className={optionClass}>—</option>
                {REPAIR_POWER_OPTIONS.map((p) => (
                  <option key={p} value={p} className={optionClass}>{p}% прочности</option>
                ))}
              </select>
            </Field>
          )}

          {subcategory === "whetstone" && (
            <>
              <Field label="Уровень камня заточки">
                <select
                  name="whetstone_level"
                  value={(item.whetstone_level as number | null) ?? ""}
                  onChange={handleNullableSelect}
                  required
                  className="input-underline"
                >
                  <option value="" className={optionClass}>—</option>
                  {WHETSTONE_OPTIONS.map(({ value, label }) => (
                    <option key={value} value={value} className={optionClass}>{label}</option>
                  ))}
                </select>
              </Field>
              <Field label="Группа камня">
                <select
                  name="whetstone_group"
                  value={(item.whetstone_group as string | null) ?? ""}
                  onChange={handleNullableSelect}
                  required
                  className="input-underline"
                >
                  <option value="" className={optionClass}>—</option>
                  {WHETSTONE_GROUP_OPTIONS.map(({ value, label }) => (
                    <option key={value} value={value} className={optionClass}>{label}</option>
                  ))}
                </select>
              </Field>
            </>
          )}
        </Section>
      )}

      {conversionsSubcategory && (
        <ItemConversionsEditor
          itemId={selected}
          subcategory={conversionsSubcategory}
          rules={refiningRules}
          rulesError={refiningRulesError}
          onChange={handleConversionsChange}
          saveError={conversionsError}
        />
      )}

      {/* ── Gathering tools ── */}
      {rules.gatheringTool && (
        <Section
          title="Инструмент сбора"
          hint="Прочность тратится при сборе и должна быть не меньше 1. Характеристики экипировки инструментам не положены."
        >
          <Field label="Тип инструмента">
            <select name="tool_category" value={(item.tool_category as string) ?? ""} onChange={handleChange} required className="input-underline">
              {TOOL_CATEGORIES.map((t) => (
                <option key={t} value={t} className={optionClass}>{TOOL_CATEGORY_LABELS[t]}</option>
              ))}
            </select>
          </Field>
          <Field label="Макс. прочность">{numberInput("max_durability", { min: 1 })}</Field>
          <Field label="Бонус шанса дубля, %">{numberInput("gather_double_chance_bonus", { min: 0, max: 50, step: 0.5 })}</Field>
          <Field label="Бонус скорости, %">{numberInput("gather_speed_bonus_pct", { min: 0, max: 50, step: 0.5 })}</Field>
          <Field label="Экономия стамины, %">{numberInput("gather_stamina_bonus_pct", { min: 0, max: 50, step: 0.5 })}</Field>
        </Section>
      )}

      {/* ── Modifiers ── */}
      {rules.modifiers && (
        <>
          {(item.item_type === "gem" || item.item_type === "rune") && (
            <p className="text-white/40 text-xs -mb-3">
              {item.item_type === "gem" ? "Камень" : "Руна"} добавляет эти значения предмету, в который вставлен.
            </p>
          )}
          {item.item_type === "consumable" && (
            <p className="text-white/40 text-xs -mb-3">Бонусы сытости: действуют 24 ч после еды.</p>
          )}
          {renderModGroup("Характеристики", ATTR_MODS)}
          {renderModGroup("Сопротивления", RES_MODS)}
          {renderModGroup("Уязвимости", VUL_MODS)}
        </>
      )}

      {/* ── Image upload + icon framing ── */}
      <fieldset className="border border-white/10 rounded-card p-4 bg-white/[0.03] flex flex-col gap-4 min-w-0">
        <legend className={`${labelText} px-2`}>Изображение</legend>

        <input
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif"
          onChange={handleFileChange}
          className="text-white text-sm max-w-full file:mr-4 file:py-2 file:px-4 file:rounded-card file:border-0 file:text-sm file:font-medium file:bg-white/[0.07] file:text-white hover:file:bg-white/[0.12] file:cursor-pointer file:transition-colors"
        />

        {cropperSrc ? (
          <ItemImageCropper key={cropperSrc} src={cropperSrc} onCropChange={setCrop} />
        ) : (
          item.image && (
            <div className="flex flex-wrap items-center gap-4">
              <img src={item.image} alt={item.name} className="w-16 h-16 rounded-card object-cover bg-white/5" />
              {item.full_image ? (
                <button type="button" onClick={() => setRecropping(true)} className="btn-line !w-auto !px-6">
                  Изменить область иконки
                </button>
              ) : (
                <p className="text-white/40 text-xs flex-1 min-w-[12rem]">
                  Исходная картинка не сохранена — загрузите файл заново, чтобы выбрать область иконки.
                </p>
              )}
            </div>
          )
        )}

        {recropping && !imgFile && (
          <button
            type="button"
            onClick={() => {
              setRecropping(false);
              setCrop(null);
            }}
            className="text-white/50 hover:text-site-blue text-sm self-start transition-colors"
          >
            Оставить иконку как есть
          </button>
        )}
      </fieldset>

      {/* ── Buttons ── */}
      <div className="flex flex-wrap gap-4 pt-2">
        <button type="submit" disabled={saving} className="btn-blue !text-base !px-8 !py-2 disabled:opacity-50">
          {saving ? "Сохранение…" : editMode ? "Сохранить" : "Создать"}
        </button>
        <button type="button" onClick={onCancel} className="btn-line !w-auto !px-8">
          Отмена
        </button>
      </div>
    </form>
  );
};

export default ItemForm;
