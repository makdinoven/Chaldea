import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../api/api';
import useDebounce from '../../hooks/useDebounce';

interface SubraceOptionWithPreset {
  id_subrace: number;
  name: string;
  stat_preset: Record<string, number> | null;
}

interface RaceWithSubracesData {
  id_race: number;
  name: string;
  subraces: SubraceOptionWithPreset[];
}

interface NpcStatsEditorProps {
  npcId: number;
  npcName: string;
  npcLevel: number;
  racesData: RaceWithSubracesData[];
  onClose: () => void;
}

interface Attributes {
  [key: string]: number | string | null;
}

interface EquipmentItem {
  strength_modifier?: number | null;
  agility_modifier?: number | null;
  intelligence_modifier?: number | null;
  endurance_modifier?: number | null;
  charisma_modifier?: number | null;
  luck_modifier?: number | null;
  health_modifier?: number | null;
  mana_modifier?: number | null;
  energy_modifier?: number | null;
  stamina_modifier?: number | null;
  [key: string]: unknown;
}

interface EquipmentSlotData {
  item: EquipmentItem | null;
  [key: string]: unknown;
}

interface SkillRankNested {
  id: number;
  skill_id: number;
  rank_number: number;
}

interface SkillAssignment {
  id: number;
  character_id: number;
  skill_rank_id: number;
  skill_rank: SkillRankNested;
  skill_name: string | null;
  skill_type?: string | null;
  skill_image?: string | null;
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
  /** character_skill row id — present only for skills already saved on the server (used for targeted DELETE). */
  character_skill_id?: number;
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
  health: 'Здоровье (база)',
  mana: 'Мана (база)',
  energy: 'Энергия (база)',
  stamina: 'Выносливость (ресурс)',
};

const PRIMARY_STATS = ['strength', 'agility', 'intelligence', 'endurance', 'charisma', 'luck'];
const BASE_RESOURCE_STATS = ['health', 'mana', 'energy', 'stamina'];
const RESOURCE_STATS = ['max_health', 'current_health', 'max_mana', 'current_mana', 'max_energy', 'current_energy', 'max_stamina', 'current_stamina'];
const COMBAT_STATS = ['damage', 'dodge', 'critical_hit_chance', 'critical_damage'];
const RESISTANCE_STATS = ['res_physical', 'res_magic', 'res_fire', 'res_ice', 'res_watering', 'res_electricity', 'res_wind', 'res_sainting', 'res_damning', 'res_catting', 'res_crushing', 'res_piercing', 'res_effects'];

const READONLY_STATS = ['max_health', 'max_mana', 'max_energy', 'max_stamina'];

const POINT_STATS = [...PRIMARY_STATS, ...BASE_RESOURCE_STATS];
const POINTS_PER_LEVEL = 10;

const NpcStatsEditor = ({ npcId, npcName, npcLevel, racesData, onClose }: NpcStatsEditorProps) => {
  const [attributes, setAttributes] = useState<Attributes | null>(null);
  const [skills, setSkills] = useState<SkillAssignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<'stats' | 'skills'>('stats');
  const [npcSubraceId, setNpcSubraceId] = useState<number | null>(null);
  const [equipmentModifiers, setEquipmentModifiers] = useState<Record<string, number>>({});

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
      const [attrRes, skillsRes, npcDetailRes, equipRes] = await Promise.allSettled([
        axios.get(`${BASE_URL}/attributes/${npcId}`),
        axios.get(`${BASE_URL}/skills/characters/${npcId}/skills`),
        axios.get(`${BASE_URL}/characters/admin/npcs/${npcId}`),
        axios.get<EquipmentSlotData[]>(`${BASE_URL}/inventory/${npcId}/equipment`),
      ]);
      if (attrRes.status === 'fulfilled') {
        setAttributes(attrRes.value.data);
      }
      if (skillsRes.status === 'fulfilled') {
        const skillData: SkillAssignment[] = Array.isArray(skillsRes.value.data) ? skillsRes.value.data : [];
        setSkills(skillData);
        // Convert to SelectedSkill format for the editor.
        // The backend returns skill_id / rank_number nested inside skill_rank.
        const selected: SelectedSkill[] = skillData.map((s) => ({
          skill_id: s.skill_rank.skill_id,
          skill_name: s.skill_name ?? `Навык #${s.skill_rank.skill_id}`,
          rank_number: s.skill_rank.rank_number,
          skill_rank_id: s.skill_rank.id,
          character_skill_id: s.id,
        }));
        setCurrentSkills(selected);
        setOriginalSkills(selected);
      }
      if (npcDetailRes.status === 'fulfilled') {
        setNpcSubraceId(npcDetailRes.value.data.id_subrace ?? null);
      }
      // Sum equipment modifiers from all equipped items
      if (equipRes.status === 'fulfilled') {
        const slots: EquipmentSlotData[] = Array.isArray(equipRes.value.data) ? equipRes.value.data : [];
        const modSums: Record<string, number> = {};
        for (const slot of slots) {
          if (!slot.item) continue;
          for (const statKey of POINT_STATS) {
            const modField = `${statKey}_modifier` as keyof EquipmentItem;
            const modValue = Number(slot.item[modField] ?? 0);
            if (modValue !== 0) {
              modSums[statKey] = (modSums[statKey] ?? 0) + modValue;
            }
          }
        }
        setEquipmentModifiers(modSums);
      } else {
        setEquipmentModifiers({});
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
      // Diff original vs current by composite key skill_id:rank_number.
      const keyOf = (s: SelectedSkill) => `${s.skill_id}:${s.rank_number}`;
      const originalKeys = new Set(originalSkills.map(keyOf));
      const currentKeys = new Set(currentSkills.map(keyOf));

      const toAdd = currentSkills.filter((s) => !originalKeys.has(keyOf(s)));
      const toRemove = originalSkills.filter(
        (s) => !currentKeys.has(keyOf(s)) && s.character_skill_id != null,
      );

      // Step 1: POST additions first. If this fails, existing skills survive untouched.
      if (toAdd.length > 0) {
        await axios.post(`${BASE_URL}/skills/assign_multiple`, {
          character_id: npcId,
          skills: toAdd.map((s) => ({
            skill_id: s.skill_id,
            rank_number: s.rank_number,
          })),
        });
      }

      // Step 2: DELETE only the entries the user actually removed, by character_skill id.
      // Done sequentially so a single failure doesn't leave the UI in an unknown state.
      for (const s of toRemove) {
        await axios.delete(
          `${BASE_URL}/skills/admin/character_skills/${s.character_skill_id}`,
        );
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

  /** Saves current attributes state to the backend. Returns true on success. */
  const saveStats = async (): Promise<boolean> => {
    if (!attributes) return false;
    try {
      await axios.put(`${BASE_URL}/attributes/admin/${npcId}`, attributes);
      return true;
    } catch (err) {
      let message = 'Не удалось сохранить статы';
      if (axios.isAxiosError(err) && err.response?.data?.detail) {
        const detail = err.response.data.detail;
        message = typeof detail === 'string' ? detail : message;
      }
      toast.error(message);
      return false;
    }
  };

  const handleSaveStats = async () => {
    if (!attributes) return;
    setSaving(true);
    try {
      const saved = await saveStats();
      if (saved) {
        toast.success('Статы НПС обновлены');
      }
    } finally {
      setSaving(false);
    }
  };

  const handleRecalculate = async () => {
    if (!attributes) return;
    setSaving(true);
    try {
      const saved = await saveStats();
      if (!saved) return;

      try {
        await axios.post(`${BASE_URL}/attributes/${npcId}/recalculate`);
      } catch {
        toast.error('Статы сохранены, но не удалось пересчитать. Попробуйте ещё раз.');
        return;
      }

      toast.success('Статы сохранены и пересчитаны');
      await fetchData();
    } finally {
      setSaving(false);
    }
  };

  // Derive subrace preset from racesData + npcSubraceId
  const subracePreset: Record<string, number> = (() => {
    if (npcSubraceId == null || racesData.length === 0) return {};
    for (const race of racesData) {
      const subrace = race.subraces.find((s) => s.id_subrace === npcSubraceId);
      if (subrace?.stat_preset) return subrace.stat_preset;
    }
    return {};
  })();

  // Compute stat points
  const totalPoints = npcLevel * POINTS_PER_LEVEL;
  const spentPoints = attributes
    ? POINT_STATS.reduce((sum, key) => {
        const current = Number(attributes[key] ?? 0);
        const base = subracePreset[key] ?? 0;
        const equipBonus = equipmentModifiers[key] ?? 0;
        return sum + Math.max(0, current - base - equipBonus);
      }, 0)
    : 0;
  const remainingPoints = totalPoints - spentPoints;

  const renderStatGroup = (title: string, keys: string[]) => (
    <div className="flex flex-col gap-3">
      <h3 className="gold-text text-sm font-medium uppercase tracking-wide">{title}</h3>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
        {keys.map((key) => {
          const val = attributes?.[key];
          if (val === undefined) return null;
          const isReadOnly = READONLY_STATS.includes(key);
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
                readOnly={isReadOnly}
                tabIndex={isReadOnly ? -1 : undefined}
                className={`input-underline !text-sm !py-1${isReadOnly ? ' opacity-60 cursor-not-allowed' : ''}`}
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
    <div className="gray-bg p-4 sm:p-6 flex flex-col gap-6">
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
              {/* Stat points counter */}
              <div className={`flex flex-wrap items-center gap-x-3 gap-y-1 rounded-card px-4 py-3 text-sm ${
                remainingPoints < 0 ? 'bg-yellow-500/10 border border-yellow-500/30' : 'bg-white/[0.05]'
              }`}>
                <span className="text-white font-medium">
                  Очки статов: {spentPoints} / {totalPoints}
                </span>
                {remainingPoints >= 0 ? (
                  <span className="text-white/50">
                    (осталось: {remainingPoints})
                  </span>
                ) : (
                  <span className="text-yellow-400 font-medium">
                    Превышен лимит на {Math.abs(remainingPoints)}!
                  </span>
                )}
                {npcSubraceId == null && !loading && (
                  <span className="text-white/40 text-xs">
                    (подраса не определена, пресет = 0)
                  </span>
                )}
              </div>

              {renderStatGroup('Основные', PRIMARY_STATS)}
              <div className="gradient-divider-h relative pb-1" />
              {renderStatGroup('Базовые ресурсы', BASE_RESOURCE_STATS)}
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
