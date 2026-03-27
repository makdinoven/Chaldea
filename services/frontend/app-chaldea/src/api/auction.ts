import axios from 'axios';
import type {
  AuctionListingsPageResponse,
  AuctionListingResponse,
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
  AuctionClaimRequest,
  AuctionClaimResponse,
  AuctionCheckAuctioneerResponse,
  AuctionDepositRequest,
  AuctionDepositResponse,
} from '../types/auction';

// --- 3.5.1 Browse Listings ---

export const fetchListings = async (
  query: AuctionListingsQuery = {},
): Promise<AuctionListingsPageResponse> => {
  const params: Record<string, string | number> = {};
  if (query.page) params.page = query.page;
  if (query.per_page) params.per_page = query.per_page;
  if (query.item_type) params.item_type = query.item_type;
  if (query.rarity) params.rarity = query.rarity;
  if (query.sort) params.sort = query.sort;
  if (query.search) params.search = query.search;

  const { data } = await axios.get<AuctionListingsPageResponse>(
    '/inventory/auction/listings',
    { params },
  );
  return data;
};

// --- 3.5.2 Get Single Listing ---

export const fetchListing = async (
  listingId: number,
): Promise<AuctionListingResponse> => {
  const { data } = await axios.get<AuctionListingResponse>(
    `/inventory/auction/listings/${listingId}`,
  );
  return data;
};

// --- 3.5.3 Create Listing ---

export const createListing = async (
  payload: AuctionCreateListingRequest,
): Promise<AuctionCreateListingResponse> => {
  const { data } = await axios.post<AuctionCreateListingResponse>(
    '/inventory/auction/listings',
    payload,
  );
  return data;
};

// --- 3.5.4 Place Bid ---

export const placeBid = async (
  listingId: number,
  payload: AuctionBidRequest,
): Promise<AuctionBidResponse> => {
  const { data } = await axios.post<AuctionBidResponse>(
    `/inventory/auction/listings/${listingId}/bid`,
    payload,
  );
  return data;
};

// --- 3.5.5 Buyout ---

export const buyout = async (
  listingId: number,
  payload: AuctionBuyoutRequest,
): Promise<AuctionBuyoutResponse> => {
  const { data } = await axios.post<AuctionBuyoutResponse>(
    `/inventory/auction/listings/${listingId}/buyout`,
    payload,
  );
  return data;
};

// --- 3.5.6 Cancel Listing ---

export const cancelListing = async (
  listingId: number,
  payload: AuctionCancelRequest,
): Promise<AuctionCancelResponse> => {
  const { data } = await axios.post<AuctionCancelResponse>(
    `/inventory/auction/listings/${listingId}/cancel`,
    payload,
  );
  return data;
};

// --- 3.5.7 Get My Listings ---

export const fetchMyListings = async (
  characterId: number,
): Promise<AuctionMyListingsResponse> => {
  const { data } = await axios.get<AuctionMyListingsResponse>(
    '/inventory/auction/my-listings',
    { params: { character_id: characterId } },
  );
  return data;
};

// --- 3.5.8 Get Auction Storage ---

export const fetchStorage = async (
  characterId: number,
): Promise<AuctionStorageResponse> => {
  const { data } = await axios.get<AuctionStorageResponse>(
    '/inventory/auction/storage',
    { params: { character_id: characterId } },
  );
  return data;
};

// --- 3.5.9 Claim from Storage ---

export const claimFromStorage = async (
  payload: AuctionClaimRequest,
): Promise<AuctionClaimResponse> => {
  const { data } = await axios.post<AuctionClaimResponse>(
    '/inventory/auction/storage/claim',
    payload,
  );
  return data;
};

// --- 3.5.10 Deposit to Storage ---

export const depositToStorage = async (
  payload: AuctionDepositRequest,
): Promise<AuctionDepositResponse> => {
  const { data } = await axios.post<AuctionDepositResponse>(
    '/inventory/auction/storage/deposit',
    payload,
  );
  return data;
};

// --- 3.5.11 Check Auctioneer NPC at Location ---

export const checkAuctioneer = async (
  characterId: number,
): Promise<AuctionCheckAuctioneerResponse> => {
  const { data } = await axios.get<AuctionCheckAuctioneerResponse>(
    '/inventory/auction/check-auctioneer',
    { params: { character_id: characterId } },
  );
  return data;
};
