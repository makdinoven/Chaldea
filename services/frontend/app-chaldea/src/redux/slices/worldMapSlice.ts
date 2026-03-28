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
  PathWaypoint,
  NeighborEdge,
  ArrowEdge,
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
  paired_location_ids?: number[];
}

export interface RegionDetailsData {
  id: number;
  name: string;
  map_image_url: string | null;
  recommended_level: number | null;
  neighbor_edges: NeighborEdge[];
  arrow_edges?: ArrowEdge[];
  map_items: RegionMapItem[];
  districts: {
    id: number;
    name: string;
    image_url: string | null;
    map_icon_url: string | null;
    map_image_url?: string | null;
    parent_district_id: number | null;
    marker_type?: string | null;
    recommended_level?: number | null;
    x: number | null;
    y: number | null;
    sort_order: number;
    locations: {
      id: number;
      name: string;
      marker_type: string;
      recommended_level?: number | null;
      image_url: string | null;
      map_icon_url: string | null;
      map_x: number | null;
      map_y: number | null;
      sort_order: number;
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
  detailsLoading: boolean;
  zonesLoading: boolean;
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
  detailsLoading: false,
  zonesLoading: false,
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
        state.detailsLoading = true;
        state.areaDetails = null;
        state.error = null;
      })
      .addCase(fetchAreaDetails.fulfilled, (state, action: PayloadAction<AreaWithCountries>) => {
        state.areaDetails = action.payload;
        state.detailsLoading = false;
      })
      .addCase(fetchAreaDetails.rejected, (state, action) => {
        state.detailsLoading = false;
        state.error = action.payload ?? 'Не удалось загрузить данные области';
      })
      // fetchClickableZones
      .addCase(fetchClickableZones.pending, (state) => {
        state.zonesLoading = true;
        state.error = null;
      })
      .addCase(fetchClickableZones.fulfilled, (state, action: PayloadAction<ClickableZone[]>) => {
        state.clickableZones = action.payload;
        state.zonesLoading = false;
      })
      .addCase(fetchClickableZones.rejected, (state, action) => {
        state.zonesLoading = false;
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
        state.detailsLoading = true;
        state.countryDetails = null;
        state.error = null;
      })
      .addCase(fetchCountryDetails.fulfilled, (state, action) => {
        state.countryDetails = action.payload;
        state.detailsLoading = false;
      })
      .addCase(fetchCountryDetails.rejected, (state, action) => {
        state.detailsLoading = false;
        state.error = action.payload ?? 'Не удалось загрузить данные страны';
      })
      // fetchRegionDetails
      .addCase(fetchRegionDetails.pending, (state) => {
        state.detailsLoading = true;
        state.regionDetails = null;
        state.error = null;
      })
      .addCase(fetchRegionDetails.fulfilled, (state, action) => {
        state.regionDetails = action.payload;
        state.detailsLoading = false;
      })
      .addCase(fetchRegionDetails.rejected, (state, action) => {
        state.detailsLoading = false;
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
export const selectDetailsLoading = (state: RootState) => state.worldMap.detailsLoading;
export const selectZonesLoading = (state: RootState) => state.worldMap.zonesLoading;
export const selectWorldMapError = (state: RootState) => state.worldMap.error;

export type { PathWaypoint, NeighborEdge, ArrowEdge };

export default worldMapSlice.reducer;
