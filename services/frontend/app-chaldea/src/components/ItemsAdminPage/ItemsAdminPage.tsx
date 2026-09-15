import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import ItemList from "./ItemList";
import ItemForm from "./ItemForm";
import IssueItemModal from "./IssueItemModal";
import { ITEM_CATEGORIES, type ItemCategoryKey } from "../../constants/items";

/* ── Types ── */

export interface ItemData {
  id: number;
  name: string;
  image?: string;
  item_type: string;
  item_rarity: string;
  item_level: number;
  price: number;
  max_stack_size: number;
  is_unique: boolean;
  description: string;
  fast_slot_bonus: number;
  armor_subclass: string | null;
  weapon_subclass: string | null;
  primary_damage_type: string | null;
  health_recovery: number;
  energy_recovery: number;
  mana_recovery: number;
  stamina_recovery: number;
  [key: string]: unknown;
}

const DEFAULT_CATEGORY: ItemCategoryKey = "equipment";

const isCategoryKey = (value: string | null): value is ItemCategoryKey =>
  ITEM_CATEGORIES.some((c) => c.key === value);

/* ── Component ── */

const ItemsAdminPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawCategory = searchParams.get("category");
  const category: ItemCategoryKey = isCategoryKey(rawCategory) ? rawCategory : DEFAULT_CATEGORY;

  const [editingId, setEditingId] = useState<number | undefined>();
  const [creating, setCreating] = useState(false);
  const [issueItem, setIssueItem] = useState<ItemData | undefined>();
  const [refreshKey, setRefreshKey] = useState(0);

  const setCategory = (key: ItemCategoryKey) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("category", key);
      return next;
    }, { replace: true });
  };

  const closeForm = () => {
    setEditingId(undefined);
    setCreating(false);
    setRefreshKey((k) => k + 1);
  };

  const defaultType = ITEM_CATEGORIES.find((c) => c.key === category)?.types[0];

  return (
    <div className="w-full max-w-container mx-auto">
      {!editingId && !creating && (
        <ItemList
          key={refreshKey}
          category={category}
          onCategoryChange={setCategory}
          onSelect={(id: number) => setEditingId(id)}
          onCreate={() => setCreating(true)}
          onIssue={(item: ItemData) => setIssueItem(item)}
        />
      )}
      {(editingId || creating) && (
        <ItemForm
          selected={editingId}
          defaultType={defaultType}
          onSuccess={closeForm}
          onCancel={closeForm}
        />
      )}
      <IssueItemModal
        open={Boolean(issueItem)}
        onClose={() => setIssueItem(undefined)}
        initialItem={issueItem}
      />
    </div>
  );
};

export default ItemsAdminPage;
