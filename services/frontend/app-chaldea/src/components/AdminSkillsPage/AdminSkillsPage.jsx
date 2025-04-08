// src/components/AdminSkillsPage/AdminSkillsPage.jsx
import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import axios from 'axios';
import {
  fetchSkills,
  fetchSkillFullTree,
  uploadSkillImage,
  updateSkillFullTree
} from '../../redux/actions/skillsAdminActions';
import { clearSelectedSkillTree } from '../../redux/slices/skillsAdminSlice';
import styles from './AdminSkillsPage.module.scss';
import FlowSkillsEditor from './FlowSkillsEditor';
import { prepareSkillPayload } from './utils/preparePayload';

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
    dispatch(uploadSkillImage({ skillId: selectedSkillTree.id, file }))
      .then(() => {
        dispatch(fetchSkills());
        dispatch(fetchSkillFullTree(selectedSkillTree.id));
      });
  };

  // Фильтр по названию навыка (регистронезависимый)
  const filteredSkills = skillsList.filter(skill =>
    skill.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleAddSkill = async () => {
    const newSkillPayload = {
      name: "Новый навык",
      skill_type: "attack",
      description: "",
    };

    try {
      const res = await axios.post('http://4452515-co41851.twc1.net:8003/skills/admin/skills/', newSkillPayload);
      dispatch(fetchSkills());
      handleSelectSkill(res.data.id);
    } catch (err) {
      console.error("Ошибка при создании навыка:", err);
      alert("Не удалось создать навык. См. консоль.");
    }
  };

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

  const handleSaveSkillTree = async () => {
    if (!selectedSkillTree) return;

    try {
      const payload = prepareSkillPayload(selectedSkillTree);
      await dispatch(updateSkillFullTree({ skillId: selectedSkillTree.id, payload })).unwrap();
      dispatch(fetchSkillFullTree(selectedSkillTree.id));
      alert('Изменения успешно сохранены!');
    } catch (err) {
      console.error("Ошибка при сохранении навыка:", err);
      alert("Произошла ошибка при сохранении. См. консоль.");
    }
  };

  return (
    <div className={styles.adminPage}>
      <h1 style={{ textAlign: 'center', marginBottom: '20px' }}>Администрирование навыков</h1>
      <div className={styles.container}>
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
                {skill.skill_image ? (
                  <img
                    src={skill.skill_image}
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
        <div className={styles.editorContainer}>
          {selectedSkillTree ? (
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
              <div style={{ marginBottom: '10px' }}>
                <button
                  style={{
                    backgroundColor: '#f44336',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '4px',
                    padding: '8px 12px',
                    cursor: 'pointer',
                    marginRight: '8px'
                  }}
                  onClick={handleDeleteSkill}
                >
                  Удалить навык
                </button>
                <div style={{ marginTop: '10px' }}>
                  <input type="file" onChange={handleSkillImageUpload} />
                  {selectedSkillTree.skill_image && (
                    <img
                      src={selectedSkillTree.skill_image}
                      alt="Skill"
                      style={{ width: '120px', marginTop: '10px', borderRadius: '4px' }}
                    />
                  )}
                </div>
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
  );
};

export default AdminSkillsPage;
