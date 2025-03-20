import { createSlice } from '@reduxjs/toolkit';
import { createDistrict, updateDistrict, uploadDistrictImage, fetchDistrictDetails } from '../actions/districtEditActions';

const initialState = {
    currentDistrict: null,
    loading: false,
    error: null
};

const districtEditSlice = createSlice({
    name: 'districtEdit',
    initialState,
    reducers: {
        resetDistrictEditState: (state) => {
            state.currentDistrict = null;
            state.loading = false;
            state.error = null;
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
            });
    }
});

export const { resetDistrictEditState } = districtEditSlice.actions;
export default districtEditSlice.reducer;