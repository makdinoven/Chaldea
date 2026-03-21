import { configureStore } from '@reduxjs/toolkit';
import { TypedUseSelectorHook, useDispatch, useSelector } from 'react-redux';
import countriesReducer from './slices/countriesSlice';
import countryDetailsReducer from './slices/countryDetailsSlice';
import regionsSliceReducer from './slices/regionsSlice';
import adminLocationsReducer from './slices/adminLocationsSlice';
import countryEditReducer from './slices/countryEditSlice';
import regionEditReducer from './slices/regionEditSlice';
import districtEditReducer from './slices/districtEditSlice';
import locationEditReducer from './slices/locationEditSlice';
import skillsSlice from './slices/skillsAdminSlice';
import userSlice from './slices/userSlice';
import notificationReducer from './slices/notificationSlice';
import profileReducer from './slices/profileSlice';
import adminCharactersReducer from './slices/adminCharactersSlice';
import userProfileReducer from './slices/userProfileSlice';
import worldMapReducer from './slices/worldMapSlice';
import racesReducer from './slices/racesSlice';
import chatReducer from './slices/chatSlice';
import gameTimeReducer from './slices/gameTimeSlice';
import classTreeAdminReducer from './slices/classTreeAdminSlice';

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
    adminCharacters: adminCharactersReducer,
    userProfile: userProfileReducer,
    worldMap: worldMapReducer,
    races: racesReducer,
    chat: chatReducer,
    gameTime: gameTimeReducer,
    classTreeAdmin: classTreeAdminReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export const useAppDispatch: () => AppDispatch = useDispatch;
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector;

export default store;
