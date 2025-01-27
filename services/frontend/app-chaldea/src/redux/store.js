import { configureStore } from '@reduxjs/toolkit';
import countriesReducer from './slices/countriesSlice.js';
import countryDetailsReducer from './slices/countryDetailsSlice.js';

export const store = configureStore({
    reducer: {
        countries: countriesReducer,
        countryDetails: countryDetailsReducer
    },
});

export default store;
