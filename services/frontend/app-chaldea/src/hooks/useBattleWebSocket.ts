import { useEffect, useRef, useState, useCallback } from 'react';
import type { BattleRewards } from '../api/mobs';

// --- Constants ---

const MAX_RECONNECT_DELAY = 30000;
const INITIAL_RECONNECT_DELAY = 1000;
const WS_CLOSE_NORMAL = 1000;
const WS_CLOSE_UNAUTHORIZED = 4001;
const MAX_RECONNECT_ATTEMPTS = 5;

// --- WS Message Types ---

interface BattleStateData {
  snapshot: unknown[];
  runtime: {
    participants: Record<
      number,
      {
        hp: number;
        mana: number;
        stamina: number;
        energy: number;
        fast_slots: unknown;
        team: number;
      }
    >;
    current_actor: number;
    next_actor: number;
    turn_number: number;
    turn_order: number[];
    total_turns: number;
    first_actor: number;
    deadline_at: string;
    is_paused?: boolean;
    paused_reason?: string | null;
    rewards?: BattleRewards | null;
  };
}

interface BattleFinishedData {
  winner_team: number;
  rewards: BattleRewards | null;
}

interface BattlePausedData {
  is_paused: boolean;
  reason: string | null;
}

interface WsBattleStateMessage {
  type: 'battle_state';
  data: BattleStateData;
}

interface WsBattleFinishedMessage {
  type: 'battle_finished';
  data: BattleFinishedData;
}

interface WsBattlePausedMessage {
  type: 'battle_paused';
  data: BattlePausedData;
}

interface WsPingMessage {
  type: 'ping';
  data: Record<string, never>;
}

type BattleWsMessage =
  | WsBattleStateMessage
  | WsBattleFinishedMessage
  | WsBattlePausedMessage
  | WsPingMessage;

// --- Hook Return Type ---

interface UseBattleWebSocketReturn {
  connected: boolean;
  reconnecting: boolean;
  fallbackToPolling: boolean;
  state: BattleStateData | null;
  battleFinished: BattleFinishedData | null;
}

// --- Hook ---

const useBattleWebSocket = (
  battleId: number | string,
  token: string | null,
): UseBattleWebSocketReturn => {
  const [connected, setConnected] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [fallbackToPolling, setFallbackToPolling] = useState(false);
  const [state, setState] = useState<BattleStateData | null>(null);
  const [battleFinished, setBattleFinished] = useState<BattleFinishedData | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const mountedRef = useRef(true);
  const currentTurnRef = useRef(0);

  const closeExistingConnection = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.close(WS_CLOSE_NORMAL);
      wsRef.current = null;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;

    // Don't connect without a token or battleId
    if (!token || !battleId) {
      setConnected(false);
      return;
    }

    const connect = () => {
      if (!mountedRef.current) return;

      // Close any existing connection
      closeExistingConnection();

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/battles/ws/${battleId}?token=${token}`;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setConnected(true);
        setReconnecting(false);
        setFallbackToPolling(false);
        reconnectDelayRef.current = INITIAL_RECONNECT_DELAY;
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event: MessageEvent) => {
        if (!mountedRef.current) return;

        try {
          const parsed = JSON.parse(event.data as string) as BattleWsMessage;

          switch (parsed.type) {
            case 'battle_state': {
              const turnNumber = parsed.data.runtime?.turn_number ?? 0;
              // Discard out-of-order messages
              if (turnNumber > 0 && turnNumber <= currentTurnRef.current) {
                break;
              }
              currentTurnRef.current = turnNumber;
              setState(parsed.data);
              break;
            }

            case 'battle_finished': {
              setBattleFinished(parsed.data);
              break;
            }

            case 'battle_paused': {
              // Update pause state within current state
              setState((prev) => {
                if (!prev) return prev;
                return {
                  ...prev,
                  runtime: {
                    ...prev.runtime,
                    is_paused: parsed.data.is_paused,
                    paused_reason: parsed.data.reason,
                  },
                };
              });
              break;
            }

            case 'ping':
              // Keepalive — ignore
              break;

            default:
              break;
          }
        } catch {
          // Non-JSON or malformed message — ignore
        }
      };

      ws.onclose = (event: CloseEvent) => {
        if (!mountedRef.current) return;
        setConnected(false);

        // Don't retry on unauthorized — token is invalid
        if (event.code === WS_CLOSE_UNAUTHORIZED) {
          setFallbackToPolling(true);
          return;
        }

        // Normal close (e.g., unmount or battle ended) — don't reconnect
        if (event.code === WS_CLOSE_NORMAL) {
          return;
        }

        scheduleReconnect();
      };

      ws.onerror = () => {
        // onclose will fire after onerror, reconnect is handled there
      };
    };

    const scheduleReconnect = () => {
      if (!mountedRef.current) return;

      reconnectAttemptsRef.current += 1;

      // After max attempts, fall back to polling
      if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
        setReconnecting(false);
        setFallbackToPolling(true);
        return;
      }

      setReconnecting(true);

      const delay = reconnectDelayRef.current;
      reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY);

      reconnectTimeoutRef.current = setTimeout(() => {
        if (mountedRef.current) {
          connect();
        }
      }, delay);
    };

    connect();

    return () => {
      mountedRef.current = false;

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }

      closeExistingConnection();
      setConnected(false);
    };
  }, [battleId, token, closeExistingConnection]);

  return { connected, reconnecting, fallbackToPolling, state, battleFinished };
};

export { useBattleWebSocket };
export type {
  BattleStateData,
  BattleFinishedData,
  BattlePausedData,
  UseBattleWebSocketReturn,
};
export default useBattleWebSocket;
