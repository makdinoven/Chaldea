// AdminSkillsPage — perk system (FEAT-125)
import { useEffect, useState, type ChangeEvent } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchSkills,
  fetchSkillAdmin,
  uploadSkillImage,
} from '../../redux/actions/skillsAdminActions';
import { clearSelectedSkill } from '../../redux/slices/skillsAdminSlice';
import PerkPoolEditor from './PerkPoolEditor';
import SkillBaseEditor from './SkillBaseEditor';

const extractError = (err: unknown, fallback: string): string => {
  const e = err as { response?: { data?: { detail?: string } }; message?: string };
  return e.response?.data?.detail || e.message || fallback;
};

const AdminSkillsPage = () => {
  const dispatch = useAppDispatch();
  const { skillsList, selectedSkill, status, error } = useAppSelector(
    (state) => state.skills
  );
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    dispatch(fetchSkills());
  }, [dispatch]);

  const handleSelectSkill = (skillId: number) => {
    dispatch(clearSelectedSkill());
    dispatch(fetchSkillAdmin(skillId));
  };

  const refreshSelected = () => {
    if (selectedSkill) dispatch(fetchSkillAdmin(selectedSkill.id));
  };

  const handleSkillImageUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedSkill) return;
    try {
      await dispatch(uploadSkillImage({ skillId: selectedSkill.id, file })).unwrap();
      dispatch(fetchSkills());
      dispatch(fetchSkillAdmin(selectedSkill.id));
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Ошибка загрузки изображения');
    }
  };

  const filteredSkills = skillsList.filter((s) =>
    s.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleAddSkill = async () => {
    const baseName = 'Новый навык';
    const existingNames = new Set(skillsList.map((s) => s.name));
    let newName = baseName;
    if (existingNames.has(newName)) {
      let counter = 2;
      while (existingNames.has(`${baseName} (${counter})`)) counter++;
      newName = `${baseName} (${counter})`;
    }
    try {
      const res = await axios.post('/skills/admin/skills/', {
        name: newName,
        skill_type: 'attack',
        description: '',
      });
      dispatch(fetchSkills());
      handleSelectSkill(res.data.id);
    } catch (err) {
      toast.error(extractError(err, 'Не удалось создать навык'));
    }
  };

  const handleDeleteSkill = async () => {
    if (!selectedSkill) return;
    if (!window.confirm(`Удалить навык "${selectedSkill.name}"?`)) return;
    try {
      await axios.delete(`/skills/admin/skills/${selectedSkill.id}`);
      toast.success('Навык удалён');
      dispatch(fetchSkills());
      dispatch(clearSelectedSkill());
    } catch (err) {
      toast.error(extractError(err, 'Не удалось удалить навык'));
    }
  };

  return (
    <div className="p-3 sm:p-5 min-h-screen text-white">
      <h1 className="gold-text text-center text-xl sm:text-2xl font-medium uppercase mb-5">
        Администрирование навыков
      </h1>
      <div className="flex flex-col lg:flex-row gap-4 lg:gap-6">
        {/* Sidebar */}
        <aside className="w-full lg:w-[260px] flex-shrink-0 rounded-card border border-white/10 bg-white/[0.03] p-3">
          <h2 className="text-white/80 text-sm font-medium mb-2">Список навыков</h2>
          <input
            type="text"
            placeholder="Поиск навыков..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="gray-bg w-full rounded-sm px-2 py-1.5 text-sm text-white mb-2"
          />
          <button
            type="button"
            className="btn-blue w-full py-1.5 text-sm mb-2"
            onClick={handleAddSkill}
          >
            + Добавить навык
          </button>
          {status === 'loading' && <p className="text-white/50 text-xs">Загрузка...</p>}
          {status === 'failed' && error && (
            <p className="text-red-400 text-xs">Ошибка: {error}</p>
          )}
          <div className="mt-2 space-y-1.5 max-h-[50vh] lg:max-h-[70vh] overflow-y-auto gold-scrollbar">
            {filteredSkills.map((skill) => (
              <button
                key={skill.id}
                type="button"
                className={`w-full flex items-center gap-2 p-2 rounded-sm border text-left text-sm transition-colors ${
                  selectedSkill?.id === skill.id
                    ? 'border-gold/60 bg-gold/10'
                    : 'border-white/10 bg-white/[0.02] hover:bg-white/[0.06]'
                }`}
                onClick={() => handleSelectSkill(skill.id)}
              >
                {skill.skill_image ? (
                  <img src={skill.skill_image} alt="" className="w-8 h-8 rounded-sm object-cover" />
                ) : (
                  <div className="w-8 h-8 bg-white/10 rounded-sm" />
                )}
                <span className="flex-1 truncate text-white">{skill.name}</span>
                <span className="text-white/40 text-[10px]">{skill.skill_type}</span>
              </button>
            ))}
          </div>
        </aside>

        {/* Editor */}
        <main className="flex-1 min-w-0">
          {selectedSkill ? (
            <div className="space-y-4">
              <div className="rounded-card border border-white/10 bg-white/[0.03] p-3 sm:p-4">
                <div className="flex items-start gap-3 flex-wrap">
                  {selectedSkill.skill_image && (
                    <img
                      src={selectedSkill.skill_image}
                      alt={selectedSkill.name}
                      className="w-16 h-16 rounded-sm object-cover"
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <h2 className="gold-text text-lg sm:text-xl font-medium">
                      {selectedSkill.name}
                    </h2>
                    <p className="text-white/60 text-xs">
                      Тип: {selectedSkill.skill_type} · Стоимость: {selectedSkill.purchase_cost}
                    </p>
                  </div>
                  <div className="flex gap-2 flex-wrap">
                    <label className="btn-line px-3 py-1.5 text-xs cursor-pointer">
                      Загрузить изображение
                      <input
                        type="file"
                        onChange={handleSkillImageUpload}
                        className="hidden"
                      />
                    </label>
                    <button
                      type="button"
                      onClick={handleDeleteSkill}
                      className="btn-line px-3 py-1.5 text-xs text-red-400 border-red-400/50"
                    >
                      Удалить навык
                    </button>
                  </div>
                </div>
              </div>

              <SkillBaseEditor skill={selectedSkill} onRefresh={refreshSelected} />
              <PerkPoolEditor skill={selectedSkill} onRefresh={refreshSelected} />
            </div>
          ) : (
            <p className="text-white/50 italic">Выберите навык для редактирования</p>
          )}
        </main>
      </div>
    </div>
  );
};

export default AdminSkillsPage;
