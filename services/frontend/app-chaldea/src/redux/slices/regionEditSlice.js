import { createSlice } from '@reduxjs/toolkit';
import { 
    createRegion, 
    updateRegion, 
    fetchRegionDetails,
    uploadRegionImage,
    uploadRegionMap 
} from '../actions/regionEditActions';

const regionEditSlice = createSlice({
    name: 'regionEdit',
    initialState: {
        loading: false,
        error: null,
        success: false,
        currentRegion: null
    },
    reducers: {
        resetRegionEditState: (state) => {
            state.loading = false;
            state.error = null;
            state.success = false;
            state.currentRegion = null;
        }
    },
    extraReducers: (builder) => {
        builder
            // Create Region
            .addCase(createRegion.pending, (state) => {
                state.loading = true;
                state.error = null;
                state.success = false;
            })
            .addCase(createRegion.fulfilled, (state) => {
                state.loading = false;
                state.success = true;
            })
            .addCase(createRegion.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })
            
            // Update Region
            .addCase(updateRegion.pending, (state) => {
                state.loading = true;
                state.error = null;
                state.success = false;
            })
            .addCase(updateRegion.fulfilled, (state) => {
                state.loading = false;
                state.success = true;
            })
            .addCase(updateRegion.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })
            
            // Fetch Region Details
            .addCase(fetchRegionDetails.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchRegionDetails.fulfilled, (state, action) => {
                state.loading = false;
                state.currentRegion = action.payload;
            })
            .addCase(fetchRegionDetails.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })
            
            // Upload Image
            .addCase(uploadRegionImage.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(uploadRegionImage.fulfilled, (state) => {
                state.loading = false;
            })
            .addCase(uploadRegionImage.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })
            
            // Upload Map
            .addCase(uploadRegionMap.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(uploadRegionMap.fulfilled, (state) => {
                state.loading = false;
            })
            .addCase(uploadRegionMap.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })
    }
});

export const { resetRegionEditState } = regionEditSlice.actions;
export default regionEditSlice.reducer;