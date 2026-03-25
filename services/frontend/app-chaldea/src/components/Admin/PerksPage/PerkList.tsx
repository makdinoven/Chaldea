import { useEffect, useState, useCallback } from "react";
import { fetchPerks, deletePerk } from "../../../api/perks";
import useDebounce from "../../../hooks/useDebounce";
import toast from "react-hot-toast";
import { motion } from "motion/react";
import type { Perk } from "../../../types/perks";

/* ── Dictionaries ── */

const CATEGORY_LABELS: Record<string, string> = {
  combat: "Боевой",
  trade: "Торговый",
  exploration: "Исследование",
  progression: "Прогрессия",
  usage: "Использование",
};

const RARITY_LABELS: Record<string, string> = {
  common: "Обычный",
  rare: "Редкий",
  legendary: "Легендарный",
};

const CATEGORIES = ["", "combat", "trade", "exploration", "progression", "usage"] as const;
const RARITIES = ["", "common", "rare", "legendary"] as const;

/* ── Props ── */

interface PerkListProps {
  onSelect: (id: number) => void;
  onCreate: () => void;
  onGrant: () => void;
}

const PerkList = ({ onSelect, onCreate, onGrant }: PerkListProps) => {
  const [perks, setPerks] = useState<Perk[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [rarity, setRarity] = useState("");
  const debounced = useDebounce(query);
  const perPage = 20;

  const load = useCallback(() => {
    fetchPerks({
      page,
      per_page: perPage,
      search: debounced || undefined,
      category: category || undefined,
      rarity: rarity || undefined,
    })
      .then((res) => {
        setPerks(res.items);
        setTotal(res.total);
      })
      .catch((e: Error) =>
        toast.error(e.message || "Не удалось загрузить перки"),
      );
  }, [debounced, page, category, rarity]);

  useEffect(() => {
    load();
  }, [load]);

  /* Reset page on filter change */
  useEffect(() => {
    setPage(1);
  }, [debounced, category, rarity]);

  const handleDelete = async (id: number) => {
    if (!confirm("Удалить перк? Все применённые бонусы будут отменены.")) return;
    try {
      await deletePerk(id);
      toast.success("Перк удалён");
      load();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка при удалении";
      toast.error(msg);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / perPage));

  return (
    <div className="flex flex-col gap-5">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em]">
        Перки
      </h1>

      {/* Toolbar: search + filters + buttons */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 flex-1">
          <input
            className="input-underline max-w-[240px] w-full"
            placeholder="Поиск по названию..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />

          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="input-underline max-w-[180px] w-full"
          >
            <option value="" className="bg-site-dark text-white">
              Все категории
            </option>
            {CATEGORIES.filter(Boolean).map((c) => (
              <option key={c} value={c} className="bg-site-dark text-white">
                {CATEGORY_LABELS[c]}
              </option>
            ))}
          </select>

          <select
            value={rarity}
            onChange={(e) => setRarity(e.target.value)}
            className="input-underline max-w-[160px] w-full"
          >
            <option value="" className="bg-site-dark text-white">
              Все редкости
            </option>
            {RARITIES.filter(Boolean).map((r) => (
              <option key={r} value={r} className="bg-site-dark text-white">
                {RARITY_LABELS[r]}
              </option>
            ))}
          </select>
        </div>

        <div className="flex gap-3">
          <button
            className="btn-blue !text-base !px-5 !py-2 whitespace-nowrap"
            onClick={onGrant}
          >
            Выдать перк
          </button>
          <button
            className="btn-blue !text-base !px-5 !py-2 whitespace-nowrap"
            onClick={onCreate}
          >
            Создать перк
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="gray-bg overflow-x-auto">
        <table className="w-full min-w-[700px]">
          <thead>
            <tr className="border-b border-white/10">
              {["ID", "Название", "Категория", "Редкость", "Порядок", "Активен", "Действия"].map(
                (h, i) => (
                  <th
                    key={h}
                    className={`text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3 ${
                      i === 6 ? "text-right" : "text-left"
                    }`}
                  >
                    {h}
                  </th>
                ),
              )}
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
            {perks.map((p) => (
              <motion.tr
                key={p.id}
                variants={{
                  hidden: { opacity: 0, y: 6 },
                  visible: { opacity: 1, y: 0 },
                }}
                className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200"
              >
                <td className="px-4 py-3 text-sm text-white/70">{p.id}</td>
                <td className="px-4 py-3 text-sm text-white">{p.name}</td>
                <td className="px-4 py-3 text-sm text-white/70">
                  {CATEGORY_LABELS[p.category] ?? p.category}
                </td>
                <td className="px-4 py-3 text-sm text-white/70">
                  {RARITY_LABELS[p.rarity] ?? p.rarity}
                </td>
                <td className="px-4 py-3 text-sm text-white/70">
                  {p.sort_order}
                </td>
                <td className="px-4 py-3 text-sm">
                  {p.is_active ? (
                    <span className="text-green-400">Да</span>
                  ) : (
                    <span className="text-white/40">Нет</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-col items-end gap-1.5">
                    <button
                      onClick={() => onSelect(p.id)}
                      className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                    >
                      Редактировать
                    </button>
                    <button
                      onClick={() => handleDelete(p.id)}
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

        {perks.length === 0 && (
          <p className="text-center text-white/50 text-sm py-8">
            Перки не найдены
          </p>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="text-sm text-white hover:text-site-blue transition-colors duration-200 disabled:text-white/20 disabled:cursor-not-allowed"
          >
            Назад
          </button>
          <span className="text-sm text-white/60">
            {page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            className="text-sm text-white hover:text-site-blue transition-colors duration-200 disabled:text-white/20 disabled:cursor-not-allowed"
          >
            Вперёд
          </button>
        </div>
      )}
    </div>
  );
};

export default PerkList;
