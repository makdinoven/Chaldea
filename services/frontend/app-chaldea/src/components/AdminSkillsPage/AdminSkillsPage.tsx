import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import axios from 'axios';
import toast from 'react-hot-toast';
import {
  fetchSkills,
  fetchSkillFullTree,
  uploadSkillImage,
  updateSkillFullTree,
} from '../../redux/actions/skillsAdminActions';
import { clearSelectedSkillTree } from '../../redux/slices/skillsAdminSlice';
import FlowSkillsEditor from './FlowSkillsEditor';
import { prepareSkillPayload } from './utils/preparePayload';

interface Skill {
  id: number;
  name: string;
  skill_type: string;
  skill_image: string | null;
}

interface SkillTree {
  id: number;
  skill_image: string | null;
  [key: string]: unknown;
}

interface SkillsState {
  skillsList: Skill[];
  selectedSkillTree: SkillTree | null;
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  updateStatus: string;
  error: string | null;
}

interface RootState {
  skills: SkillsState;
}

const AdminSkillsPage = () => {
  const dispatch = useDispatch();
  const { skillsList, selectedSkillTree, status, updateStatus, error } =
    useSelector((state: RootState) => state.skills);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    dispatch(fetchSkills() as unknown as any);
  }, [dispatch]);

  const handleSelectSkill = (skillId: number) => {
    dispatch(clearSelectedSkillTree());
    dispatch(fetchSkillFullTree(skillId) as unknown as any);
  };

  const handleSkillImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedSkillTree) return;
    (dispatch(uploadSkillImage({ skillId: selectedSkillTree.id, file }) as unknown as any) as Promise<unknown>)
      .then(() => {
        dispatch(fetchSkills() as unknown as any);
        dispatch(fetchSkillFullTree(selectedSkillTree.id) as unknown as any);
      });
  };

  const filteredSkills = skillsList.filter((skill) =>
    skill.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleAddSkill = async () => {
    const newSkillPayload = {
      name: 'Новый навык',
      skill_type: 'attack',
      description: '',
    };

    try {
      const res = await axios.post('/skills/admin/skills/', newSkillPayload);
      dispatch(fetchSkills() as unknown as any);
      handleSelectSkill(res.data.id);
    } catch (err) {
      console.error('Ошибка при создании навыка:', err);
      toast.error('Не удалось создать навык');
    }
  };

  const handleDeleteSkill = async () => {
    if (!selectedSkillTree) return;
    const skillId = selectedSkillTree.id;
    if (!window.confirm(`Вы действительно хотите удалить навык ID=${skillId}?`)) return;
    try {
      await axios.delete(`/skills/admin/skills/${skillId}`);
      dispatch(fetchSkills() as unknown as any);
      dispatch(clearSelectedSkillTree());
    } catch (err) {
      console.error('Ошибка при удалении навыка:', err);
      toast.error('Не удалось удалить навык');
    }
  };

  const handleSaveSkillTree = async () => {
    if (!selectedSkillTree) return;

    try {
      const payload = prepareSkillPayload(selectedSkillTree);
      const result = await dispatch(
        updateSkillFullTree({ skillId: selectedSkillTree.id, payload }) as unknown as any
      );
      if (result.error) throw result.error;
      dispatch(fetchSkillFullTree(selectedSkillTree.id) as unknown as any);
      toast.success('Изменения успешно сохранены!');
    } catch (err) {
      console.error('Ошибка при сохранении навыка:', err);
      toast.error('Произошла ошибка при сохранении');
    }
  };

  return (
    <div className="p-5 text-gray-700 min-h-screen bg-gray-100">
      <h1 className="text-center mb-5">Администрирование навыков</h1>
      <div className="flex gap-8">
        <div className="w-[260px] bg-[#fafafa] border border-gray-300 rounded-md p-4">
          <h2 className="text-base mb-2.5">Список навыков</h2>
          <input
            type="text"
            placeholder="Поиск навыков..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full p-1.5 mb-2.5 box-border border border-gray-300 rounded"
          />
          <button
            className="w-full bg-green-600 text-white border-none rounded py-2 px-3 mb-2.5 cursor-pointer hover:bg-green-700"
            onClick={handleAddSkill}
          >
            + Добавить навык
          </button>
          {status === 'loading' && <p>Загрузка...</p>}
          {status === 'failed' && (
            <p className="text-red-500">Ошибка: {error}</p>
          )}
          <div className="mt-2.5">
            {filteredSkills.map((skill) => (
              <button
                key={skill.id}
                className="w-full p-2.5 mb-2.5 bg-white border border-gray-300 rounded-md text-gray-700 cursor-pointer transition-colors hover:bg-gray-200 flex items-center"
                onClick={() => handleSelectSkill(skill.id)}
              >
                {skill.skill_image ? (
                  <img
                    src={skill.skill_image}
                    alt="skill"
                    className="w-10 h-10 object-cover rounded mr-2"
                  />
                ) : (
                  <div className="w-10 h-10 bg-gray-300 rounded mr-2 inline-block" />
                )}
                <span>{skill.name}</span>
                <span className="text-gray-400 ml-2">({skill.skill_type})</span>
              </button>
            ))}
          </div>
        </div>
        <div className="flex-1">
          {selectedSkillTree ? (
            <div className="flex flex-col h-full">
              <div className="mb-2.5">
                <button
                  className="bg-red-500 text-white border-none rounded py-2 px-3 cursor-pointer mr-2 hover:bg-red-600"
                  onClick={handleDeleteSkill}
                >
                  Удалить навык
                </button>
                <div className="mt-2.5">
                  <input type="file" onChange={handleSkillImageUpload} />
                  {selectedSkillTree.skill_image && (
                    <img
                      src={selectedSkillTree.skill_image}
                      alt="Skill"
                      className="w-[120px] mt-2.5 rounded"
                    />
                  )}
                </div>
              </div>
              <div className="flex-1">
                <FlowSkillsEditor
                  skillTree={selectedSkillTree}
                  updateStatus={updateStatus}
                />
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
