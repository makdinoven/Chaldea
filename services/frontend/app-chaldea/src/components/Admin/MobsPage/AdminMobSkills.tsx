// AdminMobSkills — select a flat list of skill IDs for a mob template (FEAT-125)
import { useState, useEffect } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { updateMobSkills, selectMobsSaving } from '../../../redux/slices/mobsSlice';
import type { MobSkillEntry } from '../../../api/mobs';
import useDebounce from '../../../hooks/useDebounce';

interface AdminMobSkillsProps {
  templateId: number;
  skills: MobSkillEntry[];
  onUpdate: () => void;
}

interface SkillInfo {
  id: number;
  name: string;
  skill_type: string;
}

const AdminMobSkills = ({ templateId, skills, onUpdate }: AdminMobSkillsProps) => {
  const dispatch = useAppDispatch();
  const saving = useAppSelector(selectMobsSaving);

  const [currentSkillIds, setCurrentSkillIds] = useState<number[]>(
    skills.map((s) => s.skill_id),
  );

  const [searchQuery, setSearchQuery] = useState('');
  const debouncedQuery = useDebounce(searchQuery);
  const [searchResults, setSearchResults] = useState<SkillInfo[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  useEffect(() => {
    setCurrentSkillIds(skills.map((s) => s.skill_id));
  }, [skills]);

  useEffect(() => {
    if (!debouncedQuery) {
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    axios
      .get<SkillInfo[]>('/skills/admin/skills/', { params: { q: debouncedQuery } })
      .then((res) => setSearchResults(Array.isArray(res.data) ? res.data : []))
      .catch(() => toast.error('Не удалось найти навыки'))
      .finally(() => setSearchLoading(false));
  }, [debouncedQuery]);

  const handleAddSkill = (skillId: number) => {
    if (currentSkillIds.includes(skillId)) return;
    setCurrentSkillIds((prev) => [...prev, skillId]);
  };

  const handleRemoveSkill = (skillId: number) => {
    setCurrentSkillIds((prev) => prev.filter((id) => id !== skillId));
  };

  const handleSave = async () => {
    try {
      await dispatch(updateMobSkills({ templateId, skillIds: currentSkillIds })).unwrap();
      onUpdate();
    } catch {
      // thunk already toasts
    }
  };

  const hasChanges = (() => {
    const original = skills.map((s) => s.skill_id).sort();
    const current = [...currentSkillIds].sort();
    if (original.length !== current.length) return true;
    return original.some((v, i) => v !== current[i]);
  })();

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em] mb-3">
          Текущие навыки ({currentSkillIds.length})
        </h3>
        {currentSkillIds.length === 0 ? (
          <p className="text-white/50 text-sm">Навыки не назначены</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {currentSkillIds.map((skillId) => {
              const entry = skills.find((s) => s.skill_id === skillId);
              return (
                <div
                  key={skillId}
                  className="flex items-center gap-2 bg-white/[0.07] rounded-full px-3 py-1.5"
                >
                  <span className="text-white text-sm">
                    {entry?.skill_name || `Навык #${skillId}`}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleRemoveSkill(skillId)}
                    className="text-site-red hover:text-white text-xs transition-colors"
                    title="Удалить"
                  >
                    &times;
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div>
        <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em] mb-3">
          Поиск навыков
        </h3>
        <input
          className="input-underline max-w-[320px] mb-3"
          placeholder="Введите название навыка..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        {searchLoading && (
          <div className="flex items-center gap-2 text-white/50 text-sm">
            <div className="w-4 h-4 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
            Поиск...
          </div>
        )}
        {searchResults.length > 0 && (
          <div className="flex flex-col gap-1 max-h-[300px] overflow-y-auto gold-scrollbar">
            {searchResults.map((skill) => {
              const isAdded = currentSkillIds.includes(skill.id);
              return (
                <div
                  key={skill.id}
                  className="flex items-center gap-2 px-3 py-2 rounded hover:bg-white/[0.07] transition-colors"
                >
                  <span className="text-white text-sm">{skill.name}</span>
                  <span className="text-white/40 text-xs">{skill.skill_type}</span>
                  <button
                    type="button"
                    onClick={() =>
                      isAdded ? handleRemoveSkill(skill.id) : handleAddSkill(skill.id)
                    }
                    className={`text-xs ml-auto px-2 py-0.5 rounded transition-colors ${
                      isAdded
                        ? 'text-site-red hover:text-white'
                        : 'text-site-blue hover:text-white'
                    }`}
                  >
                    {isAdded ? 'Убрать' : 'Добавить'}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {hasChanges && (
        <div className="pt-2">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="btn-blue !text-base !px-8 !py-2 disabled:opacity-50"
          >
            {saving ? 'Сохранение...' : 'Сохранить навыки'}
          </button>
        </div>
      )}
    </div>
  );
};

export default AdminMobSkills;
