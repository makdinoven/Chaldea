import { useEffect, useState } from "react";
import { deleteItem, fetchItems } from "../../api/items";
import useDebounce from "../../hooks/useDebounce";
import toast from "react-hot-toast";
import { motion } from "motion/react";
import type { ItemData } from "./ItemsAdminPage";

/* ── Props ── */

interface ItemListProps {
  onSelect: (id: number) => void;
  onCreate: () => void;
  onIssue: (item: ItemData) => void;
}

const ItemList = ({ onSelect, onCreate, onIssue }: ItemListProps) => {
  const [items, setItems] = useState<ItemData[]>([]);
  const [query, setQuery] = useState("");
  const debounced = useDebounce(query);

  useEffect(() => {
    fetchItems(debounced)
      .then(setItems)
      .catch((e: Error) => toast.error(e.message || "Не удалось загрузить предметы"));
  }, [debounced]);

  const handleDelete = async (id: number) => {
    if (!confirm("Удалить предмет?")) return;
    try {
      await deleteItem(id);
      setItems((prev) => prev.filter((i) => i.id !== id));
      toast.success("Предмет удалён");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка при удалении";
      toast.error(msg);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em]">
        Предметы
      </h1>

      {/* Search + Create */}
      <div className="flex items-center justify-between gap-4">
        <input
          className="input-underline max-w-[320px]"
          placeholder="Поиск предметов..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button className="btn-blue !text-base !px-6 !py-2" onClick={onCreate}>
          Создать предмет
        </button>
      </div>

      {/* Table */}
      <div className="gray-bg overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-white/10">
              <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                ID
              </th>
              <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                Фото
              </th>
              <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                Название
              </th>
              <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                Тип
              </th>
              <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                Редкость
              </th>
              <th className="text-right text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                Действия
              </th>
            </tr>
          </thead>
          <motion.tbody
            initial="hidden"
            animate="visible"
            variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.03 } } }}
          >
            {items.map((i) => (
              <motion.tr
                key={i.id}
                variants={{
                  hidden: { opacity: 0, y: 6 },
                  visible: { opacity: 1, y: 0 },
                }}
                className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200"
              >
                <td className="px-4 py-3 text-sm text-white/70">{i.id}</td>
                <td className="px-4 py-3">
                  {i.image ? (
                    <img
                      src={i.image}
                      alt={i.name}
                      className="w-[80px] h-[80px] object-cover rounded-[10px]"
                    />
                  ) : (
                    <div className="w-[80px] h-[80px] rounded-[10px] bg-white/[0.05] flex items-center justify-center text-white/20 text-xs">
                      Нет
                    </div>
                  )}
                </td>
                <td className="px-4 py-3 text-sm text-white">{i.name}</td>
                <td className="px-4 py-3 text-sm text-white/70">{i.item_type}</td>
                <td className="px-4 py-3 text-sm text-white/70">{i.item_rarity}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-col items-end gap-1.5">
                    <button
                      onClick={() => onSelect(i.id)}
                      className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                    >
                      Редактировать
                    </button>
                    <button
                      onClick={() => onIssue(i)}
                      className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                    >
                      Выдать
                    </button>
                    <button
                      onClick={() => handleDelete(i.id)}
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

        {items.length === 0 && (
          <p className="text-center text-white/50 text-sm py-8">Предметы не найдены</p>
        )}
      </div>
    </div>
  );
};

export default ItemList;
