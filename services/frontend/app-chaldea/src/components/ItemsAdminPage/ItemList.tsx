import { useEffect, useState, useMemo } from "react";
import { deleteItem, fetchItems } from "../../api/items";
import useDebounce from "../../hooks/useDebounce";
import toast from "react-hot-toast";
import { motion } from "motion/react";
import type { ItemData } from "./ItemsAdminPage";

/* ── Labels ── */

const TYPE_LABELS: Record<string, string> = {
  head: "Шлем", body: "Броня", cloak: "Плащ", belt: "Пояс",
  ring: "Кольцо", necklace: "Ожерелье", bracelet: "Браслет",
  main_weapon: "Оружие", additional_weapons: "Доп. оружие", shield: "Щит",
  consumable: "Расходуемое", resource: "Ресурс", scroll: "Свиток", misc: "Разное",
  blueprint: "Чертёж", recipe: "Рецепт", gem: "Камень", rune: "Руна",
};

const RARITY_LABELS: Record<string, string> = {
  common: "Обычный", rare: "Редкий", epic: "Эпический",
  mythical: "Мифический", legendary: "Легендарный",
  divine: "Божественный", demonic: "Демонический",
};

const RARITY_COLORS: Record<string, string> = {
  common: "text-white/60", rare: "text-site-blue", epic: "text-[#B875BD]",
  mythical: "text-site-red", legendary: "text-gold",
  divine: "text-[#FFD700]", demonic: "text-[#8B0000]",
};

/* ── Sort ── */

type SortKey = "id" | "name" | "item_type" | "item_rarity";
type SortDir = "asc" | "desc";

const RARITY_ORDER: Record<string, number> = {
  common: 0, rare: 1, epic: 2, mythical: 3, legendary: 4, divine: 5, demonic: 6,
};

/* ── Props ── */

interface ItemListProps {
  onSelect: (id: number) => void;
  onCreate: () => void;
  onIssue: (item: ItemData) => void;
  title?: string;
  itemTypes?: string[];
  excludeTypes?: string[];
}

const ItemList = ({ onSelect, onCreate, onIssue, title = "Предметы", itemTypes, excludeTypes }: ItemListProps) => {
  const [items, setItems] = useState<ItemData[]>([]);
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("id");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [filterType, setFilterType] = useState<string>("");
  const [filterRarity, setFilterRarity] = useState<string>("");
  const debounced = useDebounce(query);

  useEffect(() => {
    fetchItems({ query: debounced, itemTypes, excludeTypes })
      .then(setItems)
      .catch((e: Error) => toast.error(e.message || "Не удалось загрузить предметы"));
  }, [debounced, itemTypes, excludeTypes]);

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

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sortIndicator = (key: SortKey) => {
    if (sortKey !== key) return <span className="text-white/20 ml-1">↕</span>;
    return <span className="text-gold ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>;
  };

  // Available types/rarities for filters (from loaded items)
  const availableTypes = useMemo(() => [...new Set(items.map((i) => i.item_type))].sort(), [items]);
  const availableRarities = useMemo(() => [...new Set(items.map((i) => i.item_rarity))].sort((a, b) => (RARITY_ORDER[a] ?? 99) - (RARITY_ORDER[b] ?? 99)), [items]);

  // Filter + sort
  const sortedItems = useMemo(() => {
    let filtered = items;
    if (filterType) filtered = filtered.filter((i) => i.item_type === filterType);
    if (filterRarity) filtered = filtered.filter((i) => i.item_rarity === filterRarity);

    return [...filtered].sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "id": cmp = a.id - b.id; break;
        case "name": cmp = a.name.localeCompare(b.name, "ru"); break;
        case "item_type": cmp = (TYPE_LABELS[a.item_type] ?? a.item_type).localeCompare(TYPE_LABELS[b.item_type] ?? b.item_type, "ru"); break;
        case "item_rarity": cmp = (RARITY_ORDER[a.item_rarity] ?? 99) - (RARITY_ORDER[b.item_rarity] ?? 99); break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [items, sortKey, sortDir, filterType, filterRarity]);

  const thClass = "text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3 cursor-pointer hover:text-white/80 transition-colors select-none";

  return (
    <div className="flex flex-col gap-5">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em]">
        {title}
      </h1>

      {/* Search + Filters + Create */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          className="input-underline flex-1 min-w-[200px] max-w-[320px]"
          placeholder="Поиск по названию..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          className="input-underline bg-transparent text-sm w-[160px]"
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
        >
          <option value="">Все типы</option>
          {availableTypes.map((t) => (
            <option key={t} value={t}>{TYPE_LABELS[t] ?? t}</option>
          ))}
        </select>
        <select
          className="input-underline bg-transparent text-sm w-[160px]"
          value={filterRarity}
          onChange={(e) => setFilterRarity(e.target.value)}
        >
          <option value="">Все редкости</option>
          {availableRarities.map((r) => (
            <option key={r} value={r}>{RARITY_LABELS[r] ?? r}</option>
          ))}
        </select>
        <span className="text-white/30 text-xs">{sortedItems.length} шт.</span>
        <button className="btn-blue !text-base !px-6 !py-2 ml-auto" onClick={onCreate}>
          Создать предмет
        </button>
      </div>

      {/* Table */}
      <div className="gray-bg overflow-x-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-white/10">
              <th className={thClass} onClick={() => handleSort("id")}>
                ID{sortIndicator("id")}
              </th>
              <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                Фото
              </th>
              <th className={thClass} onClick={() => handleSort("name")}>
                Название{sortIndicator("name")}
              </th>
              <th className={thClass} onClick={() => handleSort("item_type")}>
                Тип{sortIndicator("item_type")}
              </th>
              <th className={thClass} onClick={() => handleSort("item_rarity")}>
                Редкость{sortIndicator("item_rarity")}
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
            {sortedItems.map((i) => (
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
                <td className="px-4 py-3 text-sm text-white/70">{TYPE_LABELS[i.item_type] ?? i.item_type}</td>
                <td className={`px-4 py-3 text-sm font-medium ${RARITY_COLORS[i.item_rarity] ?? 'text-white/70'}`}>
                  {RARITY_LABELS[i.item_rarity] ?? i.item_rarity}
                </td>
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

        {sortedItems.length === 0 && (
          <p className="text-center text-white/50 text-sm py-8">Предметы не найдены</p>
        )}
      </div>
    </div>
  );
};

export default ItemList;
