import axios from "axios";

const archiveClient = axios.create({
  baseURL: "/archive",
  withCredentials: true,
  timeout: 10000,
});

// ── Request interceptor: attach JWT token ──
archiveClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("accessToken");
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

archiveClient.interceptors.response.use(
  (r) => r,
  (e) => {
    if (e.response) {
      throw new Error(e.response.data?.detail || e.response.statusText);
    }
    throw e;
  },
);

// ── Types ──

export interface ArchiveCategory {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface ArchiveCategoryWithCount extends ArchiveCategory {
  article_count: number;
}

export interface ArchiveCategoryCreate {
  name: string;
  slug: string;
  description?: string;
  sort_order?: number;
}

export interface ArchiveCategoryUpdate {
  name?: string;
  slug?: string;
  description?: string;
  sort_order?: number;
}

export interface ArchiveArticle {
  id: number;
  title: string;
  slug: string;
  content: string | null;
  summary: string | null;
  cover_image_url: string | null;
  is_featured: boolean;
  featured_sort_order: number;
  created_by_user_id: number | null;
  created_at: string;
  updated_at: string;
  categories: ArchiveCategory[];
}

export interface ArchiveArticleListItem {
  id: number;
  title: string;
  slug: string;
  summary: string | null;
  cover_image_url: string | null;
  is_featured: boolean;
  featured_sort_order: number;
  created_at: string;
  updated_at: string;
  categories: ArchiveCategory[];
}

export interface ArchiveArticlePreview {
  id: number;
  title: string;
  slug: string;
  summary: string | null;
  cover_image_url: string | null;
}

export interface ArchiveSearchResult {
  articles: ArchiveArticleListItem[];
  total: number;
}

export interface ArchiveArticleCreate {
  title: string;
  slug: string;
  content?: string;
  summary?: string;
  cover_image_url?: string;
  is_featured?: boolean;
  featured_sort_order?: number;
  category_ids?: number[];
}

export interface ArchiveArticleUpdate {
  title?: string;
  slug?: string;
  content?: string;
  summary?: string;
  cover_image_url?: string;
  is_featured?: boolean;
  featured_sort_order?: number;
  category_ids?: number[];
}

// ── Public API functions ──

export const fetchArticles = async (params?: {
  category_slug?: string;
  search?: string;
  page?: number;
  per_page?: number;
}): Promise<ArchiveSearchResult> => {
  const { data } = await archiveClient.get("/articles", { params });
  return data;
};

export const fetchArticleBySlug = async (slug: string): Promise<ArchiveArticle> => {
  const { data } = await archiveClient.get(`/articles/${slug}`);
  return data;
};

export const fetchArticlePreview = async (slug: string): Promise<ArchiveArticlePreview> => {
  const { data } = await archiveClient.get(`/articles/preview/${slug}`);
  return data;
};

export const fetchCategories = async (): Promise<ArchiveCategoryWithCount[]> => {
  const { data } = await archiveClient.get("/categories");
  return data;
};

export const fetchFeaturedArticles = async (): Promise<ArchiveArticleListItem[]> => {
  const { data } = await archiveClient.get("/featured");
  return data;
};

// ── Admin API functions ──

export const createArticle = async (payload: ArchiveArticleCreate): Promise<ArchiveArticle> => {
  const { data } = await archiveClient.post("/articles/create", payload);
  return data;
};

export const updateArticle = async (id: number, payload: ArchiveArticleUpdate): Promise<ArchiveArticle> => {
  const { data } = await archiveClient.put(`/articles/${id}/update`, payload);
  return data;
};

export const deleteArticle = async (id: number): Promise<void> => {
  await archiveClient.delete(`/articles/${id}/delete`);
};

export const createCategory = async (payload: ArchiveCategoryCreate): Promise<ArchiveCategory> => {
  const { data } = await archiveClient.post("/categories/create", payload);
  return data;
};

export const updateCategory = async (id: number, payload: ArchiveCategoryUpdate): Promise<ArchiveCategory> => {
  const { data } = await archiveClient.put(`/categories/${id}/update`, payload);
  return data;
};

export const deleteCategory = async (id: number): Promise<void> => {
  await archiveClient.delete(`/categories/${id}/delete`);
};

export const reorderCategories = async (order: { id: number; sort_order: number }[]): Promise<void> => {
  await archiveClient.put("/categories/reorder", order);
};

// ── Image upload ──

export const uploadArchiveImage = async (file: File): Promise<{ image_url: string }> => {
  const form = new FormData();
  form.append("file", file);

  const { data } = await axios.post("/photo/upload_archive_image", form, {
    headers: {
      "Content-Type": "multipart/form-data",
      Authorization: `Bearer ${localStorage.getItem("accessToken") || ""}`,
    },
  });
  return data;
};
