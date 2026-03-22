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
  type: string;
  skill_ranks?: SkillRank[];
}

interface SkillRank {
  id: number;
  name: string;
  rank: number;
}

interface SkillFullTree {
  id: number;
  name: string;
  type: string;
  ranks: SkillRank[];
}

const AdminMobSkills = ({ templateId, skills, onUpdate }: AdminMobSkillsProps) => {
  const dispatch = useAppDispatch();
  const saving = useAppSelector(selectMobsSaving);

  const [currentSkillRankIds, setCurrentSkillRankIds] = useState<number[]>(
    skills.map((s) => s.skill_rank_id),
  );

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const debouncedQuery = useDebounce(searchQuery);
  const [searchResults, setSearchResults] = useState<SkillInfo[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // Expanded skill (to show ranks)
  const [expandedSkill, setExpandedSkill] = useState<SkillFullTree | null>(null);
  const [loadingTree, setLoadingTree] = useState(false);

  useEffect(() => {
    setCurrentSkillRankIds(skills.map((s) => s.skill_rank_id));
  }, [skills]);

  useEffect(() => {
    if (!debouncedQuery) {
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    axios.get<SkillInfo[]>('/skills/admin/skills/', { params: { q: debouncedQuery } })
      .then((res) => setSearchResults(Array.isArray(res.data) ? res.data : []))
      .catch(() => toast.error('Не удалось найти навыки'))
      .finally(() => setSearchLoading(false));
  }, [debouncedQuery]);

  const handleExpandSkill = async (skillId: number) => {
    if (expandedSkill?.id === skillId) {
      setExpandedSkill(null);
      return;
    }
    setLoadingTree(true);
    try {
      const res = await axios.get<SkillFullTree>(`/skills/admin/skills/${skillId}/full_tree`);
      setExpandedSkill(res.data);
    } catch {
      toast.error('Не удалось загрузить ранги навыка');
    } finally {
      setLoadingTree(false);
    }
  };

  const handleAddRank = (rankId: number) => {
    if (currentSkillRankIds.includes(rankId)) return;
    setCurrentSkillRankIds((prev) => [...prev, rankId]);
  };

  const handleRemoveRank = (rankId: number) => {
    setCurrentSkillRankIds((prev) => prev.filter((id) => id !== rankId));
  };

  const handleSave = async () => {
    try {
      await dispatch(updateMobSkills({ templateId, skillRankIds: currentSkillRankIds })).unwrap();
      onUpdate();
    } catch {
      // Error already shown by thunk
    }
  };

  const hasChanges = (() => {
    const original = skills.map((s) => s.skill_rank_id).sort();
    const current = [...currentSkillRankIds].sort();
    if (original.length !== current.length) return true;
    return original.some((v, i) => v !== current[i]);
  })();

  return (
    <div className="flex flex-col gap-5">
      {/* Current skills */}
      <div>
        <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em] mb-3">
          Текущие навыки ({currentSkillRankIds.length})
        </h3>
        {currentSkillRankIds.length === 0 ? (
          <p className="text-white/50 text-sm">Навыки не назначены</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {currentSkillRankIds.map((rankId) => {
              const skillEntry = skills.find((s) => s.skill_rank_id === rankId);
              return (
                <div
                  key={rankId}
                  className="flex items-center gap-2 bg-white/[0.07] rounded-full px-3 py-1.5"
                >
                  <span className="text-white text-sm">
                    {skillEntry?.skill_name || `Ранг #${rankId}`}
                    {skillEntry?.rank_name && (
                      <span className="text-white/50 ml-1">({skillEntry.rank_name})</span>
                    )}
                  </span>
                  <button
                    onClick={() => handleRemoveRank(rankId)}
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

      {/* Search */}
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
            {searchResults.map((skill) => (
              <div key={skill.id} className="flex flex-col">
                <button
                  onClick={() => handleExpandSkill(skill.id)}
                  className="flex items-center gap-2 px-3 py-2 rounded hover:bg-white/[0.07] transition-colors text-left"
                >
                  <span className="text-white text-sm">{skill.name}</span>
                  <span className="text-white/40 text-xs">{skill.type}</span>
                  <span className="text-white/30 text-xs ml-auto">
                    {expandedSkill?.id === skill.id ? '▼' : '▶'}
                  </span>
                </button>

                {/* Expanded ranks */}
                {expandedSkill?.id === skill.id && (
                  <div className="pl-6 flex flex-col gap-1 py-1">
                    {loadingTree ? (
                      <span className="text-white/50 text-xs">Загрузка...</span>
                    ) : (
                      expandedSkill.ranks?.map((rank) => {
                        const isAdded = currentSkillRankIds.includes(rank.id);
                        return (
                          <div
                            key={rank.id}
                            className="flex items-center gap-2 px-2 py-1"
                          >
                            <span className="text-white/70 text-sm">
                              {rank.name || `Ранг ${rank.rank}`}
                            </span>
                            <span className="text-white/40 text-xs">ID: {rank.id}</span>
                            <button
                              onClick={() => isAdded ? handleRemoveRank(rank.id) : handleAddRank(rank.id)}
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
                      })
                    )}
                    {!loadingTree && (!expandedSkill.ranks || expandedSkill.ranks.length === 0) && (
                      <span className="text-white/50 text-xs">Ранги не найдены</span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Save button */}
      {hasChanges && (
        <div className="pt-2">
          <button
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
