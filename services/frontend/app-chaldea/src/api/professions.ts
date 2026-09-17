import axios from "axios";
import type {
  Profession,
  CharacterProfession,
  ChooseProfessionRequest,
  ChooseProfessionResponse,
  ChangeProfessionRequest,
  ChangeProfessionResponse,
  Recipe,
  AdminRecipe,
  CraftRequest,
  CraftResult,
  ProfessionCreateRequest,
  ProfessionUpdateRequest,
  ProfessionRankCreateRequest,
  ProfessionRankUpdateRequest,
  RecipeCreateRequest,
  RecipeUpdateRequest,
  RecipesPaginatedResponse,
  AdminSetRankRequest,
  ProfessionRank,
  SharpenInfoResponse,
  SharpenRequest,
  SharpenResult,
  RepairItemRequest,
  RepairItemResult,
  ItemDetailResponse,
  RefiningRule,
  RefineInfo,
  RefineRequest,
  RefineResult,
  ItemConversionsPayload,
  ItemConversionsResponse,
} from "../types/professions";
import type {
  SocketInfoResponse,
  InsertGemRequest,
  InsertGemResult,
  ExtractGemRequest,
  ExtractGemResult,
} from "../types/gems";

/* ── Axios client for inventory-service (professions / crafting) ── */

const client = axios.create({
  baseURL: "/inventory",
  withCredentials: true,
  timeout: 10000,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("accessToken");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (r) => r,
  (e) => {
    if (e.response) {
      const detail = e.response.data?.detail;
      if (Array.isArray(detail)) {
        const msgs = detail.map((d: { loc?: string[]; msg?: string }) => {
          const field = d.loc?.slice(1).join(" \u2192 ") ?? "";
          return field ? `${field}: ${d.msg}` : (d.msg ?? "");
        });
        throw new Error(msgs.join("; ") || `Ошибка сервера (${e.response.status})`);
      }
      throw new Error(
        typeof detail === "string" && detail
          ? detail
          : `Ошибка сервера (${e.response.status})`,
      );
    }
    throw new Error("Сервер недоступен. Проверьте соединение и попробуйте ещё раз.");
  },
);

/* ── Public: Professions ── */

export const fetchProfessions = async (): Promise<Profession[]> => {
  const { data } = await client.get("/professions");
  return data;
};

export const fetchCharacterProfession = async (
  characterId: number,
): Promise<CharacterProfession> => {
  const { data } = await client.get(`/professions/${characterId}/my`);
  return data;
};

export const chooseProfession = async (
  characterId: number,
  payload: ChooseProfessionRequest,
): Promise<ChooseProfessionResponse> => {
  const { data } = await client.post(
    `/professions/${characterId}/choose`,
    payload,
  );
  return data;
};

export const changeProfession = async (
  characterId: number,
  payload: ChangeProfessionRequest,
): Promise<ChangeProfessionResponse> => {
  const { data } = await client.post(
    `/professions/${characterId}/change`,
    payload,
  );
  return data;
};

/* ── Public: Crafting ── */

export const fetchRecipes = async (
  characterId: number,
  professionId?: number,
): Promise<Recipe[]> => {
  const params: Record<string, number> = {};
  if (professionId !== undefined) params.profession_id = professionId;
  const { data } = await client.get(`/crafting/${characterId}/recipes`, {
    params,
  });
  return data;
};

export const craftItem = async (
  characterId: number,
  payload: CraftRequest,
): Promise<CraftResult> => {
  const { data } = await client.post(
    `/crafting/${characterId}/craft`,
    payload,
  );
  return data;
};

/* ── Public: Refining (FEAT-165) ── */

export const fetchRefiningRules = async (): Promise<RefiningRule[]> => {
  const { data } = await client.get("/crafting/refining-rules");
  return data;
};

export const fetchRefineInfo = async (
  characterId: number,
): Promise<RefineInfo> => {
  const { data } = await client.get(`/crafting/${characterId}/refine-info`);
  return data;
};

export const refineItem = async (
  characterId: number,
  payload: RefineRequest,
): Promise<RefineResult> => {
  const { data } = await client.post(
    `/crafting/${characterId}/refine`,
    payload,
  );
  return data;
};

/* ── Public: Sharpening ── */

export const fetchSharpenInfo = async (
  characterId: number,
  itemRowId: number,
  source: string = "inventory",
): Promise<SharpenInfoResponse> => {
  const { data } = await client.get(
    `/crafting/${characterId}/sharpen-info/${itemRowId}`,
    { params: { source } },
  );
  return data;
};

export const sharpenItem = async (
  characterId: number,
  payload: SharpenRequest,
): Promise<SharpenResult> => {
  const { data } = await client.post(
    `/crafting/${characterId}/sharpen`,
    payload,
  );
  return data;
};

/* ── Admin: Professions ── */

export const fetchAdminProfessions = async (): Promise<Profession[]> => {
  const { data } = await client.get("/admin/professions");
  return data;
};

export const createProfession = async (
  payload: ProfessionCreateRequest,
): Promise<Profession> => {
  const { data } = await client.post("/admin/professions", payload);
  return data;
};

export const updateProfession = async (
  professionId: number,
  payload: ProfessionUpdateRequest,
): Promise<Profession> => {
  const { data } = await client.put(
    `/admin/professions/${professionId}`,
    payload,
  );
  return data;
};

export const deleteProfession = async (
  professionId: number,
): Promise<void> => {
  await client.delete(`/admin/professions/${professionId}`);
};

/* ── Admin: Profession Ranks ── */

export const createProfessionRank = async (
  professionId: number,
  payload: ProfessionRankCreateRequest,
): Promise<ProfessionRank> => {
  const { data } = await client.post(
    `/admin/professions/${professionId}/ranks`,
    payload,
  );
  return data;
};

export const updateProfessionRank = async (
  rankId: number,
  payload: ProfessionRankUpdateRequest,
): Promise<ProfessionRank> => {
  const { data } = await client.put(
    `/admin/professions/ranks/${rankId}`,
    payload,
  );
  return data;
};

export const deleteProfessionRank = async (
  rankId: number,
): Promise<void> => {
  await client.delete(`/admin/professions/ranks/${rankId}`);
};

/* ── Admin: Recipes ── */

export const fetchAdminRecipes = async (params: {
  page?: number;
  per_page?: number;
  search?: string;
  profession_id?: number;
  rarity?: string;
}): Promise<RecipesPaginatedResponse> => {
  const { data } = await client.get("/admin/recipes", { params });
  return data;
};

export const createRecipe = async (
  payload: RecipeCreateRequest,
): Promise<AdminRecipe> => {
  const { data } = await client.post("/admin/recipes", payload);
  return data;
};

export const updateRecipe = async (
  recipeId: number,
  payload: RecipeUpdateRequest,
): Promise<AdminRecipe> => {
  const { data } = await client.put(`/admin/recipes/${recipeId}`, payload);
  return data;
};

export const deleteRecipe = async (recipeId: number): Promise<void> => {
  await client.delete(`/admin/recipes/${recipeId}`);
};

/* ── Admin: Recipe image upload (via photo-service) ── */

export const uploadRecipeImage = async (
  recipeId: number,
  file: File,
): Promise<{ message: string; image_url: string }> => {
  const form = new FormData();
  form.append("recipe_id", String(recipeId));
  form.append("file", file);

  const { data } = await axios.post("/photo/change_recipe_image", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
};

/* ── Public: Gem Sockets ── */

export const fetchSocketInfo = async (
  characterId: number,
  itemRowId: number,
  source: string = "inventory",
): Promise<SocketInfoResponse> => {
  const { data } = await client.get(
    `/crafting/${characterId}/socket-info/${itemRowId}`,
    { params: { source } },
  );
  return data;
};

export const insertGem = async (
  characterId: number,
  payload: InsertGemRequest,
): Promise<InsertGemResult> => {
  const { data } = await client.post(
    `/crafting/${characterId}/insert-gem`,
    payload,
  );
  return data;
};

export const extractGem = async (
  characterId: number,
  payload: ExtractGemRequest,
): Promise<ExtractGemResult> => {
  const { data } = await client.post(
    `/crafting/${characterId}/extract-gem`,
    payload,
  );
  return data;
};

/* ── Public: Item Detail & Repair ── */

export const fetchItemDetail = async (
  characterId: number,
  itemRowId: number,
  source = "inventory",
): Promise<ItemDetailResponse> => {
  const { data } = await client.get(
    `/${characterId}/item-detail/${itemRowId}`,
    { params: { source } },
  );
  return data;
};

export const repairItem = async (
  characterId: number,
  payload: RepairItemRequest,
): Promise<RepairItemResult> => {
  const { data } = await client.post(
    `/${characterId}/repair-item`,
    payload,
  );
  return data;
};

/* ── Admin: Set character rank ── */

export const adminSetRank = async (
  characterId: number,
  payload: AdminSetRankRequest,
): Promise<{ detail: string }> => {
  const { data } = await client.post(
    `/admin/professions/${characterId}/set-rank`,
    payload,
  );
  return data;
};

/* ── Admin: Item conversions (refining config, FEAT-165) ── */

export const fetchItemConversions = async (
  itemId: number,
): Promise<ItemConversionsResponse> => {
  const { data } = await client.get(`/admin/items/${itemId}/conversions`);
  return data;
};

export const putItemConversions = async (
  itemId: number,
  payload: ItemConversionsPayload,
): Promise<ItemConversionsResponse> => {
  const { data } = await client.put(
    `/admin/items/${itemId}/conversions`,
    payload,
  );
  return data;
};
