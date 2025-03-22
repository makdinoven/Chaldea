import { createAsyncThunk } from '@reduxjs/toolkit';
import axios from 'axios';

export const createLocation = createAsyncThunk(
    'locationEdit/createLocation',
    async (locationData, { rejectWithValue }) => {
        try {
            const processedData = { ...locationData };
            
            // Удаляем parent_id если он не определен
            if (!processedData.parent_id) {
                delete processedData.parent_id;
            }
            
            // Остальные преобразования
            if (processedData.district_id) {
                processedData.district_id = parseInt(processedData.district_id);
            }
            
            if (processedData.recommended_level === '' || processedData.recommended_level === null) {
                processedData.recommended_level = 1;
            } else if (processedData.recommended_level) {
                processedData.recommended_level = parseInt(processedData.recommended_level);
            }
            
            processedData.quick_travel_marker = Boolean(processedData.quick_travel_marker);
            
            console.log('Обработанные данные для создания:', processedData);
            
            const response = await axios.post('http://4452515-co41851.twc1.net:8006/locations/', processedData);
            return response.data;
        } catch (error) {
            console.error('Ошибка при создании локации:', error.response?.data || error.message);
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const updateLocation = createAsyncThunk(
    'locationEdit/updateLocation',
    async (locationData, { rejectWithValue }) => {
        try {
            console.log('Отправляемые данные для обновления локации:', locationData);
            
            const { id, neighbors, ...updateData } = locationData;
            
            // Если передан только id и type, обновляем только тип локации
            if (Object.keys(updateData).length === 1 && updateData.type) {
                const response = await axios.patch(
                    `http://4452515-co41851.twc1.net:8006/locations/${id}/update-type`,
                    { type: updateData.type }
                );
                return response.data;
            }
            
            // Иначе обычное обновление
            if (updateData.parent_id === '') {
                updateData.parent_id = null;
            } else if (updateData.parent_id) {
                updateData.parent_id = parseInt(updateData.parent_id);
            }
            
            if (updateData.recommended_level === '') {
                updateData.recommended_level = null;
            } else if (updateData.recommended_level) {
                updateData.recommended_level = parseInt(updateData.recommended_level);
            }
            
            const response = await axios.put(`http://4452515-co41851.twc1.net:8006/locations/${id}/update`, updateData);
            return response.data;
        } catch (error) {
            console.error('Ошибка при обновлении локации:', error);
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const fetchLocationDetails = createAsyncThunk(
    'locationEdit/fetchLocationDetails',
    async (locationId, { rejectWithValue }) => {
        try {
            const response = await axios.get(`http://4452515-co41851.twc1.net:8006/locations/${locationId}/details`);
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const uploadLocationImage = createAsyncThunk(
    'locationEdit/uploadImage',
    async ({ locationId, file }, { rejectWithValue }) => {
        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('location_id', locationId);
            
            const response = await axios.post(
                'http://4452515-co41851.twc1.net:8006/photo/change_location_image',
                formData,
                {
                    headers: {
                        'Content-Type': 'multipart/form-data',
                    },
                }
            );
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const updateLocationNeighbors = createAsyncThunk(
    'locationEdit/updateLocationNeighbors',
    async ({ locationId, neighbors }, { rejectWithValue }) => {
        try {
            console.log('Отправляем соседей:', { locationId, neighbors });
            
            // Преобразуем все ID в числа и убедимся, что структура данных правильная
            const processedNeighbors = neighbors.map(neighbor => {
                // Если neighbor уже объект с neighbor_id и energy_cost
                if (typeof neighbor === 'object' && neighbor.neighbor_id) {
                    return {
                        neighbor_id: parseInt(neighbor.neighbor_id),
                        energy_cost: parseInt(neighbor.energy_cost) || 1
                    };
                }
                // Если neighbor - это просто ID
                return {
                    neighbor_id: parseInt(neighbor),
                    energy_cost: 1
                };
            });
            
            // Отправляем запрос на обновление соседей
            const response = await axios.post(
                `http://4452515-co41851.twc1.net:8006/locations/${locationId}/neighbors/update`,
                { neighbors: processedNeighbors }
            );
            
            return { locationId, neighbors: response.data };
        } catch (error) {
            console.error('Ошибка при обновлении соседей:', error);
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const fetchLocationsList = createAsyncThunk(
    'locationEdit/fetchLocationsList',
    async (districtId, { rejectWithValue }) => {
        try {
            const response = await axios.get(`http://4452515-co41851.twc1.net:8006/locations/districts/${districtId}/locations`);
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const fetchDistrictLocations = createAsyncThunk(
    'locationEdit/fetchDistrictLocations',
    async (districtId, { rejectWithValue }) => {
        try {
            const response = await axios.get(`http://4452515-co41851.twc1.net:8006/districts/${districtId}/locations`);
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const fetchAllLocations = createAsyncThunk(
    'locationEdit/fetchAllLocations',
    async (_, { rejectWithValue }) => {
        try {
            const response = await axios.get('http://4452515-co41851.twc1.net:8006/locations/locations/lookup');
            return response.data;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

export const deleteLocation = createAsyncThunk(
    'locationEdit/deleteLocation',
    async (locationId, { rejectWithValue }) => {
        try {
            // Вызов роутера FastAPI: DELETE /locations/{location_id}/delete
            await axios.delete(`http://4452515-co41851.twc1.net:8006/locations/${locationId}/delete`);
            return locationId;
        } catch (error) {
            return rejectWithValue(error.response?.data || error.message);
        }
    }
);

