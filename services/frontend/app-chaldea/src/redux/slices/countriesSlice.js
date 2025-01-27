import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
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

const countriesSlice = createSlice({
    name: 'countries',
    initialState: {
        countries: [],
        loading: true,
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
                }
            })
            .addCase(fetchCountries.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            });
    },
});

export const { setOpenedCountryId } = countriesSlice.actions;
export default countriesSlice.reducer;
