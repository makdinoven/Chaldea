import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { fetchActiveMobs, type ActiveMob } from '../../../api/mobs';

interface MobStatsEditorProps {
  templateId: number;
  templateName: string;
  idClass: number;
  baseAttributes: Record<string, number>;
}

interface Attributes {
  [key: string]: number | string | null;
}

const CLASS_LABELS: Record<number, string> = {
  1: 'Воин',
  2: 'Плут',
  3: 'Маг',
};

const STAT_LABELS: Record<string, string> = {
  strength: 'Сила',
  agility: 'Ловкость',
  intelligence: 'Интеллект',
  endurance: 'Живучесть',
  charisma: 'Харизма',
  luck: 'Удача',
  health: 'Здоровье',
  mana: 'Мана',
  energy: 'Энергия',
  stamina: 'Выносливость',
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

const BASE_ATTR_KEYS = ['strength', 'agility', 'intelligence', 'endurance', 'health', 'mana', 'energy', 'stamina', 'charisma', 'luck'];

const MobStatsEditor = ({ templateId, templateName, idClass, baseAttributes }: MobStatsEditorProps) => {
  const [activeMobs, setActiveMobs] = useState<ActiveMob[]>([]);
  const [mobsLoading, setMobsLoading] = useState(false);
  const [selectedMob, setSelectedMob] = useState<ActiveMob | null>(null);

  const [attributes, setAttributes] = useState<Attributes | null>(null);
  const [attrLoading, setAttrLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const loadActiveMobs = useCallback(async () => {
    setMobsLoading(true);
    try {
      const res = await fetchActiveMobs({ template_id: templateId, page_size: 100 });
      setActiveMobs(res.items);
    } catch {
      toast.error('Не удалось загрузить активных мобов');
    } finally {
      setMobsLoading(false);
    }
  }, [templateId]);

  useEffect(() => {
    loadActiveMobs();
  }, [loadActiveMobs]);

  const loadAttributes = useCallback(async (characterId: number) => {
    setAttrLoading(true);
    try {
      const res = await axios.get(`/attributes/${characterId}`);
      setAttributes(res.data);
    } catch {
      toast.error('Не удалось загрузить атрибуты моба');
      setAttributes(null);
    } finally {
      setAttrLoading(false);
    }
  }, []);

  const handleSelectMob = (mob: ActiveMob) => {
    setSelectedMob(mob);
    loadAttributes(mob.character_id);
  };

  const handleStatChange = (key: string, value: string) => {
    setAttributes((prev) => prev ? { ...prev, [key]: value === '' ? 0 : Number(value) } : prev);
  };

  const handleSaveStats = async () => {
    if (!attributes || !selectedMob) return;
    setSaving(true);
    try {
      await axios.put(`/attributes/admin/${selectedMob.character_id}`, attributes);
      toast.success('Статы моба обновлены');
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
    if (!selectedMob) return;
    setSaving(true);
    try {
      await axios.post(`/attributes/${selectedMob.character_id}/recalculate`);
      toast.success('Статы пересчитаны');
      loadAttributes(selectedMob.character_id);
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

  const hasBaseAttrs = baseAttributes && Object.keys(baseAttributes).length > 0;

  return (
    <div className="flex flex-col gap-6">
      {/* Class info */}
      <div className="flex items-center gap-3">
        <span className="text-white/50 text-sm">Класс:</span>
        <span className="text-white text-sm font-medium">
          {CLASS_LABELS[idClass] || `ID ${idClass}`}
        </span>
      </div>

      {/* Base attributes from template */}
      {hasBaseAttrs && (
        <div className="flex flex-col gap-3">
          <h3 className="gold-text text-sm font-medium uppercase tracking-wide">
            Базовые атрибуты (из шаблона)
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
            {BASE_ATTR_KEYS.map((key) => {
              const val = baseAttributes[key];
              if (val === undefined && val !== 0) return null;
              return (
                <div key={key} className="flex flex-col gap-0.5">
                  <span className="text-white/50 text-[10px] uppercase truncate" title={STAT_LABELS[key] || key}>
                    {STAT_LABELS[key] || key}
                  </span>
                  <span className="text-white text-sm">{val ?? 0}</span>
                </div>
              );
            })}
          </div>
          <div className="gradient-divider-h relative pb-1" />
        </div>
      )}

      {/* Active mob selection */}
      <div className="flex flex-col gap-3">
        <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">
          Активные мобы ({activeMobs.length})
        </h3>

        {mobsLoading ? (
          <div className="flex items-center gap-2 text-white/50 text-sm">
            <div className="w-4 h-4 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
            Загрузка...
          </div>
        ) : activeMobs.length === 0 ? (
          <p className="text-white/50 text-sm">
            Нет активных экземпляров этого моба. Заспавните моба во вкладке «Спавн», затем выберите его здесь для просмотра статов.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {activeMobs.map((mob) => (
              <button
                key={mob.id}
                onClick={() => handleSelectMob(mob)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm transition-colors duration-200 ${
                  selectedMob?.id === mob.id
                    ? 'bg-site-blue/20 text-site-blue border border-site-blue/40'
                    : 'bg-white/[0.07] text-white/70 hover:text-white hover:bg-white/[0.12]'
                }`}
              >
                <span>{mob.name}</span>
                <span className="text-white/40 text-xs">#{mob.character_id}</span>
                <span className={`text-xs ${
                  mob.status === 'alive' ? 'text-green-400' : 'text-yellow-400'
                }`}>
                  {mob.status === 'alive' ? 'жив' : 'в бою'}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Selected mob stats */}
      {selectedMob && (
        <div className="flex flex-col gap-6">
          <div className="gradient-divider-h relative pb-1" />

          <div className="flex flex-col sm:flex-row sm:items-center gap-2">
            <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">
              Статы: {selectedMob.name}
            </h3>
            <span className="text-white/40 text-xs">
              (character_id: {selectedMob.character_id})
            </span>
          </div>

          {attrLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
            </div>
          ) : !attributes ? (
            <p className="text-white/50 text-sm">Атрибуты не найдены для этого экземпляра.</p>
          ) : (
            <>
              {renderStatGroup('Основные', PRIMARY_STATS)}
              <div className="gradient-divider-h relative pb-1" />
              {renderStatGroup('Ресурсы', RESOURCE_STATS)}
              <div className="gradient-divider-h relative pb-1" />
              {renderStatGroup('Боевые', COMBAT_STATS)}
              <div className="gradient-divider-h relative pb-1" />
              {renderStatGroup('Сопротивления', RESISTANCE_STATS)}

              <div className="flex flex-wrap gap-3 pt-4">
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
      )}
    </div>
  );
};

export default MobStatsEditor;
