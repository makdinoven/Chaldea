// src/components/AdminSkillsPage/AdminSkillsPage.jsx
import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import axios from 'axios';
import { fetchSkills, fetchSkillFullTree, uploadSkillImage } from '../../redux/actions/skillsAdminActions';
import { clearSelectedSkillTree } from '../../redux/slices/skillsAdminSlice';
import styles from './AdminSkillsPage.module.scss';
import FlowSkillsEditor from './FlowSkillsEditor';

const AdminSkillsPage = () => {
  const dispatch = useDispatch();
  const { skillsList, selectedSkillTree, status, updateStatus, error } = useSelector(state => state.skills);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    dispatch(fetchSkills());
  }, [dispatch]);

  const handleSelectSkill = (skillId) => {
    dispatch(clearSelectedSkillTree());
    dispatch(fetchSkillFullTree(skillId));
  };

  const handleSkillImageUpload = (e) => {
  const file = e.target.files[0];
  if (!file || !selectedSkillTree) return;
  dispatch(uploadSkillImage({ skillId: selectedSkillTree.id, file }));
};

  // Фильтр по названию навыка (регистронезависимый)
  const filteredSkills = skillsList.filter(skill =>
    skill.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Добавление нового навыка (POST /admin/skills/)
  const handleAddSkill = async () => {
    const newSkillPayload = {
      name: "Новый навык",
      skill_type: "attack",
      description: "",
    };

    try {
      const res = await axios.post('http://4452515-co41851.twc1.net:8003/skills/admin/skills/', newSkillPayload);
      // После создания обновляем список навыков и выбираем новый навык
      dispatch(fetchSkills());
      // Если необходимо сразу выбрать созданный навык, можно вызвать fetchSkillFullTree с новым id:
      handleSelectSkill(res.data.id);
    } catch (err) {
      console.error("Ошибка при создании навыка:", err);
      alert("Не удалось создать навык. См. консоль.");
    }
  };

  // Удаление выбранного навыка
  const handleDeleteSkill = async () => {
    if (!selectedSkillTree) return;
    const skillId = selectedSkillTree.id;
    if (!window.confirm(`Вы действительно хотите удалить навык ID=${skillId}?`)) return;
    try {
      await axios.delete(`http://4452515-co41851.twc1.net:8003/skills/admin/skills/${skillId}`);
      dispatch(fetchSkills());
      dispatch(clearSelectedSkillTree());
    } catch (err) {
      console.error("Ошибка при удалении навыка:", err);
      alert("Не удалось удалить навык. См. консоль.");
    }
  };

  return (
    <div className={styles.adminPage}>
      <h1 style={{ textAlign: 'center', marginBottom: '20px' }}>Администрирование навыков</h1>
      <div className={styles.container}>
        {/* Левая панель – список навыков и кнопки управления */}
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
          <button
            style={{
              backgroundColor: '#4CAF50',
              color: '#fff',
              border: 'none',
              borderRadius: '4px',
              padding: '8px 12px',
              marginBottom: '10px',
              cursor: 'pointer',
              width: '100%'
            }}
            onClick={handleAddSkill}
          >
            + Добавить навык
          </button>
          {status === 'loading' && <p>Загрузка...</p>}
          {status === 'failed' && <p style={{ color: 'red' }}>Ошибка: {error}</p>}
          <div className={styles.skillsList}>
            {filteredSkills.map(skill => (
              <button
                key={skill.id}
                className={styles.skillButton}
                onClick={() => handleSelectSkill(skill.id)}
              >
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

        {/* Правая панель – редактор навыка */}
        <div className={styles.editorContainer}>
          {selectedSkillTree ? (
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
              <div style={{marginBottom: '10px'}}>
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
                <div style={{marginBottom: '10px'}}>
                  <input type="file" onChange={handleSkillImageUpload}/>
                  {selectedSkillTree.skill_image && (
                      <img
                          src={selectedSkillTree.skill_image}
                          alt="Skill"
                          style={{width: '120px', marginTop: '10px', borderRadius: '4px'}}
                      />
                  )}
                </div>
              </div>
              <div style={{flex: '1'}}>
                <FlowSkillsEditor skillTree={selectedSkillTree} updateStatus={updateStatus}/>
              </div>
            </div>
          ) : (
              <p>Выберите навык для редактирования</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default AdminSkillsPage;
