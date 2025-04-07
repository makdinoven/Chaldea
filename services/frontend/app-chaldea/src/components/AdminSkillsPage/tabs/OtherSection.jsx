// src/features/skills/tabs/OtherSection.jsx
import React from 'react'
import styles from '../AdminSkillsPage.module.scss'

/**
 * props:
 *  - title: string
 *  - rank: сам объект ранга
 *  - onChange: (updatedRank) => void
 *  - fieldPrefix: "self" или "enemy"
 */
const OtherSection = ({ title, rank, onChange, fieldPrefix }) => {

  // Генерируем названия полей на основе префикса
  // Например, "selfCritChance", "enemyCritChance"
  const chanceField = `${fieldPrefix}CritChance`;
  const durationField = `${fieldPrefix}CritChanceDuration`;
  const chanceChanceField = `${fieldPrefix}CritChanceChance`; // звучит смешно :)

  const handleFieldChange = (field, value) => {
    onChange({ ...rank, [field]: value })
  }

  return (
    <div className={styles.subSection}>
      <div className={styles.sectionTitle}>{title}</div>

      <div className={styles.inputRow}>
        <div className={styles.inputGroup}>
          <label>Crit Chance (%):</label>
          <input
            type="number"
            value={rank[chanceField] || 0}
            onChange={(e) => handleFieldChange(chanceField, +e.target.value)}
          />
        </div>
        <div className={styles.inputGroup}>
          <label>Длит. (ходы):</label>
          <input
            type="number"
            value={rank[durationField] || 0}
            onChange={(e) => handleFieldChange(durationField, +e.target.value)}
          />
        </div>
        <div className={styles.inputGroup}>
          <label>Шанс срабатывания(%):</label>
          <input
            type="number"
            value={rank[chanceChanceField] || 100}
            onChange={(e) => handleFieldChange(chanceChanceField, +e.target.value)}
          />
        </div>
      </div>

      {/* Добавляйте при желании другие поля, напр. critDamage */}
    </div>
  )
}

export default OtherSection
