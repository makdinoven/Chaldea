// SkillsTab — admin character skills (perk system, FEAT-125)
import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../../redux/store';
import {
  fetchAdminSkills,
  addAdminCharacterSkill,
  removeAdminCharacterSkill,
  updateAdminSkillLevel,
  selectAdminSkills,
  selectAdminDetailLoading,
} from '../../../../redux/slices/adminCharactersSlice';
import { fetchAllSkills } from '../../../../api/adminCharacters';
import type { SkillInfo } from '../types';

interface SkillsTabProps {
  characterId: number;
}

const LEVELS = [0, 1, 2, 3, 4];

const SkillsTab = ({ characterId }: SkillsTabProps) => {
  const dispatch = useAppDispatch();
  const skills = useAppSelector(selectAdminSkills);
  const loading = useAppSelector(selectAdminDetailLoading);

  const [allSkills, setAllSkills] = useState<SkillInfo[]>([]);
  const [loadingAllSkills, setLoadingAllSkills] = useState(false);
  const [showAddPanel, setShowAddPanel] = useState(false);
  const [selectedSkillId, setSelectedSkillId] = useState<number | ''>('');
  const [deleteTarget, setDeleteTarget] = useState<{ csId: number; skillName: string } | null>(null);

  useEffect(() => {
    dispatch(fetchAdminSkills(characterId));
  }, [dispatch, characterId]);

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

  const handleAddSkill = async () => {
    if (!selectedSkillId) return;
    await dispatch(addAdminCharacterSkill({ characterId, skillId: Number(selectedSkillId) }));
    setSelectedSkillId('');
    setShowAddPanel(false);
  };

  const handleRemoveSkill = async () => {
    if (!deleteTarget) return;
    await dispatch(removeAdminCharacterSkill({ csId: deleteTarget.csId, characterId }));
    setDeleteTarget(null);
  };

  const handleLevelChange = async (csId: number, skillId: number, level: number) => {
    await dispatch(updateAdminSkillLevel({ csId, skillId, level, characterId }));
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
      <div className="gray-bg p-4 sm:p-6">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <h3 className="gold-text text-lg font-medium uppercase">Навыки персонажа</h3>
          <button
            type="button"
            className="btn-line text-sm"
            onClick={() => (showAddPanel ? setShowAddPanel(false) : handleOpenAdd())}
          >
            {showAddPanel ? 'Закрыть' : 'Добавить навык'}
          </button>
        </div>

        <AnimatePresence>
          {showAddPanel && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2 }}
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
                          setSelectedSkillId(e.target.value ? Number(e.target.value) : '')
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
                    <button
                      type="button"
                      className="btn-blue text-sm"
                      disabled={!selectedSkillId}
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

        {skills.length === 0 ? (
          <p className="text-white/50 text-center py-4">Нет навыков</p>
        ) : (
          <div className="space-y-2">
            {skills.map((skill) => {
              const skillName = skill.skill?.name ?? `Навык #${skill.skill_id}`;
              return (
                <div
                  key={skill.id}
                  className="flex flex-col sm:flex-row sm:items-center gap-3 p-3 rounded-card bg-white/[0.04] hover:bg-white/[0.07] transition-colors"
                >
                  {skill.skill?.skill_image && (
                    <img
                      src={skill.skill.skill_image}
                      alt={skillName}
                      className="w-10 h-10 rounded-full object-cover border border-white/20 flex-shrink-0"
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-white text-sm font-medium">{skillName}</p>
                    <p className="text-white/50 text-xs">
                      Уровень {skill.level}/4
                      {skill.free_perk_points > 0 && ` · ${skill.free_perk_points} своб. очко`}
                    </p>
                  </div>

                  <select
                    className="input-underline text-xs w-auto min-w-[100px]"
                    value={skill.level}
                    onChange={(e) => {
                      const newLevel = Number(e.target.value);
                      if (newLevel !== skill.level) {
                        handleLevelChange(skill.id, skill.skill_id, newLevel);
                      }
                    }}
                  >
                    {LEVELS.map((lvl) => (
                      <option key={lvl} value={lvl}>
                        Ур. {lvl}
                      </option>
                    ))}
                  </select>

                  <button
                    type="button"
                    className="text-site-red text-xs hover:opacity-80 transition-opacity"
                    onClick={() => setDeleteTarget({ csId: skill.id, skillName })}
                  >
                    Удалить
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

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
                <span className="text-gold font-medium">{deleteTarget.skillName}</span> у персонажа?
              </p>
              <div className="flex gap-4">
                <button type="button" className="btn-blue" onClick={handleRemoveSkill}>
                  Удалить
                </button>
                <button
                  type="button"
                  className="btn-line"
                  onClick={() => setDeleteTarget(null)}
                >
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
