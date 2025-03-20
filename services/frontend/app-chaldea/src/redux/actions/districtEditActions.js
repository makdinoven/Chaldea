import { createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';

export const createDistrict = createAsyncThunk(
    'districtEdit/createDistrict',
    async (districtData, { rejectWithValue }) => {
        try {
            const response = await axios.post('http://localhost:8006/locations/districts', districtData);
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const updateDistrict = createAsyncThunk(
    'districtEdit/updateDistrict',
    async ({ id, ...districtData }, { rejectWithValue }) => {
        try {
            const response = await axios.put(`http://localhost:8006/locations/districts/${id}`, districtData);
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const uploadDistrictImage = createAsyncThunk(
    'districtEdit/uploadImage',
    async ({ districtId, file }, { rejectWithValue }) => {
        try {
            const formData = new FormData();
            formData.append('district_id', districtId);
            formData.append('file', file);

            const response = await axios.post(
                'http://localhost:8006/photo/change_district_image',
                formData,
                {
                    headers: { 'Content-Type': 'multipart/form-data' }
                }
            );
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const fetchDistrictDetails = createAsyncThunk(
    'districtEdit/fetchDetails',
    async (districtId, { rejectWithValue }) => {
        try {
            const response = await axios.get(`http://localhost:8006/locations/districts/${districtId}`);
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);