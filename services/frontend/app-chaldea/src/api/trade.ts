import axios from 'axios';

// --- Types ---

export interface TradeOffer {
  trade_id: number;
  initiator_character_id: number;
  target_character_id: number;
  status: string;
}

export interface TradeItem {
  item_id: number;
  item_name: string;
  item_image: string | null;
  quantity: number;
  rarity?: string;
}

export interface TradeSide {
  character_id: number;
  character_name: string;
  items: TradeItem[];
  gold: number;
  confirmed: boolean;
}

export interface TradeState {
  trade_id: number;
  status: string;
  initiator: TradeSide;
  target: TradeSide;
}

export interface TradeCancelResult {
  trade_id: number;
  status: string;
}

export interface PendingTradeEntry {
  trade_id: number;
  initiator_character_id: number;
  initiator_name: string;
  target_character_id: number;
  target_name: string;
  status: string;
  created_at: string;
  direction: 'incoming' | 'outgoing';
}

export interface PendingTradesResponse {
  incoming: PendingTradeEntry[];
  outgoing: PendingTradeEntry[];
}

// --- API calls ---

export const getPendingTrades = async (
  characterId: number,
): Promise<PendingTradesResponse> => {
  const { data } = await axios.get<PendingTradesResponse>(
    `/inventory/trade/pending/${characterId}`,
  );
  return data;
};

export const proposeTrade = async (
  initiatorCharacterId: number,
  targetCharacterId: number,
): Promise<TradeOffer> => {
  const { data } = await axios.post<TradeOffer>('/inventory/trade/propose', {
    initiator_character_id: initiatorCharacterId,
    target_character_id: targetCharacterId,
  });
  return data;
};

export const updateTradeItems = async (
  tradeId: number,
  characterId: number,
  items: { item_id: number; quantity: number }[],
  gold: number,
): Promise<TradeState> => {
  const { data } = await axios.put<TradeState>(
    `/inventory/trade/${tradeId}/items`,
    {
      character_id: characterId,
      items,
      gold,
    },
  );
  return data;
};

export const confirmTrade = async (
  tradeId: number,
  characterId: number,
): Promise<TradeState> => {
  const { data } = await axios.post<TradeState>(
    `/inventory/trade/${tradeId}/confirm`,
    { character_id: characterId },
  );
  return data;
};

export const cancelTrade = async (
  tradeId: number,
): Promise<TradeCancelResult> => {
  const { data } = await axios.post<TradeCancelResult>(
    `/inventory/trade/${tradeId}/cancel`,
  );
  return data;
};

export const getTradeState = async (
  tradeId: number,
): Promise<TradeState> => {
  const { data } = await axios.get<TradeState>(
    `/inventory/trade/${tradeId}`,
  );
  return data;
};
