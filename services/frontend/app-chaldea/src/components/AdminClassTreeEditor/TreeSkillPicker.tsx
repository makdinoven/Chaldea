import { useState, useEffect } from 'react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { fetchSkills } from '../../redux/actions/skillsAdminActions';
import { X, Search } from 'react-feather';

interface SkillItem {
  id: number;
  name: string;
  skill_type: string;
  skill_image: string | null;
}

interface TreeSkillPickerProps {
  onSelect: (skill: { skill_id: number; skill_name: string; skill_type: string; skill_image: string | null }) => void;
  onClose: () => void;
  excludeSkillIds: number[];
}

const TreeSkillPicker = ({ onSelect, onClose, excludeSkillIds }: TreeSkillPickerProps) => {
  const dispatch = useAppDispatch();
  const skillsList = useAppSelector((state) => state.skills.skillsList) as SkillItem[];
  const skillsStatus = useAppSelector((state) => state.skills.status);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    if (skillsList.length === 0 && skillsStatus !== 'loading') {
      dispatch(fetchSkills() as ReturnType<typeof fetchSkills>);
    }
  }, [dispatch, skillsList.length, skillsStatus]);

  const filtered = skillsList.filter(
    (skill) =>
      !excludeSkillIds.includes(skill.id) &&
      skill.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content gold-outline gold-outline-thick w-full max-w-md max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h3 className="gold-text text-xl font-medium uppercase">
            Выбрать навык
          </h3>
          <button
            onClick={onClose}
            className="text-white/50 hover:text-site-blue transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Search */}
        <div className="relative mb-4">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30"
          />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Поиск по названию..."
            className="input-underline w-full pl-9"
            autoFocus
          />
        </div>

        {/* Skills list */}
        <div className="flex-1 overflow-y-auto gold-scrollbar space-y-1">
          {skillsStatus === 'loading' && (
            <p className="text-white/50 text-sm text-center py-4">Загрузка...</p>
          )}

          {filtered.length === 0 && skillsStatus !== 'loading' && (
            <p className="text-white/30 text-sm text-center py-4 italic">
              Навыки не найдены
            </p>
          )}

          {filtered.map((skill) => (
            <button
              key={skill.id}
              onClick={() =>
                onSelect({
                  skill_id: skill.id,
                  skill_name: skill.name,
                  skill_type: skill.skill_type,
                  skill_image: skill.skill_image,
                })
              }
              className="w-full flex items-center gap-3 p-2.5 rounded-card hover:bg-white/[0.07] transition-colors duration-200 ease-site text-left"
            >
              {skill.skill_image ? (
                <img
                  src={skill.skill_image}
                  alt={skill.name}
                  className="w-10 h-10 rounded object-cover flex-shrink-0"
                />
              ) : (
                <div className="w-10 h-10 rounded bg-white/10 flex-shrink-0" />
              )}
              <div className="min-w-0">
                <p className="text-white text-sm truncate">{skill.name}</p>
                <p className="text-white/40 text-xs">{skill.skill_type}</p>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default TreeSkillPicker;
