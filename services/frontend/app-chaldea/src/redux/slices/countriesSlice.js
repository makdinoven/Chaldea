import {createSlice} from '@reduxjs/toolkit';
import {fetchCountries} from '../actions/countryActions';

const countriesSlice = createSlice({
    name: 'countries',
    initialState: {
        countries: [],
        loading: true,
        isLoaded: false,
        openedCountryId: null,
        error: null,
    },
    reducers: {
        setOpenedCountryId: (state, action) => {
            state.openedCountryId = action.payload;
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(fetchCountries.pending, (state) => {
                state.loading = true;
            })
            .addCase(fetchCountries.fulfilled, (state, action) => {
                state.countries = action.payload;
                state.loading = false;
                if (action.payload.length > 0) {
                    state.openedCountryId = action.payload[0]?.id;
                    state.isLoaded = true;
                }
            })
            .addCase(fetchCountries.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            });
    },
});

export const {setOpenedCountryId} = countriesSlice.actions;
export default countriesSlice.reducer;
