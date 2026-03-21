// ComplexEffectsSection.jsx
import React from 'react'
import { COMPLEX_EFFECTS } from '../skillConstants'
import styles from '../AdminSkillsPage.module.scss'

const ComplexEffectsSection = ({ title, complexArray, onChange, side }) => {

  // Filter effects by allowed side (Holy=self only, Curse=enemy only)
  const availableEffects = COMPLEX_EFFECTS.filter(
    (ef) => !ef.allowedSides || ef.allowedSides.includes(side)
  )

  const getEffectDef = (effectName) =>
    COMPLEX_EFFECTS.find((ef) => ef.value === effectName) || null

  const handleAdd = () => {
    const first = availableEffects[0]
    const newItem = {
      effect_name: first.value,
      chance: 100,
      duration: first.fixedDuration ?? 1,
      magnitude: 0,
      attribute_key: first.hasAttributeKey && first.attributeKeyOptions
        ? first.attributeKeyOptions[0].value
        : null,
    }
    onChange([...(complexArray || []), newItem])
  }

  const handleUpdate = (index, field, value) => {
    const newArr = [...complexArray]
    const updated = { ...newArr[index], [field]: value }

    // When effect_name changes, reset fields based on new effect definition
    if (field === 'effect_name') {
      const def = getEffectDef(value)
      if (def) {
        if (def.fixedDuration !== null && def.fixedDuration !== undefined) {
          updated.duration = def.fixedDuration
        }
        if (def.hasAttributeKey && def.attributeKeyOptions) {
          updated.attribute_key = def.attributeKeyOptions[0].value
        } else {
          updated.attribute_key = null
        }
        // Reset magnitude when switching effects
        if (def.fixedDuration !== null && def.value !== 'Knockdown' && def.value !== 'Windburn') {
          // Stun: magnitude is always 0
          if (def.value === 'Stun') {
            updated.magnitude = 0
          }
        }
      }
    }

    newArr[index] = updated
    onChange(newArr)
  }

  const handleDelete = (index) => {
    onChange(complexArray.filter((_, i) => i !== index))
  }

  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>{title}</div>
      {(complexArray || []).map((item, idx) => {
        const def = getEffectDef(item.effect_name)
        const isFixedDuration = def && def.fixedDuration !== null && def.fixedDuration !== undefined
        const showAttributeKey = def && def.hasAttributeKey && def.attributeKeyOptions

        return (
          <div
            key={idx}
            className={styles.inputRow}
            style={{ border: '1px solid #444', borderRadius: '4px', padding: '6px', flexDirection: 'column', gap: '6px' }}
          >
            {/* Description */}
            {def && def.description && (
              <div style={{ fontSize: '11px', color: '#aaa', fontStyle: 'italic', marginBottom: '2px' }}>
                {def.description}
              </div>
            )}

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'flex-end' }}>
              {/* Effect selector */}
              <div className={styles.inputGroup}>
                <label>Эффект:</label>
                <select
                  value={item.effect_name}
                  onChange={(e) => handleUpdate(idx, 'effect_name', e.target.value)}
                >
                  {availableEffects.map((cf) => (
                    <option key={cf.value} value={cf.value}>
                      {cf.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Chance */}
              <div className={styles.inputGroup}>
                <label>Шанс(%):</label>
                <input
                  type="number"
                  value={item.chance}
                  onChange={(e) => handleUpdate(idx, 'chance', +e.target.value)}
                />
              </div>

              {/* Duration */}
              <div className={styles.inputGroup}>
                <label>Длит.(ходы):</label>
                <input
                  type="number"
                  value={isFixedDuration ? def.fixedDuration : item.duration}
                  disabled={isFixedDuration}
                  onChange={(e) => handleUpdate(idx, 'duration', +e.target.value)}
                  style={isFixedDuration ? { opacity: 0.5 } : {}}
                />
              </div>

              {/* Magnitude */}
              <div className={styles.inputGroup}>
                <label>Мощность:</label>
                <input
                  type="number"
                  value={item.magnitude}
                  onChange={(e) => handleUpdate(idx, 'magnitude', +e.target.value)}
                />
              </div>

              {/* Attribute key (conditional) */}
              {showAttributeKey && (
                <div className={styles.inputGroup}>
                  <label>
                    {item.effect_name === 'Poison' ? 'Подтип:' :
                     item.effect_name === 'MagicImpact' ? 'Атрибут:' :
                     'Тип навыка:'}
                  </label>
                  <select
                    value={item.attribute_key || def.attributeKeyOptions[0].value}
                    onChange={(e) => handleUpdate(idx, 'attribute_key', e.target.value)}
                  >
                    {def.attributeKeyOptions.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <button onClick={() => handleDelete(idx)} className={styles.deleteButton}>
                Удалить
              </button>
            </div>
          </div>
        )
      })}
      <button onClick={handleAdd} className={styles.addButton}>
        + Добавить
      </button>
    </div>
  )
}

export default ComplexEffectsSection
