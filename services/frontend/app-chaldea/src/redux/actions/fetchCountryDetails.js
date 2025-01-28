import { createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';

export const fetchCountryDetails = createAsyncThunk(
    'countryDetails/fetchCountryDetails',
    async (countryId, { getState, rejectWithValue }) => {
        const state = getState().countryDetails;

        // Проверка, загружены ли данные о стране
        if (state.isLoaded[countryId]) {
            console.log(`loaded ${countryId}`);
            return;
        }

        try {
            const response = await axios.get(`http://localhost:8006/locations/countries/${countryId}/details`, {
                headers: { Accept: 'application/json' },
            });

            return { countryId, country: response.data }; // Возвращаем всю информацию о стране
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);
