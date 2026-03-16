import axios from "axios";
import client from "./client";

interface ItemParams {
  q?: string;
  page?: number;
  page_size?: number;
}

interface IssueItemPayload {
  item_id: number;
  quantity: number;
}

export const fetchItems = async (query = "", page = 1, pageSize = 20) => {
  const { data } = await client.get("/items", {
    params: { q: query, page, page_size: pageSize } as ItemParams,
  });

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
