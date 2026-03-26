import { useState } from "react";
import ArchiveArticleForm from "./ArchiveArticleForm";
import ArchiveCategoryManager from "./ArchiveCategoryManager";
import type { ArchiveArticleListItem, ArchiveCategoryWithCount } from "../../../api/archive";
import {
  fetchArticles,
  fetchCategories,
  deleteArticle,
  fetchArticleBySlug,
} from "../../../api/archive";
import type { ArchiveArticle } from "../../../api/archive";
import { useEffect } from "react";
import toast from "react-hot-toast";
import { motion } from "motion/react";

type Tab = "articles" | "categories";

const ArchiveAdminPage = () => {
  const [tab, setTab] = useState<Tab>("articles");
  const [editingArticle, setEditingArticle] = useState<ArchiveArticle | undefined>();
  const [creating, setCreating] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const closeForm = () => {
    setEditingArticle(undefined);
    setCreating(false);
    setRefreshKey((k) => k + 1);
  };

  // If editing or creating, show the form
  if (editingArticle || creating) {
    return (
      <div className="w-full max-w-[1240px] mx-auto">
        <ArchiveArticleForm
          article={editingArticle}
          onSuccess={closeForm}
          onCancel={closeForm}
        />
      </div>
    );
  }

  return (
    <div className="w-full max-w-[1240px] mx-auto" key={refreshKey}>
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em] mb-6">
        Архив
      </h1>

      {/* Tabs */}
      <div className="flex gap-4 mb-6">
        <button
          onClick={() => setTab("articles")}
          className={`text-base font-medium uppercase tracking-[0.06em] pb-1 border-b-2 transition-colors duration-200 ${
            tab === "articles"
              ? "text-white border-site-blue"
              : "text-white/50 border-transparent hover:text-white"
          }`}
        >
          Статьи
        </button>
        <button
          onClick={() => setTab("categories")}
          className={`text-base font-medium uppercase tracking-[0.06em] pb-1 border-b-2 transition-colors duration-200 ${
            tab === "categories"
              ? "text-white border-site-blue"
              : "text-white/50 border-transparent hover:text-white"
          }`}
        >
          Категории
        </button>
      </div>

      {tab === "articles" && (
        <ArticlesList
          onEdit={async (article) => {
            try {
              const full = await fetchArticleBySlug(article.slug);
              setEditingArticle(full);
            } catch (err: unknown) {
              const msg = err instanceof Error ? err.message : "Не удалось загрузить статью";
              toast.error(msg);
            }
          }}
          onCreate={() => setCreating(true)}
        />
      )}

      {tab === "categories" && <ArchiveCategoryManager />}
    </div>
  );
};

/* ── Articles List Sub-component ── */

interface ArticlesListProps {
  onEdit: (article: ArchiveArticleListItem) => void;
  onCreate: () => void;
}

const ArticlesList = ({ onEdit, onCreate }: ArticlesListProps) => {
  const [articles, setArticles] = useState<ArchiveArticleListItem[]>([]);
  const [categories, setCategories] = useState<ArchiveCategoryWithCount[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ArchiveArticleListItem | null>(null);

  const perPage = 20;

  const loadArticles = async () => {
    setLoading(true);
    try {
      const result = await fetchArticles({
        search: search || undefined,
        category_slug: categoryFilter || undefined,
        page,
        per_page: perPage,
      });
      setArticles(result.articles);
      setTotal(result.total);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Не удалось загрузить статьи";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCategories()
      .then(setCategories)
      .catch((e: Error) => toast.error(e.message || "Не удалось загрузить категории"));
  }, []);

  useEffect(() => {
    loadArticles();
  }, [page, search, categoryFilter]);

  const handleSearch = (value: string) => {
    setSearch(value);
    setPage(1);
  };

  const handleCategoryChange = (value: string) => {
    setCategoryFilter(value);
    setPage(1);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteArticle(deleteTarget.id);
      setArticles((prev) => prev.filter((a) => a.id !== deleteTarget.id));
      setTotal((t) => t - 1);
      toast.success("Статья удалена");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка при удалении";
      toast.error(msg);
    } finally {
      setDeleteTarget(null);
    }
  };

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="flex flex-col gap-5">
      {/* Controls */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
        <input
          type="text"
          placeholder="Поиск по названию..."
          value={search}
          onChange={(e) => handleSearch(e.target.value)}
          className="input-underline flex-1"
        />
        <select
          value={categoryFilter}
          onChange={(e) => handleCategoryChange(e.target.value)}
          className="bg-transparent border-b border-white/20 text-white text-sm py-2 px-1 outline-none focus:border-site-blue transition-colors duration-200 min-w-[180px]"
        >
          <option value="" className="bg-site-bg">Все категории</option>
          {categories.map((cat) => (
            <option key={cat.id} value={cat.slug} className="bg-site-bg">
              {cat.name} ({cat.article_count})
            </option>
          ))}
        </select>
        <button className="btn-blue !text-base !px-6 !py-2 whitespace-nowrap" onClick={onCreate}>
          Создать статью
        </button>
      </div>

      {/* Table */}
      <div className="gray-bg overflow-hidden overflow-x-hidden">
        {loading ? (
          <p className="text-center text-white/50 text-sm py-8">Загрузка...</p>
        ) : (
          <table className="w-full min-w-[600px]">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                  Название
                </th>
                <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3 hidden sm:table-cell">
                  Slug
                </th>
                <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3 hidden md:table-cell">
                  Категории
                </th>
                <th className="text-center text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3 hidden sm:table-cell">
                  Featured
                </th>
                <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3 hidden lg:table-cell">
                  Создана
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
              {articles.map((article) => (
                <motion.tr
                  key={article.id}
                  variants={{
                    hidden: { opacity: 0, y: 6 },
                    visible: { opacity: 1, y: 0 },
                  }}
                  className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200"
                >
                  <td className="px-4 py-3 text-sm text-white">
                    {article.title}
                  </td>
                  <td className="px-4 py-3 text-sm text-white/50 hidden sm:table-cell">
                    {article.slug}
                  </td>
                  <td className="px-4 py-3 hidden md:table-cell">
                    <div className="flex flex-wrap gap-1">
                      {article.categories.map((cat) => (
                        <span
                          key={cat.id}
                          className="text-xs bg-white/[0.07] text-white/70 px-2 py-0.5 rounded-full"
                        >
                          {cat.name}
                        </span>
                      ))}
                      {article.categories.length === 0 && (
                        <span className="text-xs text-white/30">--</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-center hidden sm:table-cell">
                    {article.is_featured ? (
                      <span className="text-gold text-sm">&#9733;</span>
                    ) : (
                      <span className="text-white/20 text-sm">--</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-white/50 hidden lg:table-cell">
                    {new Date(article.created_at).toLocaleDateString("ru-RU")}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-col items-end gap-1.5">
                      <button
                        onClick={() => onEdit(article)}
                        className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                      >
                        Редактировать
                      </button>
                      <button
                        onClick={() => setDeleteTarget(article)}
                        className="text-sm text-site-red hover:text-white transition-colors duration-200"
                      >
                        Удалить
                      </button>
                    </div>
                  </td>
                </motion.tr>
              ))}
            </motion.tbody>
          </table>
        )}

        {!loading && articles.length === 0 && (
          <p className="text-center text-white/50 text-sm py-8">
            Статьи не найдены
          </p>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-2">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="text-sm text-white/60 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-200 px-3 py-1"
          >
            &larr; Назад
          </button>
          <span className="text-sm text-white/60">
            {page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            className="text-sm text-white/60 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors duration-200 px-3 py-1"
          >
            Вперёд &rarr;
          </button>
        </div>
      )}

      {/* Delete confirmation modal */}
      {deleteTarget && (
        <div className="modal-overlay">
          <div className="modal-content gold-outline gold-outline-thick">
            <h2 className="gold-text text-2xl uppercase mb-4">
              Удаление статьи
            </h2>
            <p className="text-white mb-6">
              Удалить статью &laquo;{deleteTarget.title}&raquo;? Это действие
              нельзя отменить.
            </p>
            <div className="flex gap-4">
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

export default ArchiveAdminPage;
