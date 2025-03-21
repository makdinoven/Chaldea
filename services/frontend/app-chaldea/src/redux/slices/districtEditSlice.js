import { createSlice } from '@reduxjs/toolkit';
import { createDistrict, updateDistrict, uploadDistrictImage, fetchDistrictDetails, fetchLocationsList, fetchDistrictLocations } from '../actions/districtEditActions';

const initialState = {
    currentDistrict: null,
    loading: false,
    error: null,
    districtLocations: []
};

const districtEditSlice = createSlice({
    name: 'districtEdit',
    initialState,
    reducers: {
        resetDistrictEditState: (state) => {
            state.currentDistrict = null;
            state.loading = false;
            state.error = null;
            state.districtLocations = [];
        }
    },
    extraReducers: (builder) => {
        builder
            .addCase(createDistrict.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(createDistrict.fulfilled, (state, action) => {
                state.currentDistrict = action.payload;
                state.loading = false;
            })
            .addCase(createDistrict.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })
            .addCase(updateDistrict.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(updateDistrict.fulfilled, (state, action) => {
                state.currentDistrict = action.payload;
                state.loading = false;
            })
            .addCase(updateDistrict.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })
            .addCase(fetchDistrictDetails.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchDistrictDetails.fulfilled, (state, action) => {
                state.currentDistrict = action.payload;
                state.loading = false;
            })
            .addCase(fetchDistrictDetails.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })
            .addCase(fetchLocationsList.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchLocationsList.fulfilled, (state, action) => {
                state.districtLocations = action.payload;
                state.loading = false;
            })
            .addCase(fetchLocationsList.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })
            .addCase(fetchDistrictLocations.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchDistrictLocations.fulfilled, (state, action) => {
                state.districtLocations = Array.isArray(action.payload) ? action.payload : [];
                state.loading = false;
            })
            .addCase(fetchDistrictLocations.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
                state.districtLocations = [];
            });
    }
});

export const { resetDistrictEditState } = districtEditSlice.actions;
export default districtEditSlice.reducer;