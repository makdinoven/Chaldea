import axios from 'axios';

export type MapOutlineParentType = 'area' | 'country';

/** A point on the map in percent of the image (same space as zone_data) */
export interface MapSamplePoint {
  x: number;
  y: number;
}

export interface MapOutlineSettings {
  samples: MapSamplePoint[];
  tolerance: number;
}

export interface MapOutlineRequest extends MapOutlineSettings {
  parent_type: MapOutlineParentType;
  parent_id: number;
  /** Set = preview/apply only this zone and store the settings as its own */
  zone_id?: number;
}

export interface MapOutlinePreview {
  /** data:image/png;base64 — water tinted, land transparent, same aspect as the map */
  mask_png: string;
  width: number;
  height: number;
  /** 0..1 share of land pixels */
  land_ratio: number;
}

export interface MapOutlineApplyResult {
  zones_updated: number;
  /** Zone ids where no land was found (they keep the rough polygon) */
  zones_empty: number[];
}

export const MAX_WATER_SAMPLES = 8;
export const MIN_TOLERANCE = 1;
export const MAX_TOLERANCE = 60;
export const DEFAULT_TOLERANCE = 18;

export const fetchMapOutlineSettings = async (
  parentType: MapOutlineParentType,
  parentId: number,
): Promise<MapOutlineSettings | null> => {
  const { data } = await axios.get<MapOutlineSettings | null>(
    `/photo/map_outlines/settings/${parentType}/${parentId}`,
  );
  return data ?? null;
};

export const previewMapOutlines = async (payload: MapOutlineRequest): Promise<MapOutlinePreview> => {
  const { data } = await axios.post<MapOutlinePreview>('/photo/map_outlines/preview', payload);
  return data;
};

export const applyMapOutlines = async (payload: MapOutlineRequest): Promise<MapOutlineApplyResult> => {
  const { data } = await axios.post<MapOutlineApplyResult>('/photo/map_outlines/apply', payload);
  return data;
};

/** Drop a zone's own settings; the server recomputes it with the map settings */
export const resetZoneOutlineSettings = async (zoneId: number): Promise<{ precise_path: string | null }> => {
  const { data } = await axios.delete<{ precise_path: string | null }>(
    `/photo/map_outlines/zone/${zoneId}/settings`,
  );
  return data;
};

/** Russian error text from an axios error (FastAPI `detail`), with a fallback */
export const mapOutlineErrorMessage = (error: unknown, fallback: string): string => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string' && detail) return detail;
    if (!error.response) return 'Сервер недоступен, попробуйте позже';
  }
  return fallback;
};
