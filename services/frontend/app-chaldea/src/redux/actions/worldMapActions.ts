import { createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';

// --- Types ---

export interface PathWaypoint {
  x: number;  // 0-100 percentage
  y: number;  // 0-100 percentage
}

export interface NeighborEdge {
  from_id: number;
  to_id: number;
  energy_cost: number;
  path_data: PathWaypoint[] | null;
}

export interface ArrowEdge {
  location_id: number;
  arrow_id: number;
  energy_cost: number;
  path_data: PathWaypoint[] | null;
}

export interface ZonePoint {
  x: number;
  y: number;
}

export interface ClickableZone {
  id: number;
  parent_type: 'area' | 'country';
  parent_id: number;
  target_type: 'country' | 'region' | 'area';
  target_id: number;
  zone_data: ZonePoint[];
  label: string | null;
  stroke_color: string | null;
}

export interface Area {
  id: number;
  name: string;
  description: string;
  map_image_url: string | null;
  sort_order: number;
}

export interface AreaCountry {
  id: number;
  name: string;
  x: number | null;
  y: number | null;
  map_image_url: string | null;
  emblem_url: string | null;
}

export interface AreaWithCountries extends Area {
  countries: AreaCountry[];
}

export interface HierarchyNode {
  id: number;
  name: string;
  type: 'area' | 'country' | 'region' | 'district' | 'location';
  marker_type?: string | null;
  children: HierarchyNode[];
}

// --- Async Thunks ---

export const fetchAreas = createAsyncThunk<
  Area[],
  void,
  { rejectValue: string }
>(
  'worldMap/fetchAreas',
  async (_, thunkAPI) => {
    try {
      const response = await axios.get('/locations/areas/list');
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить области');
    }
  },
);

export const fetchAreaDetails = createAsyncThunk<
  AreaWithCountries,
  number,
  { rejectValue: string }
>(
  'worldMap/fetchAreaDetails',
  async (areaId, thunkAPI) => {
    try {
      const response = await axios.get(`/locations/areas/${areaId}/details`);
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить данные области');
    }
  },
);

export const fetchClickableZones = createAsyncThunk<
  ClickableZone[],
  { parentType: 'area' | 'country'; parentId: number },
  { rejectValue: string }
>(
  'worldMap/fetchClickableZones',
  async ({ parentType, parentId }, thunkAPI) => {
    try {
      const response = await axios.get(`/locations/clickable-zones/${parentType}/${parentId}`);
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить зоны карты');
    }
  },
);

export const fetchHierarchyTree = createAsyncThunk<
  HierarchyNode[],
  void,
  { rejectValue: string }
>(
  'worldMap/fetchHierarchyTree',
  async (_, thunkAPI) => {
    try {
      const response = await axios.get('/locations/hierarchy/tree');
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить дерево локаций');
    }
  },
);

export const fetchCountryDetails = createAsyncThunk<
  { id: number; name: string; map_image_url: string | null; regions: { id: number; name: string; recommended_level: number | null; x: number | null; y: number | null }[] },
  number,
  { rejectValue: string }
>(
  'worldMap/fetchCountryDetails',
  async (countryId, thunkAPI) => {
    try {
      const response = await axios.get(`/locations/countries/${countryId}/details`);
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить данные страны');
    }
  },
);

export const updateDistrictPosition = createAsyncThunk<
  { id: number; x: number | null; y: number | null },
  { districtId: number; x: number | null; y: number | null },
  { rejectValue: string }
>(
  'worldMap/updateDistrictPosition',
  async ({ districtId, x, y }, thunkAPI) => {
    try {
      const response = await axios.put(`/locations/districts/${districtId}/update`, { x, y });
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось обновить позицию зоны');
    }
  },
);

export const fetchRegionDetails = createAsyncThunk<
  { id: number; name: string; map_image_url: string | null; recommended_level: number | null; neighbor_edges: NeighborEdge[]; arrow_edges?: ArrowEdge[]; map_items: { id: number; name: string; type: 'location' | 'district' | 'arrow'; map_icon_url: string | null; map_x: number | null; map_y: number | null; marker_type: string | null; image_url: string | null; map_image_url?: string | null; target_region_id?: number | null; target_region_name?: string | null; paired_arrow_id?: number | null }[]; districts: { id: number; name: string; image_url: string | null; map_icon_url: string | null; map_image_url?: string | null; parent_district_id: number | null; x: number | null; y: number | null; sort_order: number; locations: { id: number; name: string; marker_type: string; image_url: string | null; map_icon_url: string | null; map_x: number | null; map_y: number | null; sort_order: number }[] }[] },
  number,
  { rejectValue: string }
>(
  'worldMap/fetchRegionDetails',
  async (regionId, thunkAPI) => {
    try {
      const response = await axios.get(`/locations/regions/${regionId}/details`);
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить данные региона');
    }
  },
);

export const uploadLocationIcon = createAsyncThunk<
  { message: string; map_icon_url: string },
  { locationId: number; file: File },
  { rejectValue: string }
>(
  'worldMap/uploadLocationIcon',
  async ({ locationId, file }, thunkAPI) => {
    try {
      const formData = new FormData();
      formData.append('location_id', String(locationId));
      formData.append('file', file);

      const response = await axios.post('/photo/change_location_icon', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось загрузить иконку локации');
    }
  },
);

export const updateLocationPosition = createAsyncThunk<
  { id: number; map_x: number | null; map_y: number | null },
  { locationId: number; map_x: number | null; map_y: number | null },
  { rejectValue: string }
>(
  'worldMap/updateLocationPosition',
  async ({ locationId, map_x, map_y }, thunkAPI) => {
    try {
      const response = await axios.put(`/locations/${locationId}/update`, { map_x, map_y });
      return response.data;
    } catch {
      return thunkAPI.rejectWithValue('Не удалось обновить позицию локации');
    }
  },
);
