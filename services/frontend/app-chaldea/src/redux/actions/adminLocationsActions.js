import {createAsyncThunk} from '@reduxjs/toolkit';
import axios from 'axios';

// Получение списка стран
export const fetchCountriesList = createAsyncThunk(
    'adminLocations/fetchCountriesList',
    async (_, { rejectWithValue }) => {
        try {
            const response = await axios.get('http://4452515-co41851.twc1.net:8006/locations/countries/list');
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

// Получение деталей страны
export const fetchCountryDetails = createAsyncThunk(
    'adminLocations/fetchCountryDetails',
    async (countryId, { rejectWithValue }) => {
        try {
            const response = await axios.get(`http://4452515-co41851.twc1.net:8006/locations/countries/${countryId}/details`);
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

// Получение деталей региона
export const fetchRegionDetails = createAsyncThunk(
    'adminLocations/fetchRegionDetails',
    async (regionId, { rejectWithValue }) => {
        try {
            const response = await axios.get(`http://4452515-co41851.twc1.net:8006/locations/regions/${regionId}/details`);
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);