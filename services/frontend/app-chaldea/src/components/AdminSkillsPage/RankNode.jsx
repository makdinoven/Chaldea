// RankNode.jsx
import React, { useState } from 'react'
import { ChevronRight, ChevronDown } from 'react-feather'
import styles from './AdminSkillsPage.module.scss'
import { cloneRankAsNew } from './skillConstants'

import DamageSection from './tabs/DamageSection'
import BuffDebuffSection from './tabs/BuffDebuffSection'
import ResistSection from './tabs/ResistSection'
import VulnerabilitySection from './tabs/VulnerabilitySection'
import ComplexEffectsSection from './tabs/ComplexEffectsSection'

// Те же самые опции для классов/рас/подрас
const CLASS_OPTIONS = [
  { label: "Warrior", value: "1" },
  { label: "Mage", value: "2" },
  { label: "Rogue", value: "3" },
];
const RACE_OPTIONS = [
  { label: "Человек", value: "1" },
  { label: "Эльф", value: "2" },
  { label: "Драконид", value: "3" },
  { label: "Дворф", value: "4" },
  { label: "Демон", value: "5" },
  { label: "Бистмен", value: "6" },
  { label: "Урук", value: "7" },
];
const SUBRACE_OPTIONS = [
  { label: "Норды", value: "1", race: "1" },
  { label: "Ост", value: "2", race: "1" },
  { label: "Ориентал", value: "3", race: "1" },
  { label: "Лесной", value: "4", race: "2" },
  { label: "Тёмный", value: "5", race: "2" },
  { label: "Малах", value: "6", race: "2" },
  { label: "Равагарт", value: "7", race: "3" },
  { label: "Рорис", value: "8", race: "3" },
  { label: "Ониксовый", value: "9", race: "4" },
  { label: "Левиафан", value: "10", race: "4" },
  { label: "Альб", value: "11", race: "5" },
  { label: "Зверолюд", value: "12", race: "5" },
  { label: "Полукровка", value: "13", race: "6" },
  { label: "Северный", value: "14", race: "6" },
  { label: "Темный", value: "15", race: "7" },
  { label: "Золотой", value: "16", race: "7" },

];

const RankNode = ({
  rank,
  depth,
  expanded,
  onToggleExpand,
  onUpdate,
  onDelete,
  onCopy,
  children,
}) => {
  const [activeTab, setActiveTab] = useState("self")

  const handleFieldChange = (field, value) => {
    onUpdate({ ...rank, [field]: value })
  }

  const handleRankImageChange = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      onUpdate({
        ...rank,
        rankImageFile: file,
        rankImagePreview: ev.target.result,
      })
    }
    reader.readAsDataURL(file)
  }

  return (
    <div
      className={styles.rankNode}
      style={{
        marginLeft: depth * 30,
        borderLeft: '2px dashed #999',
        paddingLeft: '10px'
      }}
    >
      <div className={styles.rankHeader} onClick={onToggleExpand}>
        {children && children.length > 0 && (
          <span className={styles.expandIcon}>
            {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </span>
        )}
        <span className={styles.rankTitle}>Ранг #{rank.rank_number}</span>
        <div className={styles.rankHeaderActions}>
          <button
            onClick={(e) => {
              e.stopPropagation()
              onCopy(rank)
            }}
            className={styles.copyButton}
          >
            Копировать
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation()
              onDelete(rank.id)
            }}
            className={styles.deleteButton}
          >
            Удалить
          </button>
        </div>
      </div>

      {expanded && (
        <div className={styles.rankContent}>

          {/* Изображение ранга (локальный файл) */}
          <div className={styles.inputGroup}>
            <label>Изображение ранга (лок.файл):</label>
            <input
              type="file"
              accept="image/*"
              onChange={handleRankImageChange}
            />
            {rank.rankImagePreview ? (
              <img
                src={rank.rankImagePreview}
                alt="Rang"
                style={{ width: '90px', marginTop: '6px', border: '1px solid #ccc' }}
              />
            ) : (
              <div style={{
                width: '90px', height: '90px', background: '#444',
                marginTop: '6px', borderRadius: '4px',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#ccc'
              }}>
                (Нет изображения)
              </div>
            )}
          </div>

          {/* Базовые поля */}
          <div className={styles.basicFields}>
            <div className={styles.inputGroup}>
              <label>Уровень ранга:</label>
              <input
                type="number"
                value={rank.rank_number}
                onChange={(e) => handleFieldChange('rank_number', +e.target.value)}
              />
            </div>
            <div className={styles.inputGroup}>
              <label>Треб. уровень перса:</label>
              <input
                type="number"
                value={rank.level_requirement}
                onChange={(e) => handleFieldChange('level_requirement', +e.target.value)}
              />
            </div>
            <div className={styles.inputGroup}>
              <label>Описание ранга:</label>
              <textarea
                value={rank.rank_description || ""}
                onChange={(e) => handleFieldChange('rank_description', e.target.value)}
              />
            </div>
          </div>

          {/* Ограничения для ранга (селекты) */}
          <div className={styles.inputRow}>
            <div className={styles.inputGroup}>
              <label>Ограничение (класс):</label>
              <select
                value={rank.class_limitations || ""}
                onChange={(e) => handleFieldChange('class_limitations', e.target.value)}
              >
                <option value="">(Нет)</option>
                {CLASS_OPTIONS.map(c => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
            </div>
            <div className={styles.inputGroup}>
              <label>Ограничение (раса):</label>
              <select
                value={rank.race_limitations || ""}
                onChange={(e) => handleFieldChange('race_limitations', e.target.value)}
              >
                <option value="">(Нет)</option>
                {RACE_OPTIONS.map(r => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>
            <div className={styles.inputGroup}>
              <label>Ограничение (подраса):</label>
              <select
                value={rank.subrace_limitations || ""}
                onChange={(e) => handleFieldChange('subrace_limitations', e.target.value)}
              >
                <option value="">(Нет)</option>
                {SUBRACE_OPTIONS.map(sr => (
                  <option key={sr.value} value={sr.value}>{sr.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Две вкладки: self / enemy */}
          <div className={styles.tabButtons}>
            <button
              className={activeTab === "self" ? styles.activeTab : ""}
              onClick={() => setActiveTab("self")}
            >
              Для себя
            </button>
            <button
              className={activeTab === "enemy" ? styles.activeTab : ""}
              onClick={() => setActiveTab("enemy")}
            >
              Для врага
            </button>
          </div>

          {activeTab === "self" && (
            <>
              <DamageSection
                title="Колич. урон (Self)"
                damageArray={rank.selfDamage}
                onChange={(arr) => handleFieldChange('selfDamage', arr)}
              />
              <BuffDebuffSection
                title="Бафф/дебафф урона (Self)"
                buffArray={rank.selfDamageBuff}
                onChange={(arr) => handleFieldChange('selfDamageBuff', arr)}
              />
              <ResistSection
                title="Бафф/дебафф резистов (Self)"
                resistArray={rank.selfResist}
                onChange={(arr) => handleFieldChange('selfResist', arr)}
              />
              <VulnerabilitySection
                title="Уязвимости (Self)"
                vulnerabilityArray={rank.selfVulnerability}
                onChange={(arr) => handleFieldChange('selfVulnerability', arr)}
              />
              <ComplexEffectsSection
                title="Сложные эффекты (Self)"
                complexArray={rank.selfComplexEffects}
                onChange={(arr) => handleFieldChange('selfComplexEffects', arr)}
                side="self"
              />
            </>
          )}

          {activeTab === "enemy" && (
            <>
              <DamageSection
                title="Колич. урон (Enemy)"
                damageArray={rank.enemyDamage}
                onChange={(arr) => handleFieldChange('enemyDamage', arr)}
              />
              <BuffDebuffSection
                title="Бафф/дебафф урона (Enemy)"
                buffArray={rank.enemyDamageBuff}
                onChange={(arr) => handleFieldChange('enemyDamageBuff', arr)}
              />
              <ResistSection
                title="Бафф/дебафф резистов (Enemy)"
                resistArray={rank.enemyResist}
                onChange={(arr) => handleFieldChange('enemyResist', arr)}
              />
              <VulnerabilitySection
                title="Уязвимости (Enemy)"
                vulnerabilityArray={rank.enemyVulnerability}
                onChange={(arr) => handleFieldChange('enemyVulnerability', arr)}
              />
              <ComplexEffectsSection
                title="Сложные эффекты (Enemy)"
                complexArray={rank.enemyComplexEffects}
                onChange={(arr) => handleFieldChange('enemyComplexEffects', arr)}
                side="enemy"
              />
            </>
          )}

          {children && children.map(child => child)}
        </div>
      )}
    </div>
  )
}

export default RankNode
