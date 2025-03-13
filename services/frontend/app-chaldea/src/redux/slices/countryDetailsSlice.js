import {createSlice} from '@reduxjs/toolkit';
import {fetchCountryDetails} from "../actions/countryActions.js";

const countryDetailsSlice = createSlice({
    name: 'countryDetails',
    initialState: {
        data: {},
        loading: {},
        isLoaded: {},
        error: {}
    },
    reducers: {},
    extraReducers: (builder) => {
        builder
            .addCase(fetchCountryDetails.pending, (state, action) => {
                state.loading[action.meta.arg] = true;
                state.error[action.meta.arg] = null;
            })
            .addCase(fetchCountryDetails.fulfilled, (state, action) => {
                if (action.payload) {
                    const {countryId, country} = action.payload;
                    state.data[countryId] = country; // Сохраняем всю страну
                    state.isLoaded[countryId] = true;
                }
                state.loading[action.meta.arg] = false;
            })
            .addCase(fetchCountryDetails.rejected, (state, action) => {
                state.loading[action.meta.arg] = false;
                state.error[action.meta.arg] = action.payload;
            });
    }
});

export default countryDetailsSlice.reducer;
