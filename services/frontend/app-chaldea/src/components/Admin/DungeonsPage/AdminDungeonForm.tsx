import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  createDungeon,
  updateDungeon,
  fetchDungeonDetail,
  selectCurrentDungeon,
  selectDetailLoading,
  selectDungeonSaving,
  clearCurrentDungeon,
} from '../../../redux/slices/dungeonAdminSlice';
import type { DungeonCreate } from '../../../api/dungeons';

interface FormData {
  name: string;
  description: string;
  lore_text: string;
  stability_type: 'static' | 'unstable' | 'chaotic';
  danger_level: 'safe' | 'deadly';
  location_id: number;
  recommended_level: number | null;
  recommended_party_size: number | null;
  cooldown_hours: number;
  mob_multiplier: number;
  loot_multiplier: number;
  stamina_multiplier: number;
  difficulty_modifier: number;
  disable_rest_rooms: boolean;
  disable_merchants: boolean;
  mana_core_chance: number;
  mana_core_item_id: number | null;
  image_url: string;
}

const INITIAL_FORM: FormData = {
  name: '',
  description: '',
  lore_text: '',
  stability_type: 'static',
  danger_level: 'safe',
  location_id: 0,
  recommended_level: 1,
  recommended_party_size: 1,
  cooldown_hours: 24,
  mob_multiplier: 1.0,
  loot_multiplier: 1.0,
  stamina_multiplier: 1.0,
  difficulty_modifier: 1.0,
  disable_rest_rooms: false,
  disable_merchants: false,
  mana_core_chance: 0.0,
  mana_core_item_id: null,
  image_url: '',
};

const STABILITY_OPTIONS = [
  { value: 'static', label: 'Статичный (Изученный)' },
  { value: 'unstable', label: 'Нестабильный (Опасный)' },
  { value: 'chaotic', label: 'Хаотичный (Смертельный)' },
] as const;

const DANGER_OPTIONS = [
  { value: 'safe', label: 'Безопасный' },
  { value: 'deadly', label: 'Смертельный' },
] as const;

const AdminDungeonForm = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const editingId = id ? Number(id) : null;

  const currentDungeon = useAppSelector(selectCurrentDungeon);
  const detailLoading = useAppSelector(selectDetailLoading);
  const saving = useAppSelector(selectDungeonSaving);

  const [form, setForm] = useState<FormData>(INITIAL_FORM);

  useEffect(() => {
    if (editingId) {
      dispatch(fetchDungeonDetail(editingId));
    }
    return () => {
      dispatch(clearCurrentDungeon());
    };
  }, [dispatch, editingId]);

  useEffect(() => {
    if (editingId && currentDungeon && currentDungeon.id === editingId) {
      setForm({
        name: currentDungeon.name || '',
        description: currentDungeon.description || '',
        lore_text: currentDungeon.lore_text || '',
        stability_type: currentDungeon.stability_type || 'static',
        danger_level: currentDungeon.danger_level || 'safe',
        location_id: currentDungeon.location_id || 0,
        recommended_level: currentDungeon.recommended_level,
        recommended_party_size: currentDungeon.recommended_party_size,
        cooldown_hours: currentDungeon.cooldown_hours ?? 24,
        mob_multiplier: currentDungeon.mob_multiplier ?? 1.0,
        loot_multiplier: currentDungeon.loot_multiplier ?? 1.0,
        stamina_multiplier: currentDungeon.stamina_multiplier ?? 1.0,
        difficulty_modifier: currentDungeon.difficulty_modifier ?? 1.0,
        disable_rest_rooms: currentDungeon.disable_rest_rooms ?? false,
        disable_merchants: currentDungeon.disable_merchants ?? false,
        mana_core_chance: currentDungeon.mana_core_chance ?? 0.0,
        mana_core_item_id: currentDungeon.mana_core_item_id,
        image_url: currentDungeon.image_url || '',
      });
    }
  }, [editingId, currentDungeon]);

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

  const handleNullableNumber = (name: keyof FormData, value: string) => {
    setForm((prev) => ({
      ...prev,
      [name]: value === '' ? null : Number(value),
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!form.name.trim()) {
      toast.error('Название подземелья обязательно');
      return;
    }
    if (!form.description.trim()) {
      toast.error('Описание подземелья обязательно');
      return;
    }
    if (!form.location_id || form.location_id <= 0) {
      toast.error('Укажите ID локации');
      return;
    }

    const payload: DungeonCreate = {
      name: form.name,
      description: form.description,
      lore_text: form.lore_text || null,
      stability_type: form.stability_type,
      danger_level: form.danger_level,
      location_id: form.location_id,
      recommended_level: form.recommended_level,
      recommended_party_size: form.recommended_party_size,
      cooldown_hours: form.cooldown_hours,
      mob_multiplier: form.mob_multiplier,
      loot_multiplier: form.loot_multiplier,
      stamina_multiplier: form.stamina_multiplier,
      difficulty_modifier: form.difficulty_modifier,
      disable_rest_rooms: form.disable_rest_rooms,
      disable_merchants: form.disable_merchants,
      mana_core_chance: form.mana_core_chance,
      mana_core_item_id: form.mana_core_item_id,
      image_url: form.image_url || null,
    };

    try {
      if (editingId) {
        await dispatch(updateDungeon({ id: editingId, payload })).unwrap();
      } else {
        await dispatch(createDungeon(payload)).unwrap();
      }
      navigate('/admin/dungeons');
    } catch {
      // Error already shown by thunk
    }
  };

  if (detailLoading) {
    return (
      <div className="w-full max-w-[1240px] mx-auto gray-bg p-6 flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="w-full max-w-[1240px] mx-auto flex flex-col gap-6">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em]">
        {editingId ? 'Редактирование подземелья' : 'Создание подземелья'}
      </h1>

      <form className="gray-bg p-4 sm:p-6 flex flex-col gap-5" onSubmit={handleSubmit}>
        {/* Basic fields */}
        <div>
          <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em] mb-3">Основное</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5">
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Название *</span>
              <input name="name" value={form.name} onChange={handleChange} required className="input-underline" />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Тип стабильности</span>
              <select name="stability_type" value={form.stability_type} onChange={handleChange} className="input-underline">
                {STABILITY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value} className="bg-site-dark text-white">{opt.label}</option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Уровень опасности</span>
              <select name="danger_level" value={form.danger_level} onChange={handleChange} className="input-underline">
                {DANGER_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value} className="bg-site-dark text-white">{opt.label}</option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">ID локации *</span>
              <input
                type="number"
                name="location_id"
                value={form.location_id || ''}
                onChange={handleChange}
                min={1}
                required
                className="input-underline"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Рекомендуемый уровень</span>
              <input
                type="number"
                value={form.recommended_level ?? ''}
                onChange={(e) => handleNullableNumber('recommended_level', e.target.value)}
                min={1}
                className="input-underline"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Рекомендуемый размер группы</span>
              <input
                type="number"
                value={form.recommended_party_size ?? ''}
                onChange={(e) => handleNullableNumber('recommended_party_size', e.target.value)}
                min={1}
                max={4}
                className="input-underline"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Кулдаун (часы)</span>
              <input
                type="number"
                name="cooldown_hours"
                value={form.cooldown_hours}
                onChange={handleChange}
                min={0}
                className="input-underline"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">URL изображения</span>
              <input
                name="image_url"
                value={form.image_url}
                onChange={handleChange}
                placeholder="https://..."
                className="input-underline"
              />
            </label>
          </div>
        </div>

        {/* Description */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Описание *</span>
          <textarea
            name="description"
            value={form.description}
            onChange={handleChange}
            rows={3}
            required
            className="textarea-bordered"
          />
        </label>

        {/* Lore text */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Лор-текст (показывается при входе)</span>
          <textarea
            name="lore_text"
            value={form.lore_text}
            onChange={handleChange}
            rows={3}
            className="textarea-bordered"
          />
        </label>

        {/* Modifiers */}
        <div>
          <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em] mb-3">Модификаторы</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Множитель мобов</span>
              <input
                type="number"
                name="mob_multiplier"
                value={form.mob_multiplier}
                onChange={handleChange}
                min={0.1}
                step={0.1}
                className="input-underline"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Множитель лута</span>
              <input
                type="number"
                name="loot_multiplier"
                value={form.loot_multiplier}
                onChange={handleChange}
                min={0.1}
                step={0.1}
                className="input-underline"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Множитель стамины</span>
              <input
                type="number"
                name="stamina_multiplier"
                value={form.stamina_multiplier}
                onChange={handleChange}
                min={0.1}
                step={0.1}
                className="input-underline"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Модификатор сложности</span>
              <input
                type="number"
                name="difficulty_modifier"
                value={form.difficulty_modifier}
                onChange={handleChange}
                min={0.1}
                step={0.1}
                className="input-underline"
              />
            </label>
          </div>
        </div>

        {/* Toggles */}
        <div>
          <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em] mb-3">Ограничения</h3>
          <div className="flex flex-col sm:flex-row gap-4 sm:gap-6">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                name="disable_rest_rooms"
                checked={form.disable_rest_rooms}
                onChange={handleChange}
                className="w-4 h-4 accent-gold"
              />
              <span className="text-white text-sm">Отключить комнаты отдыха</span>
            </label>

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                name="disable_merchants"
                checked={form.disable_merchants}
                onChange={handleChange}
                className="w-4 h-4 accent-gold"
              />
              <span className="text-white text-sm">Отключить торговцев</span>
            </label>
          </div>
        </div>

        {/* Mana Core */}
        <div>
          <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em] mb-3">Ядро маны</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Шанс ядра маны (0.0 - 1.0)</span>
              <input
                type="number"
                name="mana_core_chance"
                value={form.mana_core_chance}
                onChange={handleChange}
                min={0}
                max={1}
                step={0.01}
                className="input-underline"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">ID предмета (Кристалл подземелья)</span>
              <input
                type="number"
                value={form.mana_core_item_id ?? ''}
                onChange={(e) => handleNullableNumber('mana_core_item_id', e.target.value)}
                min={1}
                className="input-underline"
                placeholder="Не задано"
              />
            </label>
          </div>
        </div>

        {/* Buttons */}
        <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 pt-2">
          <button type="submit" disabled={saving} className="btn-blue !text-base !px-8 !py-2 disabled:opacity-50">
            {saving ? 'Сохранение...' : editingId ? 'Сохранить' : 'Создать'}
          </button>
          <button
            type="button"
            onClick={() => navigate('/admin/dungeons')}
            className="btn-line !w-auto !px-8"
          >
            Отмена
          </button>
        </div>
      </form>
    </div>
  );
};

export default AdminDungeonForm;
