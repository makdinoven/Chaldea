// SkillTreeEditor.jsx
import React, { useState, useEffect } from 'react'
import { useDispatch } from 'react-redux'
import { updateSkillFullTree } from '../../redux/actions/skillsAdminActions'
import { cloneRankAsNew, EMPTY_RANK_TEMPLATE, SKILL_TYPES } from './skillConstants'
import styles from './AdminSkillsPage.module.scss'
import RankNode from "./RankNode";

// Пример классов (вы можете загрузить динамически)
const CLASS_OPTIONS = [
  { label: "Warrior", value: "1" },
  { label: "Mage", value: "2" },
  { label: "Rogue", value: "3" },
];
// Список рас
const RACE_OPTIONS = [
  { label: "Человек", value: "1" },
  { label: "Эльф", value: "2" },
  { label: "Драконид", value: "3" },
  { label: "Дворф", value: "4" },
  { label: "Демон", value: "5" },
  { label: "Бистмен", value: "6" },
  { label: "Урук", value: "7" },
];
// Подрасы
const SUBRACE_OPTIONS = [
  { label: "Норды", value: "1", race: "1" },
  { label: "Ост", value: "2", race: "1" },
  { label: "Ориентал", value: "3", race: "1" },
  { label: "Лесной", value: "4", race: "2" },
  // ... и т.д.
];

const SkillTreeEditor = ({ skillTree, updateStatus }) => {
  const dispatch = useDispatch()
  const [localSkill, setLocalSkill] = useState({
    id: null,
    name: '',
    skill_type: 'attack',
    description: '',
    purchaseCost: 0,
    classLimitations: '',
    raceLimitations: '',
    subraceLimitations: '',
    skillImageFile: null,
    skillImagePreview: '', // base64
    ranks: [],
  })

  const [expandedRanks, setExpandedRanks] = useState(new Set())

  useEffect(() => {
    if (skillTree) {
      setLocalSkill({
        id: skillTree.id,
        name: skillTree.name || '',
        skill_type: skillTree.skill_type || 'attack',
        description: skillTree.description || '',
        purchaseCost: skillTree.purchaseCost || 0,
        classLimitations: skillTree.classLimitations || '',
        raceLimitations: skillTree.raceLimitations || '',
        subraceLimitations: skillTree.subraceLimitations || '',
        skillImageFile: null,
        skillImagePreview: '',
        ranks: skillTree.ranks || [],
      })
    }
  }, [skillTree])

  const handleSkillFieldChange = (field, value) => {
    setLocalSkill(prev => ({ ...prev, [field]: value }))
  }

  const handleSave = () => {
    const payload = {
      ...localSkill,
      // ranks: remove isNew
      ranks: localSkill.ranks.map(r => ({ ...r, isNew: undefined })),
    }
    // Здесь нужно будет передавать и файл (skillImageFile), если нужно сохранить на сервер.
    dispatch(updateSkillFullTree({ skillId: localSkill.id, payload }))
  }

  // Загрузка локального изображения навыка
  const handleSkillImageChange = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      setLocalSkill(prev => ({
        ...prev,
        skillImageFile: file,
        skillImagePreview: ev.target.result,
      }))
    }
    reader.readAsDataURL(file)
  }

  const toggleExpand = (rankId) => {
    setExpandedRanks(prev => {
      const newSet = new Set(prev)
      if (newSet.has(rankId)) newSet.delete(rankId)
      else newSet.add(rankId)
      return newSet
    })
  }

  const updateRank = (updatedRank) => {
    setLocalSkill(prev => ({
      ...prev,
      ranks: prev.ranks.map(r => (r.id === updatedRank.id ? updatedRank : r))
    }))
  }

  const deleteRank = (rankId) => {
    setLocalSkill(prev => ({
      ...prev,
      ranks: prev.ranks.filter(r => r.id !== rankId)
    }))
  }

  const addNewRank = () => {
    const newRank = { ...EMPTY_RANK_TEMPLATE }
    newRank.id = `new-${Date.now()}`
    newRank.isNew = true
    setLocalSkill(prev => ({
      ...prev,
      ranks: [...prev.ranks, newRank]
    }))
  }

  const copyRank = (rank) => {
    const newRank = cloneRankAsNew(rank)
    newRank.id = `copy-${Date.now()}`
    setLocalSkill(prev => ({
      ...prev,
      ranks: [...prev.ranks, newRank]
    }))
  }

  const findRoots = () => {
    const childIds = new Set()
    localSkill.ranks.forEach(r => {
      if (r.left_child_id) childIds.add(r.left_child_id)
      if (r.right_child_id) childIds.add(r.right_child_id)
    })
    return localSkill.ranks.filter(r => !childIds.has(r.id))
  }

  const getChildren = (rank) => {
    return localSkill.ranks.filter(r => (
      r.id !== rank.id &&
      (rank.left_child_id === r.id || rank.right_child_id === r.id)
    ))
  }

  const renderRankNodes = (rank, depth = 0) => {
    const expanded = expandedRanks.has(rank.id)
    const children = getChildren(rank)
    return (
      <RankNode
        key={rank.id}
        rank={rank}
        depth={depth}
        expanded={expanded}
        onToggleExpand={() => toggleExpand(rank.id)}
        onUpdate={updateRank}
        onDelete={deleteRank}
        onCopy={copyRank}
      >
        {children.map(child => renderRankNodes(child, depth + 1))}
      </RankNode>
    )
  }

  const roots = findRoots()

  return (
    <div className={styles.treeEditorContainer}>
      <div className={styles.editorHeader}>
        <h2 className={styles.editorTitle}>
          Навык:
          <input
            type="text"
            value={localSkill.name}
            onChange={(e) => handleSkillFieldChange('name', e.target.value)}
            className={styles.skillNameInput}
          />
        </h2>

        <div className={styles.metaControls}>
          <select
            value={localSkill.skill_type}
            onChange={(e) => handleSkillFieldChange('skill_type', e.target.value)}
            className={styles.typeSelector}
          >
            {SKILL_TYPES.map(t => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>

          <button
            onClick={handleSave}
            disabled={updateStatus === 'loading'}
            className={styles.saveButton}
          >
            {updateStatus === 'loading' ? 'Сохранение...' : 'Сохранить'}
          </button>
        </div>
      </div>

      {/* Описание навыка */}
      <textarea
        value={localSkill.description}
        onChange={(e) => handleSkillFieldChange('description', e.target.value)}
        className={styles.skillDescription}
        placeholder="Подробное описание навыка..."
      />

      {/* purchaseCost, classLimitations, raceLimitations, subraceLimitations */}
      <div className={styles.inputRow}>
        <div className={styles.inputGroup}>
          <label>Стоимость покупки (очков):</label>
          <input
            type="number"
            value={localSkill.purchaseCost || 0}
            onChange={(e) => handleSkillFieldChange('purchaseCost', +e.target.value)}
          />
        </div>
        <div className={styles.inputGroup}>
          <label>Ограничение по классу:</label>
          {/* Пример одного селекта: */}
          <select
            value={localSkill.classLimitations}
            onChange={(e) => handleSkillFieldChange('classLimitations', e.target.value)}
          >
            <option value="">(Нет)</option>
            {CLASS_OPTIONS.map(c => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </div>
      </div>
      <div className={styles.inputRow}>
        <div className={styles.inputGroup}>
          <label>Ограничение по расе:</label>
          <select
            value={localSkill.raceLimitations}
            onChange={(e) => handleSkillFieldChange('raceLimitations', e.target.value)}
          >
            <option value="">(Нет)</option>
            {RACE_OPTIONS.map(r => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </div>
        <div className={styles.inputGroup}>
          <label>Ограничение по подрассе:</label>
          <select
            value={localSkill.subraceLimitations}
            onChange={(e) => handleSkillFieldChange('subraceLimitations', e.target.value)}
          >
            <option value="">(Нет)</option>
            {SUBRACE_OPTIONS.map(sr => (
              <option key={sr.value} value={sr.value}>{sr.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Локальное изображение навыка */}
      <div className={styles.inputRow}>
        <div className={styles.inputGroup}>
          <label>Изображение навыка (локальный файл):</label>
          <input
            type="file"
            accept="image/*"
            onChange={handleSkillImageChange}
          />
          {localSkill.skillImagePreview ? (
            <img
              src={localSkill.skillImagePreview}
              alt="Навык"
              style={{ width: '100px', marginTop: '6px', border: '1px solid #ccc' }}
            />
          ) : (
            <div style={{
              width: '100px',
              height: '100px',
              background: '#444',
              marginTop: '6px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#ccc',
              borderRadius: '4px'
            }}>
              (Нет изображения)
            </div>
          )}
        </div>
      </div>

      <div className={styles.treeContainer}>
        <div className={styles.treeWrapper}>
          {roots.map(r => renderRankNodes(r))}
        </div>
        <button onClick={addNewRank} className={styles.addRankButton}>
          + Добавить новый ранг
        </button>
      </div>
    </div>
  )
}

export default SkillTreeEditor
