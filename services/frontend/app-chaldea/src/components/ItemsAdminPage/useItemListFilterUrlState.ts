import { useCallback, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { ITEM_CATEGORIES, RARITY_LABELS, type ItemCategoryKey } from "../../constants/items";
import { useSearchParamsPatch } from "../Admin/ExpandableList/urlParams";

/**
 * FEAT-210 — item list filters in the URL: `?category=&type=&rarity=` (replace, other params kept).
 * `type` must belong to the current category and `rarity` must be a known rarity — otherwise
 * the param is removed silently. Changing the category clears `type`.
 */

const CATEGORY_PARAM = "category";
const TYPE_PARAM = "type";
const RARITY_PARAM = "rarity";
const DEFAULT_CATEGORY: ItemCategoryKey = "equipment";

const isCategoryKey = (value: string | null): value is ItemCategoryKey =>
  ITEM_CATEGORIES.some((c) => c.key === value);

export const useItemListFilterUrlState = () => {
  const [searchParams] = useSearchParams();
  const patch = useSearchParamsPatch();

  const rawCategory = searchParams.get(CATEGORY_PARAM);
  const category: ItemCategoryKey = isCategoryKey(rawCategory) ? rawCategory : DEFAULT_CATEGORY;
  const categoryTypes = (ITEM_CATEGORIES.find((c) => c.key === category)?.types ?? []) as readonly string[];

  const rawType = searchParams.get(TYPE_PARAM);
  const rawRarity = searchParams.get(RARITY_PARAM);
  const typeValid = rawType !== null && categoryTypes.includes(rawType);
  const rarityValid = rawRarity !== null && Object.prototype.hasOwnProperty.call(RARITY_LABELS, rawRarity);
  const type = typeValid ? rawType : "";
  const rarity = rarityValid ? rawRarity : "";

  // Garbage / foreign-category values → removed silently
  useEffect(() => {
    const changes: Record<string, null> = {};
    if (rawType !== null && !typeValid) changes[TYPE_PARAM] = null;
    if (rawRarity !== null && !rarityValid) changes[RARITY_PARAM] = null;
    if (Object.keys(changes).length > 0) patch(changes, true);
  }, [rawType, rawRarity, typeValid, rarityValid, patch]);

  const setCategory = useCallback(
    (key: ItemCategoryKey) => patch({ [CATEGORY_PARAM]: key, [TYPE_PARAM]: null }, true),
    [patch],
  );
  const setType = useCallback((value: string) => patch({ [TYPE_PARAM]: value || null }, true), [patch]);
  const setRarity = useCallback((value: string) => patch({ [RARITY_PARAM]: value || null }, true), [patch]);

  return { category, type, rarity, setCategory, setType, setRarity };
};
