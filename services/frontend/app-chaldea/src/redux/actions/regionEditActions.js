import { createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';

export const createRegion = createAsyncThunk(
    'regionEdit/createRegion',
    async (regionData, { rejectWithValue }) => {
        try {
            const response = await axios.post('/locations/regions/create', regionData);
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const updateRegion = createAsyncThunk(
    'regionEdit/updateRegion',
    async ({ id, ...regionData }, { rejectWithValue }) => {
        try {
            const response = await axios.put(`/locations/regions/${id}/update`, regionData);
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const fetchRegionDetails = createAsyncThunk(
    'regionEdit/fetchDetails',
    async (regionId, { rejectWithValue }) => {
        try {
            const response = await axios.get(`/locations/regions/${regionId}/details`);
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const uploadRegionImage = createAsyncThunk(
    'regionEdit/uploadImage',
    async ({ regionId, file }, { rejectWithValue }) => {
        try {
            const formData = new FormData();
            formData.append('region_id', regionId);
            formData.append('file', file);
            
            const response = await axios.post(
                '/photo/change_region_image',
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

export const uploadRegionMap = createAsyncThunk(
    'regionEdit/uploadMap',
    async ({ regionId, file }, { rejectWithValue }) => {
        try {
            const formData = new FormData();
            formData.append('region_id', regionId);
            formData.append('file', file);
            
            const response = await axios.post(
                '/photo/change_region_map',
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

export const deleteRegion = createAsyncThunk(
    'regionEdit/deleteRegion',
    async (regionId, { rejectWithValue }) => {
        try {
            await axios.delete(`/locations/regions/${regionId}/delete`);
            return regionId;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);