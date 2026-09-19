import axios from "axios";
import client from "./client";

interface ItemParams {
  q?: string;
  item_types?: string;
  exclude_types?: string;
  resource_subcategory?: string;
  page?: number;
  page_size?: number;
}

interface IssueItemPayload {
  item_id: number;
  quantity: number;
}

interface FetchItemsOptions {
  query?: string;
  page?: number;
  pageSize?: number;
  itemTypes?: string[];
  excludeTypes?: string[];
  /** Server-side filter by items.resource_subcategory (FEAT-165) */
  resourceSubcategory?: string;
}

export const fetchItems = async (
  queryOrOptions: string | FetchItemsOptions = "",
  page = 1,
  pageSize = 200,
) => {
  let params: ItemParams;

  if (typeof queryOrOptions === "string") {
    params = { q: queryOrOptions, page, page_size: pageSize };
  } else {
    const opts = queryOrOptions;
    params = {
      q: opts.query || undefined,
      page: opts.page ?? 1,
      page_size: opts.pageSize ?? 200,
    };
    if (opts.itemTypes?.length) params.item_types = opts.itemTypes.join(",");
    if (opts.excludeTypes?.length) params.exclude_types = opts.excludeTypes.join(",");
    if (opts.resourceSubcategory) params.resource_subcategory = opts.resourceSubcategory;
  }

  const { data } = await client.get("/items", { params });

  return Array.isArray(data) ? data : data.items ?? [];
};

/** Largest page the items endpoint serves (inventory-service: le=500) */
const ITEMS_MAX_PAGE_SIZE = 500;

/** Every matching item, walking pages so a long catalogue is never cut off. */
export const fetchAllItems = async (opts: Omit<FetchItemsOptions, "page" | "pageSize"> = {}) => {
  const all = [];
  for (let page = 1; ; page += 1) {
    const chunk = await fetchItems({ ...opts, page, pageSize: ITEMS_MAX_PAGE_SIZE });
    all.push(...chunk);
    if (chunk.length < ITEMS_MAX_PAGE_SIZE) return all;
  }
};

/**
 * The FULL item template for the admin editors.
 *
 * FEAT-171 thinned the public `GET /inventory/items/{id}` down to the six-key
 * card (id, name, description, image_url, rarity, type), which the editor would
 * happily load and then write back — silently zeroing the item's real data on
 * the next PUT. The admin door `GET /inventory/admin/items/{id}`
 * (JWT + `items:read`) keeps serving the unmodified fat `Item`.
 *
 * Admin-only by design: anything non-admin must use the public thin card.
 */
export const fetchItem = async (id: number) => {
  const { data } = await client.get(`/admin/items/${id}`);
  return data;
};

export const createItem = async (payload: Record<string, unknown>) => {
  const { data } = await client.post(`/items`, payload);
  return data;
};

export const updateItem = async (id: number, payload: Record<string, unknown>) => {
  const { data } = await client.put(`/items/${id}`, payload);
  return data;
};

export const deleteItem = async (id: number) => client.delete(`/items/${id}`);

/** Square area of the picture, in source-image pixels, that becomes the icon */
export interface ItemImageCrop {
  x: number;
  y: number;
  width: number;
  height: number;
}

const appendCrop = (form: FormData, crop: ItemImageCrop) => {
  form.append("crop_x", String(crop.x));
  form.append("crop_y", String(crop.y));
  form.append("crop_width", String(crop.width));
  form.append("crop_height", String(crop.height));
};

/** Uploads the original picture; the icon is cut from it by `crop` (whole picture if omitted). */
export const uploadItemImage = async (itemId: number | string, file: File, crop?: ItemImageCrop | null) => {
  const form = new FormData();
  form.append("item_id", String(itemId));
  form.append("file", file);
  if (crop) appendCrop(form, crop);

  const { data } = await axios.post(
    `/photo/change_item_image`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data;
};

/** Re-cuts the icon from the already stored original, no re-upload needed. */
export const recropItemImage = async (itemId: number | string, crop: ItemImageCrop) => {
  const form = new FormData();
  form.append("item_id", String(itemId));
  appendCrop(form, crop);

  const { data } = await axios.post(
    `/photo/recrop_item_image`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data;
};

export const issueItem = async (characterId: number, itemId: number, quantity: number) => {
  return client.post(`/${characterId}/items`, {
    item_id: itemId,
    quantity,
  } as IssueItemPayload);
};
