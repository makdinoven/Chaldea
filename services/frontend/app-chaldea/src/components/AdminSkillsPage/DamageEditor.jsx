// src/features/skills/DamageEditor.jsx
import React from 'react'
import styles from './AdminSkillsPage.module.scss'
import { DAMAGE_TYPES } from './skillConstants'

const DamageEditor = ({ damage, onChange, onDelete }) => {
  const handleField = (field, value) => {
    onChange({ ...damage, [field]: value })
  }

  return (
    <div className={styles.editorSection}>
      <div className={styles.sectionTitle}>
        Урон: {damage.damage_type || '(тип)'}
        <button 
          onClick={onDelete} 
          className={`${styles.deleteButton} ${styles.editorActions}`}
        >
          Удалить
        </button>
      </div>
      
      <div className={styles.inputGroup}>
        <label>Тип урона:</label>
        <select
          value={damage.damage_type || ''}
          onChange={(e) => handleField('damage_type', e.target.value)}
        >
          <option value="">(не выбрано)</option>
          {DAMAGE_TYPES.map(dt => (
            <option key={dt.value} value={dt.value}>
              {dt.label}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.inputGroup}>
        <label>Количество:</label>
        <input
          type="number"
          value={damage.amount || 0}
          onChange={(e) => handleField('amount', +e.target.value)}
        />
      </div>

      <div className={styles.inputGroup}>
        <label>Описание:</label>
        <input
          type="text"
          value={damage.description || ''}
          onChange={(e) => handleField('description', e.target.value)}
        />
      </div>
    </div>
  )
}

export default DamageEditor
