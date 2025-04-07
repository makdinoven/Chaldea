import React from 'react'
import DamageEditor from './DamageEditor'
import EffectEditor from './EffectEditor'
import styles from './AdminSkillsPage.module.scss'

const RankEditor = ({ rank, onUpdate, onDelete }) => {
  const handleFieldChange = (field, value) => {
    onUpdate({ ...rank, [field]: value })
  }

  const handleDamageUpdate = (updatedEntry, index) => {
    const newDamageEntries = [...rank.damage_entries]
    newDamageEntries[index] = updatedEntry
    onUpdate({ ...rank, damage_entries: newDamageEntries })
  }

  const handleAddDamage = () => {
    const newDamage = {
      id: null,
      damage_type: 'physical',
      amount: 0,
      description: ''
    }
    onUpdate({ ...rank, damage_entries: [...rank.damage_entries, newDamage] })
  }

  const handleDeleteDamage = (index) => {
    const newDamageEntries = rank.damage_entries.filter((_, i) => i !== index)
    onUpdate({ ...rank, damage_entries: newDamageEntries })
  }

  const handleEffectUpdate = (updatedEffect, index) => {
    const newEffects = [...rank.effects]
    newEffects[index] = updatedEffect
    onUpdate({ ...rank, effects: newEffects })
  }

  const handleAddEffect = () => {
    const newEffect = {
      id: null,
      target_side: 'self',
      effect_name: 'Bleeding',
      description: '',
      chance: 100,
      duration: 1,
      magnitude: 0.0,
      attribute_key: null
    }
    onUpdate({ ...rank, effects: [...rank.effects, newEffect] })
  }

  const handleDeleteEffect = (index) => {
    const newEffects = rank.effects.filter((_, i) => i !== index)
    onUpdate({ ...rank, effects: newEffects })
  }

  return (
    <div className={styles.editorSection}>
      <div className={styles.sectionTitle}>
        Ранг #{rank.rank_number}
        {rank.id && (
          <button 
            onClick={() => onDelete(rank.id)} 
            className={`${styles.deleteButton} ${styles.editorActions}`}
          >
            Удалить ранг
          </button>
        )}
      </div>

      <div className={styles.inputGroup}>
        <label>Номер ранга:</label>
        <input
          type="number"
          value={rank.rank_number}
          onChange={(e) => handleFieldChange('rank_number', +e.target.value)}
        />
      </div>

      <div className={styles.inputRow}>
        <div className={styles.inputGroup}>
          <label>Левый потомок ID:</label>
          <input
            type="number"
            value={rank.left_child_id || ''}
            onChange={(e) => handleFieldChange('left_child_id', e.target.value ? +e.target.value : null)}
          />
        </div>

        <div className={styles.inputGroup}>
          <label>Правый потомок ID:</label>
          <input
            type="number"
            value={rank.right_child_id || ''}
            onChange={(e) => handleFieldChange('right_child_id', e.target.value ? +e.target.value : null)}
          />
        </div>
      </div>

      <div className={styles.inputRow}>
        <div className={styles.inputGroup}>
          <label>Стоимость энергии:</label>
          <input
            type="number"
            value={rank.cost_energy}
            onChange={(e) => handleFieldChange('cost_energy', +e.target.value)}
          />
        </div>

        <div className={styles.inputGroup}>
          <label>Стоимость маны:</label>
          <input
            type="number"
            value={rank.cost_mana}
            onChange={(e) => handleFieldChange('cost_mana', +e.target.value)}
          />
        </div>
      </div>

      <div className={styles.inputRow}>
        <div className={styles.inputGroup}>
          <label>Перезарядка:</label>
          <input
            type="number"
            value={rank.cooldown}
            onChange={(e) => handleFieldChange('cooldown', +e.target.value)}
          />
        </div>

        <div className={styles.inputGroup}>
          <label>Требуемый уровень:</label>
          <input
            type="number"
            value={rank.level_requirement}
            onChange={(e) => handleFieldChange('level_requirement', +e.target.value)}
          />
        </div>
      </div>

      <div className={styles.inputGroup}>
        <label>Стоимость улучшения:</label>
        <input
          type="number"
          value={rank.upgrade_cost}
          onChange={(e) => handleFieldChange('upgrade_cost', +e.target.value)}
        />
      </div>

      <div className={styles.inputGroup}>
        <label>Описание ранга:</label>
        <textarea
          value={rank.rank_description || ''}
          onChange={(e) => handleFieldChange('rank_description', e.target.value)}
        />
      </div>

      <div className={styles.subSection}>
        <div className={styles.sectionTitle}>
          Урон
          <button 
            onClick={handleAddDamage}
            className={styles.editorActions}
          >
            + Добавить урон
          </button>
        </div>
        {rank.damage_entries.map((dmg, idx) => (
          <DamageEditor
            key={dmg.id ?? `dmg-${idx}`}
            damage={dmg}
            onChange={(upd) => handleDamageUpdate(upd, idx)}
            onDelete={() => handleDeleteDamage(idx)}
          />
        ))}
      </div>

      <div className={styles.subSection}>
        <div className={styles.sectionTitle}>
          Эффекты
          <button 
            onClick={handleAddEffect}
            className={styles.editorActions}
          >
            + Добавить эффект
          </button>
        </div>
        {rank.effects.map((eff, idx) => (
          <EffectEditor
            key={eff.id ?? `eff-${idx}`}
            effect={eff}
            onChange={(upd) => handleEffectUpdate(upd, idx)}
            onDelete={() => handleDeleteEffect(idx)}
          />
        ))}
      </div>
    </div>
  )
}

export default RankEditor