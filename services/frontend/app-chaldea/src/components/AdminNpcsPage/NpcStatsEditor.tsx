import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../api/api';

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
        setSkills(Array.isArray(skillsRes.value.data) ? skillsRes.value.data : []);
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
          Навыки ({skills.length})
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
        <div className="flex flex-col gap-4">
          {skills.length === 0 ? (
            <p className="text-white/50 text-sm">
              У НПС нет назначенных навыков. Навыки можно назначить через API:
              <br />
              <code className="text-site-blue text-xs">POST /skills/assign_multiple</code>
            </p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {skills.map((skill) => (
                <div
                  key={skill.id}
                  className="bg-black/30 rounded-card p-3 flex items-center gap-3"
                >
                  <div className="w-10 h-10 rounded bg-gold/10 flex items-center justify-center text-gold text-lg font-bold shrink-0">
                    {skill.rank_number}
                  </div>
                  <div className="flex flex-col min-w-0">
                    <span className="text-white text-sm font-medium truncate">
                      {skill.skill_name || `Навык #${skill.skill_id}`}
                    </span>
                    <span className="text-white/40 text-xs">Ранг {skill.rank_number}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default NpcStatsEditor;
