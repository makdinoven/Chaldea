import { createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';

// --- Types ---

export interface ZonePoint {
  x: number;
  y: number;
}

export interface ClickableZone {
  id: number;
  parent_type: 'area' | 'country';
  parent_id: number;
  target_type: 'country' | 'region';
  target_id: number;
  zone_data: ZonePoint[];
  label: string | null;
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

export const fetchRegionDetails = createAsyncThunk<
  { id: number; name: string; map_image_url: string | null; recommended_level: number | null; districts: { id: number; name: string; image_url: string | null; locations: { id: number; name: string; marker_type: string; x: number | null; y: number | null; image_url: string | null }[] }[] },
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
