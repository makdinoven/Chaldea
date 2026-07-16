import { createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';

export const deleteCountry = createAsyncThunk(
    'countryEdit/deleteCountry',
    /** @param {number | string} countryId */
    async (countryId, { rejectWithValue }) => {
        try {
            await axios.delete(`/locations/countries/${countryId}/delete`);
            return countryId;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const createCountry = createAsyncThunk(
    'countryEdit/createCountry',
    /** @param {Record<string, unknown>} countryData */
    async (countryData, { rejectWithValue }) => {
        try {
            const response = await axios.post('/locations/countries/create', countryData);
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const updateCountry = createAsyncThunk(
    'countryEdit/updateCountry',
    /** @param {Record<string, unknown>} data */
    async ({ id, ...countryData }, { rejectWithValue }) => {
        try {
            const response = await axios.put(`/locations/countries/${id}/update`, countryData);
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const uploadCountryMap = createAsyncThunk(
    'countryEdit/uploadCountryMap',
    async ({ countryId, file }, { rejectWithValue }) => {
        try {
            const formData = new FormData();
            formData.append('country_id', countryId);
            formData.append('file', file);
            
            const response = await axios.post(
                '/photo/change_country_map',
                formData,
                {
                    headers: {
                        'Content-Type': 'multipart/form-data'
                    }
                }
            );
            
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);