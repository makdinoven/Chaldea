import { useState } from "react";
import ItemList from "./ItemList";
import ItemForm from "./ItemForm";
import IssueItemModal from "./IssueItemModal";

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

/* ── Craft / Regular type constants ── */

export const CRAFT_ITEM_TYPES = ["blueprint", "recipe", "gem", "rune", "resource"] as const;

export const REGULAR_ITEM_TYPES = [
  "head", "body", "cloak", "belt", "ring", "necklace", "bracelet",
  "main_weapon", "additional_weapons", "shield", "consumable", "scroll", "misc",
] as const;

/* ── Props ── */

interface ItemsAdminPageProps {
  title?: string;
  itemTypes?: string[];
  excludeTypes?: string[];
}

const ItemsAdminPage = ({ title, itemTypes, excludeTypes }: ItemsAdminPageProps) => {
  const [editingId, setEditingId] = useState<number | undefined>();
  const [creating, setCreating] = useState(false);
  const [issueItem, setIssueItem] = useState<ItemData | undefined>();
  const [refreshKey, setRefreshKey] = useState(0);

  const closeForm = () => {
    setEditingId(undefined);
    setCreating(false);
    setRefreshKey((k) => k + 1);
  };

  return (
    <div className="w-full max-w-[1240px] mx-auto" key={refreshKey}>
      {!editingId && !creating && (
        <ItemList
          onSelect={(id: number) => setEditingId(id)}
          onCreate={() => setCreating(true)}
          onIssue={(item: ItemData) => setIssueItem(item)}
          title={title}
          itemTypes={itemTypes}
          excludeTypes={excludeTypes}
        />
      )}
      {(editingId || creating) && (
        <ItemForm
          selected={editingId}
          onSuccess={closeForm}
          onCancel={closeForm}
        />
      )}
      <IssueItemModal
        open={Boolean(issueItem)}
        onClose={() => {
          setIssueItem(undefined);
          setRefreshKey((k) => k + 1);
        }}
        initialItem={issueItem}
      />
    </div>
  );
};

export default ItemsAdminPage;
