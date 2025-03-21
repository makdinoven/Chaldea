import { createSlice } from '@reduxjs/toolkit';
import {
    createLocation,
    updateLocation,
    fetchLocationDetails,
    uploadLocationImage,
    updateLocationNeighbors,
    fetchLocationsList,
    fetchDistrictLocations,
    fetchAllLocations
} from '../actions/locationEditActions';

const initialState = {
    locations: [],
    locationsList: [],
    locationDetails: {},
    currentLocation: null,
    loading: false,
    error: null,
    imageUploading: false,
    imageError: null,
    districtLocations: [],
    allLocations: []
};

const locationEditSlice = createSlice({
    name: 'locationEdit',
    initialState,
    reducers: {
        resetLocationEditState: (state) => {
            state.currentLocation = null;
            state.error = null;
        },
        setCurrentLocation: (state, action) => {
            state.currentLocation = action.payload;
        }
    },
    extraReducers: (builder) => {
        builder
            // Обработка createLocation
            .addCase(createLocation.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(createLocation.fulfilled, (state, action) => {
                state.currentLocation = action.payload;
                state.loading = false;
                state.locations.push(action.payload);
            })
            .addCase(createLocation.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })

            // Обработка updateLocation
            .addCase(updateLocation.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(updateLocation.fulfilled, (state, action) => {
                state.currentLocation = action.payload;
                state.loading = false;
                const index = state.locations.findIndex(loc => loc.id === action.payload.id);
                if (index !== -1) {
                    state.locations[index] = action.payload;
                }
            })
            .addCase(updateLocation.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })

            // Обработка fetchLocationDetails
            .addCase(fetchLocationDetails.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchLocationDetails.fulfilled, (state, action) => {
                state.currentLocation = action.payload;
                state.locationDetails[action.payload.id] = action.payload;
                state.loading = false;
            })
            .addCase(fetchLocationDetails.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })

            // Обработка uploadLocationImage
            .addCase(uploadLocationImage.pending, (state) => {
                state.imageUploading = true;
                state.imageError = null;
            })
            .addCase(uploadLocationImage.fulfilled, (state, action) => {
                state.imageUploading = false;
                if (state.currentLocation) {
                    state.currentLocation.image_url = action.payload.image_url;
                }
            })
            .addCase(uploadLocationImage.rejected, (state, action) => {
                state.imageUploading = false;
                state.imageError = action.payload;
            })

            // Обработка updateLocationNeighbors
            .addCase(updateLocationNeighbors.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(updateLocationNeighbors.fulfilled, (state, action) => {
                state.loading = false;
                if (state.currentLocation) {
                    state.currentLocation.neighbors = action.payload.neighbors;
                }
            })
            .addCase(updateLocationNeighbors.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })

            // Обработка fetchLocationsList
            .addCase(fetchLocationsList.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchLocationsList.fulfilled, (state, action) => {
                state.locationsList = action.payload;
                state.districtLocations = action.payload;
                state.loading = false;
            })
            .addCase(fetchLocationsList.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })

            // Обработка fetchDistrictLocations
            .addCase(fetchDistrictLocations.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchDistrictLocations.fulfilled, (state, action) => {
                state.districtLocations = action.payload;
                state.loading = false;
            })
            .addCase(fetchDistrictLocations.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            })

            // Обработка fetchAllLocations
            .addCase(fetchAllLocations.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchAllLocations.fulfilled, (state, action) => {
                state.allLocations = action.payload;
                state.loading = false;
            })
            .addCase(fetchAllLocations.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload;
            });
    }
});

export const { resetLocationEditState, setCurrentLocation } = locationEditSlice.actions;
export default locationEditSlice.reducer;