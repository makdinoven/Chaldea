import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import toast from "react-hot-toast";
import { deleteItem, fetchAdminItemList, setItemReady, type ItemAdminListRow } from "../../api/items";
import {
  ITEM_CATEGORIES,
  ITEM_TYPE_LABELS,
  RARITY_LABELS,
  RARITY_ORDER,
} from "../../constants/items";
import {
  RESOURCE_SUBCATEGORY_GROUPS,
  RESOURCE_SUBCATEGORY_LABELS,
  RESOURCE_SUBCATEGORY_NONE_LABEL,
} from "../../constants/professions";
import AdminPagination from "../Admin/AdminPagination/AdminPagination";
import ConfirmationModal from "../ui/ConfirmationModal";
import ReadyFilterSelect from "../Admin/ExpandableList/ReadyFilterSelect";
import { usePanelUrlState } from "../Admin/ExpandableList/usePanelUrlState";
import { useDirtyGuard } from "../Admin/ExpandableList/useDirtyGuard";
import { useReadyFilterUrlState } from "../Admin/ExpandableList/useReadyFilterUrlState";
import ItemRow, { ITEM_ROW_GRID } from "./ItemRow";
import ItemExpandedPanel from "./ItemExpandedPanel";
import IssueItemModal from "./IssueItemModal";
import { isItemTabKey, type ItemTabKey } from "./itemTabKeys";
import { useItemListFilterUrlState } from "./useItemListFilterUrlState";

/* FEAT-210: item catalogue as expandable plates. The whole (slim) catalogue is loaded once and
   filtered / sorted / paged on the client. URL: ?category&type&rarity&ready&item&tab;
   search, resource subcategory, sort and page are local state. */

const ITEMS_PAGE_SIZE = 50;

/** Subcategory filter value for resources without a subcategory («Прочее») */
const NO_SUBCATEGORY = "__none__";

type SortKey = "id" | "name" | "item_type" | "item_rarity";
type SortDir = "asc" | "desc";

const SORT_LABELS: Record<SortKey, string> = {
  id: "ID",
  name: "Название",
  item_type: "Тип",
  item_rarity: "Редкость",
};

const OPTION_CLASS = "bg-site-dark text-white";

const errorMessage = (e: unknown, fallback: string): string =>
  e instanceof Error && e.message ? e.message : fallback;

/* ── Component ── */

const ItemsAdminPage = () => {
  const [items, setItems] = useState<ItemAdminListRow[]>([]);
  const [listLoading, setListLoading] = useState(true);
  /** The last list request succeeded (a deep-linked id is checked only against a real catalogue) */
  const [listLoaded, setListLoaded] = useState(false);

  const { category, type: filterType, rarity: filterRarity, setCategory, setType, setRarity } =
    useItemListFilterUrlState();
  const { ready: readyFilter, setReady } = useReadyFilterUrlState();
  const [query, setQuery] = useState("");
  const [filterSubcategory, setFilterSubcategory] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("id");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [page, setPage] = useState(1);

  const {
    target: openTarget,
    rawTarget: rawItem,
    tab: urlTab,
    open: openPanel,
    setTab,
    close,
    normalize,
  } = usePanelUrlState("item", isItemTabKey, "general");
  const { onDirtyChange, guard, pendingLeave, confirmLeave, cancelLeave, resetDirty } = useDirtyGuard(
    openTarget !== null,
  );
  const [formSeq, setFormSeq] = useState(0);
  const [deleteTarget, setDeleteTarget] = useState<ItemAdminListRow | null>(null);
  const [issueItem, setIssueItem] = useState<ItemAdminListRow | null>(null);
  const [readyPending, setReadyPending] = useState(false);
  const openRowRef = useRef<HTMLDivElement>(null);

  /* ── Catalogue ── */

  const loadItems = useCallback(async () => {
    setListLoading(true);
    try {
      const rows = await fetchAdminItemList();
      setItems(rows);
      setListLoaded(true);
    } catch (e) {
      toast.error(errorMessage(e, "Не удалось загрузить предметы"));
      setListLoaded(false);
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  // A subcategory filter from another category would hide everything
  useEffect(() => {
    setFilterSubcategory("");
  }, [category]);

  const currentCategory = ITEM_CATEGORIES.find((c) => c.key === category) ?? ITEM_CATEGORIES[0];
  const categoryTypes = currentCategory.types as readonly string[];

  const countsByCategory = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const cat of ITEM_CATEGORIES) {
      counts[cat.key] = items.filter((i) => (cat.types as readonly string[]).includes(i.item_type)).length;
    }
    return counts;
  }, [items]);

  const visibleItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = items.filter(
      (i) =>
        categoryTypes.includes(i.item_type) &&
        (!filterType || i.item_type === filterType) &&
        (!filterRarity || i.item_rarity === filterRarity) &&
        (readyFilter === null || i.admin_ready === readyFilter) &&
        (!filterSubcategory ||
          (i.item_type === "resource" &&
            (filterSubcategory === NO_SUBCATEGORY
              ? !i.resource_subcategory
              : i.resource_subcategory === filterSubcategory))) &&
        (!q || i.name.toLowerCase().includes(q) || String(i.id) === q),
    );
    return filtered.sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "id":
          cmp = a.id - b.id;
          break;
        case "name":
          cmp = a.name.localeCompare(b.name, "ru");
          break;
        case "item_type":
          cmp = (ITEM_TYPE_LABELS[a.item_type] ?? a.item_type).localeCompare(
            ITEM_TYPE_LABELS[b.item_type] ?? b.item_type,
            "ru",
          );
          break;
        case "item_rarity":
          cmp = (RARITY_ORDER[a.item_rarity ?? ""] ?? 99) - (RARITY_ORDER[b.item_rarity ?? ""] ?? 99);
          break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [items, categoryTypes, filterType, filterRarity, readyFilter, filterSubcategory, query, sortKey, sortDir]);

  // Any filter / search / sort change → back to page 1
  const filterKey = [category, filterType, filterRarity, readyFilter, filterSubcategory, query, sortKey, sortDir].join("|");
  useEffect(() => {
    setPage(1);
  }, [filterKey]);

  const totalPages = Math.max(1, Math.ceil(visibleItems.length / ITEMS_PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageRows = visibleItems.slice((currentPage - 1) * ITEMS_PAGE_SIZE, currentPage * ITEMS_PAGE_SIZE);

  // Resource subcategories: shown for the craft category or the resource type filter
  const showSubcategoryFilter = filterType === "resource" || categoryTypes.includes("resource");

  /* ── Open item resolution ── */

  const openId = typeof openTarget === "number" ? openTarget : null;
  const isNew = openTarget === "new";
  const inPage = openId !== null && pageRows.some((i) => i.id === openId);
  const catalogueItem = openId !== null ? items.find((i) => i.id === openId) ?? null : null;
  // Opened by link / outside the current page or filter → pinned plate from the loaded catalogue
  const pinnedItem = !inPage ? catalogueItem : null;

  // Garbage `item` param → silent reset
  useEffect(() => {
    if (rawItem !== null && openTarget === null) normalize(null);
  }, [rawItem, openTarget, normalize]);

  // Unknown id → toast + params cleared (checked against a successfully loaded catalogue only)
  useEffect(() => {
    if (openId === null || !listLoaded || listLoading || catalogueItem) return;
    toast.error("Предмет не найден");
    normalize(null);
  }, [openId, listLoaded, listLoading, catalogueItem, normalize]);

  const handleTabNormalize = useCallback(
    (tab: ItemTabKey) => {
      if (openTarget !== null) normalize(openTarget, tab);
    },
    [openTarget, normalize],
  );

  /* ── Actions ── */

  const toggleRow = (id: number) => {
    if (openId === id) guard(close);
    else guard(() => openPanel(id));
  };

  const handleSaved = async (id: number, created: boolean, tab: ItemTabKey) => {
    if (!created) setFormSeq((s) => s + 1); // remount → fresh load of the saved item
    await loadItems(); // name / icon / type / rarity may have changed
    if (created) normalize(id, tab);
  };

  const handleDelete = async () => {
    const target = deleteTarget;
    setDeleteTarget(null);
    if (!target) return;
    try {
      await deleteItem(target.id);
      toast.success("Предмет удалён");
      resetDirty();
      if (openId === target.id) normalize(null);
      setItems((prev) => prev.filter((i) => i.id !== target.id));
    } catch (e) {
      toast.error(errorMessage(e, "Не удалось удалить предмет"));
    }
  };

  const handleToggleReady = async (item: ItemAdminListRow) => {
    setReadyPending(true);
    try {
      const res = await setItemReady(item.id, !item.admin_ready);
      // The list is client-side: a ready filter re-applies by itself (the open item becomes pinned)
      setItems((prev) =>
        prev.map((i) =>
          i.id === res.id
            ? {
                ...i,
                admin_ready: res.admin_ready,
                admin_ready_at: res.admin_ready_at,
                admin_ready_by: res.admin_ready_by,
              }
            : i,
        ),
      );
      toast.success(res.admin_ready ? "Отмечено: готов" : "Отметка «Готов» снята");
    } catch (e) {
      const detail = e instanceof Error && e.message ? `: ${e.message}` : "";
      toast.error(`Не удалось изменить отметку «Готов»${detail}`);
    } finally {
      setReadyPending(false);
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

  /* ── Render ── */

  // A new item starts with the filtered type, else the first type of the category (recipes come from professions)
  const defaultType = filterType || categoryTypes.find((t) => t !== "recipe") || "head";

  const renderPanel = (item: ItemAdminListRow | null) => (
    <ItemExpandedPanel
      key="panel"
      item={item}
      formSeq={formSeq}
      defaultType={defaultType}
      urlTab={urlTab}
      onTabSelect={setTab}
      onTabNormalize={handleTabNormalize}
      onSaved={handleSaved}
      onCancel={() => guard(close)}
      onDirtyChange={onDirtyChange}
      onIssue={() => item && setIssueItem(item)}
      onDeleteRequest={() => item && guard(() => setDeleteTarget(item))}
      onToggleReady={() => item && handleToggleReady(item)}
      readyPending={readyPending}
      scrollTargetRef={openRowRef}
    />
  );

  const sortButton = (key: SortKey) => (
    <button
      type="button"
      onClick={() => handleSort(key)}
      className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 hover:text-white/80 transition-colors select-none"
    >
      {SORT_LABELS[key]}
      {sortKey !== key ? (
        <span className="text-white/20 ml-1">↕</span>
      ) : (
        <span className="text-gold ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>
      )}
    </button>
  );

  const selectClass = "input-underline bg-transparent text-sm w-full min-[420px]:w-[170px]";

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-5">
      <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">Предметы</h1>

      {/* Categories */}
      <div className="flex gap-2 overflow-x-auto gold-scrollbar pb-1.5 -mx-1 px-1">
        {ITEM_CATEGORIES.map((cat) => {
          const active = cat.key === category;
          return (
            <button
              key={cat.key}
              type="button"
              onClick={() => setCategory(cat.key)}
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
            className={selectClass}
            aria-label="Тип"
            value={filterType}
            onChange={(e) => setType(e.target.value)}
          >
            <option value="" className={OPTION_CLASS}>Все типы</option>
            {currentCategory.types.map((t) => (
              <option key={t} value={t} className={OPTION_CLASS}>{ITEM_TYPE_LABELS[t]}</option>
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
            <option value="" className={OPTION_CLASS}>Все подкатегории</option>
            {RESOURCE_SUBCATEGORY_GROUPS.map((group) => (
              <optgroup key={group.label} label={group.label} className={OPTION_CLASS}>
                {group.items.map((value) => (
                  <option key={value} value={value} className={OPTION_CLASS}>
                    {RESOURCE_SUBCATEGORY_LABELS[value]}
                  </option>
                ))}
              </optgroup>
            ))}
            <option value={NO_SUBCATEGORY} className={OPTION_CLASS}>{RESOURCE_SUBCATEGORY_NONE_LABEL}</option>
          </select>
        )}
        <select
          className={selectClass}
          aria-label="Редкость"
          value={filterRarity}
          onChange={(e) => setRarity(e.target.value)}
        >
          <option value="" className={OPTION_CLASS}>Все редкости</option>
          {Object.entries(RARITY_LABELS).map(([value, label]) => (
            <option key={value} value={value} className={OPTION_CLASS}>{label}</option>
          ))}
        </select>
        <ReadyFilterSelect value={readyFilter} onChange={setReady} className="w-full min-[420px]:w-[170px]" />
        {/* Sorting where there is no header strip */}
        <select
          className={`md:hidden ${selectClass}`}
          aria-label="Сортировка"
          value={`${sortKey}:${sortDir}`}
          onChange={(e) => {
            const [key, dir] = e.target.value.split(":") as [SortKey, SortDir];
            setSortKey(key);
            setSortDir(dir);
          }}
        >
          {(Object.keys(SORT_LABELS) as SortKey[]).flatMap((key) => [
            <option key={`${key}:asc`} value={`${key}:asc`} className={OPTION_CLASS}>{SORT_LABELS[key]} ↑</option>,
            <option key={`${key}:desc`} value={`${key}:desc`} className={OPTION_CLASS}>{SORT_LABELS[key]} ↓</option>,
          ])}
        </select>
        <span className="text-white/30 text-xs">{visibleItems.length} шт.</span>
        <button
          className="btn-blue !text-base !px-6 !py-2 w-full sm:w-auto sm:ml-auto"
          onClick={() => guard(() => openPanel("new"))}
        >
          Создать предмет
        </button>
      </div>

      {/* Item list */}
      <div className="gray-bg">
        <div className="flex flex-col gap-1 p-2 sm:p-3">
          {/* Sort header strip, aligned with the plate grid (md+) */}
          <div className={`hidden md:grid ${ITEM_ROW_GRID} items-center gap-4 px-4 pb-2 border-b border-white/10`}>
            <div className="flex items-center gap-4 pl-[56px]">
              {sortButton("id")}
              {sortButton("name")}
            </div>
            {sortButton("item_type")}
            {sortButton("item_rarity")}
            <span className="w-5" />
          </div>

          {/* Pinned: create panel / item opened by link or off the current page */}
          {isNew && (
            <ItemRow item={null} open onToggle={() => guard(close)} rowRef={openRowRef}>
              {renderPanel(null)}
            </ItemRow>
          )}
          {pinnedItem && (
            <ItemRow
              key={`pinned-${pinnedItem.id}`}
              item={pinnedItem}
              open
              onToggle={() => toggleRow(pinnedItem.id)}
              badge="Открыт по ссылке"
              rowRef={openRowRef}
            >
              {renderPanel(pinnedItem)}
            </ItemRow>
          )}

          {listLoading && items.length === 0 ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
            </div>
          ) : (
            <div className={`flex flex-col gap-1 transition-opacity duration-200 ${listLoading ? "opacity-60" : ""}`}>
              {pageRows.map((item) => {
                const isOpen = openId === item.id;
                return (
                  <ItemRow
                    key={item.id}
                    item={item}
                    open={isOpen}
                    onToggle={() => toggleRow(item.id)}
                    rowRef={isOpen ? openRowRef : undefined}
                  >
                    {isOpen && renderPanel(item)}
                  </ItemRow>
                );
              })}
              {!listLoading && pageRows.length === 0 && (
                <p className="text-center text-white/50 text-sm py-8">Предметы не найдены</p>
              )}
            </div>
          )}
        </div>

        <AdminPagination
          page={currentPage}
          totalPages={totalPages}
          onPageChange={setPage}
          total={visibleItems.length}
          pageSize={ITEMS_PAGE_SIZE}
          className="px-4 py-3 border-t border-white/10"
        />
      </div>

      <IssueItemModal open={issueItem !== null} onClose={() => setIssueItem(null)} initialItem={issueItem} />

      <ConfirmationModal
        isOpen={pendingLeave}
        title="Несохранённые изменения"
        message="Есть несохранённые изменения. Уйти без сохранения?"
        onConfirm={confirmLeave}
        onCancel={cancelLeave}
      />

      <ConfirmationModal
        isOpen={deleteTarget !== null}
        title="Удаление предмета"
        message={`Удалить предмет «${deleteTarget?.name ?? ""}»? Это действие нельзя отменить.`}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
};

export default ItemsAdminPage;
