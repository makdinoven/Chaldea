import { useState, useEffect } from "react";
import {
  fetchCategories,
  createCategory,
  updateCategory,
  deleteCategory,
  reorderCategories,
} from "../../../api/archive";
import type { ArchiveCategoryWithCount } from "../../../api/archive";
import toast from "react-hot-toast";
import { motion } from "motion/react";

/* ── Slug generator (same as article form) ── */

const generateSlug = (name: string): string => {
  const translitMap: Record<string, string> = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "j", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
  };

  return name
    .toLowerCase()
    .split("")
    .map((ch) => translitMap[ch] ?? ch)
    .join("")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
};

/* ── Inline edit state ── */

interface EditState {
  id: number;
  name: string;
  slug: string;
  description: string;
  sort_order: number;
}

/* ── New category state ── */

interface NewCategoryState {
  name: string;
  slug: string;
  description: string;
  sort_order: number;
}

const emptyNew: NewCategoryState = { name: "", slug: "", description: "", sort_order: 0 };

const ArchiveCategoryManager = () => {
  const [categories, setCategories] = useState<ArchiveCategoryWithCount[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<EditState | null>(null);
  const [creating, setCreating] = useState(false);
  const [newCat, setNewCat] = useState<NewCategoryState>(emptyNew);
  const [deleteTarget, setDeleteTarget] = useState<ArchiveCategoryWithCount | null>(null);
  const [saving, setSaving] = useState(false);
  const [reorderDirty, setReorderDirty] = useState(false);

  const loadCategories = async () => {
    setLoading(true);
    try {
      const data = await fetchCategories();
      setCategories(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Не удалось загрузить категории";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCategories();
  }, []);

  /* ── Inline Edit ── */

  const startEdit = (cat: ArchiveCategoryWithCount) => {
    setEditing({
      id: cat.id,
      name: cat.name,
      slug: cat.slug,
      description: cat.description ?? "",
      sort_order: cat.sort_order,
    });
  };

  const cancelEdit = () => setEditing(null);

  const saveEdit = async () => {
    if (!editing) return;
    if (!editing.name.trim() || !editing.slug.trim()) {
      toast.error("Название и slug обязательны");
      return;
    }

    setSaving(true);
    try {
      await updateCategory(editing.id, {
        name: editing.name.trim(),
        slug: editing.slug.trim(),
        description: editing.description.trim() || undefined,
        sort_order: editing.sort_order,
      });
      toast.success("Категория обновлена");
      setEditing(null);
      await loadCategories();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка при сохранении";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  /* ── Create ── */

  const handleCreate = async () => {
    if (!newCat.name.trim() || !newCat.slug.trim()) {
      toast.error("Название и slug обязательны");
      return;
    }

    setSaving(true);
    try {
      await createCategory({
        name: newCat.name.trim(),
        slug: newCat.slug.trim(),
        description: newCat.description.trim() || undefined,
        sort_order: newCat.sort_order,
      });
      toast.success("Категория создана");
      setCreating(false);
      setNewCat(emptyNew);
      await loadCategories();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка при создании";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  /* ── Delete ── */

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteCategory(deleteTarget.id);
      setCategories((prev) => prev.filter((c) => c.id !== deleteTarget.id));
      toast.success("Категория удалена");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка при удалении";
      toast.error(msg);
    } finally {
      setDeleteTarget(null);
    }
  };

  /* ── Reorder ── */

  const handleSortOrderChange = (catId: number, newOrder: number) => {
    setCategories((prev) =>
      prev.map((c) => (c.id === catId ? { ...c, sort_order: newOrder } : c))
    );
    setReorderDirty(true);
  };

  const saveReorder = async () => {
    const order = categories.map((c) => ({ id: c.id, sort_order: c.sort_order }));
    try {
      await reorderCategories(order);
      toast.success("Порядок сохранён");
      setReorderDirty(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка при сохранении порядка";
      toast.error(msg);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      {/* Controls */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-3">
          {!creating && (
            <button
              className="btn-blue !text-base !px-6 !py-2"
              onClick={() => setCreating(true)}
            >
              Добавить категорию
            </button>
          )}
          {reorderDirty && (
            <button
              className="btn-blue !text-base !px-6 !py-2"
              onClick={saveReorder}
            >
              Сохранить порядок
            </button>
          )}
        </div>
      </div>

      {/* New category inline form */}
      {creating && (
        <div className="gray-bg p-4 flex flex-col gap-3">
          <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">
            Новая категория
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input
              value={newCat.name}
              onChange={(e) => setNewCat((s) => ({ ...s, name: e.target.value }))}
              placeholder="Название"
              className="input-underline"
            />
            <div className="flex gap-2 items-end">
              <input
                value={newCat.slug}
                onChange={(e) => setNewCat((s) => ({ ...s, slug: e.target.value }))}
                placeholder="slug"
                className="input-underline flex-1"
              />
              <button
                type="button"
                onClick={() => setNewCat((s) => ({ ...s, slug: generateSlug(s.name) }))}
                className="text-xs text-site-blue hover:text-white transition-colors duration-200 whitespace-nowrap pb-1"
              >
                Из названия
              </button>
            </div>
          </div>
          <input
            value={newCat.description}
            onChange={(e) => setNewCat((s) => ({ ...s, description: e.target.value }))}
            placeholder="Описание (необязательно)"
            className="input-underline"
          />
          <input
            type="number"
            value={newCat.sort_order}
            onChange={(e) => setNewCat((s) => ({ ...s, sort_order: Number(e.target.value) }))}
            placeholder="Порядок сортировки"
            className="input-underline w-32"
          />
          <div className="flex gap-3">
            <button
              className="btn-blue !text-sm !px-5 !py-1.5 disabled:opacity-50"
              onClick={handleCreate}
              disabled={saving}
            >
              {saving ? "Создание..." : "Создать"}
            </button>
            <button
              className="btn-line !w-auto !px-5 !text-sm"
              onClick={() => { setCreating(false); setNewCat(emptyNew); }}
            >
              Отмена
            </button>
          </div>
        </div>
      )}

      {/* Category list */}
      <div className="gray-bg overflow-hidden overflow-x-auto">
        {loading ? (
          <p className="text-center text-white/50 text-sm py-8">Загрузка...</p>
        ) : (
          <table className="w-full min-w-[500px]">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3 w-16">
                  Порядок
                </th>
                <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                  Название
                </th>
                <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3 hidden sm:table-cell">
                  Slug
                </th>
                <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3 hidden md:table-cell">
                  Описание
                </th>
                <th className="text-center text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                  Статей
                </th>
                <th className="text-right text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                  Действия
                </th>
              </tr>
            </thead>
            <motion.tbody
              initial="hidden"
              animate="visible"
              variants={{
                hidden: {},
                visible: { transition: { staggerChildren: 0.03 } },
              }}
            >
              {categories.map((cat) => (
                <motion.tr
                  key={cat.id}
                  variants={{
                    hidden: { opacity: 0, y: 6 },
                    visible: { opacity: 1, y: 0 },
                  }}
                  className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200"
                >
                  {editing?.id === cat.id ? (
                    /* Editing row */
                    <>
                      <td className="px-4 py-2">
                        <input
                          type="number"
                          value={editing.sort_order}
                          onChange={(e) =>
                            setEditing((s) => s && { ...s, sort_order: Number(e.target.value) })
                          }
                          className="input-underline w-14 text-sm"
                        />
                      </td>
                      <td className="px-4 py-2">
                        <input
                          value={editing.name}
                          onChange={(e) =>
                            setEditing((s) => s && { ...s, name: e.target.value })
                          }
                          className="input-underline text-sm w-full"
                        />
                      </td>
                      <td className="px-4 py-2 hidden sm:table-cell">
                        <input
                          value={editing.slug}
                          onChange={(e) =>
                            setEditing((s) => s && { ...s, slug: e.target.value })
                          }
                          className="input-underline text-sm w-full"
                        />
                      </td>
                      <td className="px-4 py-2 hidden md:table-cell">
                        <input
                          value={editing.description}
                          onChange={(e) =>
                            setEditing((s) => s && { ...s, description: e.target.value })
                          }
                          className="input-underline text-sm w-full"
                          placeholder="Описание"
                        />
                      </td>
                      <td className="px-4 py-2 text-center text-sm text-white/50">
                        {cat.article_count}
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex flex-col items-end gap-1.5">
                          <button
                            onClick={saveEdit}
                            disabled={saving}
                            className="text-sm text-site-blue hover:text-white transition-colors duration-200 disabled:opacity-50"
                          >
                            {saving ? "..." : "Сохранить"}
                          </button>
                          <button
                            onClick={cancelEdit}
                            className="text-sm text-white/50 hover:text-white transition-colors duration-200"
                          >
                            Отмена
                          </button>
                        </div>
                      </td>
                    </>
                  ) : (
                    /* Display row */
                    <>
                      <td className="px-4 py-3">
                        <input
                          type="number"
                          value={cat.sort_order}
                          onChange={(e) => handleSortOrderChange(cat.id, Number(e.target.value))}
                          className="bg-transparent border-b border-white/10 text-white/70 text-sm w-14 outline-none focus:border-site-blue transition-colors duration-200 py-0.5"
                        />
                      </td>
                      <td className="px-4 py-3 text-sm text-white">
                        {cat.name}
                      </td>
                      <td className="px-4 py-3 text-sm text-white/50 hidden sm:table-cell">
                        {cat.slug}
                      </td>
                      <td className="px-4 py-3 text-sm text-white/50 hidden md:table-cell">
                        {cat.description || <span className="text-white/20">--</span>}
                      </td>
                      <td className="px-4 py-3 text-center text-sm text-white/50">
                        {cat.article_count}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col items-end gap-1.5">
                          <button
                            onClick={() => startEdit(cat)}
                            className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                          >
                            Редактировать
                          </button>
                          <button
                            onClick={() => setDeleteTarget(cat)}
                            className="text-sm text-site-red hover:text-white transition-colors duration-200"
                          >
                            Удалить
                          </button>
                        </div>
                      </td>
                    </>
                  )}
                </motion.tr>
              ))}
            </motion.tbody>
          </table>
        )}

        {!loading && categories.length === 0 && (
          <p className="text-center text-white/50 text-sm py-8">
            Категории пока не добавлены
          </p>
        )}
      </div>

      {/* Delete confirmation modal */}
      {deleteTarget && (
        <div className="modal-overlay">
          <div className="modal-content gold-outline gold-outline-thick">
            <h2 className="gold-text text-2xl uppercase mb-4">
              Удаление категории
            </h2>
            <p className="text-white mb-2">
              Удалить категорию &laquo;{deleteTarget.name}&raquo;?
            </p>
            {deleteTarget.article_count > 0 && (
              <p className="text-site-red text-sm mb-4">
                В этой категории {deleteTarget.article_count} статей. Статьи не будут удалены,
                но потеряют привязку к этой категории.
              </p>
            )}
            <div className="flex gap-4 mt-4">
              <button
                className="btn-blue !text-base !px-6 !py-2"
                onClick={confirmDelete}
              >
                Удалить
              </button>
              <button
                className="btn-line !w-auto !px-6"
                onClick={() => setDeleteTarget(null)}
              >
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ArchiveCategoryManager;
