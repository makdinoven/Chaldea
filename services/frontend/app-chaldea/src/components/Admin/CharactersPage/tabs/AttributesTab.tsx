import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../../redux/store';
import {
  fetchAdminAttributes,
  updateAdminAttributes,
  selectAdminAttributes,
  selectAdminDetailLoading,
} from '../../../../redux/slices/adminCharactersSlice';
import type { CharacterAttributes, AdminAttributeUpdate } from '../types';

interface AttributesTabProps {
  characterId: number;
}

// Section definitions with field groupings
const SECTIONS: { title: string; fields: { key: keyof CharacterAttributes; label: string }[] }[] = [
  {
    title: 'Ресурсы',
    fields: [
      { key: 'health', label: 'Здоровье (базовое)' },
      { key: 'max_health', label: 'Макс. здоровье' },
      { key: 'current_health', label: 'Текущее здоровье' },
      { key: 'mana', label: 'Мана (базовая)' },
      { key: 'max_mana', label: 'Макс. мана' },
      { key: 'current_mana', label: 'Текущая мана' },
      { key: 'energy', label: 'Энергия (базовая)' },
      { key: 'max_energy', label: 'Макс. энергия' },
      { key: 'current_energy', label: 'Текущая энергия' },
      { key: 'stamina', label: 'Стамина (базовая)' },
      { key: 'max_stamina', label: 'Макс. стамина' },
      { key: 'current_stamina', label: 'Текущая стамина' },
    ],
  },
  {
    title: 'Базовые статы',
    fields: [
      { key: 'strength', label: 'Сила' },
      { key: 'agility', label: 'Ловкость' },
      { key: 'intelligence', label: 'Интеллект' },
      { key: 'endurance', label: 'Выносливость' },
      { key: 'charisma', label: 'Харизма' },
      { key: 'luck', label: 'Удача' },
    ],
  },
  {
    title: 'Боевые',
    fields: [
      { key: 'damage', label: 'Урон' },
      { key: 'dodge', label: 'Уклонение' },
      { key: 'critical_hit_chance', label: 'Крит. шанс' },
      { key: 'critical_damage', label: 'Крит. урон' },
    ],
  },
  {
    title: 'Опыт',
    fields: [
      { key: 'passive_experience', label: 'Пассивный опыт' },
      { key: 'active_experience', label: 'Активный опыт' },
    ],
  },
  {
    title: 'Сопротивления',
    fields: [
      { key: 'res_effects', label: 'Эффекты' },
      { key: 'res_physical', label: 'Физическое' },
      { key: 'res_catting', label: 'Режущее' },
      { key: 'res_crushing', label: 'Дробящее' },
      { key: 'res_piercing', label: 'Колющее' },
      { key: 'res_magic', label: 'Магия' },
      { key: 'res_fire', label: 'Огонь' },
      { key: 'res_ice', label: 'Лёд' },
      { key: 'res_watering', label: 'Вода' },
      { key: 'res_electricity', label: 'Электричество' },
      { key: 'res_sainting', label: 'Свет' },
      { key: 'res_wind', label: 'Ветер' },
      { key: 'res_damning', label: 'Тьма' },
    ],
  },
  {
    title: 'Уязвимости',
    fields: [
      { key: 'vul_effects', label: 'Эффекты' },
      { key: 'vul_physical', label: 'Физическое' },
      { key: 'vul_catting', label: 'Режущее' },
      { key: 'vul_crushing', label: 'Дробящее' },
      { key: 'vul_piercing', label: 'Колющее' },
      { key: 'vul_magic', label: 'Магия' },
      { key: 'vul_fire', label: 'Огонь' },
      { key: 'vul_ice', label: 'Лёд' },
      { key: 'vul_watering', label: 'Вода' },
      { key: 'vul_electricity', label: 'Электричество' },
      { key: 'vul_sainting', label: 'Свет' },
      { key: 'vul_wind', label: 'Ветер' },
      { key: 'vul_damning', label: 'Тьма' },
    ],
  },
];

const AttributesTab = ({ characterId }: AttributesTabProps) => {
  const dispatch = useAppDispatch();
  const attributes = useAppSelector(selectAdminAttributes);
  const loading = useAppSelector(selectAdminDetailLoading);
  const [localAttrs, setLocalAttrs] = useState<CharacterAttributes | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    dispatch(fetchAdminAttributes(characterId));
  }, [dispatch, characterId]);

  useEffect(() => {
    if (attributes) {
      setLocalAttrs({ ...attributes });
    }
  }, [attributes]);

  const handleFieldChange = (key: keyof CharacterAttributes, value: string) => {
    if (!localAttrs) return;
    setLocalAttrs({ ...localAttrs, [key]: Number(value) || 0 });
  };

  const handleSave = async () => {
    if (!localAttrs || !attributes) return;
    setSaving(true);
    try {
      // Only send changed fields
      const update: AdminAttributeUpdate = {};
      for (const key of Object.keys(localAttrs) as (keyof CharacterAttributes)[]) {
        if (localAttrs[key] !== attributes[key]) {
          (update as Record<string, number>)[key] = localAttrs[key];
        }
      }
      if (Object.keys(update).length === 0) {
        toast('Нет изменений для сохранения');
        return;
      }
      await dispatch(
        updateAdminAttributes({ characterId, update }),
      ).unwrap();
    } finally {
      setSaving(false);
    }
  };

  if (loading && !localAttrs) {
    return (
      <div className="flex justify-center items-center py-12">
        <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
      </div>
    );
  }

  if (!localAttrs) {
    return <p className="text-white/50 text-center py-8">Атрибуты не найдены</p>;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="space-y-6"
    >
      {SECTIONS.map((section) => (
        <div key={section.title} className="gray-bg p-6">
          <h3 className="gold-text text-lg font-medium uppercase mb-4">{section.title}</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {section.fields.map((field) => (
              <div key={field.key} className="flex flex-col gap-1">
                <label className="text-white/60 text-xs uppercase tracking-[0.06em]">
                  {field.label}
                </label>
                <input
                  type="number"
                  className="input-underline"
                  value={localAttrs[field.key]}
                  onChange={(e) => handleFieldChange(field.key, e.target.value)}
                  step={
                    field.key.startsWith('res_') ||
                    field.key.startsWith('vul_') ||
                    field.key === 'dodge' ||
                    field.key === 'critical_hit_chance' ||
                    field.key === 'critical_damage'
                      ? '0.01'
                      : '1'
                  }
                />
              </div>
            ))}
          </div>
        </div>
      ))}

      <div className="flex gap-4">
        <button className="btn-blue" onClick={handleSave} disabled={saving}>
          {saving ? 'Сохранение...' : 'Сохранить'}
        </button>
      </div>
    </motion.div>
  );
};

export default AttributesTab;
