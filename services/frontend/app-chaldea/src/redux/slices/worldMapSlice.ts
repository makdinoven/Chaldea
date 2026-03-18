import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from '../store';
import {
  fetchAreas,
  fetchAreaDetails,
  fetchClickableZones,
  fetchHierarchyTree,
  fetchCountryDetails,
  fetchRegionDetails,
  Area,
  AreaWithCountries,
  ClickableZone,
  HierarchyNode,
} from '../actions/worldMapActions';

// --- Types ---

export type MapLevel = 'world' | 'area' | 'country' | 'region';

export interface CountryDetailsData {
  id: number;
  name: string;
  map_image_url: string | null;
  regions: {
    id: number;
    name: string;
    recommended_level: number | null;
    x: number | null;
    y: number | null;
  }[];
}

export interface RegionDetailsData {
  id: number;
  name: string;
  map_image_url: string | null;
  recommended_level: number | null;
  districts: {
    id: number;
    name: string;
    image_url: string | null;
    locations: {
      id: number;
      name: string;
      marker_type: string;
      x: number | null;
      y: number | null;
      image_url: string | null;
    }[];
  }[];
}

export interface WorldMapState {
  areas: Area[];
  hierarchyTree: HierarchyNode[];
  currentLevel: MapLevel;
  currentEntityId: number | null;
  clickableZones: ClickableZone[];
  areaDetails: AreaWithCountries | null;
  countryDetails: CountryDetailsData | null;
  regionDetails: RegionDetailsData | null;
  loading: boolean;
  error: string | null;
}

// --- Initial State ---

const initialState: WorldMapState = {
  areas: [],
  hierarchyTree: [],
  currentLevel: 'world',
  currentEntityId: null,
  clickableZones: [],
  areaDetails: null,
  countryDetails: null,
  regionDetails: null,
  loading: false,
  error: null,
};

// --- Slice ---

const worldMapSlice = createSlice({
  name: 'worldMap',
  initialState,
  reducers: {
    setCurrentLevel(state, action: PayloadAction<{ level: MapLevel; entityId: number | null }>) {
      state.currentLevel = action.payload.level;
      state.currentEntityId = action.payload.entityId;
    },
    clearError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // fetchAreas
      .addCase(fetchAreas.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchAreas.fulfilled, (state, action: PayloadAction<Area[]>) => {
        state.areas = action.payload;
        state.loading = false;
      })
      .addCase(fetchAreas.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload ?? 'Не удалось загрузить области';
      })
      // fetchAreaDetails
      .addCase(fetchAreaDetails.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchAreaDetails.fulfilled, (state, action: PayloadAction<AreaWithCountries>) => {
        state.areaDetails = action.payload;
        state.loading = false;
      })
      .addCase(fetchAreaDetails.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload ?? 'Не удалось загрузить данные области';
      })
      // fetchClickableZones
      .addCase(fetchClickableZones.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchClickableZones.fulfilled, (state, action: PayloadAction<ClickableZone[]>) => {
        state.clickableZones = action.payload;
        state.loading = false;
      })
      .addCase(fetchClickableZones.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload ?? 'Не удалось загрузить зоны карты';
      })
      // fetchHierarchyTree
      .addCase(fetchHierarchyTree.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchHierarchyTree.fulfilled, (state, action: PayloadAction<HierarchyNode[]>) => {
        state.hierarchyTree = action.payload;
        state.loading = false;
      })
      .addCase(fetchHierarchyTree.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload ?? 'Не удалось загрузить дерево локаций';
      })
      // fetchCountryDetails
      .addCase(fetchCountryDetails.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchCountryDetails.fulfilled, (state, action) => {
        state.countryDetails = action.payload;
        state.loading = false;
      })
      .addCase(fetchCountryDetails.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload ?? 'Не удалось загрузить данные страны';
      })
      // fetchRegionDetails
      .addCase(fetchRegionDetails.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchRegionDetails.fulfilled, (state, action) => {
        state.regionDetails = action.payload;
        state.loading = false;
      })
      .addCase(fetchRegionDetails.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload ?? 'Не удалось загрузить данные региона';
      });
  },
});

export const { setCurrentLevel, clearError } = worldMapSlice.actions;

// --- Selectors ---

export const selectAreas = (state: RootState) => state.worldMap.areas;
export const selectHierarchyTree = (state: RootState) => state.worldMap.hierarchyTree;
export const selectCurrentLevel = (state: RootState) => state.worldMap.currentLevel;
export const selectCurrentEntityId = (state: RootState) => state.worldMap.currentEntityId;
export const selectClickableZones = (state: RootState) => state.worldMap.clickableZones;
export const selectAreaDetails = (state: RootState) => state.worldMap.areaDetails;
export const selectCountryDetails = (state: RootState) => state.worldMap.countryDetails;
export const selectRegionDetails = (state: RootState) => state.worldMap.regionDetails;
export const selectWorldMapLoading = (state: RootState) => state.worldMap.loading;
export const selectWorldMapError = (state: RootState) => state.worldMap.error;

export default worldMapSlice.reducer;
