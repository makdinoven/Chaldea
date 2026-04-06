import React from "react";
import { DAMAGE_TYPES, WEAPON_SLOTS } from "../skillConstants";
import styles from "../AdminSkillsPage.module.scss";

interface DamageEntry {
  damage_type: string;
  amount: number;
  chance: number;
  weapon_slot: string;
  description: string;
}

interface DamageSectionProps {
  title: string;
  damageArray: DamageEntry[];
  onChange: (arr: DamageEntry[]) => void;
}

const DamageSection = ({ title, damageArray, onChange }: DamageSectionProps) => {
  const handleAdd = () =>
    onChange([
      ...(damageArray || []),
      { damage_type: "all", amount: 0, chance: 100, weapon_slot: "main_weapon", description: "" },
    ]);

  const handleUpdate = (idx: number, field: keyof DamageEntry, value: string | number) => {
    const arr = [...damageArray];
    arr[idx] = { ...arr[idx], [field]: value };
    onChange(arr);
  };

  const handleDelete = (idx: number) => onChange(damageArray.filter((_, i) => i !== idx));

  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>{title}</div>

      {(damageArray || []).map((item, idx) => (
        <div key={idx} className={styles.inputRow} style={{ border: "1px solid #444", borderRadius: 4, padding: 6 }}>
          <div className={styles.inputGroup}>
            <label>Тип:</label>
            <select value={item.damage_type} onChange={(e) => handleUpdate(idx, "damage_type", e.target.value)}>
              {DAMAGE_TYPES.map((dt) => (
                <option key={dt.value} value={dt.value}>
                  {dt.label}
                </option>
              ))}
            </select>
          </div>

          <div className={styles.inputGroup}>
            <label>Оружие:</label>
            <select value={item.weapon_slot} onChange={(e) => handleUpdate(idx, "weapon_slot", e.target.value)}>
              {WEAPON_SLOTS.map((ws) => (
                <option key={ws.value} value={ws.value}>
                  {ws.label}
                </option>
              ))}
            </select>
          </div>

          <div className={styles.inputGroup}>
            <label>Значение:</label>
            <input type="number" value={item.amount} onChange={(e) => handleUpdate(idx, "amount", +e.target.value)} />
          </div>

          <div className={styles.inputGroup}>
            <label>Шанс(%)</label>
            <input type="number" value={item.chance} onChange={(e) => handleUpdate(idx, "chance", +e.target.value)} />
          </div>

          <button onClick={() => handleDelete(idx)} className={styles.deleteButton}>
            Удалить
          </button>
        </div>
      ))}

      <button onClick={handleAdd} className={styles.addButton}>
        +Добавить
      </button>
    </div>
  );
};

export default DamageSection;
