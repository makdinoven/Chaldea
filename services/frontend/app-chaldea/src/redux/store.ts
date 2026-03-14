import { configureStore } from '@reduxjs/toolkit';
import { TypedUseSelectorHook, useDispatch, useSelector } from 'react-redux';
import countriesReducer from './slices/countriesSlice.js';
import countryDetailsReducer from './slices/countryDetailsSlice.js';
import regionsSliceReducer from './slices/regionsSlice.js';
import adminLocationsReducer from './slices/adminLocationsSlice.js';
import countryEditReducer from './slices/countryEditSlice.js';
import regionEditReducer from './slices/regionEditSlice.js';
import districtEditReducer from './slices/districtEditSlice.js';
import locationEditReducer from './slices/locationEditSlice.js';
import skillsSlice from './slices/skillsAdminSlice.js';
import userSlice from './slices/userSlice.js';
import notificationReducer from './slices/notificationSlice.ts';
import profileReducer from './slices/profileSlice.ts';

export const store = configureStore({
  reducer: {
    countries: countriesReducer,
    countryDetails: countryDetailsReducer,
    regions: regionsSliceReducer,
    adminLocations: adminLocationsReducer,
    countryEdit: countryEditReducer,
    regionEdit: regionEditReducer,
    districtEdit: districtEditReducer,
    locationEdit: locationEditReducer,
    skills: skillsSlice,
    user: userSlice,
    notifications: notificationReducer,
    profile: profileReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export const useAppDispatch: () => AppDispatch = useDispatch;
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector;

export default store;
