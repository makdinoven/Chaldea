import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { motion } from 'motion/react';
import {
  adminCreateBackground,
  adminUpdateBackground,
  adminUploadBackgroundImage,
} from '../../../api/cosmetics';
import type {
  CosmeticBackground,
  CosmeticBackgroundType,
  CosmeticRarity,
} from '../../../types/cosmetics';

/* ── Dictionaries ── */

const BG_TYPES: { value: CosmeticBackgroundType; label: string }[] = [
  { value: 'css', label: 'CSS' },
  { value: 'image', label: 'Изображение' },
];

const RARITIES: { value: CosmeticRarity; label: string }[] = [
  { value: 'common', label: 'Обычная' },
  { value: 'rare', label: 'Редкая' },
  { value: 'epic', label: 'Эпическая' },
  { value: 'legendary', label: 'Легендарная' },
];

/* ── Form state ── */

interface BgFormState {
  name: string;
  slug: string;
  type: CosmeticBackgroundType;
  css_class: string;
  image_url: string;
  rarity: CosmeticRarity;
  is_default: boolean;
}

const INITIAL: BgFormState = {
  name: '',
  slug: '',
  type: 'css',
  css_class: '',
  image_url: '',
  rarity: 'common',
  is_default: false,
};

/* ── Helpers ── */

const toSlug = (name: string): string =>
  name
    .toLowerCase()
    .replace(/[^a-z0-9а-яё\s-]/gi, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .slice(0, 50);

/* ── Props ── */

interface BackgroundEditorProps {
  background?: CosmeticBackground | null;
  onSuccess: () => void;
  onCancel: () => void;
}

/* ── Component ── */

const BackgroundEditor = ({ background, onSuccess, onCancel }: BackgroundEditorProps) => {
  const editMode = Boolean(background);
  const [form, setForm] = useState<BgFormState>(INITIAL);
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (background) {
      setForm({
        name: background.name,
        slug: background.slug,
        type: background.type,
        css_class: background.css_class ?? '',
        image_url: background.image_url ?? '',
        rarity: background.rarity,
        is_default: background.is_default,
      });
    } else {
      setForm(INITIAL);
    }
  }, [background]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>,
  ) => {
    const target = e.target;
    const name = target.name;
    const value =
      target instanceof HTMLInputElement && target.type === 'checkbox'
        ? target.checked
        : target.value;
    setForm((s) => {
      const next = { ...s, [name]: value };
      if (name === 'name' && !editMode) {
        next.slug = toSlug(String(value));
      }
      return next;
    });
  };

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const res = await adminUploadBackgroundImage(file);
      setForm((s) => ({ ...s, image_url: res.data.url }));
      toast.success('Изображение загружено');
    } catch {
      toast.error('Не удалось загрузить изображение');
    } finally {
      setUploading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) {
      toast.error('Название обязательно');
      return;
    }
    if (!form.slug.trim()) {
      toast.error('Slug обязателен');
      return;
    }
    if (form.type === 'css' && !form.css_class.trim()) {
      toast.error('CSS-класс обязателен для типа CSS');
      return;
    }
    if (form.type === 'image' && !form.image_url.trim()) {
      toast.error('Изображение обязательно для типа Изображение');
      return;
    }

    const payload = {
      name: form.name.trim(),
      slug: form.slug.trim(),
      type: form.type,
      css_class: form.css_class.trim() || null,
      image_url: form.image_url.trim() || null,
      rarity: form.rarity,
      is_default: form.is_default,
    };

    setSubmitting(true);
    try {
      if (editMode && background) {
        await adminUpdateBackground(background.id, payload);
        toast.success('Подложка обновлена');
      } else {
        await adminCreateBackground(payload);
        toast.success('Подложка создана');
      }
      onSuccess();
    } catch {
      toast.error(editMode ? 'Ошибка при обновлении подложки' : 'Ошибка при создании подложки');
    } finally {
      setSubmitting(false);
    }
  };

  const showCssField = form.type === 'css';
  const showImageField = form.type === 'image';

  return (
    <motion.form
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="gray-bg p-6 flex flex-col gap-6"
      onSubmit={handleSubmit}
    >
      <h2 className="gold-text text-2xl font-medium uppercase tracking-[0.06em]">
        {editMode ? 'Редактирование подложки' : 'Создание подложки'}
      </h2>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {/* Name */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Название
          </span>
          <input
            name="name"
            value={form.name}
            onChange={handleChange}
            required
            className="input-underline"
            placeholder="Тёмно-синий градиент"
          />
        </label>

        {/* Slug */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Slug
          </span>
          <input
            name="slug"
            value={form.slug}
            onChange={handleChange}
            required
            className="input-underline"
            placeholder="dark-blue"
          />
        </label>

        {/* Type */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Тип
          </span>
          <select
            name="type"
            value={form.type}
            onChange={handleChange}
            className="input-underline"
          >
            {BG_TYPES.map((t) => (
              <option key={t.value} value={t.value} className="bg-site-dark text-white">
                {t.label}
              </option>
            ))}
          </select>
        </label>

        {/* CSS Class */}
        {showCssField && (
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              CSS-класс
            </span>
            <input
              name="css_class"
              value={form.css_class}
              onChange={handleChange}
              className="input-underline"
              placeholder="bg-msg-dark-blue"
            />
          </label>
        )}

        {/* Rarity */}
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Редкость
          </span>
          <select
            name="rarity"
            value={form.rarity}
            onChange={handleChange}
            className="input-underline"
          >
            {RARITIES.map((r) => (
              <option key={r.value} value={r.value} className="bg-site-dark text-white">
                {r.label}
              </option>
            ))}
          </select>
        </label>

        {/* Is Default */}
        <label className="flex items-center gap-3 self-end pb-2">
          <input
            type="checkbox"
            name="is_default"
            checked={form.is_default}
            onChange={handleChange}
            className="w-5 h-5 accent-site-blue"
          />
          <span className="text-sm text-white">По умолчанию</span>
        </label>
      </div>

      {/* Image Upload */}
      {showImageField && (
        <fieldset className="border border-white/10 rounded-card p-4 bg-white/[0.03]">
          <legend className="text-white/50 text-xs font-medium uppercase tracking-[0.06em] px-2">
            Изображение подложки
          </legend>
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 mt-2">
            <label className="btn-blue !text-sm !px-4 !py-1.5 cursor-pointer inline-block">
              {uploading ? 'Загрузка...' : 'Загрузить изображение'}
              <input
                type="file"
                accept="image/png,image/gif,image/webp,image/jpeg"
                onChange={handleImageUpload}
                className="hidden"
                disabled={uploading}
              />
            </label>
            {form.image_url && (
              <div className="flex items-center gap-3">
                <img
                  src={form.image_url}
                  alt="Превью"
                  className="w-24 h-12 rounded-card object-cover border border-white/10"
                />
                <span className="text-xs text-white/40 break-all max-w-[200px]">
                  {form.image_url}
                </span>
              </div>
            )}
          </div>
        </fieldset>
      )}

      {/* Preview — message bubble with background */}
      {(form.css_class || form.image_url) && (
        <fieldset className="border border-white/10 rounded-card p-4 bg-white/[0.03]">
          <legend className="text-white/50 text-xs font-medium uppercase tracking-[0.06em] px-2">
            Превью сообщения
          </legend>
          <div className="mt-2 max-w-[320px]">
            <div
              className={`rounded-card px-4 py-3 ${form.css_class || ''}`}
              style={
                form.image_url
                  ? {
                      backgroundImage: `url(${form.image_url})`,
                      backgroundSize: 'cover',
                      backgroundPosition: 'center',
                    }
                  : undefined
              }
            >
              <p className="text-white text-sm">Пример сообщения в чате</p>
              <p className="text-white/50 text-xs mt-1">Персонаж, 12:00</p>
            </div>
          </div>
        </fieldset>
      )}

      {/* Buttons */}
      <div className="flex gap-4 pt-2">
        <button
          type="submit"
          disabled={submitting}
          className="btn-blue !text-base !px-8 !py-2"
        >
          {submitting
            ? 'Сохранение...'
            : editMode
              ? 'Сохранить'
              : 'Создать'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="btn-line !w-auto !px-8"
        >
          Отмена
        </button>
      </div>
    </motion.form>
  );
};

export default BackgroundEditor;
