import { createSlice } from '@reduxjs/toolkit';
import { createCountry, updateCountry, uploadCountryMap, deleteCountry } from '../actions/countryEditActions';

const countryEditSlice = createSlice({
    name: 'countryEdit',
    initialState: {
        loading: false,
        error: null,
        success: false
    },
    reducers: {
        resetCountryEditState: (state) => {
            state.loading = false;
            state.error = null;
            state.success = false;
        }
    },
    extraReducers: (builder) => {
        builder
            .addCase(createCountry.pending, (state) => {
                state.loading = true;
                state.error = null;
                state.success = false;
            })
            .addCase(createCountry.fulfilled, (state) => {
                state.loading = false;
                state.success = true;
            })
            .addCase(createCountry.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })

            .addCase(updateCountry.pending, (state) => {
                state.loading = true;
                state.error = null;
                state.success = false;
            })
            .addCase(updateCountry.fulfilled, (state) => {
                state.loading = false;
                state.success = true;
            })
            .addCase(updateCountry.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })

            .addCase(uploadCountryMap.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(uploadCountryMap.fulfilled, (state) => {
                state.loading = false;
            })
            .addCase(uploadCountryMap.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })

            .addCase(deleteCountry.pending, (state) => {
                state.loading = true;
                state.error = null;
                state.success = false;
            })
            .addCase(deleteCountry.fulfilled, (state) => {
                state.loading = false;
                state.success = true;
            })
            .addCase(deleteCountry.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            });
    }
});

export const { resetCountryEditState } = countryEditSlice.actions;
export default countryEditSlice.reducer;