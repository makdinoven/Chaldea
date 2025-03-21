import {configureStore} from '@reduxjs/toolkit';
import countriesReducer from './slices/countriesSlice.js';
import countryDetailsReducer from './slices/countryDetailsSlice.js';
import regionsSliceReducer from "./slices/regionsSlice.js";
import adminLocationsReducer from './slices/adminLocationsSlice.js';
import countryEditReducer from './slices/countryEditSlice.js';
import regionEditReducer from './slices/regionEditSlice.js';
import districtEditReducer from './slices/districtEditSlice.js';
import locationEditReducer from './slices/locationEditSlice.js';
export const store = configureStore({
    reducer: {
        countries: countriesReducer,
        countryDetails: countryDetailsReducer,
        regions: regionsSliceReducer,
        adminLocations: adminLocationsReducer,
        countryEdit: countryEditReducer,
        regionEdit: regionEditReducer,
        districtEdit: districtEditReducer,
        locationEdit: locationEditReducer
    }
});

export default store;