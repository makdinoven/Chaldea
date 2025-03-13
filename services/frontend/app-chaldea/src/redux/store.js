import {configureStore} from '@reduxjs/toolkit';
import countriesReducer from './slices/countriesSlice.js';
import countryDetailsReducer from './slices/countryDetailsSlice.js';
import regionsSliceReducer from "./slices/regionsSlice.js";

export const store = configureStore({
    reducer: {
        countries: countriesReducer,
        countryDetails: countryDetailsReducer,
        regions: regionsSliceReducer
    },
});

export default store;
