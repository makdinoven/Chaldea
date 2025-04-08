// src/features/skills/NodeRankDetails.jsx
import React, { useState } from 'react'
import { Handle, Position } from 'reactflow'
import styles from './AdminSkillsPage.module.scss'

import {
  CLASS_OPTIONS,
  RACE_OPTIONS,
  SUBRACE_OPTIONS
} from './skillConstants'

import DamageSection from './tabs/DamageSection'
import BuffDebuffSection from './tabs/DamageSection' // оставляем, как и было, если другой путь, исправьте
import ResistSection from './tabs/ResistSection'
import VulnerabilitySection from './tabs/VulnerabilitySection'
import ComplexEffectsSection from './tabs/ComplexEffectsSection'
import { uploadSkillRankImage } from "../../redux/actions/skillsAdminActions.js";
import { useDispatch } from "react-redux";

export default function NodeRankDetails({
  id,
  data,
  selected,
  onChangeNode,
  onDeleteRank
}) {
  // Свернуто по умолчанию
  const [expanded, setExpanded] = useState(false)
  // Активная вкладка (для редактирования эффектов)
  const [activeTab, setActiveTab] = useState('self')

  const handleChange = (field, value) => {
    onChangeNode(id, field, value)
  }

  const dispatch = useDispatch()

  const handleRankImageChange = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      onChangeNode(id, 'rank_image', ev.target.result)
      dispatch(uploadSkillRankImage({ skillRankId: data.id, file }))
    }
    reader.readAsDataURL(file)
  }

  // Функция для рендеринга "шапки" узла – название, ID и круг с фото
  const renderCircularHeader = () => (
    <div style={{ textAlign: 'center', marginBottom: '8px' }}>
      <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>
        {id.toString().startsWith('temp-') ? 'Новый ранг' : `ID: ${id}`} – {data.rank_name ?? 'Ранг'}
      </div>
      <div
        style={{
          width: 80,
          height: 80,
          margin: '0 auto',
          borderRadius: '50%',
          overflow: 'hidden',
          backgroundColor: data.rank_image ? 'transparent' : '#ddd',
          backgroundImage: data.rank_image ? `url(${data.rank_image})` : 'none',
          backgroundSize: 'cover',
          backgroundPosition: 'center'
        }}
      />
    </div>
  )

  // Для свернутого (collapsed) вида
  if (!expanded) {
    return (
      <div
        style={{
          background: selected ? '#fff7e6' : '#fff',
          border: '1px solid #ccc',
          borderRadius: 6,
          padding: 6,
          minWidth: 120,
          textAlign: 'center',
          cursor: 'pointer',
          position: 'relative'
        }}
        onClick={() => setExpanded(true)}
      >
        {/* Хэндлы – все располагаем с правой стороны */}
        <Handle
          type="target"
          position={Position.Right}
          style={{ top: '10%', right: -8, background: '#555' }}
        />
        <Handle
          type="source"
          id="left"
          position={Position.Right}
          style={{ top: '45%', right: -8, background: 'blue' }}
        />
        <Handle
          type="source"
          id="right"
          position={Position.Right}
          style={{ top: '80%', right: -8, background: 'green' }}
        />

        {renderCircularHeader()}
      </div>
    )
  }

  // Для развернутого (expanded) вида – здесь можно сохранить форму редактирования
  return (
    <div
      style={{
        background: selected ? '#fff7e6' : '#fff',
        border: '1px solid #ccc',
        borderRadius: 6,
        padding: 8,
        minWidth: 260,
        position: 'relative'
      }}
    >
      {/* Хэндлы – аналогично, с правой стороны */}
      <Handle
        type="target"
        position={Position.Right}
        style={{ top: '10%', right: -8, width: '16px', height: '16px', borderRadius: '50%', background: '#555' }}
      />
      <Handle
        type="source"
        id="left"
        position={Position.Right}
        style={{ top: '45%', right: -8, width: '16px', height: '16px', borderRadius: '50%', background: 'blue' }}
      />
      <Handle
        type="source"
        id="right"
        position={Position.Right}
        style={{ top: '80%', right: -8, width: '16px', height: '16px', borderRadius: '50%', background: 'green' }}
      />

      {/* В шапке отображается круг и заголовок */}
      {renderCircularHeader()}

      {/* Кнопки управления – Свернуть/Удалить */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <button
          style={{
            background: '#ddd',
            border: '1px solid #ccc',
            borderRadius: 4,
            cursor: 'pointer'
          }}
          onClick={() => setExpanded(false)}
        >
          Свернуть
        </button>
        {onDeleteRank && (
          <button
            style={{
              background: '#f44336',
              color: '#fff',
              border: 'none',
              borderRadius: 4,
              cursor: 'pointer'
            }}
            onClick={() => onDeleteRank(id)}
          >
            Удалить
          </button>
        )}
      </div>

      {/* Поля для редактирования */}
      <div className={styles.inputRow}>
        <div className={styles.inputGroup}>
          <label>Название ранга:</label>
          <input
            type="text"
            value={data.rank_name ?? ''}
            onChange={(e) => handleChange('rank_name', e.target.value)}
          />
        </div>
      </div>

      <div className={styles.inputGroup}>
        <label>Фото ранга:</label>
        <input type="file" accept="image/*" onChange={handleRankImageChange} />
        {data.rank_image ? (
          <img src={data.rank_image} alt="Rank" style={{ width: 80, height: 80, borderRadius: '50%', marginTop: 4 }} />
        ) : (
          <div
            style={{
              width: 80,
              height: 80,
              background: '#ddd',
              borderRadius: '50%',
              marginTop: 4,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#999'
            }}
          >
            (нет фото)
          </div>
        )}
      </div>

      {/* Остальные поля ввода – можно оставить как было */}
      <div className={styles.inputRow}>
        <div className={styles.inputGroup}>
          <label>Ур. навыка (rank_number):</label>
          <input
            type="number"
            value={data.rank_number ?? 1}
            onChange={(e) => handleChange('rank_number', +e.target.value)}
          />
        </div>
        <div className={styles.inputGroup}>
          <label>Min ур. перса:</label>
          <input
            type="number"
            value={data.level_requirement ?? 1}
            onChange={(e) => handleChange('level_requirement', +e.target.value)}
          />
        </div>
      </div>

      <div className={styles.inputRow}>
        <div className={styles.inputGroup}>
          <label>Энергия (cost_energy):</label>
          <input
            type="number"
            value={data.cost_energy ?? 0}
            onChange={(e) => handleChange('cost_energy', +e.target.value)}
          />
        </div>
        <div className={styles.inputGroup}>
          <label>Мана (cost_mana):</label>
          <input
            type="number"
            value={data.cost_mana ?? 0}
            onChange={(e) => handleChange('cost_mana', +e.target.value)}
          />
        </div>
      </div>

      <div className={styles.inputRow}>
        <div className={styles.inputGroup}>
          <label>Кулдаун:</label>
          <input
            type="number"
            value={data.cooldown ?? 0}
            onChange={(e) => handleChange('cooldown', +e.target.value)}
          />
        </div>
        <div className={styles.inputGroup}>
          <label>Цена улучш.(upgrade_cost):</label>
          <input
            type="number"
            value={data.upgrade_cost ?? 0}
            onChange={(e) => handleChange('upgrade_cost', +e.target.value)}
          />
        </div>
      </div>

      <div className={styles.inputRow}>
        <div className={styles.inputGroup}>
          <label>Класс (огр.):</label>
          <select
            value={data.class_limitations ?? ''}
            onChange={(e) => handleChange('class_limitations', e.target.value)}
          >
            <option value="">(нет)</option>
            {CLASS_OPTIONS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.inputGroup}>
          <label>Раса (огр.):</label>
          <select
            value={data.race_limitations ?? ''}
            onChange={(e) => handleChange('race_limitations', e.target.value)}
          >
            <option value="">(нет)</option>
            {RACE_OPTIONS.map(r => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className={styles.inputRow}>
        <div className={styles.inputGroup}>
          <label>Подраса (огр.):</label>
          <select
            value={data.subrace_limitations ?? ''}
            onChange={(e) => handleChange('subrace_limitations', e.target.value)}
          >
            <option value="">(нет)</option>
            {SUBRACE_OPTIONS.map(sr => (
              <option key={sr.value} value={sr.value}>
                {sr.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Вкладки для дополнительных настроек */}
      <div className={styles.tabButtons} style={{ marginTop: 6 }}>
        <button
          className={`${styles.tabButton} ${activeTab === 'self' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('self')}
        >
          Для себя
        </button>
        <button
          className={`${styles.tabButton} ${activeTab === 'enemy' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('enemy')}
        >
          Для врага
        </button>
      </div>

      {activeTab === 'self' && (
        <>
          <DamageSection
            title="Колич. урон (Self)"
            damageArray={data.selfDamage || []}
            onChange={(arr) => handleChange('selfDamage', arr)}
          />
          <BuffDebuffSection
            title="Бафф/дебафф (Self)"
            buffArray={data.selfDamageBuff || []}
            onChange={(arr) => handleChange('selfDamageBuff', arr)}
          />
          <ResistSection
            title="Резисты (Self)"
            resistArray={data.selfResist || []}
            onChange={(arr) => handleChange('selfResist', arr)}
          />
          <VulnerabilitySection
            title="Уязвимости (Self)"
            vulnerabilityArray={data.selfVulnerability || []}
            onChange={(arr) => handleChange('selfVulnerability', arr)}
          />
          <ComplexEffectsSection
            title="Сложн. эффекты (Self)"
            complexArray={data.selfComplexEffects || []}
            onChange={(arr) => handleChange('selfComplexEffects', arr)}
          />
        </>
      )}

      {activeTab === 'enemy' && (
        <>
          <DamageSection
            title="Колич. урон (Enemy)"
            damageArray={data.enemyDamage || []}
            onChange={(arr) => handleChange('enemyDamage', arr)}
          />
          <BuffDebuffSection
            title="Бафф/дебафф (Enemy)"
            buffArray={data.enemyDamageBuff || []}
            onChange={(arr) => handleChange('enemyDamageBuff', arr)}
          />
          <ResistSection
            title="Резисты (Enemy)"
            resistArray={data.enemyResist || []}
            onChange={(arr) => handleChange('enemyResist', arr)}
          />
          <VulnerabilitySection
            title="Уязвимости (Enemy)"
            vulnerabilityArray={data.enemyVulnerability || []}
            onChange={(arr) => handleChange('enemyVulnerability', arr)}
          />
          <ComplexEffectsSection
            title="Сложн. эффекты (Enemy)"
            complexArray={data.enemyComplexEffects || []}
            onChange={(arr) => handleChange('enemyComplexEffects', arr)}
          />
        </>
      )}
    </div>
  )
}
