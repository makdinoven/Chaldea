import axios from "axios";
import client from "./client";

interface ItemParams {
  q?: string;
  item_types?: string;
  exclude_types?: string;
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
  }

  const { data } = await client.get("/items", { params });

  return Array.isArray(data) ? data : data.items ?? [];
};

export const fetchItem = async (id: number) => {
  const { data } = await client.get(`/items/${id}`);
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

export const uploadItemImage = async (itemId: number | string, file: File) => {
  const form = new FormData();
  form.append("item_id", String(itemId));
  form.append("file", file);

  const { data } = await axios.post(
    `/photo/change_item_image`,
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
