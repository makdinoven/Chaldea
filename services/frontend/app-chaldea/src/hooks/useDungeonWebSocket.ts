import { useEffect, useRef, useState, useCallback } from 'react';
import { getAccessToken, refreshAccessToken } from '../api/authToken';

// --- Constants ---

const MAX_RECONNECT_DELAY = 30000;
const INITIAL_RECONNECT_DELAY = 1000;
const WS_CLOSE_NORMAL = 1000;
const WS_CLOSE_UNAUTHORIZED = 4001;
const WS_CLOSE_FORBIDDEN = 4003;
const MAX_RECONNECT_ATTEMPTS = 5;
const HEARTBEAT_INTERVAL = 30000;

// --- WS Message Types ---

// Event list and payloads: docs/services/dungeon-service.md, «WebSocket».
export type DungeonWsEventType =
  | 'session_status'
  | 'room_entered'
  | 'battle_started'
  | 'battle_ended'
  | 'member_status_changed'
  | 'trap_triggered'
  | 'loot_added'
  | 'event_result'
  | 'rest_started'
  | 'rest_completed'
  | 'mana_core_revealed'
  | 'mana_core_result'
  | 'leader_changed'
  | 'loot_distributed'
  | 'party_vote'
  | 'party_ping'
  | 'challenge_started'
  | 'challenge_finished'
  | 'chat_message'
  | 'room_lit'
  | 'heartbeat_ack'
  | 'ping';

export interface DungeonWsMessage {
  type: DungeonWsEventType;
  data: Record<string, unknown>;
}

// --- Hook Return Type ---

interface UseDungeonWebSocketReturn {
  connected: boolean;
  reconnecting: boolean;
  /** Start over after the hook gave up reconnecting (the player's own "try again"). */
  reconnect: () => void;
}

// --- Hook ---

/**
 * Live events of a dungeon run. Every message is handed to `onMessage`
 * (a queue-free callback — several events arriving in one tick must not
 * overwrite each other the way a `lastMessage` state would).
 */
const useDungeonWebSocket = (
  sessionId: number | null,
  token: string | null,
  onMessage: (message: DungeonWsMessage) => void,
): UseDungeonWebSocketReturn => {
  const [connected, setConnected] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  // Bumped by reconnect(): a fresh round of connection attempts.
  const [round, setRound] = useState(0);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const mountedRef = useRef(true);

  const closeExistingConnection = useCallback(() => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
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

    if (!token || !sessionId) {
      setConnected(false);
      return;
    }

    const connect = () => {
      if (!mountedRef.current) return;

      closeExistingConnection();

      // Re-read the token on every (re)connect so a token refreshed by the
      // HTTP layer (or another tab) is used instead of the captured prop.
      const wsToken = getAccessToken() ?? token;

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/dungeons/ws/${sessionId}?token=${wsToken}`;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setConnected(true);
        setReconnecting(false);
        reconnectDelayRef.current = INITIAL_RECONNECT_DELAY;
        reconnectAttemptsRef.current = 0;

        // Start heartbeat
        heartbeatRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'heartbeat' }));
          }
        }, HEARTBEAT_INTERVAL);
      };

      ws.onmessage = (event: MessageEvent) => {
        if (!mountedRef.current) return;

        try {
          const parsed = JSON.parse(event.data as string) as DungeonWsMessage;

          if (parsed.type === 'ping' || parsed.type === 'heartbeat_ack') {
            return;
          }

          onMessageRef.current({ type: parsed.type, data: parsed.data ?? {} });
        } catch {
          // Non-JSON or malformed message — ignore
        }
      };

      ws.onclose = (event: CloseEvent) => {
        if (!mountedRef.current) return;
        setConnected(false);

        if (heartbeatRef.current) {
          clearInterval(heartbeatRef.current);
          heartbeatRef.current = null;
        }

        // Normal close (the run ended) or not a member: do not retry.
        if (event.code === WS_CLOSE_NORMAL || event.code === WS_CLOSE_FORBIDDEN) {
          setReconnecting(false);
          return;
        }

        // Unauthorized — the access token was rejected. Refresh it via the
        // shared single-flight flow, then reconnect with the fresh token.
        // WS failures never clear tokens or trigger logout (FEAT-150): on a
        // fatal refresh we just stop reconnecting; logout is decided only by
        // the HTTP layer's handleAuthFailure.
        if (event.code === WS_CLOSE_UNAUTHORIZED) {
          void refreshAccessToken(wsToken).then((result) => {
            if (!mountedRef.current) return;
            if (result.status === 'fatal') {
              setReconnecting(false);
              return;
            }
            scheduleReconnect();
          });
          return;
        }

        scheduleReconnect();
      };

      ws.onerror = () => {
        // onclose will fire after onerror
      };
    };

    const scheduleReconnect = () => {
      if (!mountedRef.current) return;

      reconnectAttemptsRef.current += 1;

      if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
        setReconnecting(false);
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
  }, [sessionId, token, closeExistingConnection, round]);

  const reconnect = useCallback(() => {
    reconnectAttemptsRef.current = 0;
    reconnectDelayRef.current = INITIAL_RECONNECT_DELAY;
    setReconnecting(true);
    setRound((r) => r + 1);
  }, []);

  return { connected, reconnecting, reconnect };
};

export default useDungeonWebSocket;
