import React, { useEffect, useState } from "react";
import {
  createItem,
  updateItem,
  uploadItemImage,
  fetchItem,
} from "../../api/items";
import toast from "react-hot-toast";

/* ── Dictionaries ── */

const ITEM_TYPES = [
  "head", "body", "cloak", "belt", "ring", "necklace", "bracelet",
  "main_weapon", "additional_weapons", "shield", "consumable", "resource",
  "scroll", "misc", "blueprint", "recipe", "gem", "rune",
] as const;

const ITEM_TYPE_LABELS: Record<string, string> = {
  head: "Голова", body: "Тело", cloak: "Плащ", belt: "Пояс",
  ring: "Кольцо", necklace: "Ожерелье", bracelet: "Браслет",
  main_weapon: "Основное оружие", additional_weapons: "Доп. оружие", shield: "Щит",
  consumable: "Расходуемое", resource: "Ресурс", scroll: "Свиток", misc: "Разное",
  blueprint: "Чертёж", recipe: "Рецепт", gem: "Камень", rune: "Руна",
};

const ITEM_RARITIES = [
  "common", "rare", "epic", "mythical", "legendary", "divine", "demonic",
] as const;

const ITEM_RARITY_LABELS: Record<string, string> = {
  common: "Обычное", rare: "Редкое", epic: "Эпическое",
  mythical: "Мифическое", legendary: "Легендарное",
  divine: "Божественное", demonic: "Демоническое",
};

const ARMOR_SUBCLASSES = ["cloth", "light_armor", "medium_armor", "heavy_armor"] as const;
const ARMOR_SUBCLASS_LABELS: Record<string, string> = {
  cloth: "Ткань", light_armor: "Легкая броня", medium_armor: "Средняя броня", heavy_armor: "Тяжелая броня",
};

const WEAPON_SUBCLASSES = [
  "one_handed_weapon", "two_handed_weapon", "maces", "axes", "battle_axes",
  "hammers", "polearms", "scythes", "daggers", "twin_daggers", "short_swords",
  "rapiers", "spears", "bows", "firearms", "knuckledusters",
  "one_handed_staffs", "two_handed_staffs", "grimoires", "catalysts",
  "spheres", "wands", "amulets", "magic_weapon",
] as const;

const WEAPON_SUBCLASS_LABELS: Record<string, string> = {
  one_handed_weapon: "Одноручное оружие", two_handed_weapon: "Двуручное оружие",
  maces: "Булава", axes: "Топоры", battle_axes: "Боевые топоры",
  hammers: "Молоты", polearms: "Древковое оружие", scythes: "Косы",
  daggers: "Кинжалы", twin_daggers: "Парные кинжалы", short_swords: "Короткие мечи",
  rapiers: "Рапиры", spears: "Копья", bows: "Луки", firearms: "Огнестрельное оружие",
  knuckledusters: "Кастеты", one_handed_staffs: "Одноручные посохи",
  two_handed_staffs: "Двуручные посохи", grimoires: "Гримуары", catalysts: "Катализаторы",
  spheres: "Сферы", wands: "Жезлы", amulets: "Амулеты", magic_weapon: "Магическое оружие",
};

const DAMAGE_TYPES = [
  "physical", "catting", "crushing", "piercing", "magic",
  "fire", "ice", "watering", "electricity", "wind", "sainting", "damning",
] as const;

const DAMAGE_TYPE_LABELS: Record<string, string> = {
  physical: "Физический", catting: "Режущий", crushing: "Дробящий",
  piercing: "Колющий", magic: "Магический", fire: "Огненный", ice: "Ледяной",
  watering: "Водный", electricity: "Электрический", wind: "Воздушный",
  sainting: "Святой", damning: "Проклятый",
};

/* ── Modifier groups ── */

interface ModDef {
  key: string;
  label: string;
}

const ATTR_MODS: ModDef[] = [
  { key: "strength_modifier", label: "Сила" },
  { key: "agility_modifier", label: "Ловкость" },
  { key: "intelligence_modifier", label: "Интеллект" },
  { key: "endurance_modifier", label: "Выносливость" },
  { key: "health_modifier", label: "Здоровье" },
  { key: "energy_modifier", label: "Энергия" },
  { key: "mana_modifier", label: "Мана" },
  { key: "stamina_modifier", label: "Станмина" },
  { key: "charisma_modifier", label: "Харизма" },
  { key: "luck_modifier", label: "Удача" },
  { key: "damage_modifier", label: "Урон" },
  { key: "dodge_modifier", label: "Уклонение" },
  { key: "critical_hit_chance_modifier", label: "Крит шанс" },
  { key: "critical_damage_modifier", label: "Крит урон" },
];

const RES_MODS: ModDef[] = [
  { key: "res_effects_modifier", label: "Сопр. эффектам" },
  { key: "res_physical_modifier", label: "Сопр. физическому" },
  { key: "res_catting_modifier", label: "Сопр. режущему" },
  { key: "res_crushing_modifier", label: "Сопр. дробящему" },
  { key: "res_piercing_modifier", label: "Сопр. колющему" },
  { key: "res_magic_modifier", label: "Сопр. магии" },
  { key: "res_fire_modifier", label: "Сопр. огню" },
  { key: "res_ice_modifier", label: "Сопр. льду" },
  { key: "res_watering_modifier", label: "Сопр. воде" },
  { key: "res_electricity_modifier", label: "Сопр. молнии" },
  { key: "res_wind_modifier", label: "Сопр. ветру" },
  { key: "res_sainting_modifier", label: "Сопр. святому" },
  { key: "res_damning_modifier", label: "Сопр. проклятому" },
];

const VUL_MODS: ModDef[] = RES_MODS.map(({ key, label }) => ({
  key: key.replace("res_", "vul_"),
  label: label.replace("Сопр.", "Уязв."),
}));

/* ── Initial state ── */

interface ItemFormState {
  name: string;
  item_level: number;
  item_type: string;
  item_rarity: string;
  price: number;
  max_stack_size: number;
  is_unique: boolean;
  description: string;
  fast_slot_bonus: number;
  armor_subclass: string | null;
  weapon_subclass: string | null;
  primary_damage_type: string | null;
  health_recovery: number;
  energy_recovery: number;
  mana_recovery: number;
  stamina_recovery: number;
  socket_count: number;
  whetstone_level: string;
  max_durability: number;
  [key: string]: unknown;
}

const INITIAL_STATE: ItemFormState = [...ATTR_MODS, ...RES_MODS, ...VUL_MODS].reduce<ItemFormState>(
  (acc, { key }) => ({ ...acc, [key]: 0 }),
  {
    name: "",
    item_level: 0,
    item_type: "head",
    item_rarity: "common",
    price: 0,
    max_stack_size: 1,
    is_unique: false,
    description: "",
    fast_slot_bonus: 0,
    armor_subclass: null,
    weapon_subclass: null,
    primary_damage_type: null,
    health_recovery: 0,
    energy_recovery: 0,
    mana_recovery: 0,
    stamina_recovery: 0,
    socket_count: 0,
    whetstone_level: "",
    max_durability: 0,
  },
);

/* ── Props ── */

interface ItemFormProps {
  selected?: number;
  onSuccess: () => void;
  onCancel: () => void;
}

/* ── Component ── */

const ItemForm = ({ selected, onSuccess, onCancel }: ItemFormProps) => {
  const [item, setItem] = useState<ItemFormState>(INITIAL_STATE);
  const [imgFile, setImgFile] = useState<File | undefined>();
  const editMode = Boolean(selected);

  useEffect(() => {
    if (selected) {
      fetchItem(selected)
        .then(setItem)
        .catch((e: Error) => toast.error(e.message || "Не удалось загрузить предмет"));
    }
  }, [selected]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) => {
    const target = e.target;
    const name = target.name;
    const value =
      target instanceof HTMLInputElement && target.type === "checkbox"
        ? target.checked
        : target.value;
    setItem((st) => {
      const updated = { ...st, [name]: value };
      // Auto-set max_durability when switching to a durability type
      if (name === "item_type") {
        const DURABILITY_TYPES = ["head", "body", "cloak", "main_weapon", "additional_weapons"];
        if (DURABILITY_TYPES.includes(value as string) && (st.max_durability === 0 || st.max_durability === "0")) {
          updated.max_durability = 100;
        }
      }
      return updated;
    });
  };

  const showArmor = ["head", "body"].includes(item.item_type);
  const showWeapon = ["main_weapon", "additional_weapons"].includes(item.item_type);
  const showConsumable = item.item_type === "consumable";
  const excludeMods = ["resource", "scroll", "misc", "consumable"].includes(item.item_type);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload = {
        ...item,
        socket_count: Number(item.socket_count) || 0,
        whetstone_level: item.whetstone_level ? Number(item.whetstone_level) : null,
        max_durability: Number(item.max_durability) || 0,
      };
      const saved = editMode
        ? await updateItem(selected!, payload)
        : await createItem(payload);
      if (imgFile) await uploadItemImage(saved.id, imgFile);
      toast.success(editMode ? "Предмет сохранён" : "Предмет создан");
      onSuccess();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка при сохранении";
      toast.error(msg);
    }
  };

  /* ── Helper: renders a group of modifier fields ── */
  const renderModGroup = (title: string, mods: ModDef[]) => (
    <fieldset className="col-span-full border border-white/10 rounded-card p-4 bg-white/[0.03]">
      <legend className="text-white/50 text-xs font-medium uppercase tracking-[0.06em] px-2">
        {title}
      </legend>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 mt-2">
        {mods.map(({ key, label }) => (
          <label key={key} className="flex items-center justify-between gap-2">
            <span className="text-sm text-white/70">{label}</span>
            <input
              name={key}
              type="number"
              value={item[key] as number}
              onChange={handleChange}
              className="w-20 text-center bg-transparent border-b border-white/30 text-white text-sm outline-none focus:border-site-blue transition-colors"
            />
          </label>
        ))}
      </div>
    </fieldset>
  );

  return (
    <form className="gray-bg p-6 flex flex-col gap-6" onSubmit={handleSubmit}>
      <h2 className="gold-text text-2xl font-medium uppercase tracking-[0.06em]">
        {editMode ? "Редактирование предмета" : "Создание предмета"}
      </h2>

      {/* ── Base fields grid ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {/* Name */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Название
          </span>
          <input
            name="name"
            value={item.name}
            onChange={handleChange}
            required
            className="input-underline"
          />
        </label>

        {/* Level */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Уровень предмета
          </span>
          <input
            type="number"
            name="item_level"
            value={item.item_level}
            onChange={handleChange}
            min={0}
            className="input-underline"
          />
        </label>

        {/* Type */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Тип
          </span>
          <select
            name="item_type"
            value={item.item_type}
            onChange={handleChange}
            className="input-underline"
          >
            {ITEM_TYPES.map((t) => (
              <option key={t} value={t} className="bg-site-dark text-white">
                {ITEM_TYPE_LABELS[t]}
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
            name="item_rarity"
            value={item.item_rarity}
            onChange={handleChange}
            className="input-underline"
          >
            {ITEM_RARITIES.map((t) => (
              <option key={t} value={t} className="bg-site-dark text-white">
                {ITEM_RARITY_LABELS[t]}
              </option>
            ))}
          </select>
        </label>

        {/* Price */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Цена
          </span>
          <input
            type="number"
            name="price"
            value={item.price}
            onChange={handleChange}
            min={0}
            className="input-underline"
          />
        </label>

        {/* Max stack */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Максимум в стаке
          </span>
          <input
            type="number"
            name="max_stack_size"
            value={item.max_stack_size}
            onChange={handleChange}
            min={1}
            className="input-underline"
          />
        </label>

        {/* Unique checkbox */}
        <label className="flex items-center gap-3 self-end pb-2">
          <input
            type="checkbox"
            name="is_unique"
            checked={item.is_unique}
            onChange={handleChange}
            className="w-5 h-5 accent-site-blue"
          />
          <span className="text-sm text-white">Уникальный</span>
        </label>

        {/* Fast slot bonus */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Бонус быстрых слотов
          </span>
          <input
            type="number"
            name="fast_slot_bonus"
            value={item.fast_slot_bonus}
            onChange={handleChange}
            className="input-underline"
          />
        </label>

        {/* Max durability */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Макс. прочность
          </span>
          <input
            type="number"
            name="max_durability"
            value={item.max_durability}
            onChange={handleChange}
            min={0}
            className="input-underline"
            placeholder="0 = без прочности"
          />
        </label>

        {/* Socket count */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Слоты для камней/рун
          </span>
          <input
            type="number"
            name="socket_count"
            value={item.socket_count}
            onChange={handleChange}
            min={0}
            max={10}
            className="input-underline"
          />
        </label>

        {/* Whetstone level */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Уровень точильного камня
          </span>
          <select
            name="whetstone_level"
            value={item.whetstone_level}
            onChange={handleChange}
            className="input-underline bg-transparent"
          >
            <option value="">Не точильный камень</option>
            <option value="1">1 — Обычный (25%)</option>
            <option value="2">2 — Редкий (50%)</option>
            <option value="3">3 — Легендарный (75%)</option>
          </select>
        </label>

        {/* Description (spans full width) */}
        <label className="flex flex-col gap-1 col-span-full">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Описание
          </span>
          <textarea
            name="description"
            value={item.description}
            onChange={handleChange}
            rows={3}
            className="textarea-bordered"
          />
        </label>
      </div>

      {/* ── Conditional fields ── */}
      {showArmor && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Класс брони
            </span>
            <select
              name="armor_subclass"
              value={item.armor_subclass || ""}
              onChange={handleChange}
              className="input-underline"
            >
              <option value="" className="bg-site-dark text-white">—</option>
              {ARMOR_SUBCLASSES.map((t) => (
                <option key={t} value={t} className="bg-site-dark text-white">
                  {ARMOR_SUBCLASS_LABELS[t]}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {showWeapon && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Подкласс оружия
            </span>
            <select
              name="weapon_subclass"
              value={item.weapon_subclass || ""}
              onChange={handleChange}
              className="input-underline"
            >
              <option value="" className="bg-site-dark text-white">—</option>
              {WEAPON_SUBCLASSES.map((t) => (
                <option key={t} value={t} className="bg-site-dark text-white">
                  {WEAPON_SUBCLASS_LABELS[t]}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Тип урона
            </span>
            <select
              name="primary_damage_type"
              value={item.primary_damage_type || ""}
              onChange={handleChange}
              className="input-underline"
            >
              <option value="" className="bg-site-dark text-white">—</option>
              {DAMAGE_TYPES.map((t) => (
                <option key={t} value={t} className="bg-site-dark text-white">
                  {DAMAGE_TYPE_LABELS[t]}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {showConsumable && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Восстановление HP
            </span>
            <input
              name="health_recovery"
              type="number"
              value={item.health_recovery}
              onChange={handleChange}
              min={0}
              className="input-underline"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Восстановление энергии
            </span>
            <input
              name="energy_recovery"
              type="number"
              value={item.energy_recovery}
              onChange={handleChange}
              min={0}
              className="input-underline"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Восстановление маны
            </span>
            <input
              name="mana_recovery"
              type="number"
              value={item.mana_recovery}
              onChange={handleChange}
              min={0}
              className="input-underline"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Восстановление выносливости
            </span>
            <input
              name="stamina_recovery"
              type="number"
              value={item.stamina_recovery}
              onChange={handleChange}
              min={0}
              className="input-underline"
            />
          </label>
        </div>
      )}

      {/* ── Modifiers ── */}
      {!excludeMods && (
        <>
          {renderModGroup("Характеристики", ATTR_MODS)}
          {renderModGroup("Сопротивления", RES_MODS)}
          {renderModGroup("Уязвимости", VUL_MODS)}
        </>
      )}

      {/* ── Image upload ── */}
      <label className="flex flex-col gap-1">
        <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
          Изображение
        </span>
        <input
          type="file"
          accept="image/*"
          onChange={(e) => setImgFile(e.target.files?.[0])}
          className="text-white text-sm file:mr-4 file:py-2 file:px-4 file:rounded-card file:border-0 file:text-sm file:font-medium file:bg-white/[0.07] file:text-white hover:file:bg-white/[0.12] file:cursor-pointer file:transition-colors"
        />
      </label>

      {/* ── Buttons ── */}
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

export default ItemForm;
