import { useEffect, useState } from "react";
import styles from "./ItemsAdmin.module.scss";
import {
  createItem,
  updateItem,
  uploadItemImage,
  fetchItem,
} from "../../api/items";

// --- справочники ----------------------------------------------------------
const ITEM_TYPES = [
  "head",
  "body",
  "cloak",
  "belt",
  "ring",
  "necklace",
  "bracelet",
  "main_weapon",
  "additional_weapons",
  "consumable",
  "resource",
  "scroll",
  "misc",
];
const ITEM_RARITIES = [
  "common",
  "rare",
  "epic",
  "legendary",
  "mythical",
  "divine",
  "demonic",
];
const ARMOR_SUBCLASSES = [
  "cloth",
  "light_armor",
  "medium_armor",
  "heavy_armor",
];
const WEAPON_SUBCLASSES = [
  "one_handed_weapon",
  "two_handed_weapon",
  "maces",
  "axes",
  "battle_axes",
  "hammers",
  "polearms",
  "scythes",
  "daggers",
  "twin_daggers",
  "short_swords",
  "rapiers",
  "spears",
  "bows",
  "firearms",
  "knuckledusters",
  "one_handed_staffs",
  "two_handed_staffs",
  "grimoires",
  "catalysts",
  "spheres",
  "wands",
  "amulets",
  "magic_weapon",
];
const DAMAGE_TYPES = [
  "physical",
  "catting",
  "crushing",
  "piercing",
  "magic",
  "fire",
  "ice",
  "watering",
  "electricity",
  "wind",
  "sainting",
  "damning",
];

// --- поля с переводом -----------------------------------------------------
const ATTR_MODS = [
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

const RES_MODS = [
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

const VUL_MODS = RES_MODS.map(({ key, label }) => ({
  key: key.replace("res_", "vul_"),
  label: label.replace("Сопр.", "Уязв."),
}));

// --- начальное состояние --------------------------------------------------
const INITIAL_STATE = ATTR_MODS.concat(RES_MODS, VUL_MODS).reduce(
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
    // consumable recovery
    health_recovery: 0,
    energy_recovery: 0,
    mana_recovery: 0,
    stamina_recovery: 0,
  },
);

export default function ItemForm({ selected, onSuccess, onCancel }) {
  const [item, setItem] = useState(INITIAL_STATE);
  const [imgFile, setImgFile] = useState();
  const [error, setError] = useState(null);
  const editMode = Boolean(selected);

  useEffect(() => {
    if (selected) {
      fetchItem(selected)
        .then(setItem)
        .catch((e) => setError(e.message));
    }
  }, [selected]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setItem((st) => ({ ...st, [name]: type === "checkbox" ? checked : value }));
  };

  const showArmor = ["head", "body"].includes(item.item_type);
  const showWeapon = ["main_weapon", "additional_weapons"].includes(item.item_type);
  const showConsumable = item.item_type === "consumable";
  const excludeMods = ["resource", "scroll", "misc", "consumable"].includes(item.item_type);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const saved = editMode ? await updateItem(selected, item) : await createItem(item);
      if (imgFile) await uploadItemImage(saved.id, imgFile);
      onSuccess();
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <form className={`${styles.card} ${styles.form}`} onSubmit={handleSubmit}>
      {error && <p className={styles.error}>{error}</p>}

      {/* === базовые поля ================================================= */}
      <label>
        Название
        <input name="name" value={item.name} onChange={handleChange} required />
      </label>

      <label>
        Уровень предмета
        <input type="number" name="item_level" value={item.item_level} onChange={handleChange} min={0} />
      </label>

      <label>
        Тип
        <select name="item_type" value={item.item_type} onChange={handleChange}>
          {ITEM_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </label>

      <label>
        Редкость
        <select name="item_rarity" value={item.item_rarity} onChange={handleChange}>
          {ITEM_RARITIES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </label>

      <label>
        Цена
        <input type="number" name="price" value={item.price} onChange={handleChange} min={0} />
      </label>

      <label>
        Максимум в стаке
        <input type="number" name="max_stack_size" value={item.max_stack_size} onChange={handleChange} min={1} />
      </label>

      <label className={styles.checkboxLabel}>
        <input type="checkbox" name="is_unique" checked={item.is_unique} onChange={handleChange} />
        Уникальный
      </label>

      <label>
        Описание
        <textarea name="description" value={item.description} onChange={handleChange} />
      </label>

      <label>
        Бонус быстрых слотов
        <input type="number" name="fast_slot_bonus" value={item.fast_slot_bonus} onChange={handleChange} />
      </label>

      {/* --- специфические ------------------------------------------------- */}
      {showArmor && (
        <label>
          Класс брони
          <select name="armor_subclass" value={item.armor_subclass || ""} onChange={handleChange}>
            <option value="">—</option>
            {ARMOR_SUBCLASSES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
      )}

      {showWeapon && (
        <>
          <label>
            Подкласс оружия
            <select name="weapon_subclass" value={item.weapon_subclass || ""} onChange={handleChange}>
              <option value="">—</option>
              {WEAPON_SUBCLASSES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>
          <label>
            Тип урона
            <select name="primary_damage_type" value={item.primary_damage_type || ""} onChange={handleChange}>
              <option value="">—</option>
              {DAMAGE_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>
        </>
      )}

      {showConsumable && (
        <>
          <label>
            Восстановление HP
            <input name="health_recovery" type="number" value={item.health_recovery} onChange={handleChange} min={0} />
          </label>
          <label>
            Восстановление энергии
            <input name="energy_recovery" type="number" value={item.energy_recovery} onChange={handleChange} min={0} />
          </label>
          <label>
            Восстановление маны
            <input name="mana_recovery" type="number" value={item.mana_recovery} onChange={handleChange} min={0} />
          </label>
          <label>
            Восстановление выносливости
            <input name="stamina_recovery" type="number" value={item.stamina_recovery} onChange={handleChange} min={0} />
          </label>
        </>
      )}

      {/* --- модификаторы -------------------------------------------------- */}
      {!excludeMods && (
        <>
          <fieldset className={styles.mods}>
            <legend>Характеристики</legend>
            {ATTR_MODS.map(({ key, label }) => (
              <label key={key}>{label}<input name={key} type="number" value={item[key]} onChange={handleChange} /></label>
            ))}
          </fieldset>

          <fieldset className={styles.mods}>
            <legend>Сопротивления</legend>
            {RES_MODS.map(({ key, label }) => (
              <label key={key}>{label}<input name={key} type="number" value={item[key]} onChange={handleChange} /></label>
            ))}
          </fieldset>

          <fieldset className={styles.mods}>
            <legend>Уязвимости</legend>
            {VUL_MODS.map(({ key, label }) => (
              <label key={key}>{label}<input name={key} type="number" value={item[key]} onChange={handleChange} /></label>
            ))}
          </fieldset>
        </>
      )}

      {/* --- изображение --------------------------------------------------- */}
      <label>
        Изображение
        <input type="file" accept="image/*" onChange={(e) => setImgFile(e.target.files[0])} />
      </label>

      {/* --- кнопки -------------------------------------------------------- */}
      <div className={styles.actions}>
        <button type="submit" className={styles.primary}>{editMode ? "Сохранить" : "Создать"}</button>
        <button type="button" className="btn btn--ghost" onClick={onCancel}>Отмена</button>
      </div>
    </form>
  );
}