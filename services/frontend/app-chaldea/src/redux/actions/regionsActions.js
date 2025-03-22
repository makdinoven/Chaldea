import {createAsyncThunk} from "@reduxjs/toolkit";
import axios from "axios";

export const fetchRegionDetails = createAsyncThunk(
    "regions/fetchRegionDetails",
    async (regionId, {rejectWithValue}) => {
        try {
            const response = await axios.get(`http://4452515-co41851.twc1.net:8006/locations/regions/${regionId}/details`);
            return {regionId, data: response.data};
        } catch (error) {
            return rejectWithValue({regionId, error: error.response.data});
        }
    }
);