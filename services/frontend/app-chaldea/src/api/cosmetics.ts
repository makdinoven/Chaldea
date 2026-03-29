import axios from 'axios';
import { BASE_URL_DEFAULT } from './api';
import type {
  CosmeticFrame,
  CosmeticBackground,
  CosmeticsCatalogResponse,
  UserFramesResponse,
  UserBackgroundsResponse,
  EquipFrameResponse,
  EquipBackgroundResponse,
  CosmeticFrameCreatePayload,
  CosmeticFrameUpdatePayload,
  CosmeticBackgroundCreatePayload,
  CosmeticBackgroundUpdatePayload,
  CosmeticGrantPayload,
  CosmeticGrantResponse,
  CosmeticDeleteResponse,
  CosmeticImageUploadResponse,
} from '../types/cosmetics';

/* ── Public catalog ── */

export const getFramesCatalog = () =>
  axios.get<CosmeticsCatalogResponse<CosmeticFrame>>(
    `${BASE_URL_DEFAULT}/users/cosmetics/frames`,
  );

export const getBackgroundsCatalog = () =>
  axios.get<CosmeticsCatalogResponse<CosmeticBackground>>(
    `${BASE_URL_DEFAULT}/users/cosmetics/backgrounds`,
  );

/* ── User collection ── */

export const getMyFrames = () =>
  axios.get<UserFramesResponse>(
    `${BASE_URL_DEFAULT}/users/cosmetics/my/frames`,
  );

export const getMyBackgrounds = () =>
  axios.get<UserBackgroundsResponse>(
    `${BASE_URL_DEFAULT}/users/cosmetics/my/backgrounds`,
  );

export const equipFrame = (slug: string | null) =>
  axios.put<EquipFrameResponse>(
    `${BASE_URL_DEFAULT}/users/cosmetics/my/frame`,
    { slug },
  );

export const equipBackground = (slug: string | null) =>
  axios.put<EquipBackgroundResponse>(
    `${BASE_URL_DEFAULT}/users/cosmetics/my/background`,
    { slug },
  );

/* ── Admin CRUD: Frames ── */

export const adminCreateFrame = (payload: CosmeticFrameCreatePayload) =>
  axios.post<CosmeticFrame>(
    `${BASE_URL_DEFAULT}/users/admin/cosmetics/frames`,
    payload,
  );

export const adminUpdateFrame = (
  frameId: number,
  payload: CosmeticFrameUpdatePayload,
) =>
  axios.put<CosmeticFrame>(
    `${BASE_URL_DEFAULT}/users/admin/cosmetics/frames/${frameId}`,
    payload,
  );

export const adminDeleteFrame = (frameId: number) =>
  axios.delete<CosmeticDeleteResponse>(
    `${BASE_URL_DEFAULT}/users/admin/cosmetics/frames/${frameId}`,
  );

/* ── Admin CRUD: Backgrounds ── */

export const adminCreateBackground = (
  payload: CosmeticBackgroundCreatePayload,
) =>
  axios.post<CosmeticBackground>(
    `${BASE_URL_DEFAULT}/users/admin/cosmetics/backgrounds`,
    payload,
  );

export const adminUpdateBackground = (
  backgroundId: number,
  payload: CosmeticBackgroundUpdatePayload,
) =>
  axios.put<CosmeticBackground>(
    `${BASE_URL_DEFAULT}/users/admin/cosmetics/backgrounds/${backgroundId}`,
    payload,
  );

export const adminDeleteBackground = (backgroundId: number) =>
  axios.delete<CosmeticDeleteResponse>(
    `${BASE_URL_DEFAULT}/users/admin/cosmetics/backgrounds/${backgroundId}`,
  );

/* ── Admin Grant ── */

export const adminGrantCosmetic = (payload: CosmeticGrantPayload) =>
  axios.post<CosmeticGrantResponse>(
    `${BASE_URL_DEFAULT}/users/admin/cosmetics/grant`,
    payload,
  );

/* ── Admin Image Upload (via photo-service) ── */

export const adminUploadFrameImage = (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  return axios.post<CosmeticImageUploadResponse>(
    `${BASE_URL_DEFAULT}/photo/admin/cosmetics/frames/upload`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
};

export const adminUploadBackgroundImage = (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  return axios.post<CosmeticImageUploadResponse>(
    `${BASE_URL_DEFAULT}/photo/admin/cosmetics/backgrounds/upload`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
};
