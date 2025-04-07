// ComplexEffectsSection.jsx
import React from 'react'
import { COMPLEX_EFFECTS } from '../skillConstants'
import styles from '../AdminSkillsPage.module.scss'

const ComplexEffectsSection = ({ title, complexArray, onChange }) => {

  const handleAdd = () => {
    const newItem = {
      effect_name: 'Bleeding',
      chance: 100,
      duration: 1,
      magnitude: 0,
    }
    onChange([...(complexArray || []), newItem])
  }

  const handleUpdate = (index, field, value) => {
    const newArr = [...complexArray]
    newArr[index] = { ...newArr[index], [field]: value }
    onChange(newArr)
  }

  const handleDelete = (index) => {
    const newArr = complexArray.filter((_, i) => i !== index)
    onChange(newArr)
  }

  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>{title}</div>
      {(complexArray || []).map((item, idx) => (
        <div key={idx} className={styles.inputRow} style={{ border: '1px solid #444', borderRadius: '4px', padding: '6px' }}>
          <div className={styles.inputGroup}>
            <label>Эффект:</label>
            <select
              value={item.effect_name}
              onChange={(e) => handleUpdate(idx, 'effect_name', e.target.value)}
            >
              {COMPLEX_EFFECTS.map(cf => (
                <option key={cf.value} value={cf.value}>{cf.label}</option>
              ))}
            </select>
          </div>
          <div className={styles.inputGroup}>
            <label>Шанс(%):</label>
            <input
              type="number"
              value={item.chance}
              onChange={(e) => handleUpdate(idx, 'chance', +e.target.value)}
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
            <label>Мощность:</label>
            <input
              type="number"
              value={item.magnitude}
              onChange={(e) => handleUpdate(idx, 'magnitude', +e.target.value)}
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

export default ComplexEffectsSection
