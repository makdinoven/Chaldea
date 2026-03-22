import { useEffect, useRef, useState } from 'react';
import { useAppDispatch } from '../redux/store';
import { addNotification, NotificationItem } from '../redux/slices/notificationSlice';
import { addMessage, removeMessage } from '../redux/slices/chatSlice';
import type { ChatMessage, ChatChannel } from '../types/chat';
import toast from 'react-hot-toast';

const MAX_RECONNECT_DELAY = 30000;
const INITIAL_RECONNECT_DELAY = 1000;
const UNAUTHORIZED_RECONNECT_DELAY = 30000;
const WS_CLOSE_NORMAL = 1000;
const WS_CLOSE_UNAUTHORIZED = 4001;

interface WebSocketMessage {
  type: string;
  data?: unknown;
}

interface UseWebSocketReturn {
  connected: boolean;
}

const useWebSocket = (): UseWebSocketReturn => {
  const [connected, setConnected] = useState(false);
  const dispatch = useAppDispatch();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    const connect = () => {
      const token = localStorage.getItem('accessToken');
      if (!token) {
        setConnected(false);
        return;
      }

      // Close any existing connection
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.onmessage = null;
        wsRef.current.close(WS_CLOSE_NORMAL);
        wsRef.current = null;
      }

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/notifications/ws?token=${token}`;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setConnected(true);
        reconnectDelayRef.current = INITIAL_RECONNECT_DELAY;
      };

      ws.onmessage = (event: MessageEvent) => {
        if (!mountedRef.current) return;

        try {
          const parsed = JSON.parse(event.data as string) as WebSocketMessage;

          switch (parsed.type) {
            case 'notification': {
              const notification = parsed.data as NotificationItem;
              dispatch(addNotification(notification));
              if (notification.message) {
                toast(notification.message);
              }
              break;
            }
            case 'chat_message': {
              dispatch(addMessage(parsed.data as ChatMessage));
              break;
            }
            case 'chat_message_deleted': {
              dispatch(
                removeMessage(parsed.data as { id: number; channel: ChatChannel }),
              );
              break;
            }
            case 'pvp_battle_start': {
              const pvpData = parsed.data as {
                battle_id: number;
                attacker_name?: string;
                battle_type?: string;
              };
              const battleType = pvpData.battle_type;
              if (battleType === 'pvp_attack') {
                toast.error(
                  `${pvpData.attacker_name ?? 'Кто-то'} напал на вас! Бой #${pvpData.battle_id} начинается.`,
                  { duration: 8000 },
                );
              } else {
                toast.success(
                  `Бой #${pvpData.battle_id} начинается!`,
                  { duration: 6000 },
                );
              }
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

        if (event.code === WS_CLOSE_UNAUTHORIZED) {
          // Token invalid/expired — use longer delay and re-read token
          reconnectDelayRef.current = UNAUTHORIZED_RECONNECT_DELAY;
        }

        scheduleReconnect();
      };

      ws.onerror = () => {
        // onclose will fire after onerror, reconnect is handled there
      };
    };

    const scheduleReconnect = () => {
      if (!mountedRef.current) return;

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

      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.onmessage = null;
        wsRef.current.close(WS_CLOSE_NORMAL);
        wsRef.current = null;
      }

      setConnected(false);
    };
  }, [dispatch]);

  return { connected };
};

export { useWebSocket };
export default useWebSocket;
