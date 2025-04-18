import client from "./client";

export const fetchItems = async (query = "", page = 1, pageSize = 20) => {
  const { data } = await client.get("/items", {
    params: { q: query, page, page_size: pageSize },
  });
  return data;
};

export const fetchItem = async (id) => {
  const { data } = await client.get(`/items/${id}`);
  return data;
};

export const createItem = async (payload) => {
  const { data } = await client.post(`/items`, payload);
  return data;
};

export const updateItem = async (id, payload) => {
  const { data } = await client.put(`/items/${id}`, payload);
  return data;
};

export const deleteItem = async (id) => client.delete(`/items/${id}`);

export const uploadItemImage = async (itemId, file) => {
  const form = new FormData();
  form.append("item_id", itemId);
  form.append("file", file);

  const { data } = await axios.post(
    `http://4452515-co41851.twc1.net/photo/change_item_image`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data;
};

export const issueItem = async (characterId, itemId, quantity) => {
  return client.post(`/inventory/${characterId}/items`, {
    item_id: itemId,
    quantity,
  });
};