import { createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';

export const deleteCountry = createAsyncThunk(
    'countryEdit/deleteCountry',
    async (countryId, { rejectWithValue }) => {
        try {
            await axios.delete(`http://localhost:8006/locations/countries/${countryId}/delete`);
            return countryId;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const createCountry = createAsyncThunk(
    'countryEdit/createCountry',
    async (countryData, { rejectWithValue }) => {
        try {
            const response = await axios.post('http://localhost:8006/locations/countries/create', countryData);
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const updateCountry = createAsyncThunk(
    'countryEdit/updateCountry',
    async ({ id, ...countryData }, { rejectWithValue }) => {
        try {
            const response = await axios.put(`http://localhost:8006/locations/countries/${id}/update`, countryData);
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
                'http://localhost:8006/photo/change_country_map',
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