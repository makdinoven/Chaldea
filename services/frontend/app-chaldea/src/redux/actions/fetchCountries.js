import { createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';

// Async Thunk для загрузки стран
export const fetchCountries = createAsyncThunk(
    'world/fetchCountries',
    async (_, { rejectWithValue }) => {
        try {
            const response = await axios.get('http://localhost:8006/locations/countries/lookup', {
                headers: { Accept: 'application/json' },
            });
            return response.data;
        } catch (error) {
            return rejectWithValue(error.message);
        }
    }
);