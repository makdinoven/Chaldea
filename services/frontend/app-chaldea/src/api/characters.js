import axios from "axios";

const charClient = axios.create({
  baseURL: "",
  timeout: 10000,
});

// ── Request interceptor: attach JWT token ──
charClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("accessToken");
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const fetchCharacters = async () => {
  const { data } = await charClient.get("/characters/list");
  return data;
};