import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import {
  fetchCountriesList,
  fetchCountryDetails,
  fetchRegionDetails,
  fetchAreasList,
  createArea,
  updateArea,
  deleteArea,
  uploadAreaMap,
  fetchClickableZones,
  createClickableZone,
  updateClickableZone,
  deleteClickableZone,
} from '../actions/adminLocationsActions';
import type {
  Country,
  CountryDetails,
  RegionDetails,
  Area,
  ClickableZone,
} from '../actions/adminLocationsActions';

// --- State Interface ---

export interface AdminLocationsState {
  countries: Country[];
  countryDetails: Record<number, CountryDetails>;
  regionDetails: Record<number, RegionDetails>;
  areas: Area[];
  clickableZones: ClickableZone[];
  loading: boolean;
  error: string | null;
}

const initialState: AdminLocationsState = {
  countries: [],
  countryDetails: {},
  regionDetails: {},
  areas: [],
  clickableZones: [],
  loading: false,
  error: null,
};

// --- Slice ---

const adminLocationsSlice = createSlice({
  name: 'adminLocations',
  initialState,
  reducers: {
    clearAdminLocationsError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // --- fetchCountriesList ---
      .addCase(fetchCountriesList.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchCountriesList.fulfilled, (state, action: PayloadAction<Country[]>) => {
        state.countries = action.payload || [];
        state.loading = false;
        state.error = null;
      })
      .addCase(fetchCountriesList.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка загрузки списка стран';
        state.countries = [];
      })

      // --- fetchCountryDetails ---
      .addCase(fetchCountryDetails.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchCountryDetails.fulfilled, (state, action: PayloadAction<CountryDetails>) => {
        if (action.payload) {
          state.countryDetails[action.payload.id] = action.payload;
        }
        state.loading = false;
        state.error = null;
      })
      .addCase(fetchCountryDetails.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка загрузки деталей страны';
      })

      // --- fetchRegionDetails ---
      .addCase(fetchRegionDetails.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchRegionDetails.fulfilled, (state, action: PayloadAction<RegionDetails>) => {
        if (action.payload) {
          state.regionDetails[action.payload.id] = action.payload;
        }
        state.loading = false;
        state.error = null;
      })
      .addCase(fetchRegionDetails.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка загрузки деталей региона';
      })

      // --- fetchAreasList ---
      .addCase(fetchAreasList.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchAreasList.fulfilled, (state, action: PayloadAction<Area[]>) => {
        state.areas = action.payload || [];
        state.loading = false;
      })
      .addCase(fetchAreasList.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка загрузки областей';
      })

      // --- createArea ---
      .addCase(createArea.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(createArea.fulfilled, (state, action: PayloadAction<Area>) => {
        state.areas.push(action.payload);
        state.loading = false;
      })
      .addCase(createArea.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка создания области';
      })

      // --- updateArea ---
      .addCase(updateArea.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(updateArea.fulfilled, (state, action: PayloadAction<Area>) => {
        const index = state.areas.findIndex((a) => a.id === action.payload.id);
        if (index !== -1) {
          state.areas[index] = action.payload;
        }
        state.loading = false;
      })
      .addCase(updateArea.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка обновления области';
      })

      // --- deleteArea ---
      .addCase(deleteArea.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(deleteArea.fulfilled, (state, action: PayloadAction<number>) => {
        state.areas = state.areas.filter((a) => a.id !== action.payload);
        state.loading = false;
      })
      .addCase(deleteArea.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка удаления области';
      })

      // --- uploadAreaMap ---
      .addCase(uploadAreaMap.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(uploadAreaMap.fulfilled, (state, action) => {
        // Update the area's map_image_url in the list
        const url = action.payload.map_image_url;
        // We don't know which area was updated from the payload directly,
        // but the caller should refetch after this
        state.loading = false;
      })
      .addCase(uploadAreaMap.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка загрузки карты области';
      })

      // --- fetchClickableZones ---
      .addCase(fetchClickableZones.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchClickableZones.fulfilled, (state, action: PayloadAction<ClickableZone[]>) => {
        state.clickableZones = action.payload || [];
        state.loading = false;
      })
      .addCase(fetchClickableZones.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка загрузки кликабельных зон';
      })

      // --- createClickableZone ---
      .addCase(createClickableZone.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(createClickableZone.fulfilled, (state, action: PayloadAction<ClickableZone>) => {
        state.clickableZones.push(action.payload);
        state.loading = false;
      })
      .addCase(createClickableZone.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка создания кликабельной зоны';
      })

      // --- updateClickableZone ---
      .addCase(updateClickableZone.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(updateClickableZone.fulfilled, (state, action: PayloadAction<ClickableZone>) => {
        const index = state.clickableZones.findIndex((z) => z.id === action.payload.id);
        if (index !== -1) {
          state.clickableZones[index] = action.payload;
        }
        state.loading = false;
      })
      .addCase(updateClickableZone.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка обновления кликабельной зоны';
      })

      // --- deleteClickableZone ---
      .addCase(deleteClickableZone.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(deleteClickableZone.fulfilled, (state, action: PayloadAction<number>) => {
        state.clickableZones = state.clickableZones.filter((z) => z.id !== action.payload);
        state.loading = false;
      })
      .addCase(deleteClickableZone.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Ошибка удаления кликабельной зоны';
      });
  },
});

export const { clearAdminLocationsError } = adminLocationsSlice.actions;

export default adminLocationsSlice.reducer;
