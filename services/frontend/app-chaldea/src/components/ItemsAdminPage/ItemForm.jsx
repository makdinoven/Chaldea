import { useState, useEffect } from "react";
import styles from "./ItemsAdmin.modules.scss";
import {
  createItem,
  updateItem,
  uploadItemImage,
  fetchItem,
} from "../../api/items";

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
const ARMOR_SUBCLASSES = ["cloth", "light_armor", "medium_armor", "heavy_armor"];
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

const INITIAL_STATE = {
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
  // modifiers
  strength_modifier: 0,
  agility_modifier: 0,
  intelligence_modifier: 0,
  endurance_modifier: 0,
  health_modifier: 0,
  energy_modifier: 0,
  mana_modifier: 0,
  stamina_modifier: 0,
  charisma_modifier: 0,
  luck_modifier: 0,
  damage_modifier: 0,
  dodge_modifier: 0,
};

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

  const modifiers = [
    "strength_modifier",
    "agility_modifier",
    "intelligence_modifier",
    "endurance_modifier",
    "health_modifier",
    "energy_modifier",
    "mana_modifier",
    "stamina_modifier",
    "charisma_modifier",
    "luck_modifier",
    "damage_modifier",
    "dodge_modifier",
  ];

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      let saved = null;
      if (editMode) {
        saved = await updateItem(selected, item);
      } else {
        saved = await createItem(item);
      }
      if (imgFile) {
        await uploadItemImage(saved.id, imgFile);
      }
      onSuccess();
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      {error && <p className={styles.error}>{error}</p>}

      <label>
        Название
        <input name="name" value={item.name} onChange={handleChange} required />
      </label>

      <label>
        Уровень предмета
        <input
          type="number"
          name="item_level"
          value={item.item_level}
          onChange={handleChange}
          min={0}
        />
      </label>

      <label>
        Тип
        <select name="item_type" value={item.item_type} onChange={handleChange}>
          {ITEM_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>

      <label>
        Редкость
        <select name="item_rarity" value={item.item_rarity} onChange={handleChange}>
          {ITEM_RARITIES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>

      <label>
        Цена
        <input type="number" name="price" value={item.price} onChange={handleChange} min={0} />
      </label>

      <label>
        Максимум в стаке
        <input
          type="number"
          name="max_stack_size"
          value={item.max_stack_size}
          onChange={handleChange}
          min={1}
        />
      </label>

      <label className={styles.checkboxLabel}>
        <input type="checkbox" name="is_unique" checked={item.is_unique} onChange={handleChange} />
        Уникальный
      </label>

      <label>
        Описание
        <textarea name="description" value={item.description} onChange={handleChange} />
      </label>

      {showArmor && (
        <label>
          Класс брони
          <select name="armor_subclass" value={item.armor_subclass || ""} onChange={handleChange}>
            <option value="">—</option>
            {ARMOR_SUBCLASSES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
      )}

      {showWeapon && (
        <>
          <label>
            Подкласс оружия
            <select
              name="weapon_subclass"
              value={item.weapon_subclass || ""}
              onChange={handleChange}
            >
              <option value="">—</option>
              {WEAPON_SUBCLASSES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label>
            Тип урона
            <select
              name="primary_damage_type"
              value={item.primary_damage_type || ""}
              onChange={handleChange}
            >
              <option value="">—</option>
              {DAMAGE_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
        </>
      )}

      {showConsumable && (
        <>
          <label>
            Восстановление HP
            <input
              name="health_recovery"
              type="number"
              value={item.health_recovery}
              onChange={handleChange}
              min={0}
            />
          </label>
          <label>
            Восстановление энергии
            <input
              name="energy_recovery"
              type="number"
              value={item.energy_recovery}
              onChange={handleChange}
              min={0}
            />
          </label>
          <label>
            Восстановление маны
            <input
              name="mana_recovery"
              type="number"
              value={item.mana_recovery}
              onChange={handleChange}
              min={0}
            />
          </label>
          <label>
            Восстановление выносливости
            <input
              name="stamina_recovery"
              type="number"
              value={item.stamina_recovery}
              onChange={handleChange}
              min={0}
            />
          </label>
        </>
      )}

      {!excludeMods && (
        <fieldset className={styles.mods}>
          <legend>Модификаторы</legend>
          {modifiers.map((m) => (
            <label key={m}>
              {m.replace("_modifier", "").replace("_", " ")}
              <input name={m} type="number" value={item[m]} onChange={handleChange} />
            </label>
          ))}
        </fieldset>
      )}

      <label>
        Изображение
        <input type="file" accept="image/*" onChange={(e) => setImgFile(e.target.files[0])} />
      </label>

      <div className={styles.actions}>
        <button type="submit" className={styles.primary}>
          {editMode ? "Сохранить" : "Создать"}
        </button>
        <button type="button" onClick={onCancel}>
          Отмена
        </button>
      </div>
    </form>
  );
}