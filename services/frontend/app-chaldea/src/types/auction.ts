/* ── Auction House types ── */

// --- Enums / Literal types ---

export type AuctionListingStatus = 'active' | 'sold' | 'expired' | 'cancelled';

export type AuctionStorageSource = 'purchase' | 'expired' | 'cancelled' | 'sale_proceeds' | 'deposit';

export type AuctionSortOption =
  | 'price_asc'
  | 'price_desc'
  | 'time_asc'
  | 'time_desc'
  | 'name_asc'
  | 'name_desc';

// --- Item info (embedded in listing/storage responses) ---

export interface AuctionItemInfo {
  id: number;
  name: string;
  image: string | null;
  item_type: string;
  item_rarity: string;
  item_level: number;
}

// --- Enhancement data snapshot ---

export interface AuctionEnhancementData {
  enhancement_points_spent?: number;
  enhancement_bonuses?: Record<string, number>;
  socketed_gems?: unknown[];
  current_durability?: number;
  is_identified?: boolean;
}

// --- Listing ---

export interface AuctionListingResponse {
  id: number;
  seller_character_id: number;
  seller_name: string;
  item: AuctionItemInfo;
  quantity: number;
  enhancement_data: AuctionEnhancementData | null;
  start_price: number;
  buyout_price: number | null;
  current_bid: number;
  current_bidder_id: number | null;
  current_bidder_name: string | null;
  status: AuctionListingStatus;
  created_at: string;
  expires_at: string;
  time_remaining_seconds: number;
  bid_count: number;
}

export interface AuctionListingsPageResponse {
  listings: AuctionListingResponse[];
  total: number;
  page: number;
  per_page: number;
}

// --- My Listings ---

export interface AuctionMyListingsResponse {
  active: AuctionListingResponse[];
  completed: AuctionListingResponse[];
}

// --- Storage ---

export interface AuctionStorageItemResponse {
  id: number;
  item: AuctionItemInfo | null;
  quantity: number;
  enhancement_data: AuctionEnhancementData | null;
  gold_amount: number;
  source: AuctionStorageSource;
  created_at: string;
}

export interface AuctionStorageResponse {
  items: AuctionStorageItemResponse[];
  total_gold: number;
}

// --- Deposit to storage ---

export interface AuctionDepositRequest {
  character_id: number;
  inventory_item_id: number;
  quantity: number;
}

export interface AuctionDepositResponse {
  storage_id: number;
  item_name: string;
  quantity: number;
  message: string;
}

// --- Request payloads ---

export interface AuctionCreateListingRequest {
  character_id: number;
  storage_id: number;
  start_price: number;
  buyout_price?: number | null;
}

export interface AuctionBidRequest {
  character_id: number;
  amount: number;
}

export interface AuctionBuyoutRequest {
  character_id: number;
}

export interface AuctionCancelRequest {
  character_id: number;
}

export interface AuctionClaimRequest {
  character_id: number;
  storage_ids: number[];
}

// --- Response payloads ---

export interface AuctionCreateListingResponse {
  listing_id: number;
  item_name: string;
  quantity: number;
  start_price: number;
  buyout_price: number | null;
  expires_at: string;
  active_listing_count: number;
  message: string;
}

export interface AuctionBidResponse {
  listing_id: number;
  bid_id: number;
  amount: number;
  new_gold_balance: number;
  message: string;
}

export interface AuctionBuyoutResponse {
  listing_id: number;
  amount: number;
  new_gold_balance: number;
  message: string;
}

export interface AuctionCancelResponse {
  listing_id: number;
  message: string;
}

export interface AuctionClaimResponse {
  claimed_items: number;
  claimed_gold: number;
  new_gold_balance: number;
  message: string;
}

// --- Auctioneer check ---

export interface AuctionCheckAuctioneerResponse {
  has_auctioneer: boolean;
  auctioneer_name: string | null;
}

// --- Query params for browse ---

export interface AuctionListingsQuery {
  page?: number;
  per_page?: number;
  item_type?: string | null;
  rarity?: string | null;
  sort?: AuctionSortOption;
  search?: string | null;
}

// --- WebSocket event data ---

export interface WsAuctionOutbidData {
  listing_id: number;
  item_name: string;
  new_bid_amount: number;
  refunded_amount: number;
  notification_id: number;
  message: string;
}

export interface WsAuctionSoldData {
  listing_id: number;
  item_name: string;
  sold_price: number;
  commission: number;
  net_gold: number;
  buyer_name: string;
  notification_id: number;
  message: string;
}

export interface WsAuctionWonData {
  listing_id: number;
  item_name: string;
  winning_bid: number;
  notification_id: number;
  message: string;
}

export interface WsAuctionExpiredData {
  listing_id: number;
  item_name: string;
  notification_id: number;
  message: string;
}
