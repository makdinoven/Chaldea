import type { ReactNode, Ref } from "react";
import type { ItemAdminListRow } from "../../api/items";
import {
  ARMOR_SUBCLASS_LABELS,
  ITEM_TYPE_LABELS,
  RARITY_LABELS,
  RARITY_TEXT_COLORS,
  WEAPON_SUBCLASS_LABELS,
  itemHasRarity,
} from "../../constants/items";
import { resourceSubcategoryLabel } from "../../constants/professions";
import ExpandableRow from "../Admin/ExpandableList/ExpandableRow";
import { adminReadyMark } from "../Admin/ExpandableList/readyMark";

/* FEAT-210: compact clickable item plate (over the shared ExpandableRow); the expanded panel renders under it. */

/** Grid of the plate (and of the sort header strip in ItemsAdminPage — keep them in sync). */
export const ITEM_ROW_GRID = "sm:grid-cols-[minmax(0,2.2fr)_minmax(0,1.4fr)_minmax(0,1fr)_auto]";

/** Second line of the type cell: weapon / armor subclass or the resource subcategory. */
export const itemSubtypeLabel = (item: ItemAdminListRow): string | null => {
  if (item.item_type === "resource") return resourceSubcategoryLabel(item.resource_subcategory ?? null);
  return (
    (item.weapon_subclass && WEAPON_SUBCLASS_LABELS[item.weapon_subclass]) ||
    (item.armor_subclass && ARMOR_SUBCLASS_LABELS[item.armor_subclass]) ||
    null
  );
};

interface ItemRowProps {
  /** null = the «Новый предмет» plate of the create panel */
  item: ItemAdminListRow | null;
  open: boolean;
  onToggle: () => void;
  /** Small caption over the plate, e.g. «Открыт по ссылке» */
  badge?: string;
  rowRef?: Ref<HTMLDivElement>;
  /** The expanded panel (rendered only while open) */
  children?: ReactNode;
}

const Icon = ({ item }: { item: ItemAdminListRow | null }) =>
  item?.image ? (
    <img src={item.image} alt={item.name} className="w-10 h-10 sm:w-11 sm:h-11 rounded-[10px] object-cover shrink-0" />
  ) : (
    <div className="w-10 h-10 sm:w-11 sm:h-11 rounded-[10px] bg-white/[0.05] flex items-center justify-center text-white/30 text-[10px] shrink-0">
      {item ? "Нет" : "+"}
    </div>
  );

const ItemCells = ({ item }: { item: ItemAdminListRow }) => {
  const subtype = itemSubtypeLabel(item);
  const hasRarity = itemHasRarity(item.item_type);
  const rarity = item.item_rarity ?? "";
  return (
    <>
      {/* Type (+ subclass / subcategory) */}
      <span className="flex flex-col min-w-0 pl-[52px] sm:pl-0 text-xs sm:text-sm text-white/70">
        <span className="truncate">{ITEM_TYPE_LABELS[item.item_type] ?? item.item_type}</span>
        {subtype && <span className="text-xs text-white/40 truncate">{subtype}</span>}
      </span>

      {/* Rarity */}
      <span
        className={`text-xs sm:text-sm font-medium truncate pl-[52px] sm:pl-0 ${
          hasRarity ? RARITY_TEXT_COLORS[rarity] ?? "text-white/70" : "text-white/40"
        }`}
      >
        {hasRarity ? RARITY_LABELS[rarity] ?? (rarity || "—") : "—"}
      </span>
    </>
  );
};

const ItemRow = ({ item, open, onToggle, badge, rowRef, children }: ItemRowProps) => (
  <ExpandableRow
    open={open}
    onToggle={onToggle}
    avatar={<Icon item={item} />}
    title={item ? item.name : "Новый предмет"}
    subtitle={item ? `#${item.id}` : undefined}
    ready={item ? adminReadyMark(item) : null}
    cells={item ? <ItemCells item={item} /> : undefined}
    gridClassName={ITEM_ROW_GRID}
    badge={badge}
    rowRef={rowRef}
  >
    {children}
  </ExpandableRow>
);

export default ItemRow;
