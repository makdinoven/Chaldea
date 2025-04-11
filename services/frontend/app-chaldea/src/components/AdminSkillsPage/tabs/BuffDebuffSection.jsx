// BuffDebuffSection.jsx
import React from 'react'
import { DAMAGE_TYPES } from '../skillConstants'
import styles from '../AdminSkillsPage.module.scss'

const BuffDebuffSection = ({ title, buffArray, onChange }) => {
  const handleAdd = () => {
    const newItem = { damage_type: 'fire', percent: 0, duration: 0, chance: 100 }
    onChange([...(buffArray || []), newItem])
  }

  const handleUpdate = (index, field, value) => {
    const newArr = [...buffArray]
     const key = field === 'type' ? 'damage_type' : field
    newArr[index] = { ...newArr[index], [key]: value }
    onChange(newArr)
  }

  const handleDelete = (index) => {
    onChange(buffArray.filter((_, i) => i !== index))
  }

  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>{title}</div>
      {(buffArray || []).map((item, idx) => (
        <div key={idx} className={styles.inputRow} style={{ border: '1px solid #444', borderRadius: '4px', padding: '6px' }}>
          <div className={styles.inputGroup}>
            <label>Тип:</label>
            <select
              value={item.damage_type}
              onChange={(e) => handleUpdate(idx, 'damage_type', e.target.value)}
            >
              {DAMAGE_TYPES.map(dt => (
                <option key={dt.value} value={dt.value}>{dt.label}</option>
              ))}
            </select>
          </div>
          <div className={styles.inputGroup}>
            <label>Процент(%):</label>
            <input
              type="number"
              value={item.percent}
              onChange={(e) => handleUpdate(idx, 'percent', +e.target.value)}
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
          <button onClick={() => handleDelete(idx)} className={styles.deleteButton}>
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

export default BuffDebuffSection
