// src/components/AdminSkillsPage/AdminSkillsPage.jsx
import React, { useEffect, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import axios from 'axios'
import { fetchSkills, fetchSkillFullTree } from '../../redux/actions/skillsAdminActions'
import { clearSelectedSkillTree } from '../../redux/slices/skillsAdminSlice'
import styles from './AdminSkillsPage.module.scss'
import FlowSkillsEditor from './FlowSkillsEditor'

const AdminSkillsPage = () => {
  const dispatch = useDispatch()
  const { skillsList, selectedSkillTree, status, updateStatus, error } = useSelector(state => state.skills)

  // Поисковая строка для списка навыков
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    dispatch(fetchSkills())
  }, [dispatch])

  // Выбор навыка
  const handleSelectSkill = (skillId) => {
    dispatch(clearSelectedSkillTree())
    dispatch(fetchSkillFullTree(skillId))
  }

  // Фильтр по названию (регистронезависимый)
  const filteredSkills = skillsList.filter(skill =>
    skill.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  // -----------------------------
  // Кнопка удаления навыка
  // -----------------------------
  const handleDeleteSkill = async () => {
    if (!selectedSkillTree) return
    const skillId = selectedSkillTree.id
    // Подтверждение удаления
    if (!window.confirm(`Вы действительно хотите удалить навык ID=${skillId}?`)) {
      return
    }
    try {
      // DELETE запрос
      await axios.delete(`http://localhost:8003/skills/admin/skills/${skillId}`)
      // Обновляем список навыков, сбрасываем выделенный
      dispatch(fetchSkills())
      dispatch(clearSelectedSkillTree())
    } catch (err) {
      console.error('Ошибка при удалении навыка:', err)
      alert('Не удалось удалить навык. См. консоль.')
    }
  }

  return (
    <div className={styles.adminPage}>
      <h1 style={{ textAlign: 'center', marginBottom: '20px' }}>Администрирование навыков</h1>
      <div className={styles.container}>

        {/* Левая панель (список навыков) */}
        <div className={styles.sidebar}>
          <h2>Список навыков</h2>

          <input
            type="text"
            placeholder="Поиск навыков..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: '100%',
              padding: '6px',
              marginBottom: '10px',
              boxSizing: 'border-box'
            }}
          />

          {status === 'loading' && <p>Загрузка...</p>}
          {status === 'failed' && <p style={{ color: 'red' }}>Ошибка: {error}</p>}

          <div className={styles.skillsList}>
            {filteredSkills.map(skill => (
              <button
                key={skill.id}
                className={styles.skillButton}
                onClick={() => handleSelectSkill(skill.id)}
              >
                {/* Отображение картинки навыка (или заливка) */}
                {skill.skill_image_preview ? (
                  <img
                    src={skill.skill_image_preview}
                    alt="skill"
                    style={{
                      width: '40px',
                      height: '40px',
                      objectFit: 'cover',
                      borderRadius: '4px',
                      marginRight: '8px'
                    }}
                  />
                ) : (
                  <div
                    style={{
                      width: '40px',
                      height: '40px',
                      background: '#ddd',
                      borderRadius: '4px',
                      marginRight: '8px',
                      display: 'inline-block'
                    }}
                  />
                )}

                <span>{skill.name}</span>
                <span style={{ color: '#999', marginLeft: '8px' }}>({skill.skill_type})</span>
              </button>
            ))}
          </div>
        </div>

        {/* Правая область (FlowSkillsEditor) */}
        <div className={styles.editorContainer}>
          {selectedSkillTree ? (
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
              {/* Кнопка удаления навыка */}
              <div style={{ marginBottom: '10px' }}>
                <button
                  style={{
                    backgroundColor: '#f44336',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '4px',
                    padding: '8px 12px',
                    cursor: 'pointer'
                  }}
                  onClick={handleDeleteSkill}
                >
                  Удалить навык
                </button>
              </div>

              <div style={{ flex: '1' }}>
                <FlowSkillsEditor skillTree={selectedSkillTree} updateStatus={updateStatus} />
              </div>
            </div>
          ) : (
            <p>Выберите навык для редактирования</p>
          )}
        </div>
      </div>
    </div>
  )
}

export default AdminSkillsPage
