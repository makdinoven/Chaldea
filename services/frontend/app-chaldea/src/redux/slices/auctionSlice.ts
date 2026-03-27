import { createSlice, createAsyncThunk, PayloadAction } from "@reduxjs/toolkit";
import type { RootState } from "../store";
import * as auctionApi from "../../api/auction";
import type {
  AuctionListingResponse,
  AuctionListingsPageResponse,
  AuctionListingsQuery,
  AuctionCreateListingRequest,
  AuctionCreateListingResponse,
  AuctionBidRequest,
  AuctionBidResponse,
  AuctionBuyoutRequest,
  AuctionBuyoutResponse,
  AuctionCancelRequest,
  AuctionCancelResponse,
  AuctionMyListingsResponse,
  AuctionStorageResponse,
  AuctionStorageItemResponse,
  AuctionClaimRequest,
  AuctionClaimResponse,
  AuctionCheckAuctioneerResponse,
  AuctionDepositRequest,
  AuctionDepositResponse,
  WsAuctionOutbidData,
  WsAuctionSoldData,
  WsAuctionWonData,
  WsAuctionExpiredData,
} from "../../types/auction";

// --- State ---

interface AuctionFilters {
  itemType: string | null;
  rarity: string | null;
  sort: string;
  search: string;
}

interface AuctionState {
  // Browse tab
  listings: AuctionListingResponse[];
  listingsTotal: number;
  listingsPage: number;
  listingsPerPage: number;
  listingsLoading: boolean;
  listingsError: string | null;
  // Filters
  filters: AuctionFilters;
  // Single listing detail
  selectedListingId: number | null;
  selectedListing: AuctionListingResponse | null;
  selectedListingLoading: boolean;
  selectedListingError: string | null;
  // My listings tab
  myActiveListings: AuctionListingResponse[];
  myCompletedListings: AuctionListingResponse[];
  myListingsLoading: boolean;
  myListingsError: string | null;
  // Storage tab
  storageItems: AuctionStorageItemResponse[];
  storageTotalGold: number;
  storageLoading: boolean;
  storageError: string | null;
  // Auctioneer check
  hasAuctioneer: boolean;
  auctioneerName: string | null;
  auctioneerLoading: boolean;
  // UI state
  createModalOpen: boolean;
  // Action loading (bid, buyout, cancel, create, claim)
  actionLoading: boolean;
  actionError: string | null;
}

const initialState: AuctionState = {
  // Browse tab
  listings: [],
  listingsTotal: 0,
  listingsPage: 1,
  listingsPerPage: 20,
  listingsLoading: false,
  listingsError: null,
  // Filters
  filters: {
    itemType: null,
    rarity: null,
    sort: "time_asc",
    search: "",
  },
  // Single listing detail
  selectedListingId: null,
  selectedListing: null,
  selectedListingLoading: false,
  selectedListingError: null,
  // My listings tab
  myActiveListings: [],
  myCompletedListings: [],
  myListingsLoading: false,
  myListingsError: null,
  // Storage tab
  storageItems: [],
  storageTotalGold: 0,
  storageLoading: false,
  storageError: null,
  // Auctioneer check
  hasAuctioneer: false,
  auctioneerName: null,
  auctioneerLoading: false,
  // UI state
  createModalOpen: false,
  // Action loading
  actionLoading: false,
  actionError: null,
};

// --- Async Thunks ---

export const fetchListings = createAsyncThunk<
  AuctionListingsPageResponse,
  AuctionListingsQuery | undefined,
  { rejectValue: string }
>("auction/fetchListings", async (query, thunkAPI) => {
  try {
    return await auctionApi.fetchListings(query ?? {});
  } catch (e) {
    const msg =
      e instanceof Error ? e.message : "Не удалось загрузить лоты аукциона";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const fetchListing = createAsyncThunk<
  AuctionListingResponse,
  number,
  { rejectValue: string }
>("auction/fetchListing", async (listingId, thunkAPI) => {
  try {
    return await auctionApi.fetchListing(listingId);
  } catch (e) {
    const msg =
      e instanceof Error ? e.message : "Не удалось загрузить лот";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const createListing = createAsyncThunk<
  AuctionCreateListingResponse,
  AuctionCreateListingRequest,
  { rejectValue: string }
>("auction/createListing", async (payload, thunkAPI) => {
  try {
    return await auctionApi.createListing(payload);
  } catch (e) {
    const msg =
      e instanceof Error ? e.message : "Не удалось выставить лот на аукцион";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const placeBid = createAsyncThunk<
  AuctionBidResponse,
  { listingId: number; payload: AuctionBidRequest },
  { rejectValue: string }
>("auction/placeBid", async ({ listingId, payload }, thunkAPI) => {
  try {
    return await auctionApi.placeBid(listingId, payload);
  } catch (e) {
    const msg =
      e instanceof Error ? e.message : "Не удалось сделать ставку";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const buyoutListing = createAsyncThunk<
  AuctionBuyoutResponse,
  { listingId: number; payload: AuctionBuyoutRequest },
  { rejectValue: string }
>("auction/buyout", async ({ listingId, payload }, thunkAPI) => {
  try {
    return await auctionApi.buyout(listingId, payload);
  } catch (e) {
    const msg =
      e instanceof Error ? e.message : "Не удалось выкупить лот";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const cancelListing = createAsyncThunk<
  AuctionCancelResponse,
  { listingId: number; payload: AuctionCancelRequest },
  { rejectValue: string }
>("auction/cancelListing", async ({ listingId, payload }, thunkAPI) => {
  try {
    return await auctionApi.cancelListing(listingId, payload);
  } catch (e) {
    const msg =
      e instanceof Error ? e.message : "Не удалось отменить лот";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const fetchMyListings = createAsyncThunk<
  AuctionMyListingsResponse,
  number,
  { rejectValue: string }
>("auction/fetchMyListings", async (characterId, thunkAPI) => {
  try {
    return await auctionApi.fetchMyListings(characterId);
  } catch (e) {
    const msg =
      e instanceof Error ? e.message : "Не удалось загрузить ваши лоты";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const fetchStorage = createAsyncThunk<
  AuctionStorageResponse,
  number,
  { rejectValue: string }
>("auction/fetchStorage", async (characterId, thunkAPI) => {
  try {
    return await auctionApi.fetchStorage(characterId);
  } catch (e) {
    const msg =
      e instanceof Error ? e.message : "Не удалось загрузить склад аукциона";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const claimFromStorage = createAsyncThunk<
  AuctionClaimResponse,
  AuctionClaimRequest,
  { rejectValue: string }
>("auction/claimFromStorage", async (payload, thunkAPI) => {
  try {
    return await auctionApi.claimFromStorage(payload);
  } catch (e) {
    const msg =
      e instanceof Error ? e.message : "Не удалось забрать предметы со склада";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const depositToStorage = createAsyncThunk<
  AuctionDepositResponse,
  AuctionDepositRequest,
  { rejectValue: string }
>("auction/depositToStorage", async (payload, thunkAPI) => {
  try {
    return await auctionApi.depositToStorage(payload);
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } };
    const msg =
      err.response?.data?.detail || "Ошибка при помещении на склад";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const checkAuctioneer = createAsyncThunk<
  AuctionCheckAuctioneerResponse,
  number,
  { rejectValue: string }
>("auction/checkAuctioneer", async (characterId, thunkAPI) => {
  try {
    return await auctionApi.checkAuctioneer(characterId);
  } catch (e) {
    const msg =
      e instanceof Error
        ? e.message
        : "Не удалось проверить наличие аукциониста";
    return thunkAPI.rejectWithValue(msg);
  }
});

// --- Slice ---

const auctionSlice = createSlice({
  name: "auction",
  initialState,
  reducers: {
    // Filter changes
    setFilterItemType(state, action: PayloadAction<string | null>) {
      state.filters.itemType = action.payload;
      state.listingsPage = 1;
    },
    setFilterRarity(state, action: PayloadAction<string | null>) {
      state.filters.rarity = action.payload;
      state.listingsPage = 1;
    },
    setFilterSort(state, action: PayloadAction<string>) {
      state.filters.sort = action.payload;
      state.listingsPage = 1;
    },
    setFilterSearch(state, action: PayloadAction<string>) {
      state.filters.search = action.payload;
      state.listingsPage = 1;
    },
    resetFilters(state) {
      state.filters = { itemType: null, rarity: null, sort: "time_asc", search: "" };
      state.listingsPage = 1;
    },
    setListingsPage(state, action: PayloadAction<number>) {
      state.listingsPage = action.payload;
    },
    // UI state
    setSelectedListingId(state, action: PayloadAction<number | null>) {
      state.selectedListingId = action.payload;
      if (action.payload === null) {
        state.selectedListing = null;
        state.selectedListingError = null;
      }
    },
    setCreateModalOpen(state, action: PayloadAction<boolean>) {
      state.createModalOpen = action.payload;
    },
    clearActionError(state) {
      state.actionError = null;
    },
    // WebSocket event handlers
    handleAuctionOutbid(state, action: PayloadAction<WsAuctionOutbidData>) {
      const { listing_id, new_bid_amount } = action.payload;
      // Update listing in browse list
      const listing = state.listings.find((l) => l.id === listing_id);
      if (listing) {
        listing.current_bid = new_bid_amount;
        listing.bid_count += 1;
      }
      // Update selected listing detail
      if (state.selectedListing?.id === listing_id) {
        state.selectedListing.current_bid = new_bid_amount;
        state.selectedListing.bid_count += 1;
      }
      // Update in my active listings
      const myListing = state.myActiveListings.find((l) => l.id === listing_id);
      if (myListing) {
        myListing.current_bid = new_bid_amount;
        myListing.bid_count += 1;
      }
    },
    handleAuctionSold(state, action: PayloadAction<WsAuctionSoldData>) {
      const { listing_id } = action.payload;
      // Remove from browse listings
      state.listings = state.listings.filter((l) => l.id !== listing_id);
      state.listingsTotal = Math.max(0, state.listingsTotal - 1);
      // Move from active to completed in my listings
      const idx = state.myActiveListings.findIndex((l) => l.id === listing_id);
      if (idx !== -1) {
        const [sold] = state.myActiveListings.splice(idx, 1);
        sold.status = "sold";
        state.myCompletedListings.unshift(sold);
      }
      // Close detail modal if viewing this listing
      if (state.selectedListingId === listing_id) {
        state.selectedListingId = null;
        state.selectedListing = null;
      }
    },
    handleAuctionWon(state, action: PayloadAction<WsAuctionWonData>) {
      const { listing_id } = action.payload;
      // Remove from browse listings
      state.listings = state.listings.filter((l) => l.id !== listing_id);
      state.listingsTotal = Math.max(0, state.listingsTotal - 1);
      // Close detail modal if viewing this listing
      if (state.selectedListingId === listing_id) {
        state.selectedListingId = null;
        state.selectedListing = null;
      }
    },
    handleAuctionExpired(state, action: PayloadAction<WsAuctionExpiredData>) {
      const { listing_id } = action.payload;
      // Remove from browse listings
      state.listings = state.listings.filter((l) => l.id !== listing_id);
      state.listingsTotal = Math.max(0, state.listingsTotal - 1);
      // Move from active to completed in my listings
      const idx = state.myActiveListings.findIndex((l) => l.id === listing_id);
      if (idx !== -1) {
        const [expired] = state.myActiveListings.splice(idx, 1);
        expired.status = "expired";
        state.myCompletedListings.unshift(expired);
      }
      // Close detail modal if viewing this listing
      if (state.selectedListingId === listing_id) {
        state.selectedListingId = null;
        state.selectedListing = null;
      }
    },
  },
  extraReducers: (builder) => {
    // fetchListings
    builder
      .addCase(fetchListings.pending, (state) => {
        state.listingsLoading = true;
        state.listingsError = null;
      })
      .addCase(
        fetchListings.fulfilled,
        (state, action: PayloadAction<AuctionListingsPageResponse>) => {
          state.listingsLoading = false;
          state.listings = action.payload.listings;
          state.listingsTotal = action.payload.total;
          state.listingsPage = action.payload.page;
          state.listingsPerPage = action.payload.per_page;
        },
      )
      .addCase(fetchListings.rejected, (state, action) => {
        state.listingsLoading = false;
        state.listingsError = action.payload ?? "Произошла ошибка";
      });

    // fetchListing
    builder
      .addCase(fetchListing.pending, (state) => {
        state.selectedListingLoading = true;
        state.selectedListingError = null;
      })
      .addCase(
        fetchListing.fulfilled,
        (state, action: PayloadAction<AuctionListingResponse>) => {
          state.selectedListingLoading = false;
          state.selectedListing = action.payload;
        },
      )
      .addCase(fetchListing.rejected, (state, action) => {
        state.selectedListingLoading = false;
        state.selectedListingError = action.payload ?? "Произошла ошибка";
      });

    // createListing
    builder
      .addCase(createListing.pending, (state) => {
        state.actionLoading = true;
        state.actionError = null;
      })
      .addCase(createListing.fulfilled, (state) => {
        state.actionLoading = false;
        state.createModalOpen = false;
      })
      .addCase(createListing.rejected, (state, action) => {
        state.actionLoading = false;
        state.actionError = action.payload ?? "Произошла ошибка";
      });

    // placeBid
    builder
      .addCase(placeBid.pending, (state) => {
        state.actionLoading = true;
        state.actionError = null;
      })
      .addCase(
        placeBid.fulfilled,
        (state, action: PayloadAction<AuctionBidResponse>) => {
          state.actionLoading = false;
          const { listing_id, amount } = action.payload;
          // Update listing in browse list
          const listing = state.listings.find((l) => l.id === listing_id);
          if (listing) {
            listing.current_bid = amount;
            listing.bid_count += 1;
          }
          // Update selected listing
          if (state.selectedListing?.id === listing_id) {
            state.selectedListing.current_bid = amount;
            state.selectedListing.bid_count += 1;
          }
        },
      )
      .addCase(placeBid.rejected, (state, action) => {
        state.actionLoading = false;
        state.actionError = action.payload ?? "Произошла ошибка";
      });

    // buyoutListing
    builder
      .addCase(buyoutListing.pending, (state) => {
        state.actionLoading = true;
        state.actionError = null;
      })
      .addCase(
        buyoutListing.fulfilled,
        (state, action: PayloadAction<AuctionBuyoutResponse>) => {
          state.actionLoading = false;
          const { listing_id } = action.payload;
          // Remove from browse listings
          state.listings = state.listings.filter((l) => l.id !== listing_id);
          state.listingsTotal = Math.max(0, state.listingsTotal - 1);
          // Close detail if viewing this listing
          if (state.selectedListingId === listing_id) {
            state.selectedListingId = null;
            state.selectedListing = null;
          }
        },
      )
      .addCase(buyoutListing.rejected, (state, action) => {
        state.actionLoading = false;
        state.actionError = action.payload ?? "Произошла ошибка";
      });

    // cancelListing
    builder
      .addCase(cancelListing.pending, (state) => {
        state.actionLoading = true;
        state.actionError = null;
      })
      .addCase(
        cancelListing.fulfilled,
        (state, action: PayloadAction<AuctionCancelResponse>) => {
          state.actionLoading = false;
          const { listing_id } = action.payload;
          // Remove from browse listings
          state.listings = state.listings.filter((l) => l.id !== listing_id);
          state.listingsTotal = Math.max(0, state.listingsTotal - 1);
          // Remove from my active listings
          state.myActiveListings = state.myActiveListings.filter(
            (l) => l.id !== listing_id,
          );
          // Close detail if viewing this listing
          if (state.selectedListingId === listing_id) {
            state.selectedListingId = null;
            state.selectedListing = null;
          }
        },
      )
      .addCase(cancelListing.rejected, (state, action) => {
        state.actionLoading = false;
        state.actionError = action.payload ?? "Произошла ошибка";
      });

    // fetchMyListings
    builder
      .addCase(fetchMyListings.pending, (state) => {
        state.myListingsLoading = true;
        state.myListingsError = null;
      })
      .addCase(
        fetchMyListings.fulfilled,
        (state, action: PayloadAction<AuctionMyListingsResponse>) => {
          state.myListingsLoading = false;
          state.myActiveListings = action.payload.active;
          state.myCompletedListings = action.payload.completed;
        },
      )
      .addCase(fetchMyListings.rejected, (state, action) => {
        state.myListingsLoading = false;
        state.myListingsError = action.payload ?? "Произошла ошибка";
      });

    // fetchStorage
    builder
      .addCase(fetchStorage.pending, (state) => {
        state.storageLoading = true;
        state.storageError = null;
      })
      .addCase(
        fetchStorage.fulfilled,
        (state, action: PayloadAction<AuctionStorageResponse>) => {
          state.storageLoading = false;
          state.storageItems = action.payload.items;
          state.storageTotalGold = action.payload.total_gold;
        },
      )
      .addCase(fetchStorage.rejected, (state, action) => {
        state.storageLoading = false;
        state.storageError = action.payload ?? "Произошла ошибка";
      });

    // claimFromStorage
    builder
      .addCase(claimFromStorage.pending, (state) => {
        state.actionLoading = true;
        state.actionError = null;
      })
      .addCase(
        claimFromStorage.fulfilled,
        (state, action) => {
          state.actionLoading = false;
          // Storage will be refetched after claim to get updated state
        },
      )
      .addCase(claimFromStorage.rejected, (state, action) => {
        state.actionLoading = false;
        state.actionError = action.payload ?? "Произошла ошибка";
      });

    // depositToStorage
    builder
      .addCase(depositToStorage.pending, (state) => {
        state.actionLoading = true;
        state.actionError = null;
      })
      .addCase(depositToStorage.fulfilled, (state) => {
        state.actionLoading = false;
      })
      .addCase(depositToStorage.rejected, (state, action) => {
        state.actionLoading = false;
        state.actionError = action.payload ?? "Произошла ошибка";
      });

    // checkAuctioneer
    builder
      .addCase(checkAuctioneer.pending, (state) => {
        state.auctioneerLoading = true;
      })
      .addCase(
        checkAuctioneer.fulfilled,
        (state, action: PayloadAction<AuctionCheckAuctioneerResponse>) => {
          state.auctioneerLoading = false;
          state.hasAuctioneer = action.payload.has_auctioneer;
          state.auctioneerName = action.payload.auctioneer_name;
        },
      )
      .addCase(checkAuctioneer.rejected, (state) => {
        state.auctioneerLoading = false;
        state.hasAuctioneer = false;
        state.auctioneerName = null;
      });
  },
});

export const {
  setFilterItemType,
  setFilterRarity,
  setFilterSort,
  setFilterSearch,
  resetFilters,
  setListingsPage,
  setSelectedListingId,
  setCreateModalOpen,
  clearActionError,
  handleAuctionOutbid,
  handleAuctionSold,
  handleAuctionWon,
  handleAuctionExpired,
} = auctionSlice.actions;

// --- Selectors ---

// Browse
export const selectListings = (state: RootState) => state.auction.listings;
export const selectListingsTotal = (state: RootState) => state.auction.listingsTotal;
export const selectListingsPage = (state: RootState) => state.auction.listingsPage;
export const selectListingsPerPage = (state: RootState) => state.auction.listingsPerPage;
export const selectListingsLoading = (state: RootState) => state.auction.listingsLoading;
export const selectListingsError = (state: RootState) => state.auction.listingsError;

// Filters
export const selectFilters = (state: RootState) => state.auction.filters;

// Single listing
export const selectSelectedListingId = (state: RootState) => state.auction.selectedListingId;
export const selectSelectedListing = (state: RootState) => state.auction.selectedListing;
export const selectSelectedListingLoading = (state: RootState) =>
  state.auction.selectedListingLoading;
export const selectSelectedListingError = (state: RootState) =>
  state.auction.selectedListingError;

// My listings
export const selectMyActiveListings = (state: RootState) => state.auction.myActiveListings;
export const selectMyCompletedListings = (state: RootState) => state.auction.myCompletedListings;
export const selectMyListingsLoading = (state: RootState) => state.auction.myListingsLoading;
export const selectMyListingsError = (state: RootState) => state.auction.myListingsError;

// Storage
export const selectStorageItems = (state: RootState) => state.auction.storageItems;
export const selectStorageTotalGold = (state: RootState) => state.auction.storageTotalGold;
export const selectStorageLoading = (state: RootState) => state.auction.storageLoading;
export const selectStorageError = (state: RootState) => state.auction.storageError;

// Auctioneer
export const selectHasAuctioneer = (state: RootState) => state.auction.hasAuctioneer;
export const selectAuctioneerName = (state: RootState) => state.auction.auctioneerName;
export const selectAuctioneerLoading = (state: RootState) => state.auction.auctioneerLoading;

// UI
export const selectCreateModalOpen = (state: RootState) => state.auction.createModalOpen;
export const selectActionLoading = (state: RootState) => state.auction.actionLoading;
export const selectActionError = (state: RootState) => state.auction.actionError;

export default auctionSlice.reducer;
