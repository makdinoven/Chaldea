// src/features/skills/tabs/DamageSection.jsx
import React from 'react'
import { DAMAGE_TYPES } from '../skillConstants'
import styles from '../AdminSkillsPage.module.scss'

const DamageSection = ({ title, damageArray, onChange }) => {
  const handleAdd = () => {
    const newItem = { damage_type: 'all', amount: 0, duration: 0, chance: 100, description: ''}
    onChange([...(damageArray || []), newItem])
  }

  const handleUpdate = (index, field, value) => {
    const newArr = [...damageArray]
    const key = field === 'type' ? 'damage_type' : field
    newArr[index] = { ...newArr[index], [key]: value }
    onChange(newArr)
  }

  const handleDelete = (index) => {
    const newArr = damageArray.filter((_, i) => i !== index)
    onChange(newArr)
  }

  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>{title}</div>
      {(damageArray || []).map((item, idx) => (
        <div key={idx} className={styles.inputRow} style={{ border: '1px solid #444', borderRadius: '4px', padding: '6px' }}>
          <div className={styles.inputGroup}>
            <label>Тип:</label>
            <select
              value={item.type}
              onChange={(e) => handleUpdate(idx, 'type', e.target.value)}
            >
              {DAMAGE_TYPES.map(dt => (
                <option key={dt.value} value={dt.value}>{dt.label}</option>
              ))}
            </select>
          </div>
          <div className={styles.inputGroup}>
            <label>Значение:</label>
            <input
              type="number"
              value={item.amount}
              onChange={(e) => handleUpdate(idx, 'amount', +e.target.value)}
            />
          </div>
          <div className={styles.inputGroup}>
            <label>Длит.(ходы):</label>
            <input
              type="number"
              value={item.duration}
              onChange={(e) => handleUpdate(idx, 'duration', +e.target.value)}
            />
          </div>
          <div className={styles.inputGroup}>
            <label>Шанс(%):</label>
            <input
              type="number"
              value={item.chance}
              onChange={(e) => handleUpdate(idx, 'chance', +e.target.value)}
            />
          </div>
          <button
            onClick={() => handleDelete(idx)}
            className={styles.deleteButton}
          >
            Удалить
          </button>
        </div>
      ))}

      <button onClick={handleAdd} className={styles.addButton}>
        + Добавить
      </button>
    </div>
  )
}

export default DamageSection
