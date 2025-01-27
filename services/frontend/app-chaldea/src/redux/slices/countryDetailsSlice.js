import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';

// Асинхронная загрузка данных о стране (включая регионы)
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

const countryDetailsSlice = createSlice({
    name: 'countryDetails',
    initialState: {
        data: {},
        loading: {},
        isLoaded: {},
        error: {}
    },
    reducers: {},
    extraReducers: (builder) => {
        builder
            .addCase(fetchCountryDetails.pending, (state, action) => {
                state.loading[action.meta.arg] = true;
                state.error[action.meta.arg] = null;
            })
            .addCase(fetchCountryDetails.fulfilled, (state, action) => {
                if (action.payload) {
                    const { countryId, country } = action.payload;
                    state.data[countryId] = country; // Сохраняем всю страну
                    state.isLoaded[countryId] = true;
                }
                state.loading[action.meta.arg] = false;
            })
            .addCase(fetchCountryDetails.rejected, (state, action) => {
                state.loading[action.meta.arg] = false;
                state.error[action.meta.arg] = action.payload;
            });
    }
});

export default countryDetailsSlice.reducer;
