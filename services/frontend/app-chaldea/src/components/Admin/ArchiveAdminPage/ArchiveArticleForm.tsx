import { useState, useEffect } from "react";
import {
  createArticle,
  updateArticle,
  uploadArchiveImage,
  fetchCategories,
} from "../../../api/archive";
import type {
  ArchiveArticle,
  ArchiveCategoryWithCount,
} from "../../../api/archive";
import WysiwygEditor from "../../CommonComponents/WysiwygEditor/WysiwygEditor";
import toast from "react-hot-toast";

/* ── Props ── */

interface ArchiveArticleFormProps {
  article?: ArchiveArticle;
  onSuccess: () => void;
  onCancel: () => void;
}

/* ── Slug generator ── */

const generateSlug = (title: string): string => {
  const translitMap: Record<string, string> = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "j", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
  };

  return title
    .toLowerCase()
    .split("")
    .map((ch) => translitMap[ch] ?? ch)
    .join("")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
};

const ArchiveArticleForm = ({ article, onSuccess, onCancel }: ArchiveArticleFormProps) => {
  const editMode = Boolean(article);

  const [title, setTitle] = useState(article?.title ?? "");
  const [slug, setSlug] = useState(article?.slug ?? "");
  const [summary, setSummary] = useState(article?.summary ?? "");
  const [content, setContent] = useState(article?.content ?? "");
  const [coverImageUrl, setCoverImageUrl] = useState(article?.cover_image_url ?? "");
  const [isFeatured, setIsFeatured] = useState(article?.is_featured ?? false);
  const [featuredSortOrder, setFeaturedSortOrder] = useState(article?.featured_sort_order ?? 0);
  const [selectedCategoryIds, setSelectedCategoryIds] = useState<number[]>(
    article?.categories.map((c) => c.id) ?? []
  );

  const [categories, setCategories] = useState<ArchiveCategoryWithCount[]>([]);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchCategories()
      .then(setCategories)
      .catch((e: Error) => toast.error(e.message || "Не удалось загрузить категории"));
  }, []);

  const handleGenerateSlug = () => {
    if (!title.trim()) {
      toast.error("Введите название для генерации slug");
      return;
    }
    setSlug(generateSlug(title));
  };

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const result = await uploadArchiveImage(file);
      setCoverImageUrl(result.image_url);
      toast.success("Изображение загружено");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка загрузки изображения";
      toast.error(msg);
    } finally {
      setUploading(false);
    }
  };

  const toggleCategory = (catId: number) => {
    setSelectedCategoryIds((prev) =>
      prev.includes(catId) ? prev.filter((id) => id !== catId) : [...prev, catId]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!title.trim()) {
      toast.error("Название не может быть пустым");
      return;
    }
    if (!slug.trim()) {
      toast.error("Slug не может быть пустым");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        title: title.trim(),
        slug: slug.trim(),
        content,
        summary: summary.trim() || undefined,
        cover_image_url: coverImageUrl || undefined,
        is_featured: isFeatured,
        featured_sort_order: featuredSortOrder,
        category_ids: selectedCategoryIds,
      };

      if (editMode && article) {
        await updateArticle(article.id, payload);
      } else {
        await createArticle(payload);
      }

      toast.success(editMode ? "Статья сохранена" : "Статья создана");
      onSuccess();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка при сохранении";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="gray-bg p-6 flex flex-col gap-6" onSubmit={handleSubmit}>
      <h2 className="gold-text text-2xl font-medium uppercase tracking-[0.06em]">
        {editMode ? "Редактирование статьи" : "Создание статьи"}
      </h2>

      {/* Title + Slug */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Название *
          </span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            className="input-underline"
            placeholder="Название статьи"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Slug *
          </span>
          <div className="flex gap-2 items-end">
            <input
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              required
              className="input-underline flex-1"
              placeholder="url-slug"
            />
            <button
              type="button"
              onClick={handleGenerateSlug}
              className="text-xs text-site-blue hover:text-white transition-colors duration-200 whitespace-nowrap pb-1"
            >
              Из названия
            </button>
          </div>
        </label>
      </div>

      {/* Summary */}
      <label className="flex flex-col gap-1">
        <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
          Краткое описание (макс. 500 символов)
        </span>
        <textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value.slice(0, 500))}
          maxLength={500}
          rows={3}
          className="textarea-bordered"
          placeholder="Краткое описание для превью при наведении..."
        />
        <span className="text-xs text-white/30 self-end">{summary.length}/500</span>
      </label>

      {/* Cover image */}
      <div className="flex flex-col gap-1">
        <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
          Обложка
        </span>
        {coverImageUrl && (
          <div className="flex items-start gap-3 mb-2">
            <img
              src={coverImageUrl}
              alt="Обложка"
              className="w-[200px] h-[120px] object-cover rounded-[10px]"
            />
            <button
              type="button"
              onClick={() => setCoverImageUrl("")}
              className="text-xs text-site-red hover:text-white transition-colors duration-200"
            >
              Удалить
            </button>
          </div>
        )}
        <input
          type="file"
          accept="image/*"
          onChange={handleImageUpload}
          disabled={uploading}
          className="text-white text-sm file:mr-4 file:py-2 file:px-4 file:rounded-card file:border-0 file:text-sm file:font-medium file:bg-white/[0.07] file:text-white hover:file:bg-white/[0.12] file:cursor-pointer file:transition-colors"
        />
        {uploading && <span className="text-xs text-white/50">Загрузка...</span>}
      </div>

      {/* Categories */}
      <div className="flex flex-col gap-2">
        <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
          Категории
        </span>
        {categories.length === 0 ? (
          <p className="text-white/30 text-sm">Нет доступных категорий</p>
        ) : (
          <div className="flex flex-wrap gap-3">
            {categories.map((cat) => (
              <label
                key={cat.id}
                className="flex items-center gap-2 cursor-pointer group"
              >
                <input
                  type="checkbox"
                  checked={selectedCategoryIds.includes(cat.id)}
                  onChange={() => toggleCategory(cat.id)}
                  className="w-4 h-4 rounded bg-transparent border border-white/20 accent-site-blue"
                />
                <span className="text-sm text-white/70 group-hover:text-white transition-colors duration-200">
                  {cat.name}
                </span>
              </label>
            ))}
          </div>
        )}
      </div>

      {/* Featured */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={isFeatured}
            onChange={(e) => setIsFeatured(e.target.checked)}
            className="w-4 h-4 rounded bg-transparent border border-white/20 accent-site-blue"
          />
          <span className="text-white/70 text-sm">Избранная статья (featured)</span>
        </label>

        {isFeatured && (
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Порядок сортировки (featured)
            </span>
            <input
              type="number"
              value={featuredSortOrder}
              onChange={(e) => setFeaturedSortOrder(Number(e.target.value))}
              className="input-underline"
            />
          </label>
        )}
      </div>

      {/* WYSIWYG editor */}
      <div className="flex flex-col gap-1">
        <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
          Содержание
        </span>
        <WysiwygEditor content={content} onChange={setContent} enableArchiveLinks />
      </div>

      {/* Buttons */}
      <div className="flex gap-4 pt-2">
        <button
          type="submit"
          disabled={saving}
          className="btn-blue !text-base !px-8 !py-2 disabled:opacity-50"
        >
          {saving
            ? "Сохранение..."
            : editMode
              ? "Сохранить"
              : "Создать"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="btn-line !w-auto !px-8"
        >
          Отмена
        </button>
      </div>
    </form>
  );
};

export default ArchiveArticleForm;
