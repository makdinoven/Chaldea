import { useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { motion } from "motion/react";
import { deleteItem, fetchAllItems } from "../../api/items";
import {
  ARMOR_SUBCLASS_LABELS,
  ITEM_CATEGORIES,
  ITEM_TYPE_LABELS,
  RARITY_LABELS,
  RARITY_ORDER,
  RARITY_TEXT_COLORS,
  itemHasRarity,
  WEAPON_SUBCLASS_LABELS,
  type ItemCategoryKey,
} from "../../constants/items";
import {
  RESOURCE_SUBCATEGORY_GROUPS,
  RESOURCE_SUBCATEGORY_LABELS,
  RESOURCE_SUBCATEGORY_NONE_LABEL,
  resourceSubcategoryLabel,
} from "../../constants/professions";
import type { ItemData } from "./ItemsAdminPage";

/** Subcategory filter value for resources without a subcategory («Прочее») */
const NO_SUBCATEGORY = "__none__";

const subcategoryOf = (item: ItemData): string | null =>
  typeof item.resource_subcategory === "string" && item.resource_subcategory ? item.resource_subcategory : null;

/* ── Sort ── */

type SortKey = "id" | "name" | "item_type" | "item_rarity";
type SortDir = "asc" | "desc";

const SORT_LABELS: Record<SortKey, string> = {
  id: "ID",
  name: "Название",
  item_type: "Тип",
  item_rarity: "Редкость",
};

const subclassLabel = (item: ItemData) =>
  (item.weapon_subclass && WEAPON_SUBCLASS_LABELS[item.weapon_subclass]) ||
  (item.armor_subclass && ARMOR_SUBCLASS_LABELS[item.armor_subclass]) ||
  null;

/* ── Props ── */

interface ItemListProps {
  category: ItemCategoryKey;
  onCategoryChange: (key: ItemCategoryKey) => void;
  onSelect: (id: number) => void;
  onCreate: () => void;
  onIssue: (item: ItemData) => void;
}

const ItemList = ({ category, onCategoryChange, onSelect, onCreate, onIssue }: ItemListProps) => {
  const [items, setItems] = useState<ItemData[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("id");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [filterType, setFilterType] = useState("");
  const [filterRarity, setFilterRarity] = useState("");
  const [filterSubcategory, setFilterSubcategory] = useState("");

  // The whole catalogue is loaded once; categories, filters and search are local
  useEffect(() => {
    fetchAllItems()
      .then(setItems)
      .catch((e: Error) => toast.error(e.message || "Не удалось загрузить предметы"))
      .finally(() => setLoading(false));
  }, []);

  // A type filter from another category would hide everything
  useEffect(() => {
    setFilterType("");
    setFilterSubcategory("");
  }, [category]);

  const currentCategory = ITEM_CATEGORIES.find((c) => c.key === category) ?? ITEM_CATEGORIES[0];

  const countsByCategory = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const cat of ITEM_CATEGORIES) {
      counts[cat.key] = items.filter((i) => (cat.types as readonly string[]).includes(i.item_type)).length;
    }
    return counts;
  }, [items]);

  const visibleItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    const types = currentCategory.types as readonly string[];
    const filtered = items.filter(
      (i) =>
        types.includes(i.item_type) &&
        (!filterType || i.item_type === filterType) &&
        (!filterRarity || i.item_rarity === filterRarity) &&
        (!filterSubcategory ||
          (i.item_type === "resource" &&
            (filterSubcategory === NO_SUBCATEGORY
              ? subcategoryOf(i) === null
              : subcategoryOf(i) === filterSubcategory))) &&
        (!q || i.name.toLowerCase().includes(q) || String(i.id) === q),
    );

    return filtered.sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "id": cmp = a.id - b.id; break;
        case "name": cmp = a.name.localeCompare(b.name, "ru"); break;
        case "item_type":
          cmp = (ITEM_TYPE_LABELS[a.item_type] ?? a.item_type).localeCompare(ITEM_TYPE_LABELS[b.item_type] ?? b.item_type, "ru");
          break;
        case "item_rarity": cmp = (RARITY_ORDER[a.item_rarity] ?? 99) - (RARITY_ORDER[b.item_rarity] ?? 99); break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [items, currentCategory, filterType, filterRarity, filterSubcategory, query, sortKey, sortDir]);

  // Resource subcategories: shown for the craft category or the resource type filter
  const showSubcategoryFilter =
    filterType === "resource" || (currentCategory.types as readonly string[]).includes("resource");

  const handleDelete = async (item: ItemData) => {
    if (!confirm(`Удалить предмет «${item.name}»?`)) return;
    try {
      await deleteItem(item.id);
      setItems((prev) => prev.filter((i) => i.id !== item.id));
      toast.success("Предмет удалён");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Ошибка при удалении");
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

  const sortIndicator = (key: SortKey) =>
    sortKey !== key
      ? <span className="text-white/20 ml-1">↕</span>
      : <span className="text-gold ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>;

  const thSortable =
    "text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-3 py-3 cursor-pointer hover:text-white/80 transition-colors select-none";

  const thumb = (i: ItemData) =>
    i.image ? (
      <img src={i.image} alt={i.name} className="w-12 h-12 object-cover rounded-[10px] shrink-0" />
    ) : (
      <div className="w-12 h-12 rounded-[10px] bg-white/[0.05] flex items-center justify-center text-white/20 text-[10px] shrink-0">
        Нет
      </div>
    );

  const actions = (i: ItemData) => (
    <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-1">
      <button onClick={() => onSelect(i.id)} className="text-sm text-white hover:text-site-blue transition-colors duration-200">
        Изменить
      </button>
      <button onClick={() => onIssue(i)} className="text-sm text-white hover:text-site-blue transition-colors duration-200">
        Выдать
      </button>
      <button onClick={() => handleDelete(i)} className="text-sm text-site-red hover:text-white transition-colors duration-200">
        Удалить
      </button>
    </div>
  );

  return (
    <div className="flex flex-col gap-5">
      <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">Предметы</h1>

      {/* Categories */}
      <div className="flex gap-2 overflow-x-auto gold-scrollbar pb-1.5 -mx-1 px-1">
        {ITEM_CATEGORIES.map((cat) => {
          const active = cat.key === category;
          return (
            <button
              key={cat.key}
              type="button"
              onClick={() => onCategoryChange(cat.key)}
              aria-pressed={active}
              className={`shrink-0 rounded-full px-4 py-1.5 text-sm transition-colors border ${
                active
                  ? "border-gold/60 text-gold bg-gold/10"
                  : "border-white/15 text-white/70 hover:text-white hover:border-white/30"
              }`}
            >
              {cat.label}
              <span className="ml-1.5 text-xs text-white/40">{countsByCategory[cat.key] ?? 0}</span>
            </button>
          );
        })}
      </div>

      {/* Search + filters + create */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          className="input-underline flex-1 min-w-[180px] sm:max-w-[320px]"
          placeholder="Поиск по названию или ID…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {currentCategory.types.length > 1 && (
          <select
            className="input-underline bg-transparent text-sm w-full min-[420px]:w-[170px]"
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
          >
            <option value="" className="bg-site-dark">Все типы</option>
            {currentCategory.types.map((t) => (
              <option key={t} value={t} className="bg-site-dark">{ITEM_TYPE_LABELS[t]}</option>
            ))}
          </select>
        )}
        {showSubcategoryFilter && (
          <select
            className="input-underline bg-transparent text-sm w-full min-[420px]:w-[190px]"
            value={filterSubcategory}
            onChange={(e) => setFilterSubcategory(e.target.value)}
            aria-label="Подкатегория ресурса"
          >
            <option value="" className="bg-site-dark">Все подкатегории</option>
            {RESOURCE_SUBCATEGORY_GROUPS.map((group) => (
              <optgroup key={group.label} label={group.label} className="bg-site-dark">
                {group.items.map((value) => (
                  <option key={value} value={value} className="bg-site-dark">
                    {RESOURCE_SUBCATEGORY_LABELS[value]}
                  </option>
                ))}
              </optgroup>
            ))}
            <option value={NO_SUBCATEGORY} className="bg-site-dark">{RESOURCE_SUBCATEGORY_NONE_LABEL}</option>
          </select>
        )}
        <select
          className="input-underline bg-transparent text-sm w-full min-[420px]:w-[170px]"
          value={filterRarity}
          onChange={(e) => setFilterRarity(e.target.value)}
        >
          <option value="" className="bg-site-dark">Все редкости</option>
          {Object.entries(RARITY_LABELS).map(([value, label]) => (
            <option key={value} value={value} className="bg-site-dark">{label}</option>
          ))}
        </select>
        {/* Sorting for the card layout, where there are no column headers */}
        <select
          className="md:hidden input-underline bg-transparent text-sm w-full min-[420px]:w-[170px]"
          value={`${sortKey}:${sortDir}`}
          onChange={(e) => {
            const [key, dir] = e.target.value.split(":") as [SortKey, SortDir];
            setSortKey(key);
            setSortDir(dir);
          }}
        >
          {(Object.keys(SORT_LABELS) as SortKey[]).flatMap((key) => [
            <option key={`${key}:asc`} value={`${key}:asc`} className="bg-site-dark">{SORT_LABELS[key]} ↑</option>,
            <option key={`${key}:desc`} value={`${key}:desc`} className="bg-site-dark">{SORT_LABELS[key]} ↓</option>,
          ])}
        </select>
        <span className="text-white/30 text-xs">{visibleItems.length} шт.</span>
        <button className="btn-blue !text-base !px-6 !py-2 w-full sm:w-auto sm:ml-auto" onClick={onCreate}>
          Создать предмет
        </button>
      </div>

      {/* Table (md+) */}
      <div className="gray-bg overflow-x-auto hidden md:block">
        <table className="w-full">
          <thead>
            <tr className="border-b border-white/10">
              <th className={thSortable} onClick={() => handleSort("id")}>ID{sortIndicator("id")}</th>
              <th className="px-3 py-3" />
              <th className={thSortable} onClick={() => handleSort("name")}>Название{sortIndicator("name")}</th>
              <th className={thSortable} onClick={() => handleSort("item_type")}>Тип{sortIndicator("item_type")}</th>
              <th className={thSortable} onClick={() => handleSort("item_rarity")}>Редкость{sortIndicator("item_rarity")}</th>
              <th className="px-3 py-3" />
            </tr>
          </thead>
          <motion.tbody
            initial="hidden"
            animate="visible"
            variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.02 } } }}
          >
            {visibleItems.map((i) => (
              <motion.tr
                key={i.id}
                variants={{ hidden: { opacity: 0, y: 4 }, visible: { opacity: 1, y: 0 } }}
                className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200"
              >
                <td className="px-3 py-2 text-sm text-white/50">{i.id}</td>
                <td className="px-3 py-2">{thumb(i)}</td>
                <td className="px-3 py-2 text-sm text-white">{i.name}</td>
                <td className="px-3 py-2 text-sm text-white/70">
                  {ITEM_TYPE_LABELS[i.item_type] ?? i.item_type}
                  {subclassLabel(i) && <span className="block text-xs text-white/40">{subclassLabel(i)}</span>}
                  {i.item_type === "resource" && (
                    <span className="block text-xs text-white/40">{resourceSubcategoryLabel(subcategoryOf(i))}</span>
                  )}
                </td>
                <td className={`px-3 py-2 text-sm font-medium ${RARITY_TEXT_COLORS[i.item_rarity] ?? "text-white/70"}`}>
                  {itemHasRarity(i.item_type) ? RARITY_LABELS[i.item_rarity] ?? i.item_rarity : "—"}
                </td>
                <td className="px-3 py-2">{actions(i)}</td>
              </motion.tr>
            ))}
          </motion.tbody>
        </table>
      </div>

      {/* Cards (mobile) */}
      <div className="flex flex-col gap-2 md:hidden">
        {visibleItems.map((i) => (
          <div key={i.id} className="gray-bg p-3 flex flex-col gap-2">
            <div className="flex items-center gap-3 min-w-0">
              {thumb(i)}
              <div className="min-w-0">
                <p className="text-sm text-white truncate">{i.name}</p>
                <p className="text-xs text-white/50 truncate">
                  #{i.id} · {ITEM_TYPE_LABELS[i.item_type] ?? i.item_type}
                  {subclassLabel(i) ? ` · ${subclassLabel(i)}` : ""}
                  {i.item_type === "resource" ? ` · ${resourceSubcategoryLabel(subcategoryOf(i))}` : ""}
                </p>
                {itemHasRarity(i.item_type) && (
                  <p className={`text-xs font-medium ${RARITY_TEXT_COLORS[i.item_rarity] ?? "text-white/70"}`}>
                    {RARITY_LABELS[i.item_rarity] ?? i.item_rarity}
                  </p>
                )}
              </div>
            </div>
            {actions(i)}
          </div>
        ))}
      </div>

      {!loading && visibleItems.length === 0 && (
        <p className="text-center text-white/50 text-sm py-8">Предметы не найдены</p>
      )}
      {loading && <p className="text-center text-white/50 text-sm py-8">Загрузка…</p>}
    </div>
  );
};

export default ItemList;
