import { createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';

export const createDistrict = createAsyncThunk(
    'districtEdit/createDistrict',
    async (districtData, { rejectWithValue }) => {
        try {
            console.log('Creating district with data:', districtData);
            const response = await axios.post('http://4452515-co41851.twc1.net:8006/locations/districts', districtData);
            console.log('Server response:', response.data);
            return response.data;
        } catch (error) {
            console.error('Server error:', {
                response: error.response?.data,
                status: error.response?.status,
                message: error.message
            });
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const updateDistrict = createAsyncThunk(
    'districtEdit/updateDistrict',
    async ({ id, ...districtData }, { rejectWithValue }) => {
        try {
            const response = await axios.put(`http://4452515-co41851.twc1.net:8006/locations/districts/${id}/update`, districtData);
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
                'http://4452515-co41851.twc1.net:8006/photo/change_district_image',
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
    'districtEdit/fetchDistrictDetails',
    async (districtId, { rejectWithValue }) => {
        try {
            console.log('Fetching district details:', districtId);
            const response = await axios.get(`http://4452515-co41851.twc1.net:8006/locations/districts/${districtId}/details`);
            console.log('District details response:', response.data);
            return response.data;
        } catch (error) {
            console.error('Error fetching district details:', error);
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const fetchLocationsList = createAsyncThunk(
    'districtEdit/fetchLocationsList',
    async (districtId, { rejectWithValue }) => {
        try {
            console.log('Fetching locations for district:', districtId);
            const response = await axios.get(`http://4452515-co41851.twc1.net:8006/locations/districts/${districtId}/locations`);
            console.log('Locations response:', response.data);
            return response.data;
        } catch (error) {
            console.error('Error fetching locations:', error);
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const fetchDistrictLocations = createAsyncThunk(
    'districtEdit/fetchDistrictLocations',
    async (districtId, { rejectWithValue }) => {
        try {
            console.log('Fetching locations for district:', districtId);
            const response = await axios.get(`http://4452515-co41851.twc1.net:8006/locations/districts/${districtId}/locations`);
            console.log('Raw locations response:', response.data);
            
            if (!Array.isArray(response.data)) {
                console.error('Unexpected response format:', response.data);
                return [];
            }
            
            return response.data;
        } catch (error) {
            console.error('Error fetching locations:', error);
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);