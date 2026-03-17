import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../../redux/store';
import {
  fetchAdminSkills,
  addAdminCharacterSkill,
  removeAdminCharacterSkill,
  updateAdminSkillRank,
  selectAdminSkills,
  selectAdminDetailLoading,
} from '../../../../redux/slices/adminCharactersSlice';
import { fetchAllSkills, fetchSkillFullTree } from '../../../../api/adminCharacters';
import type { SkillInfo, SkillRank } from '../types';

interface SkillsTabProps {
  characterId: number;
}

const SkillsTab = ({ characterId }: SkillsTabProps) => {
  const dispatch = useAppDispatch();
  const skills = useAppSelector(selectAdminSkills);
  const loading = useAppSelector(selectAdminDetailLoading);

  // All available skills for adding
  const [allSkills, setAllSkills] = useState<SkillInfo[]>([]);
  const [loadingAllSkills, setLoadingAllSkills] = useState(false);

  // Ranks for selected skill (fetched via full_tree)
  const [selectedSkillRanks, setSelectedSkillRanks] = useState<SkillRank[]>([]);
  const [loadingRanks, setLoadingRanks] = useState(false);

  // Ranks cache per skill for the rank-change dropdown on existing skills
  const [skillRanksCache, setSkillRanksCache] = useState<Record<number, SkillRank[]>>({});

  // Add skill state
  const [showAddPanel, setShowAddPanel] = useState(false);
  const [selectedSkillId, setSelectedSkillId] = useState<number | ''>('');
  const [selectedRankId, setSelectedRankId] = useState<number | ''>('');

  // Delete confirmation
  const [deleteTarget, setDeleteTarget] = useState<{
    csId: number;
    skillName: string;
  } | null>(null);

  useEffect(() => {
    dispatch(fetchAdminSkills(characterId));
    loadAllSkills();
  }, [dispatch, characterId]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadAllSkills = async () => {
    if (allSkills.length > 0) return;
    setLoadingAllSkills(true);
    try {
      const data = await fetchAllSkills();
      setAllSkills(data);
    } catch {
      toast.error('Не удалось загрузить список навыков');
    } finally {
      setLoadingAllSkills(false);
    }
  };

  const handleOpenAdd = () => {
    setShowAddPanel(true);
    loadAllSkills();
  };

  const handleSkillSelect = async (skillId: number | '') => {
    setSelectedSkillId(skillId);
    setSelectedRankId('');
    setSelectedSkillRanks([]);

    if (!skillId) return;

    setLoadingRanks(true);
    try {
      const tree = await fetchSkillFullTree(skillId);
      setSelectedSkillRanks(tree.ranks);
    } catch {
      toast.error('Не удалось загрузить ранги навыка');
    } finally {
      setLoadingRanks(false);
    }
  };

  const loadRanksForSkill = async (skillId: number) => {
    if (skillRanksCache[skillId]) return;
    try {
      const tree = await fetchSkillFullTree(skillId);
      setSkillRanksCache((prev) => ({ ...prev, [skillId]: tree.ranks }));
    } catch {
      // Silently fail for rank change dropdown — it's not critical
    }
  };

  // Load ranks for all existing skills to enable rank-change dropdowns
  useEffect(() => {
    const skillIds = new Set(
      skills.map((s) => s.skill_rank.skill_id).filter((id): id is number => id != null),
    );
    skillIds.forEach((id) => loadRanksForSkill(id));
  }, [skills]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleAddSkill = async () => {
    if (!selectedRankId) return;
    await dispatch(
      addAdminCharacterSkill({ characterId, skillRankId: Number(selectedRankId) }),
    );
    setSelectedSkillId('');
    setSelectedRankId('');
    setSelectedSkillRanks([]);
    setShowAddPanel(false);
  };

  const handleRemoveSkill = async () => {
    if (!deleteTarget) return;
    await dispatch(
      removeAdminCharacterSkill({ csId: deleteTarget.csId, characterId }),
    );
    setDeleteTarget(null);
  };

  const handleRankChange = async (csId: number, newRankId: number) => {
    await dispatch(
      updateAdminSkillRank({ csId, skillRankId: newRankId, characterId }),
    );
  };

  const getSkillName = (skillId: number | null | undefined): string => {
    if (skillId == null) return 'Неизвестный навык';
    const info = allSkills.find((s) => s.id === skillId);
    return info?.name ?? 'Неизвестный навык';
  };

  if (loading && skills.length === 0) {
    return (
      <div className="flex justify-center items-center py-12">
        <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="space-y-6"
    >
      <div className="gray-bg p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="gold-text text-lg font-medium uppercase">Навыки персонажа</h3>
          <button
            className="btn-line text-sm"
            onClick={() => (showAddPanel ? setShowAddPanel(false) : handleOpenAdd())}
          >
            {showAddPanel ? 'Закрыть' : 'Добавить навык'}
          </button>
        </div>

        {/* Add skill panel */}
        <AnimatePresence>
          {showAddPanel && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="mb-4 overflow-hidden"
            >
              <div className="p-4 rounded-card bg-white/[0.04] space-y-3">
                {loadingAllSkills ? (
                  <p className="text-white/50 text-sm">Загрузка навыков...</p>
                ) : (
                  <>
                    <div className="flex flex-col gap-1">
                      <label className="text-white/60 text-xs uppercase tracking-[0.06em]">
                        Навык
                      </label>
                      <select
                        className="input-underline"
                        value={selectedSkillId}
                        onChange={(e) =>
                          handleSkillSelect(e.target.value ? Number(e.target.value) : '')
                        }
                      >
                        <option value="">Выберите навык</option>
                        {allSkills.map((skill) => (
                          <option key={skill.id} value={skill.id}>
                            {skill.name}
                          </option>
                        ))}
                      </select>
                    </div>

                    {selectedSkillId && loadingRanks && (
                      <p className="text-white/50 text-sm">Загрузка рангов...</p>
                    )}

                    {selectedSkillId && !loadingRanks && selectedSkillRanks.length > 0 && (
                      <div className="flex flex-col gap-1">
                        <label className="text-white/60 text-xs uppercase tracking-[0.06em]">
                          Ранг
                        </label>
                        <select
                          className="input-underline"
                          value={selectedRankId}
                          onChange={(e) =>
                            setSelectedRankId(e.target.value ? Number(e.target.value) : '')
                          }
                        >
                          <option value="">Выберите ранг</option>
                          {selectedSkillRanks.map((rank) => (
                            <option key={rank.id} value={rank.id}>
                              {rank.rank_name ?? `Ранг ${rank.rank_number}`} (Ур. {rank.rank_number})
                            </option>
                          ))}
                        </select>
                      </div>
                    )}

                    <button
                      className="btn-blue text-sm"
                      disabled={!selectedRankId}
                      onClick={handleAddSkill}
                    >
                      Добавить
                    </button>
                  </>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Skills list */}
        {skills.length === 0 ? (
          <p className="text-white/50 text-center py-4">Нет навыков</p>
        ) : (
          <motion.div
            initial="hidden"
            animate="visible"
            variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.03 } } }}
            className="space-y-2"
          >
            {skills.map((skill) => {
              const skillName = getSkillName(skill.skill_rank.skill_id);
              const cachedRanks = skill.skill_rank.skill_id != null
                ? skillRanksCache[skill.skill_rank.skill_id]
                : undefined;
              return (
                <motion.div
                  key={skill.id}
                  variants={{
                    hidden: { opacity: 0, y: 5 },
                    visible: { opacity: 1, y: 0 },
                  }}
                  className="flex items-center gap-4 p-3 rounded-card bg-white/[0.04] hover:bg-white/[0.07] transition-colors duration-200"
                >
                  {skill.skill_rank.rank_image && (
                    <img
                      src={skill.skill_rank.rank_image}
                      alt={skillName}
                      className="w-10 h-10 rounded-full object-cover border border-white/20 flex-shrink-0"
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-white text-sm font-medium">{skillName}</p>
                    <p className="text-white/50 text-xs">
                      {skill.skill_rank.rank_name ?? `Ранг ${skill.skill_rank.rank_number}`} (Ур. {skill.skill_rank.rank_number})
                    </p>
                  </div>

                  {/* Rank change dropdown */}
                  {cachedRanks && cachedRanks.length > 1 && (
                    <select
                      className="input-underline text-xs w-auto min-w-[140px]"
                      value={skill.skill_rank_id}
                      onChange={(e) => {
                        const newRankId = Number(e.target.value);
                        if (newRankId !== skill.skill_rank_id) {
                          handleRankChange(skill.id, newRankId);
                        }
                      }}
                    >
                      {cachedRanks.map((rank) => (
                        <option key={rank.id} value={rank.id}>
                          {rank.rank_name ?? `Ранг ${rank.rank_number}`} (Ур. {rank.rank_number})
                        </option>
                      ))}
                    </select>
                  )}

                  <button
                    className="text-site-red text-xs hover:opacity-80 transition-opacity duration-200 flex-shrink-0"
                    onClick={() =>
                      setDeleteTarget({ csId: skill.id, skillName })
                    }
                  >
                    Удалить
                  </button>
                </motion.div>
              );
            })}
          </motion.div>
        )}
      </div>

      {/* Delete skill confirmation modal */}
      <AnimatePresence>
        {deleteTarget && (
          <div className="modal-overlay" onClick={() => setDeleteTarget(null)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="gold-text text-2xl uppercase mb-4">Удаление навыка</h2>
              <p className="text-white mb-6">
                Удалить навык{' '}
                <span className="text-gold font-medium">{deleteTarget.skillName}</span> у
                персонажа?
              </p>
              <div className="flex gap-4">
                <button className="btn-blue" onClick={handleRemoveSkill}>
                  Удалить
                </button>
                <button className="btn-line" onClick={() => setDeleteTarget(null)}>
                  Отмена
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default SkillsTab;
