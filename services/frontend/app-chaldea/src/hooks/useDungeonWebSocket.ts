import { useEffect, useRef, useState, useCallback } from 'react';

// --- Constants ---

const MAX_RECONNECT_DELAY = 30000;
const INITIAL_RECONNECT_DELAY = 1000;
const WS_CLOSE_NORMAL = 1000;
const WS_CLOSE_UNAUTHORIZED = 4001;
const MAX_RECONNECT_ATTEMPTS = 5;
const HEARTBEAT_INTERVAL = 30000;

// --- WS Message Types ---

export interface DungeonWsMessage {
  type:
    | 'room_entered'
    | 'battle_started'
    | 'battle_ended'
    | 'member_status_changed'
    | 'loot_added'
    | 'trap_triggered'
    | 'event_result'
    | 'session_status'
    | 'leader_changed'
    | 'session_update'
    | 'ping';
  data: Record<string, unknown>;
}

// --- Hook Return Type ---

interface UseDungeonWebSocketReturn {
  connected: boolean;
  reconnecting: boolean;
  lastMessage: DungeonWsMessage | null;
}

// --- Hook ---

const useDungeonWebSocket = (
  sessionId: number | null,
  token: string | null,
): UseDungeonWebSocketReturn => {
  const [connected, setConnected] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [lastMessage, setLastMessage] = useState<DungeonWsMessage | null>(null);

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

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/dungeons/ws/${sessionId}?token=${token}`;

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

          if (parsed.type === 'ping') {
            return;
          }

          setLastMessage(parsed);
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

        if (event.code === WS_CLOSE_UNAUTHORIZED || event.code === WS_CLOSE_NORMAL) {
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
  }, [sessionId, token, closeExistingConnection]);

  return { connected, reconnecting, lastMessage };
};

export default useDungeonWebSocket;
