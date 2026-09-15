import React, { useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import {
  createItem,
  updateItem,
  uploadItemImage,
  recropItemImage,
  fetchItem,
  fetchAllItems,
  type ItemImageCrop,
} from "../../api/items";
import { fetchAdminRecipes } from "../../api/professions";
import ItemImageCropper from "./ItemImageCropper";
import {
  ARMOR_SUBCLASS_LABELS,
  DAMAGE_TYPE_LABELS,
  ITEM_CATEGORIES,
  ITEM_RARITIES,
  ITEM_TYPE_LABELS,
  RARITY_LABELS,
  TOOL_CATEGORIES,
  TOOL_CATEGORY_LABELS,
  WEAPON_SUBCLASS_GROUPS,
} from "../../constants/items";
import {
  ATTR_MODS,
  BUFF_TYPE_OPTIONS,
  DEFAULT_DURABILITY,
  DEFAULT_DURABILITY_TYPES,
  DEFAULT_TOOL_DURABILITY,
  IDENTIFY_LEVEL_OPTIONS,
  RECOVERY_FIELDS,
  REPAIR_POWER_OPTIONS,
  RES_MODS,
  RESOURCE_KIND_LABELS,
  VUL_MODS,
  WHETSTONE_OPTIONS,
  buildItemPayload,
  detectResourceKind,
  rulesFor,
  type ModDef,
  type ResourceKind,
} from "./itemFormRules";

/* ── State ── */

interface ItemFormState {
  name: string;
  item_type: string;
  item_rarity: string;
  item_level: number | string;
  price: number | string;
  max_stack_size: number | string;
  is_unique: boolean;
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
    essence_result_item_id: null,
    blueprint_recipe_id: null,
    tool_category: itemType === "gathering_tool" ? "pickaxe" : null,
    gather_double_chance_bonus: 0,
    gather_speed_bonus_pct: 0,
    gather_stamina_bonus_pct: 0,
  };
};

interface Option {
  id: number;
  name: string;
}

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
  const [resourceKind, setResourceKind] = useState<ResourceKind>("plain");
  const [saving, setSaving] = useState(false);

  const [imgFile, setImgFile] = useState<File | undefined>();
  const [imgFileUrl, setImgFileUrl] = useState<string | null>(null);
  const [crop, setCrop] = useState<ItemImageCrop | null>(null);
  /** Re-framing the icon of an already stored original */
  const [recropping, setRecropping] = useState(false);

  const [essenceOptions, setEssenceOptions] = useState<Option[] | null>(null);
  const [recipeOptions, setRecipeOptions] = useState<Option[] | null>(null);

  const editMode = Boolean(selected);
  const rules = rulesFor(item.item_type);

  useEffect(() => {
    if (!selected) return;
    fetchItem(selected)
      .then((loaded: ItemFormState) => {
        setItem(loaded);
        setResourceKind(detectResourceKind(loaded));
      })
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

  // Lazy lookups for the pickers, loaded once when first needed
  const needsEssences = rules.resourceKind && resourceKind === "crystal";
  useEffect(() => {
    if (!needsEssences || essenceOptions) return;
    fetchAllItems({ itemTypes: ["resource"] })
      .then((list: Option[]) =>
        setEssenceOptions(list.map(({ id, name }) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name, "ru"))),
      )
      .catch((e: Error) => toast.error(e.message || "Не удалось загрузить список эссенций"));
  }, [needsEssences, essenceOptions]);

  useEffect(() => {
    if (!rules.blueprintRecipe || recipeOptions) return;
    (async () => {
      const all: Option[] = [];
      for (let page = 1; ; page += 1) {
        const res = await fetchAdminRecipes({ page, per_page: 100 });
        all.push(...res.items.map(({ id, name }) => ({ id, name })));
        if (all.length >= res.total || res.items.length === 0) break;
      }
      setRecipeOptions(all.sort((a, b) => a.name.localeCompare(b.name, "ru")));
    })().catch((e: Error) => toast.error(e.message || "Не удалось загрузить список рецептов"));
  }, [rules.blueprintRecipe, recipeOptions]);

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
    setItem((st) => {
      const next: ItemFormState = { ...st, item_type: nextType };
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = buildItemPayload(item, resourceKind);
      const saved = editMode ? await updateItem(selected!, payload) : await createItem(payload);
      if (imgFile) {
        await uploadItemImage(saved.id, imgFile, crop);
      } else if (recropping && crop) {
        await recropItemImage(saved.id, crop);
      }
      toast.success(editMode ? "Предмет сохранён" : "Предмет создан");
      onSuccess();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      const msg = typeof detail === "string" ? detail : err instanceof Error ? err.message : "Ошибка при сохранении";
      toast.error(msg || "Ошибка при сохранении");
    } finally {
      setSaving(false);
    }
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

        <Field label="Редкость">
          <select name="item_rarity" value={item.item_rarity} onChange={handleChange} className="input-underline">
            {ITEM_RARITIES.map((r) => (
              <option key={r} value={r} className={optionClass}>
                {RARITY_LABELS[r]}
              </option>
            ))}
          </select>
        </Field>

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
          Здесь можно поменять только название, описание, редкость и картинку.
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

      {rules.buff && (
        <Section title="Бафф" hint="Бонус к опыту задаётся в процентах: 50 = +50% опыта на время действия.">
          <Field label="Тип баффа">
            <select
              name="buff_type"
              value={(item.buff_type as string) ?? ""}
              onChange={handleNullableSelect}
              className="input-underline"
            >
              <option value="" className={optionClass}>Нет</option>
              {BUFF_TYPE_OPTIONS.map(({ value, label }) => (
                <option key={value} value={value} className={optionClass}>{label}</option>
              ))}
            </select>
          </Field>
          {Boolean(item.buff_type) && (
            <>
              <Field label="Сила, %">
                <input
                  type="number"
                  min={0}
                  step={1}
                  value={item.buff_value == null ? "" : Math.round(Number(item.buff_value) * 100)}
                  onChange={(e) => setField("buff_value", e.target.value === "" ? null : Number(e.target.value) / 100)}
                  className="input-underline"
                />
              </Field>
              <Field label="Длительность, мин">{numberInput("buff_duration_minutes", { min: 1 })}</Field>
            </>
          )}
        </Section>
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
      {rules.resourceKind && (
        <Section title="Вид ресурса">
          <Field label="Вид">
            <select
              value={resourceKind}
              onChange={(e) => setResourceKind(e.target.value as ResourceKind)}
              className="input-underline"
            >
              {(Object.keys(RESOURCE_KIND_LABELS) as ResourceKind[]).map((kind) => (
                <option key={kind} value={kind} className={optionClass}>{RESOURCE_KIND_LABELS[kind]}</option>
              ))}
            </select>
          </Field>

          {resourceKind === "repair_kit" && (
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

          {resourceKind === "whetstone" && (
            <Field label="Уровень точильного камня">
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
          )}

          {resourceKind === "crystal" && (
            <Field label="Эссенция из кристалла">
              <select
                name="essence_result_item_id"
                value={(item.essence_result_item_id as number | null) ?? ""}
                onChange={handleNullableSelect}
                required
                disabled={!essenceOptions}
                className="input-underline"
              >
                <option value="" className={optionClass}>{essenceOptions ? "—" : "Загрузка…"}</option>
                {essenceOptions
                  ?.filter((o) => o.id !== selected)
                  .map((o) => (
                    <option key={o.id} value={o.id} className={optionClass}>{o.name}</option>
                  ))}
              </select>
            </Field>
          )}
        </Section>
      )}

      {rules.blueprintRecipe && (
        <Section title="Чертёж" hint="С чертежом рецепт можно сделать один раз без изучения; чертёж при этом тратится.">
          <Field label="Рецепт">
            <select
              name="blueprint_recipe_id"
              value={(item.blueprint_recipe_id as number | null) ?? ""}
              onChange={handleNullableSelect}
              disabled={!recipeOptions}
              className="input-underline"
            >
              <option value="" className={optionClass}>{recipeOptions ? "—" : "Загрузка…"}</option>
              {recipeOptions?.map((o) => (
                <option key={o.id} value={o.id} className={optionClass}>{o.name}</option>
              ))}
            </select>
          </Field>
        </Section>
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
