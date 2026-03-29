import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { motion } from 'motion/react';
import {
  adminCreateFrame,
  adminUpdateFrame,
  adminUploadFrameImage,
} from '../../../api/cosmetics';
import type {
  CosmeticFrame,
  CosmeticFrameType,
  CosmeticRarity,
} from '../../../types/cosmetics';

/* ── Dictionaries ── */

const FRAME_TYPES: { value: CosmeticFrameType; label: string }[] = [
  { value: 'css', label: 'CSS' },
  { value: 'image', label: 'Изображение' },
  { value: 'combo', label: 'Комбо (CSS + Изображение)' },
];

const RARITIES: { value: CosmeticRarity; label: string }[] = [
  { value: 'common', label: 'Обычная' },
  { value: 'rare', label: 'Редкая' },
  { value: 'epic', label: 'Эпическая' },
  { value: 'legendary', label: 'Легендарная' },
];

/* ── Form state ── */

interface FrameFormState {
  name: string;
  slug: string;
  type: CosmeticFrameType;
  css_class: string;
  image_url: string;
  rarity: CosmeticRarity;
  is_default: boolean;
  is_seasonal: boolean;
}

const INITIAL: FrameFormState = {
  name: '',
  slug: '',
  type: 'css',
  css_class: '',
  image_url: '',
  rarity: 'common',
  is_default: false,
  is_seasonal: false,
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

interface FrameEditorProps {
  frame?: CosmeticFrame | null;
  onSuccess: () => void;
  onCancel: () => void;
}

/* ── Component ── */

const FrameEditor = ({ frame, onSuccess, onCancel }: FrameEditorProps) => {
  const editMode = Boolean(frame);
  const [form, setForm] = useState<FrameFormState>(INITIAL);
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (frame) {
      setForm({
        name: frame.name,
        slug: frame.slug,
        type: frame.type,
        css_class: frame.css_class ?? '',
        image_url: frame.image_url ?? '',
        rarity: frame.rarity,
        is_default: frame.is_default,
        is_seasonal: frame.is_seasonal,
      });
    } else {
      setForm(INITIAL);
    }
  }, [frame]);

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
      // Auto-generate slug from name on create
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
      const res = await adminUploadFrameImage(file);
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
    if ((form.type === 'css' || form.type === 'combo') && !form.css_class.trim()) {
      toast.error('CSS-класс обязателен для типа CSS / Комбо');
      return;
    }
    if ((form.type === 'image' || form.type === 'combo') && !form.image_url.trim()) {
      toast.error('Изображение обязательно для типа Изображение / Комбо');
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
      is_seasonal: form.is_seasonal,
    };

    setSubmitting(true);
    try {
      if (editMode && frame) {
        await adminUpdateFrame(frame.id, payload);
        toast.success('Рамка обновлена');
      } else {
        await adminCreateFrame(payload);
        toast.success('Рамка создана');
      }
      onSuccess();
    } catch {
      toast.error(editMode ? 'Ошибка при обновлении рамки' : 'Ошибка при создании рамки');
    } finally {
      setSubmitting(false);
    }
  };

  const showCssField = form.type === 'css' || form.type === 'combo';
  const showImageField = form.type === 'image' || form.type === 'combo';

  return (
    <motion.form
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="gray-bg p-6 flex flex-col gap-6"
      onSubmit={handleSubmit}
    >
      <h2 className="gold-text text-2xl font-medium uppercase tracking-[0.06em]">
        {editMode ? 'Редактирование рамки' : 'Создание рамки'}
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
            placeholder="Золотое свечение"
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
            placeholder="golden-glow"
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
            {FRAME_TYPES.map((t) => (
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
              placeholder="frame-golden-glow"
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

        {/* Is Seasonal */}
        <label className="flex items-center gap-3 self-end pb-2">
          <input
            type="checkbox"
            name="is_seasonal"
            checked={form.is_seasonal}
            onChange={handleChange}
            className="w-5 h-5 accent-site-blue"
          />
          <span className="text-sm text-white">Сезонная</span>
        </label>
      </div>

      {/* Image Upload */}
      {showImageField && (
        <fieldset className="border border-white/10 rounded-card p-4 bg-white/[0.03]">
          <legend className="text-white/50 text-xs font-medium uppercase tracking-[0.06em] px-2">
            Изображение рамки
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
                  className="w-16 h-16 rounded-card object-contain border border-white/10"
                />
                <span className="text-xs text-white/40 break-all max-w-[200px]">
                  {form.image_url}
                </span>
              </div>
            )}
          </div>
        </fieldset>
      )}

      {/* Preview */}
      {(form.css_class || form.image_url) && (
        <fieldset className="border border-white/10 rounded-card p-4 bg-white/[0.03]">
          <legend className="text-white/50 text-xs font-medium uppercase tracking-[0.06em] px-2">
            Превью
          </legend>
          <div className="flex items-center gap-4 mt-2">
            <div className={`relative w-16 h-16 rounded-full ${form.css_class || ''}`}>
              <div className="w-full h-full rounded-full bg-white/10 flex items-center justify-center text-white/50 text-xs">
                Аватар
              </div>
              {form.image_url && (
                <img
                  src={form.image_url}
                  alt="Frame"
                  className="absolute inset-0 w-full h-full object-contain pointer-events-none"
                />
              )}
            </div>
            <span className="text-sm text-white/60">
              {form.css_class && <span className="text-white/40">Класс: {form.css_class}</span>}
            </span>
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

export default FrameEditor;
