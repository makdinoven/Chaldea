import { useEffect, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  createMobTemplate,
  updateMobTemplate,
  selectMobsSaving,
} from '../../../redux/slices/mobsSlice';
import { NPC_CLASSES, NPC_RACES, NPC_SEXES } from '../../../constants/npc';
import type { MobTemplateCreatePayload } from '../../../api/mobs';

interface AdminMobTemplateFormProps {
  editingId: number | null;
  onClose: () => void;
}

const STAT_KEYS = [
  { key: 'strength', label: 'Сила' },
  { key: 'agility', label: 'Ловкость' },
  { key: 'intelligence', label: 'Интеллект' },
  { key: 'endurance', label: 'Выносливость' },
  { key: 'health', label: 'Здоровье' },
  { key: 'mana', label: 'Мана' },
  { key: 'energy', label: 'Энергия' },
  { key: 'stamina', label: 'Стамина' },
  { key: 'charisma', label: 'Харизма' },
  { key: 'luck', label: 'Удача' },
] as const;

const DEFAULT_ATTRIBUTES: Record<string, number> = {
  strength: 10,
  agility: 10,
  intelligence: 10,
  endurance: 10,
  health: 100,
  mana: 50,
  energy: 50,
  stamina: 50,
  charisma: 5,
  luck: 5,
};

interface FormData {
  name: string;
  description: string;
  tier: 'normal' | 'elite' | 'boss';
  level: number;
  id_race: number;
  id_subrace: number;
  id_class: number;
  sex: 'male' | 'female' | 'genderless';
  base_attributes: Record<string, number>;
  xp_reward: number;
  gold_reward: number;
  respawn_enabled: boolean;
  respawn_seconds: number | null;
}

const INITIAL_FORM: FormData = {
  name: '',
  description: '',
  tier: 'normal',
  level: 1,
  id_race: 1,
  id_subrace: 1,
  id_class: 1,
  sex: 'genderless',
  base_attributes: { ...DEFAULT_ATTRIBUTES },
  xp_reward: 0,
  gold_reward: 0,
  respawn_enabled: false,
  respawn_seconds: null,
};

const AdminMobTemplateForm = ({ editingId, onClose }: AdminMobTemplateFormProps) => {
  const dispatch = useAppDispatch();
  const saving = useAppSelector(selectMobsSaving);

  const [form, setForm] = useState<FormData>(INITIAL_FORM);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    if (editingId) {
      setLoadingDetail(true);
      axios.get(`/characters/admin/mob-templates/${editingId}`)
        .then((res) => {
          const t = res.data;
          setForm({
            name: t.name || '',
            description: t.description || '',
            tier: t.tier || 'normal',
            level: t.level || 1,
            id_race: t.id_race || 1,
            id_subrace: t.id_subrace || 1,
            id_class: t.id_class || 1,
            sex: t.sex || 'genderless',
            base_attributes: t.base_attributes || { ...DEFAULT_ATTRIBUTES },
            xp_reward: t.xp_reward || 0,
            gold_reward: t.gold_reward || 0,
            respawn_enabled: t.respawn_enabled ?? false,
            respawn_seconds: t.respawn_seconds ?? null,
          });
          if (t.avatar) {
            setAvatarPreview(t.avatar);
          }
        })
        .catch(() => {
          toast.error('Не удалось загрузить данные шаблона');
        })
        .finally(() => setLoadingDetail(false));
    }
  }, [editingId]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) => {
    const { name, value, type } = e.target;
    if (type === 'checkbox') {
      const checked = (e.target as HTMLInputElement).checked;
      setForm((prev) => ({ ...prev, [name]: checked }));
      return;
    }
    setForm((prev) => ({
      ...prev,
      [name]: type === 'number' ? (value === '' ? 0 : Number(value)) : value,
    }));
  };

  const handleAttrChange = (key: string, value: string) => {
    setForm((prev) => ({
      ...prev,
      base_attributes: {
        ...prev.base_attributes,
        [key]: value === '' ? 0 : Number(value),
      },
    }));
  };

  const handleAvatarFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setAvatarFile(file);
    setAvatarPreview(URL.createObjectURL(file));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) {
      toast.error('Имя моба обязательно');
      return;
    }
    if (form.level < 1) {
      toast.error('Уровень должен быть не менее 1');
      return;
    }

    const payload: MobTemplateCreatePayload = {
      name: form.name,
      description: form.description,
      tier: form.tier,
      level: form.level,
      id_race: form.id_race,
      id_subrace: form.id_subrace,
      id_class: form.id_class,
      sex: form.sex,
      base_attributes: form.base_attributes,
      xp_reward: form.xp_reward,
      gold_reward: form.gold_reward,
      respawn_enabled: form.respawn_enabled,
      respawn_seconds: form.respawn_enabled ? form.respawn_seconds : null,
    };

    try {
      let templateId = editingId;
      if (editingId) {
        await dispatch(updateMobTemplate({ id: editingId, payload })).unwrap();
      } else {
        const result = await dispatch(createMobTemplate(payload)).unwrap();
        templateId = result.id;
      }

      // Upload avatar if file selected
      if (avatarFile && templateId) {
        try {
          const formData = new FormData();
          formData.append('mob_template_id', String(templateId));
          formData.append('file', avatarFile);
          await axios.post('/photo/change_mob_avatar', formData);
        } catch {
          toast.error('Шаблон сохранён, но не удалось загрузить аватар');
        }
      }

      onClose();
    } catch {
      // Error already shown by thunk
    }
  };

  if (loadingDetail) {
    return (
      <div className="gray-bg p-6 flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <form className="gray-bg p-4 sm:p-6 flex flex-col gap-5" onSubmit={handleSubmit}>
      <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase tracking-[0.06em]">
        {editingId ? 'Редактирование шаблона моба' : 'Создание шаблона моба'}
      </h2>

      {/* Basic fields */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Имя</span>
          <input name="name" value={form.name} onChange={handleChange} required className="input-underline" />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Тип</span>
          <select name="tier" value={form.tier} onChange={handleChange} className="input-underline">
            <option value="normal" className="bg-site-dark text-white">Обычный</option>
            <option value="elite" className="bg-site-dark text-white">Элитный</option>
            <option value="boss" className="bg-site-dark text-white">Босс</option>
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Уровень</span>
          <input type="number" name="level" value={form.level} onChange={handleChange} min={1} className="input-underline" />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Раса</span>
          <select name="id_race" value={form.id_race} onChange={handleChange} className="input-underline">
            {NPC_RACES.map((r) => (
              <option key={r.value} value={r.value} className="bg-site-dark text-white">{r.label}</option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Подраса</span>
          <input type="number" name="id_subrace" value={form.id_subrace} onChange={handleChange} min={1} className="input-underline" />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Класс</span>
          <select name="id_class" value={form.id_class} onChange={handleChange} className="input-underline">
            {NPC_CLASSES.map((c) => (
              <option key={c.value} value={c.value} className="bg-site-dark text-white">{c.label}</option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Пол</span>
          <select name="sex" value={form.sex} onChange={handleChange} className="input-underline">
            {NPC_SEXES.map((s) => (
              <option key={s.value} value={s.value} className="bg-site-dark text-white">{s.label}</option>
            ))}
          </select>
        </label>

        {/* Avatar upload */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Аватар</span>
          <div className="flex items-center gap-3">
            {avatarPreview && (
              <img
                src={avatarPreview}
                alt="Превью"
                className="w-12 h-12 rounded-full object-cover shrink-0 border border-white/20"
              />
            )}
            <input
              type="file"
              accept="image/*"
              onChange={handleAvatarFile}
              className="text-sm text-white/70 file:mr-3 file:py-1.5 file:px-4 file:rounded file:border-0 file:text-sm file:bg-white/10 file:text-white/70 hover:file:bg-white/20 file:cursor-pointer"
            />
          </div>
        </label>
      </div>

      {/* Description */}
      <label className="flex flex-col gap-1">
        <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Описание</span>
        <textarea name="description" value={form.description} onChange={handleChange} rows={3} className="textarea-bordered" />
      </label>

      {/* Rewards */}
      <div>
        <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em] mb-3">Награды</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Опыт (XP)</span>
            <input type="number" name="xp_reward" value={form.xp_reward} onChange={handleChange} min={0} className="input-underline" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Золото</span>
            <input type="number" name="gold_reward" value={form.gold_reward} onChange={handleChange} min={0} className="input-underline" />
          </label>
        </div>
      </div>

      {/* Base attributes */}
      <div>
        <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em] mb-3">Базовые атрибуты</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
          {STAT_KEYS.map(({ key, label }) => (
            <label key={key} className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">{label}</span>
              <input
                type="number"
                value={form.base_attributes[key] ?? 0}
                onChange={(e) => handleAttrChange(key, e.target.value)}
                min={0}
                className="input-underline"
              />
            </label>
          ))}
        </div>
      </div>

      {/* Respawn */}
      <div>
        <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em] mb-3">Респавн</h3>
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              name="respawn_enabled"
              checked={form.respawn_enabled}
              onChange={handleChange}
              className="w-4 h-4 accent-gold"
            />
            <span className="text-white text-sm">Включить респавн</span>
          </label>
          {form.respawn_enabled && (
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Таймер (сек)</span>
              <input
                type="number"
                value={form.respawn_seconds ?? ''}
                onChange={(e) => setForm((prev) => ({
                  ...prev,
                  respawn_seconds: e.target.value === '' ? null : Number(e.target.value),
                }))}
                min={0}
                className="input-underline w-[140px]"
                placeholder="300"
              />
            </label>
          )}
        </div>
      </div>

      {/* Buttons */}
      <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 pt-2">
        <button type="submit" disabled={saving} className="btn-blue !text-base !px-8 !py-2 disabled:opacity-50">
          {saving ? 'Сохранение...' : editingId ? 'Сохранить' : 'Создать'}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="btn-line !w-auto !px-8"
        >
          Отмена
        </button>
      </div>
    </form>
  );
};

export default AdminMobTemplateForm;
