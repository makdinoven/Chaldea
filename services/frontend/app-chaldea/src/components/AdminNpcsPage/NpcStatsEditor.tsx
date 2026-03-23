import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../api/api';
import useDebounce from '../../hooks/useDebounce';

interface NpcStatsEditorProps {
  npcId: number;
  npcName: string;
  onClose: () => void;
}

interface Attributes {
  [key: string]: number | string | null;
}

interface SkillAssignment {
  id: number;
  skill_id: number;
  skill_name: string;
  rank_number: number;
}

interface SkillInfo {
  id: number;
  name: string;
  skill_type: string;
}

interface SkillRank {
  id: number;
  rank_name: string | null;
  rank_number: number;
}

interface SkillFullTree {
  id: number;
  name: string;
  skill_type: string;
  ranks: SkillRank[];
}

/** Tracks a skill that has been added to the NPC. */
interface SelectedSkill {
  skill_id: number;
  skill_name: string;
  rank_number: number;
  /** skill_rank_id from the full_tree endpoint — needed for display/lookup */
  skill_rank_id: number;
}

const STAT_LABELS: Record<string, string> = {
  strength: 'Сила',
  agility: 'Ловкость',
  intelligence: 'Интеллект',
  endurance: 'Живучесть',
  charisma: 'Харизма',
  luck: 'Удача',
  max_health: 'Макс. здоровье',
  current_health: 'Текущее здоровье',
  max_mana: 'Макс. мана',
  current_mana: 'Текущая мана',
  max_energy: 'Макс. энергия',
  current_energy: 'Текущая энергия',
  max_stamina: 'Макс. выносливость',
  current_stamina: 'Текущая выносливость',
  damage: 'Урон',
  dodge: 'Уклонение',
  critical_hit_chance: 'Шанс крита',
  critical_damage: 'Крит. урон',
  res_physical: 'Физ. защита',
  res_magic: 'Маг. защита',
  res_fire: 'Защ. огонь',
  res_ice: 'Защ. лёд',
  res_watering: 'Защ. вода',
  res_electricity: 'Защ. электр.',
  res_wind: 'Защ. ветер',
  res_sainting: 'Защ. свет',
  res_damning: 'Защ. тьма',
  res_catting: 'Защ. реж.',
  res_crushing: 'Защ. дроб.',
  res_piercing: 'Защ. кол.',
  res_effects: 'Сопр. эффектам',
};

const PRIMARY_STATS = ['strength', 'agility', 'intelligence', 'endurance', 'charisma', 'luck'];
const RESOURCE_STATS = ['max_health', 'current_health', 'max_mana', 'current_mana', 'max_energy', 'current_energy', 'max_stamina', 'current_stamina'];
const COMBAT_STATS = ['damage', 'dodge', 'critical_hit_chance', 'critical_damage'];
const RESISTANCE_STATS = ['res_physical', 'res_magic', 'res_fire', 'res_ice', 'res_watering', 'res_electricity', 'res_wind', 'res_sainting', 'res_damning', 'res_catting', 'res_crushing', 'res_piercing', 'res_effects'];

const NpcStatsEditor = ({ npcId, npcName, onClose }: NpcStatsEditorProps) => {
  const [attributes, setAttributes] = useState<Attributes | null>(null);
  const [skills, setSkills] = useState<SkillAssignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<'stats' | 'skills'>('stats');

  // Skills editor state
  const [currentSkills, setCurrentSkills] = useState<SelectedSkill[]>([]);
  const [originalSkills, setOriginalSkills] = useState<SelectedSkill[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const debouncedQuery = useDebounce(searchQuery);
  const [searchResults, setSearchResults] = useState<SkillInfo[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [expandedSkill, setExpandedSkill] = useState<SkillFullTree | null>(null);
  const [loadingTree, setLoadingTree] = useState(false);
  const [savingSkills, setSavingSkills] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [attrRes, skillsRes] = await Promise.allSettled([
        axios.get(`${BASE_URL}/attributes/${npcId}`),
        axios.get(`${BASE_URL}/skills/characters/${npcId}/skills`),
      ]);
      if (attrRes.status === 'fulfilled') {
        setAttributes(attrRes.value.data);
      }
      if (skillsRes.status === 'fulfilled') {
        const skillData: SkillAssignment[] = Array.isArray(skillsRes.value.data) ? skillsRes.value.data : [];
        setSkills(skillData);
        // Convert to SelectedSkill format for the editor
        const selected: SelectedSkill[] = skillData.map((s) => ({
          skill_id: s.skill_id,
          skill_name: s.skill_name,
          rank_number: s.rank_number,
          skill_rank_id: s.id, // the assignment ID is used as a key but we track by skill_id+rank_number
        }));
        setCurrentSkills(selected);
        setOriginalSkills(selected);
      }
    } catch {
      toast.error('Не удалось загрузить данные');
    } finally {
      setLoading(false);
    }
  }, [npcId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Skill search
  useEffect(() => {
    if (!debouncedQuery) {
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    axios
      .get<SkillInfo[]>(`${BASE_URL}/skills/admin/skills/`, { params: { q: debouncedQuery } })
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
      const res = await axios.get<SkillFullTree>(`${BASE_URL}/skills/admin/skills/${skillId}/full_tree`);
      setExpandedSkill(res.data);
    } catch {
      toast.error('Не удалось загрузить ранги навыка');
    } finally {
      setLoadingTree(false);
    }
  };

  const handleAddRank = (rank: SkillRank, skillName: string, skillId: number) => {
    // Don't add duplicate (same skill_id + rank)
    const exists = currentSkills.some(
      (s) => s.skill_id === skillId && s.rank_number === rank.rank_number,
    );
    if (exists) return;
    setCurrentSkills((prev) => [
      ...prev,
      {
        skill_id: skillId,
        skill_name: skillName,
        rank_number: rank.rank_number,
        skill_rank_id: rank.id,
      },
    ]);
  };

  const handleRemoveSkill = (skillId: number, rankNumber: number) => {
    setCurrentSkills((prev) =>
      prev.filter((s) => !(s.skill_id === skillId && s.rank_number === rankNumber)),
    );
  };

  const isRankAdded = (skillId: number, rankNumber: number): boolean => {
    return currentSkills.some((s) => s.skill_id === skillId && s.rank_number === rankNumber);
  };

  const hasSkillChanges = (() => {
    if (originalSkills.length !== currentSkills.length) return true;
    const origSet = originalSkills.map((s) => `${s.skill_id}:${s.rank_number}`).sort();
    const currSet = currentSkills.map((s) => `${s.skill_id}:${s.rank_number}`).sort();
    return origSet.some((v, i) => v !== currSet[i]);
  })();

  const handleSaveSkills = async () => {
    setSavingSkills(true);
    try {
      // Step 1: Delete all current skills
      await axios.delete(`${BASE_URL}/skills/admin/character_skills/by_character/${npcId}`);

      // Step 2: Assign new skills (if any)
      if (currentSkills.length > 0) {
        await axios.post(`${BASE_URL}/skills/assign_multiple`, {
          character_id: npcId,
          skills: currentSkills.map((s) => ({
            skill_id: s.skill_id,
            rank_number: s.rank_number,
          })),
        });
      }

      toast.success('Навыки НПС обновлены');
      // Refresh data
      await fetchData();
    } catch (err) {
      let message = 'Не удалось сохранить навыки';
      if (axios.isAxiosError(err) && err.response?.data?.detail) {
        const detail = err.response.data.detail;
        message = typeof detail === 'string' ? detail : message;
      }
      toast.error(message);
    } finally {
      setSavingSkills(false);
    }
  };

  const handleStatChange = (key: string, value: string) => {
    setAttributes((prev) => prev ? { ...prev, [key]: value === '' ? 0 : Number(value) } : prev);
  };

  const handleSaveStats = async () => {
    if (!attributes) return;
    setSaving(true);
    try {
      await axios.put(`${BASE_URL}/attributes/admin/${npcId}`, attributes);
      toast.success('Статы НПС обновлены');
    } catch (err) {
      let message = 'Не удалось сохранить статы';
      if (axios.isAxiosError(err) && err.response?.data?.detail) {
        const detail = err.response.data.detail;
        message = typeof detail === 'string' ? detail : message;
      }
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const handleRecalculate = async () => {
    setSaving(true);
    try {
      await axios.post(`${BASE_URL}/attributes/${npcId}/recalculate`);
      toast.success('Статы пересчитаны');
      fetchData();
    } catch {
      toast.error('Не удалось пересчитать статы');
    } finally {
      setSaving(false);
    }
  };

  const renderStatGroup = (title: string, keys: string[]) => (
    <div className="flex flex-col gap-3">
      <h3 className="gold-text text-sm font-medium uppercase tracking-wide">{title}</h3>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
        {keys.map((key) => {
          const val = attributes?.[key];
          if (val === undefined) return null;
          return (
            <label key={key} className="flex flex-col gap-1">
              <span className="text-white/50 text-[10px] uppercase truncate" title={STAT_LABELS[key] || key}>
                {STAT_LABELS[key] || key}
              </span>
              <input
                type="number"
                value={val ?? 0}
                onChange={(e) => handleStatChange(key, e.target.value)}
                step="any"
                className="input-underline !text-sm !py-1"
              />
            </label>
          );
        })}
      </div>
    </div>
  );

  const renderSkillsEditor = () => (
    <div className="flex flex-col gap-5">
      {/* Current skills */}
      <div>
        <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em] mb-3">
          Текущие навыки ({currentSkills.length})
        </h3>
        {currentSkills.length === 0 ? (
          <p className="text-white/50 text-sm">Навыки не назначены</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {currentSkills.map((skill) => (
              <div
                key={`${skill.skill_id}-${skill.rank_number}`}
                className="flex items-center gap-2 bg-white/[0.07] rounded-full px-3 py-1.5"
              >
                <span className="text-white text-sm">
                  {skill.skill_name || `Навык #${skill.skill_id}`}
                  <span className="text-white/50 ml-1">(Ранг {skill.rank_number})</span>
                </span>
                <button
                  onClick={() => handleRemoveSkill(skill.skill_id, skill.rank_number)}
                  className="text-site-red hover:text-white text-xs transition-colors"
                  title="Удалить"
                >
                  &times;
                </button>
              </div>
            ))}
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
                  <span className="text-white/40 text-xs">{skill.skill_type}</span>
                  <span className="text-white/30 text-xs ml-auto">
                    {expandedSkill?.id === skill.id ? '\u25BC' : '\u25B6'}
                  </span>
                </button>

                {/* Expanded ranks */}
                {expandedSkill?.id === skill.id && (
                  <div className="pl-6 flex flex-col gap-1 py-1">
                    {loadingTree ? (
                      <span className="text-white/50 text-xs">Загрузка...</span>
                    ) : (
                      expandedSkill.ranks?.map((rank) => {
                        const added = isRankAdded(skill.id, rank.rank_number);
                        return (
                          <div
                            key={rank.id}
                            className="flex items-center gap-2 px-2 py-1"
                          >
                            <span className="text-white/70 text-sm">
                              {rank.rank_name || `Ранг ${rank.rank_number}`}
                            </span>
                            <span className="text-white/40 text-xs">Ранг {rank.rank_number}</span>
                            <button
                              onClick={() =>
                                added
                                  ? handleRemoveSkill(skill.id, rank.rank_number)
                                  : handleAddRank(rank, skill.name, skill.id)
                              }
                              className={`text-xs ml-auto px-2 py-0.5 rounded transition-colors ${
                                added
                                  ? 'text-site-red hover:text-white'
                                  : 'text-site-blue hover:text-white'
                              }`}
                            >
                              {added ? 'Убрать' : 'Добавить'}
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
      {hasSkillChanges && (
        <div className="pt-2">
          <button
            onClick={handleSaveSkills}
            disabled={savingSkills}
            className="btn-blue !text-base !px-8 !py-2 disabled:opacity-50"
          >
            {savingSkills ? 'Сохранение...' : 'Сохранить навыки'}
          </button>
        </div>
      )}
    </div>
  );

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="gold-text text-2xl font-semibold uppercase tracking-wide">
            Статы и навыки
          </h2>
          <p className="text-white/50 text-sm mt-1">НПС: {npcName}</p>
        </div>
        <button onClick={onClose} className="btn-line !px-6">
          Назад к НПС
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-4 border-b border-white/10 pb-2">
        <button
          onClick={() => setActiveTab('stats')}
          className={`text-sm font-medium uppercase tracking-wide pb-1 transition-colors ${
            activeTab === 'stats' ? 'gold-text border-b-2 border-gold' : 'text-white/50 hover:text-white/80'
          }`}
        >
          Характеристики
        </button>
        <button
          onClick={() => setActiveTab('skills')}
          className={`text-sm font-medium uppercase tracking-wide pb-1 transition-colors ${
            activeTab === 'skills' ? 'gold-text border-b-2 border-gold' : 'text-white/50 hover:text-white/80'
          }`}
        >
          Навыки ({currentSkills.length})
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        </div>
      ) : activeTab === 'stats' ? (
        <div className="flex flex-col gap-6">
          {!attributes ? (
            <p className="text-white/50 text-sm">Атрибуты не найдены. Попробуйте пересоздать НПС.</p>
          ) : (
            <>
              {renderStatGroup('Основные', PRIMARY_STATS)}
              <div className="gradient-divider-h relative pb-1" />
              {renderStatGroup('Ресурсы', RESOURCE_STATS)}
              <div className="gradient-divider-h relative pb-1" />
              {renderStatGroup('Боевые', COMBAT_STATS)}
              <div className="gradient-divider-h relative pb-1" />
              {renderStatGroup('Сопротивления', RESISTANCE_STATS)}

              <div className="flex gap-3 pt-4">
                <button
                  onClick={handleSaveStats}
                  disabled={saving}
                  className="btn-blue !px-8 !py-2 disabled:opacity-50"
                >
                  {saving ? 'Сохранение...' : 'Сохранить статы'}
                </button>
                <button
                  onClick={handleRecalculate}
                  disabled={saving}
                  className="btn-line !px-6 !py-2 disabled:opacity-50"
                >
                  Пересчитать
                </button>
              </div>
            </>
          )}
        </div>
      ) : (
        renderSkillsEditor()
      )}
    </div>
  );
};

export default NpcStatsEditor;
