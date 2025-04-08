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
import BuffDebuffSection from './tabs/BuffDebuffSection'
import ResistSection from './tabs/ResistSection'
import VulnerabilitySection from './tabs/VulnerabilitySection'
import ComplexEffectsSection from './tabs/ComplexEffectsSection'
import {uploadSkillRankImage} from "../../redux/actions/skillsAdminActions.js";
import {useDispatch} from "react-redux";

/**
 * Узел (ранг) в React Flow.
 *
 * props:
 *   - id (string)         : уникальный ID узла в ReactFlow
 *   - data (object)       : данные ранга: { id, rank_name, rank_number, ..., damage_entries, effects, ... }
 *   - selected (bool)     : выделен ли узел мышью
 *   - onChangeNode(...)   : колбэк (nodeId, field, value) => void
 *   - onDeleteRank?(...)  : колбэк удаления (nodeId) => void (необязательный)
 *
 * По умолчанию свёрнуто (expanded=false).
 * При "Удалить" вызываем onDeleteRank(id) если есть.
 */
export default function NodeRankDetails({
  id,
  data,
  selected,
  onChangeNode,
  onDeleteRank
}) {
  // Свернутый по умолчанию
  const [expanded, setExpanded] = useState(false)

  // Вкладка: self / enemy
  const [activeTab, setActiveTab] = useState('self')

  // Удобная обёртка
  const handleChange = (field, value) => {
    onChangeNode(id, field, value)
  }

  const dispatch = useDispatch()

   const handleRankImageChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      onChangeNode(id, 'rank_image', ev.target.result);
      dispatch(uploadSkillRankImage({ skillRankId: data.id, file }));
    };
    reader.readAsDataURL(file);
  };


  if (!expanded) {
    // Свёрнутая «мини-карта»
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
        {/* Хэндлы */}
        <Handle
          type="target"
          position={Position.Top}
          style={{ background: '#555' }}
        />
        <Handle
          type="source"
          id="left"
          position={Position.Bottom}
          style={{ left: '20%', background: 'blue' }}
        />
        <Handle
          type="source"
          id="right"
          position={Position.Bottom}
          style={{ left: '80%', background: 'green' }}
        />

        <div>
          <strong>
            {id.toString().startsWith('temp-') ? 'Новый ранг' : `ID:${id}`} - {data.rank_name ?? 'Ранг'}
          </strong>

          <div style={{marginTop: 4}}>
            {data.rank_image? (
                <img
                    src={data.rank_image}
                alt="Rank"
                style={{
                  width: 80,
                  height: 80,
                  objectFit: 'cover',
                  borderRadius: 4
                }}
              />
            ) : (
              <div
                style={{
                  width: 80,
                  height: 80,
                  background: '#ddd',
                  borderRadius: 4,
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
        </div>
      </div>
    )
  }

  // Раскрытая форма
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
        {/* Хэндлы */}
        <Handle
            type="target"
            position={Position.Top}
            style={{
              background: '#555',
              width: '14px',
              height: '14px',
              borderRadius: '50%'
            }}
        />
        <Handle
            type="source"
            id="left"
            position={Position.Bottom}
            style={{
              left: '20%',
              background: 'blue',
              width: '14px',
              height: '14px',
              borderRadius: '50%'
            }}
        />
        <Handle
            type="source"
            id="right"
            position={Position.Bottom}
            style={{
              left: '80%',
              background: 'green',
              width: '14px',
              height: '14px',
              borderRadius: '50%'
            }}
        />

        {/* Заголовок + Кнопки (Свернуть/Удалить) */}
        <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: 8}}>
          <strong>{data.rank_name ?? 'Ранг'}</strong>
          <div style={{display: 'flex', gap: '6px'}}>
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
          <input type="file" accept="image/*" onChange={handleRankImageChange}/>
          {data.rank_image ? (
              <img src={data.rank_image} alt="Rank"
                   style={{width: 80, height: 80, borderRadius: 4, marginTop: 4}}/>
          ) : (
              <div style={{width: 80, height: 80, background: '#ddd', borderRadius: 4, marginTop: 4}}>
                (нет фото)
              </div>
          )}
        </div>

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

        {/* Ограничения */}
        <div className={styles.inputRow}>
          <div className={styles.inputGroup}>
            <label>Класс (огр.):</label>
            <select
                value={data.class_limitations ?? ''}
                onChange={(e) => handleChange('class_limitations', e.target.value)}
            >
              <option value="">(нет)</option>
              {CLASS_OPTIONS.map((c) => (
                  <option key={c.value} value={c.value}>{c.label}</option>
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
                  <option key={r.value} value={r.value}>{r.label}</option>
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
                  <option key={sr.value} value={sr.value}>{sr.label}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Только чтение: left_child_id/right_child_id */}
        <div className={styles.inputRow}>
          <div className={styles.inputGroup}>
            <label>Left child ID:</label>
            <input
                type="text"
                readOnly
                value={data.left_child_id ?? ''}
            />
          </div>
          <div className={styles.inputGroup}>
            <label>Right child ID:</label>
            <input
                type="text"
                readOnly
                value={data.right_child_id ?? ''}
            />
          </div>
        </div>

        {/* Вкладки self/enemy */}
        <div className={styles.tabButtons} style={{marginTop: 6}}>
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
