import {createSlice, createAsyncThunk} from "@reduxjs/toolkit";
import axios from "axios";
import {fetchRegionDetails} from "../actions/regionsActions.js";

const regionsSlice = createSlice({
    name: "regions",
    initialState: {
        data: {}, // Данные регионов
        loading: {}, // Статус загрузки для каждого региона
        isLoaded: {}, // Статус завершения загрузки для каждого региона
        error: {}, // Ошибки для каждого региона
        openedRegionId: null,
    },
    reducers: {
        setOpenedRegionId: (state, action) => {
            state.openedRegionId = action.payload;
        },
    },
    extraReducers: (builder) => {
        builder
            // Обработка начала загрузки
            .addCase(fetchRegionDetails.pending, (state, action) => {
                const regionId = action.meta.arg;
                state.loading[regionId] = true;
                state.isLoaded[regionId] = false;
                state.error[regionId] = null;
            })
            // Обработка успешной загрузки
            .addCase(fetchRegionDetails.fulfilled, (state, action) => {
                const {regionId, data} = action.payload;
                state.data[regionId] = data; // Сохраняем данные региона
                state.loading[regionId] = false;
                state.isLoaded[regionId] = true;
                state.error[regionId] = null;
            })
            // Обработка ошибки
            .addCase(fetchRegionDetails.rejected, (state, action) => {
                const {regionId, error} = action.payload;
                state.loading[regionId] = false;
                state.isLoaded[regionId] = false;
                state.error[regionId] = error;
            });
    },
});

export const {setOpenedRegionId} = regionsSlice.actions;
export default regionsSlice.reducer;