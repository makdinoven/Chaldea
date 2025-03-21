import { createSelector } from '@reduxjs/toolkit';

// Базовые селекторы
const getRegionEdit = state => state.regionEdit || {};
const getCountryEdit = state => state.countryEdit || {};
const getDistrictEdit = state => state.districtEdit || {};
const getAdminLocations = state => state.adminLocations || {};

// Мемоизированные селекторы
export const selectRegionEdit = createSelector(
    [getRegionEdit],
    regionEdit => ({
        loading: regionEdit.loading || false,
        error: regionEdit.error || null,
        currentRegion: regionEdit.currentRegion || null
    })
);

export const selectCountryEdit = createSelector(
    [getCountryEdit],
    countryEdit => ({
        loading: countryEdit.loading || false,
        error: countryEdit.error || null,
        currentCountry: countryEdit.currentCountry || null
    })
);

export const selectDistrictEdit = createSelector(
    [getDistrictEdit],
    districtEdit => ({
        loading: districtEdit.loading || false,
        error: districtEdit.error || null,
        currentDistrict: districtEdit.currentDistrict || null
    })
);

export const selectAdminLocations = createSelector(
    [getAdminLocations],
    adminLocations => ({
        countries: adminLocations.countries || [],
        countryDetails: adminLocations.countryDetails || {},
        regionDetails: adminLocations.regionDetails || {},
        loading: adminLocations.loading || false,
        error: adminLocations.error || null
    })
);

export const selectLocationEdit = (state) => state.locationEdit;

export const selectLocations = (state, districtId) => {
    const locationsList = state.locationEdit.locationsList || [];
    if (!districtId) return [];
    return locationsList.filter(location => location.district_id === districtId);
};