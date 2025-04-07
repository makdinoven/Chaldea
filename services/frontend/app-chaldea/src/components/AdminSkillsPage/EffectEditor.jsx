// src/features/skills/EffectEditor.jsx
import React from 'react'
import styles from './AdminSkillsPage.module.scss'
import { COMPLEX_EFFECTS } from './skillConstants'

const EffectEditor = ({ effect, onChange, onDelete }) => {
  const handleField = (field, value) => {
    onChange({ ...effect, [field]: value })
  }

  return (
    <div className={styles.editorSection}>
      <div className={styles.sectionTitle}>
        Эффект: {effect.effect_name || "(нет)"}
        <button
          onClick={onDelete}
          className={`${styles.deleteButton} ${styles.editorActions}`}
        >
          Удалить
        </button>
      </div>

      <div className={styles.inputGroup}>
        <label>Тип эффекта:</label>
        <select
          value={effect.effect_name || ""}
          onChange={(e) => handleField("effect_name", e.target.value)}
        >
          <option value="">(не выбрано)</option>
          {/* Сложные эффекты */}
          {COMPLEX_EFFECTS.map(cf => (
            <option key={cf.value} value={cf.value}>
              {cf.label}
            </option>
          ))}
          {/* Можно добавить дополнительные, вроде "fire_damage_up", "res_fire_up", etc. */}
          <option value="fire_damage_up">Усиление огня</option>
          <option value="res_fire_up">Сопротивление огню</option>
          <option value="vul_physical_up">Уязвимость к физ.урону</option>
        </select>
      </div>

      <div className={styles.inputGroup}>
        <label>Длительность (ходы):</label>
        <input
          type="number"
          min="0"
          value={effect.duration || 0}
          onChange={(e) => handleField("duration", +e.target.value)}
        />
      </div>

      <div className={styles.inputGroup}>
        <label>Описание эффекта:</label>
        <input
          type="text"
          value={effect.description || ""}
          onChange={(e) => handleField("description", e.target.value)}
        />
      </div>

      <div className={styles.inputRow}>
        <div className={styles.inputGroup}>
          <label>critResistChance (%):</label>
          <input
            type="number"
            step="0.1"
            value={effect.critResistChance || 0}
            onChange={(e) => handleField("critResistChance", +e.target.value)}
          />
        </div>
        <div className={styles.inputGroup}>
          <label>critResistDamage (%):</label>
          <input
            type="number"
            step="0.1"
            value={effect.critResistDamage || 0}
            onChange={(e) => handleField("critResistDamage", +e.target.value)}
          />
        </div>
      </div>
    </div>
  )
}

export default EffectEditor
