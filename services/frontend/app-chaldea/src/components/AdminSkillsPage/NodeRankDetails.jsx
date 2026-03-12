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
import BuffDebuffSection from './tabs/BuffDebuffSection.jsx'
import ResistSection from './tabs/ResistSection'
import ComplexEffectsSection from './tabs/ComplexEffectsSection'
import StatModifierSection from "./tabs/StatModifierSection.jsx";
import { useDispatch } from "react-redux";
import axios from "axios";

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
  const file = e.target.files?.[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('skill_rank_id', data.id);
  formData.append('file', file);

  axios.post('/photo/change_skill_rank_image', formData)
    .then(res => {
       // Обновляем поле rank_image URL'ом, полученным от сервера
       onChangeNode(id, 'rank_image', res.data.image_url);
    })
    .catch(error => {
       console.error("Ошибка при загрузке картинки:", error);
    });
};


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
    // Внешняя оболочка, которая не скрывает содержимое (overflow: visible)
    <div
      style={{
        position: 'relative',
        width: 100,
        height: 120, // немного увеличили высоту, чтобы сверху было место для названия
        cursor: 'pointer',
      }}
      onClick={() => setExpanded(true)}
    >
      {/* Элемент для названия, абсолютно позиционированный сверху */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          textAlign: 'center',
          fontWeight: 'bold',
          zIndex: 3, // выше остальных элементов
          // Дополнительные стили, чтобы текст не обрезался
          whiteSpace: 'nowrap',
          overflow: 'visible'
        }}
      >
        {data.rank_name || `ID: ${id}`}
      </div>

      {/* Контейнер-круг, в котором будет изображение */}
      <div
        style={{
          position: 'absolute',
          top: 20, // смещаем вниз, чтобы под сверху было название
          left: 0,
          width: 100,
          height: 100,
          borderRadius: '50%',
          border: '1px solid #ccc',
          overflow: 'hidden', // здесь обрезается только фон
          background: data.rank_image
                      ? `url(${data.rank_image}) center/cover no-repeat`
                      : '#ddd'
        }}
      />

      {/* Handle для входящих соединений – отображается поверх всего */}
      <Handle
        type="target"
        position={Position.Left}
        style={{
          top: '50%',
          left: -8,
          transform: 'translateY(-50%)',
          zIndex: 4, // выше всего
          background: '#555',
        }}
      />
      {/* Handle для исходящих соединений "left" */}
      <Handle
        type="source"
        id="left"
        position={Position.Right}
        style={{
          top: '40%',
          right: -8,
          transform: 'translateY(-50%)',
          zIndex: 4,
          background: 'blue',
        }}
      />
      {/* Handle для исходящих соединений "right" */}
      <Handle
        type="source"
        id="right"
        position={Position.Right}
        style={{
          top: '60%',
          right: -8,
          transform: 'translateY(-50%)',
          zIndex: 4,
          background: 'green',
        }}
      />
    </div>
  );
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
          <StatModifierSection
          title="Стат‑модификаторы (Self)"
          modsArray={data.selfStatMods || []}
          onChange={(arr) => handleChange("selfStatMods", arr)}
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
          <StatModifierSection
              title="Стат‑модификаторы (Enemy)"
              modsArray={data.enemyStatMods || []}
              onChange={(arr) => handleChange("enemyStatMods", arr)}
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
