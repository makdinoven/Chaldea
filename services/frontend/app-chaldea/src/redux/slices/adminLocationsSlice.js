import {createSlice} from '@reduxjs/toolkit';
import {fetchCountriesList, fetchCountryDetails, fetchRegionDetails} from '../actions/adminLocationsActions';

const initialState = {
    countries: [],
    countryDetails: {},  // Хранит детали стран по id
    regionDetails: {},   // Хранит детали регионов по id
    loading: false,
    error: null
};

const adminLocationsSlice = createSlice({
    name: 'adminLocations',
    initialState,
    reducers: {},
    extraReducers: (builder) => {
        builder
            // Обработка fetchCountriesList
            .addCase(fetchCountriesList.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchCountriesList.fulfilled, (state, action) => {
                state.countries = action.payload || [];
                state.loading = false;
                state.error = null;
            })
            .addCase(fetchCountriesList.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload || 'Ошибка загрузки списка стран';
                state.countries = [];
            })
            // Обработка fetchCountryDetails
            .addCase(fetchCountryDetails.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchCountryDetails.fulfilled, (state, action) => {
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
            // Обработка fetchRegionDetails
            .addCase(fetchRegionDetails.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchRegionDetails.fulfilled, (state, action) => {
                if (action.payload) {
                    state.regionDetails[action.payload.id] = action.payload;
                }
                state.loading = false;
                state.error = null;
            })
            .addCase(fetchRegionDetails.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload || 'Ошибка загрузки деталей региона';
            });
    }
});

export default adminLocationsSlice.reducer;