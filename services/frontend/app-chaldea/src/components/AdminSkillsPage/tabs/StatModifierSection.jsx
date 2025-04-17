import React from "react";
import { STAT_MODIFIERS } from "../skillConstants";
import styles from "../AdminSkillsPage.module.scss";

const StatModifierSection = ({ title, modsArray, onChange }) => {
  const addRow = () =>
    onChange([...(modsArray || []), { key: "crit_chance", amount: 0, duration: 1, chance: 100 }]);

  const upd = (i, f, v) => onChange(modsArray.map((r, idx) => (idx === i ? { ...r, [f]: v } : r)));

  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>{title}</div>
      {(modsArray || []).map((row, i) => (
        <div key={i} className={styles.inputRow} style={{ border: "1px solid #444", borderRadius: 4, padding: 6 }}>
          <div className={styles.inputGroup}>
            <label>Параметр:</label>
            <select value={row.key} onChange={(e) => upd(i, "key", e.target.value)}>
              {STAT_MODIFIERS.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>

          <div className={styles.inputGroup}>
            <label>{row.key.startsWith("crit") || row.key.endsWith("chance") ? "Процент (±)" : "Значение (±)"}</label>
            <input type="number" value={row.amount} onChange={(e) => upd(i, "amount", +e.target.value)} />
          </div>

          <div className={styles.inputGroup}>
            <label>Длит. (ходы)</label>
            <input type="number" value={row.duration} onChange={(e) => upd(i, "duration", +e.target.value)} />
          </div>

          <div className={styles.inputGroup}>
            <label>Шанс (%)</label>
            <input type="number" value={row.chance} onChange={(e) => upd(i, "chance", +e.target.value)} />
          </div>

          <button onClick={() => onChange(modsArray.filter((_, idx) => idx !== i))} className={styles.deleteButton}>
            Удалить
          </button>
        </div>
      ))}

      <button onClick={addRow} className={styles.addButton}>
        + Добавить
      </button>
    </div>
  );
};

export default StatModifierSection;
