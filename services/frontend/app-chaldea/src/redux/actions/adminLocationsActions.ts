import { createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';
import type { Area, ClickableZone, ZonePoint, PathWaypoint, NeighborEdge, ArrowEdge } from './worldMapActions';

// --- Types ---

export interface Country {
  id: number;
  name: string;
  description: string;
  map_image_url: string | null;
  emblem_url: string | null;
  area_id: number | null;
  x: number | null;
  y: number | null;
}

export interface Region {
  id: number;
  name: string;
  description: string;
  country_id: number;
}

export interface District {
  id: number;
  name: string;
  description: string;
  region_id: number;
  image_url: string | null;
  map_icon_url: string | null;
  map_image_url: string | null;
  parent_district_id: number | null;
  marker_type: string | null;
  recommended_level: number | null;
  x: number | null;
  y: number | null;
  sort_order: number;
  locations: LocationItem[];
}

export interface LocationItem {
  id: number;
  name: string;
  type: string;
  image_url: string | null;
  marker_type: string;
  map_icon_url: string | null;
  map_x: number | null;
  map_y: number | null;
  sort_order: number;
  children?: LocationItem[];
}

export interface CountryDetails {
  id: number;
  name: string;
  description: string;
  map_image_url: string | null;
  emblem_url: string | null;
  area_id: number | null;
  regions: Region[];
}

export interface RegionMapItem {
  id: number;
  name: string;
  type: 'location' | 'district' | 'arrow';
  map_icon_url: string | null;
  map_x: number | null;
  map_y: number | null;
  marker_type: string | null;
  image_url: string | null;
  map_image_url?: string | null;
  district_id?: number | null;
  parent_district_id?: number | null;
  sort_order?: number;
  recommended_level?: number | null;
  target_region_id?: number | null;
  target_region_name?: string | null;
  paired_arrow_id?: number | null;
}

export interface RegionDetails {
  id: number;
  name: string;
  description: string;
  country_id: number;
  map_image_url: string | null;
  neighbor_edges: NeighborEdge[];
  arrow_edges?: ArrowEdge[];
  map_items: RegionMapItem[];
  districts: District[];
}

export interface AreaCreateData {
  name: string;
  description: string;
  sort_order?: number;
}

export interface AreaUpdateData {
  id: number;
  name?: string;
  description?: string;
  sort_order?: number;
}

export interface ClickableZoneCreateData {
  parent_type: 'area' | 'country';
  parent_id: number;
  target_type: 'country' | 'region' | 'area';
  target_id: number;
  zone_data: ZonePoint[];
  label?: string;
  stroke_color?: string;
}

export interface ClickableZoneUpdateData {
  id: number;
  parent_type?: 'area' | 'country';
  parent_id?: number;
  target_type?: 'country' | 'region' | 'area';
  target_id?: number;
  zone_data?: ZonePoint[];
  label?: string;
  stroke_color?: string;
}

// Re-export for convenience
export type { Area, ClickableZone, ZonePoint, PathWaypoint, NeighborEdge, ArrowEdge };

// --- Arrow Types ---

export interface TransitionArrowRead {
  id: number;
  region_id: number;
  target_region_id: number;
  target_region_name: string | null;
  paired_arrow_id: number | null;
  x: number | null;
  y: number | null;
  label: string | null;
}

export interface TransitionArrowCreateResponse {
  arrow: TransitionArrowRead;
  paired_arrow: TransitionArrowRead;
}

export interface ArrowNeighborRead {
  id: number;
  location_id: number;
  arrow_id: number;
  energy_cost: number;
  path_data: PathWaypoint[] | null;
}

// --- Existing Thunks (migrated from JS) ---

export const fetchCountriesList = createAsyncThunk<
  Country[],
  void,
  { rejectValue: string }
>(
  'adminLocations/fetchCountriesList',
  async (_, { rejectWithValue }) => {
    try {
      const response = await axios.get('/locations/countries/list');
      return response.data;
    } catch {
      return rejectWithValue('Ошибка загрузки списка стран');
    }
  }
);

export const fetchCountryDetails = createAsyncThunk<
  CountryDetails,
  number,
  { rejectValue: string }
>(
  'adminLocations/fetchCountryDetails',
  async (countryId, { rejectWithValue }) => {
    try {
      const response = await axios.get(`/locations/countries/${countryId}/details`);
      return response.data;
    } catch {
      return rejectWithValue('Ошибка загрузки деталей страны');
    }
  }
);

export const fetchRegionDetails = createAsyncThunk<
  RegionDetails,
  number,
  { rejectValue: string }
>(
  'adminLocations/fetchRegionDetails',
  async (regionId, { rejectWithValue }) => {
    try {
      const response = await axios.get(`/locations/regions/${regionId}/details`);
      return response.data;
    } catch {
      return rejectWithValue('Ошибка загрузки деталей региона');
    }
  }
);

// --- New Area Thunks ---

export const fetchAreasList = createAsyncThunk<
  Area[],
  void,
  { rejectValue: string }
>(
  'adminLocations/fetchAreasList',
  async (_, { rejectWithValue }) => {
    try {
      const response = await axios.get('/locations/areas/list');
      return response.data;
    } catch {
      return rejectWithValue('Ошибка загрузки списка областей');
    }
  }
);

export const createArea = createAsyncThunk<
  Area,
  AreaCreateData,
  { rejectValue: string }
>(
  'adminLocations/createArea',
  async (areaData, { rejectWithValue }) => {
    try {
      const response = await axios.post('/locations/areas/create', areaData);
      return response.data;
    } catch {
      return rejectWithValue('Ошибка создания области');
    }
  }
);

export const updateArea = createAsyncThunk<
  Area,
  AreaUpdateData,
  { rejectValue: string }
>(
  'adminLocations/updateArea',
  async ({ id, ...areaData }, { rejectWithValue }) => {
    try {
      const response = await axios.put(`/locations/areas/${id}/update`, areaData);
      return response.data;
    } catch {
      return rejectWithValue('Ошибка обновления области');
    }
  }
);

export const deleteArea = createAsyncThunk<
  number,
  number,
  { rejectValue: string }
>(
  'adminLocations/deleteArea',
  async (areaId, { rejectWithValue }) => {
    try {
      await axios.delete(`/locations/areas/${areaId}/delete`);
      return areaId;
    } catch {
      return rejectWithValue('Ошибка удаления области');
    }
  }
);

export const uploadAreaMap = createAsyncThunk<
  { message: string; map_image_url: string },
  { areaId: number; file: File },
  { rejectValue: string }
>(
  'adminLocations/uploadAreaMap',
  async ({ areaId, file }, { rejectWithValue }) => {
    try {
      const formData = new FormData();
      formData.append('area_id', String(areaId));
      formData.append('file', file);

      const response = await axios.post('/photo/change_area_map', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return response.data;
    } catch {
      return rejectWithValue('Ошибка загрузки карты области');
    }
  }
);

// --- New ClickableZone Thunks ---

export const fetchClickableZones = createAsyncThunk<
  ClickableZone[],
  { parentType: 'area' | 'country'; parentId: number },
  { rejectValue: string }
>(
  'adminLocations/fetchClickableZones',
  async ({ parentType, parentId }, { rejectWithValue }) => {
    try {
      const response = await axios.get(`/locations/clickable-zones/${parentType}/${parentId}`);
      return response.data;
    } catch {
      return rejectWithValue('Ошибка загрузки кликабельных зон');
    }
  }
);

export const createClickableZone = createAsyncThunk<
  ClickableZone,
  ClickableZoneCreateData,
  { rejectValue: string }
>(
  'adminLocations/createClickableZone',
  async (zoneData, { rejectWithValue }) => {
    try {
      const response = await axios.post('/locations/clickable-zones/create', zoneData);
      return response.data;
    } catch {
      return rejectWithValue('Ошибка создания кликабельной зоны');
    }
  }
);

export const updateClickableZone = createAsyncThunk<
  ClickableZone,
  ClickableZoneUpdateData,
  { rejectValue: string }
>(
  'adminLocations/updateClickableZone',
  async ({ id, ...zoneData }, { rejectWithValue }) => {
    try {
      const response = await axios.put(`/locations/clickable-zones/${id}/update`, zoneData);
      return response.data;
    } catch {
      return rejectWithValue('Ошибка обновления кликабельной зоны');
    }
  }
);

export const uploadDistrictMap = createAsyncThunk<
  { message: string; map_image_url: string },
  { districtId: number; file: File },
  { rejectValue: string }
>(
  'adminLocations/uploadDistrictMap',
  async ({ districtId, file }, { rejectWithValue }) => {
    try {
      const formData = new FormData();
      formData.append('district_id', String(districtId));
      formData.append('file', file);

      const response = await axios.post('/photo/change_district_map', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return response.data;
    } catch {
      return rejectWithValue('Ошибка загрузки карты района');
    }
  }
);

export const deleteClickableZone = createAsyncThunk<
  number,
  number,
  { rejectValue: string }
>(
  'adminLocations/deleteClickableZone',
  async (zoneId, { rejectWithValue }) => {
    try {
      await axios.delete(`/locations/clickable-zones/${zoneId}/delete`);
      return zoneId;
    } catch {
      return rejectWithValue('Ошибка удаления кликабельной зоны');
    }
  }
);

// --- Path Editor Thunks ---

export const createNeighborWithPath = createAsyncThunk<
  { neighbor_id: number; energy_cost: number; path_data: PathWaypoint[] | null },
  { locationId: number; neighbor_id: number; energy_cost: number; path_data: PathWaypoint[] | null },
  { rejectValue: string }
>(
  'adminLocations/createNeighborWithPath',
  async ({ locationId, neighbor_id, energy_cost, path_data }, { rejectWithValue }) => {
    try {
      const response = await axios.post(`/locations/${locationId}/neighbors/`, {
        neighbor_id,
        energy_cost,
        path_data,
      });
      return response.data;
    } catch {
      return rejectWithValue('Ошибка создания связи между локациями');
    }
  }
);

export const updateNeighborPath = createAsyncThunk<
  NeighborEdge,
  { fromId: number; toId: number; path_data: PathWaypoint[] },
  { rejectValue: string }
>(
  'adminLocations/updateNeighborPath',
  async ({ fromId, toId, path_data }, { rejectWithValue }) => {
    try {
      const response = await axios.put(`/locations/neighbors/${fromId}/${toId}/path`, {
        path_data,
      });
      return response.data;
    } catch {
      return rejectWithValue('Ошибка обновления пути между локациями');
    }
  }
);

export const deleteNeighborEdge = createAsyncThunk<
  { locationId: number; neighborId: number },
  { locationId: number; neighborId: number },
  { rejectValue: string }
>(
  'adminLocations/deleteNeighborEdge',
  async ({ locationId, neighborId }, { rejectWithValue }) => {
    try {
      await axios.delete(`/locations/${locationId}/neighbors/${neighborId}`);
      return { locationId, neighborId };
    } catch {
      return rejectWithValue('Ошибка удаления связи между локациями');
    }
  }
);

// --- Transition Arrow Thunks ---

export const createTransitionArrow = createAsyncThunk<
  TransitionArrowCreateResponse,
  { region_id: number; target_region_id: number; x: number | null; y: number | null; label: string | null },
  { rejectValue: string }
>(
  'adminLocations/createTransitionArrow',
  async (data, { rejectWithValue }) => {
    try {
      const response = await axios.post('/locations/arrows/create', data);
      return response.data;
    } catch {
      return rejectWithValue('Ошибка создания стрелки перехода');
    }
  }
);

export const updateTransitionArrow = createAsyncThunk<
  TransitionArrowRead,
  { arrowId: number; x?: number | null; y?: number | null; label?: string | null },
  { rejectValue: string }
>(
  'adminLocations/updateTransitionArrow',
  async ({ arrowId, ...data }, { rejectWithValue }) => {
    try {
      const response = await axios.put(`/locations/arrows/${arrowId}/update`, data);
      return response.data;
    } catch {
      return rejectWithValue('Ошибка обновления стрелки перехода');
    }
  }
);

export const deleteTransitionArrow = createAsyncThunk<
  { deleted_ids: number[] },
  number,
  { rejectValue: string }
>(
  'adminLocations/deleteTransitionArrow',
  async (arrowId, { rejectWithValue }) => {
    try {
      const response = await axios.delete(`/locations/arrows/${arrowId}/delete`);
      return response.data;
    } catch {
      return rejectWithValue('Ошибка удаления стрелки перехода');
    }
  }
);

export const createArrowNeighbor = createAsyncThunk<
  ArrowNeighborRead,
  { arrowId: number; location_id: number; energy_cost: number; path_data: PathWaypoint[] | null },
  { rejectValue: string }
>(
  'adminLocations/createArrowNeighbor',
  async ({ arrowId, location_id, energy_cost, path_data }, { rejectWithValue }) => {
    try {
      const response = await axios.post(`/locations/arrows/${arrowId}/neighbors/`, {
        location_id,
        energy_cost,
        path_data,
      });
      return response.data;
    } catch {
      return rejectWithValue('Ошибка создания пути к стрелке');
    }
  }
);

export const updateArrowNeighborPath = createAsyncThunk<
  ArrowNeighborRead,
  { locationId: number; arrowId: number; path_data: PathWaypoint[] },
  { rejectValue: string }
>(
  'adminLocations/updateArrowNeighborPath',
  async ({ locationId, arrowId, path_data }, { rejectWithValue }) => {
    try {
      const response = await axios.put(`/locations/arrows/neighbors/${locationId}/${arrowId}/path`, {
        path_data,
      });
      return response.data;
    } catch {
      return rejectWithValue('Ошибка обновления пути к стрелке');
    }
  }
);

export const deleteArrowNeighbor = createAsyncThunk<
  { locationId: number; arrowId: number },
  { locationId: number; arrowId: number },
  { rejectValue: string }
>(
  'adminLocations/deleteArrowNeighbor',
  async ({ locationId, arrowId }, { rejectWithValue }) => {
    try {
      await axios.delete(`/locations/arrows/neighbors/${locationId}/${arrowId}`);
      return { locationId, arrowId };
    } catch {
      return rejectWithValue('Ошибка удаления пути к стрелке');
    }
  }
);
