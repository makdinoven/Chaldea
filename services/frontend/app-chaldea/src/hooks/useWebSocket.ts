import { useEffect, useRef, useState } from 'react';
import { useAppDispatch, useAppSelector } from '../redux/store';
import { addNotification, NotificationItem } from '../redux/slices/notificationSlice';
import { addMessage, removeMessage } from '../redux/slices/chatSlice';
import {
  receivePrivateMessage,
  receiveMessageDeleted,
  receiveMessageEdited,
  receiveConversationCreated,
  receiveConversationRead,
  receiveConversationPinChanged,
  receiveTyping,
  receiveReaction,
  removeOptimisticMessage,
  removeConversation,
  receiveOwnSentMessage,
} from '../redux/slices/messengerSlice';
import {
  handleAuctionOutbid,
  handleAuctionSold,
  handleAuctionWon,
  handleAuctionExpired,
} from '../redux/slices/auctionSlice';
import {
  receiveTicketReply,
  receiveTicketNewMessage,
} from '../redux/slices/ticketSlice';
import type {
  PrivateMessage,
  WsPrivateMessageData,
  WsPrivateMessageDeletedData,
  WsMessageEditedData,
  WsConversationCreatedData,
  WsConversationReadData,
  WsConversationPinChangedData,
  WsTypingData,
  WsMessageReactionData,
  WsConversationRemovedData,
} from '../types/messenger';
import type {
  WsAuctionOutbidData,
  WsAuctionSoldData,
  WsAuctionWonData,
  WsAuctionExpiredData,
} from '../types/auction';
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

// Module-level WebSocket reference for sendWsMessage
let activeWs: WebSocket | null = null;

// Outbound frames produced while the socket is briefly reconnecting
// (e.g. right after a production deploy restarts notification-service).
// They are flushed on reconnect, so a transient drop doesn't surface an error.
interface QueuedFrame {
  frame: string;
  ts: number;
}
let outboundQueue: QueuedFrame[] = [];
const OUTBOUND_QUEUE_MAX = 50;
const OUTBOUND_TTL_MS = 30000;

/** Flush queued frames once the socket is open again, dropping stale ones. */
const flushOutboundQueue = (): void => {
  if (!activeWs || activeWs.readyState !== WebSocket.OPEN) return;
  const now = Date.now();
  const pending = outboundQueue;
  outboundQueue = [];
  for (const item of pending) {
    if (now - item.ts > OUTBOUND_TTL_MS) continue; // too old — drop
    try {
      activeWs.send(item.frame);
    } catch {
      // Socket died again mid-flush — keep it for the next reconnect.
      outboundQueue.push(item);
    }
  }
};

/**
 * Send a message through the shared WebSocket connection.
 * If the socket is momentarily reconnecting, the frame is queued and flushed
 * once the connection is back. Returns true if the frame was sent or queued,
 * false only if the queue is full (a genuine inability to deliver).
 */
export const sendWsMessage = (action: string, data: Record<string, unknown>): boolean => {
  const frame = JSON.stringify({ action, data });
  if (activeWs && activeWs.readyState === WebSocket.OPEN) {
    activeWs.send(frame);
    return true;
  }
  if (outboundQueue.length < OUTBOUND_QUEUE_MAX) {
    outboundQueue.push({ frame, ts: Date.now() });
    return true;
  }
  return false;
};

const useWebSocket = (): UseWebSocketReturn => {
  const [connected, setConnected] = useState(false);
  const dispatch = useAppDispatch();
  const currentUserId = useAppSelector((state) => state.user.id);
  const currentUserIdRef = useRef(currentUserId);
  useEffect(() => {
    currentUserIdRef.current = currentUserId;
  }, [currentUserId]);
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
        activeWs = null;
      }

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/notifications/ws?token=${token}`;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      activeWs = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setConnected(true);
        reconnectDelayRef.current = INITIAL_RECONNECT_DELAY;
        // Deliver anything queued while we were reconnecting.
        flushOutboundQueue();
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
                location_id?: number;
                attacker_name?: string;
                battle_type?: string;
                notification_id?: number;
              };
              const battleType = pvpData.battle_type;
              const pvpMessage = battleType === 'pvp_attack'
                ? `${pvpData.attacker_name ?? 'Кто-то'} напал на вас! Бой #${pvpData.battle_id} начинается.`
                : `Бой #${pvpData.battle_id} начинается!`;
              if (battleType === 'pvp_attack') {
                toast.error(pvpMessage, { duration: 8000 });
              } else {
                toast.success(pvpMessage, { duration: 6000 });
              }
              dispatch(addNotification({
                id: pvpData.notification_id ?? Date.now(),
                user_id: 0,
                message: pvpMessage,
                status: 'unread',
                created_at: new Date().toISOString(),
                // Route needs both ids (location/:locationId/battle/:battleId);
                // fall back gracefully if location_id is somehow absent.
                link: pvpData.location_id != null
                  ? `/location/${pvpData.location_id}/battle/${pvpData.battle_id}`
                  : undefined,
              } as NotificationItem));
              break;
            }
            case 'party_invitation': {
              const inv = parsed.data as { leader_name?: string };
              toast(`${inv.leader_name ?? 'Игрок'} приглашает вас в группу`, {
                duration: 7000,
              });
              break;
            }
            case 'party_started': {
              const ps = parsed.data as {
                battle_id: number;
                battle_url?: string;
              };
              toast.success(`Бой #${ps.battle_id} начинается!`, { duration: 6000 });
              dispatch(addNotification({
                id: Date.now(),
                user_id: 0,
                message: `Бой #${ps.battle_id} начинается!`,
                status: 'unread',
                created_at: new Date().toISOString(),
                link: ps.battle_url ?? `/battle/${ps.battle_id}`,
              } as NotificationItem));
              break;
            }
            case 'private_message': {
              const pm = parsed.data as WsPrivateMessageData;
              dispatch(receivePrivateMessage(pm));
              // Desktop notification when the tab is in the background.
              if (
                typeof document !== 'undefined' && document.hidden &&
                typeof Notification !== 'undefined' && Notification.permission === 'granted'
              ) {
                try {
                  new Notification(pm.sender_username || 'Новое сообщение', {
                    body: pm.content || '📷 Изображение',
                  });
                } catch {
                  // Ignore — notifications are best-effort.
                }
              }
              break;
            }
            case 'private_message_deleted': {
              dispatch(receiveMessageDeleted(parsed.data as WsPrivateMessageDeletedData));
              break;
            }
            case 'private_message_edited': {
              dispatch(receiveMessageEdited(parsed.data as WsMessageEditedData));
              break;
            }
            case 'conversation_created': {
              dispatch(receiveConversationCreated(parsed.data as WsConversationCreatedData));
              break;
            }
            case 'conversation_read': {
              dispatch(receiveConversationRead(parsed.data as WsConversationReadData));
              break;
            }
            case 'conversation_pin_changed': {
              dispatch(receiveConversationPinChanged(parsed.data as WsConversationPinChangedData));
              break;
            }
            case 'conversation_removed': {
              const data = parsed.data as WsConversationRemovedData;
              dispatch(removeConversation(data.conversation_id));
              toast('Вас исключили из беседы');
              break;
            }
            case 'messenger_typing': {
              dispatch(receiveTyping(parsed.data as WsTypingData));
              break;
            }
            case 'message_reaction': {
              const r = parsed.data as WsMessageReactionData;
              dispatch(receiveReaction({ ...r, is_self: r.user_id === currentUserIdRef.current }));
              break;
            }
            case 'messenger_send_ok': {
              dispatch(receiveOwnSentMessage(parsed.data as PrivateMessage));
              break;
            }
            case 'messenger_edit_ok':
            case 'messenger_delete_ok':
            case 'messenger_mark_read_ok':
              // Success confirmations — state already updated via WS broadcast events
              break;
            case 'messenger_error': {
              const errData = parsed.data as { detail?: string; temp_id?: number };
              if (errData.temp_id != null) {
                dispatch(removeOptimisticMessage({ tempId: errData.temp_id }));
              }
              toast.error(errData.detail ?? 'Ошибка мессенджера');
              break;
            }
            case 'messenger_mention': {
              const m = parsed.data as { from_username?: string };
              const text = `${m.from_username ?? 'Кто-то'} упомянул вас`;
              toast(text);
              dispatch(addNotification({
                id: Date.now(),
                user_id: 0,
                message: text,
                status: 'unread',
                created_at: new Date().toISOString(),
              } as NotificationItem));
              break;
            }
            case 'auction_outbid': {
              const outbidData = parsed.data as WsAuctionOutbidData;
              dispatch(handleAuctionOutbid(outbidData));
              if (outbidData.message) {
                toast(outbidData.message);
                dispatch(addNotification({
                  id: outbidData.notification_id,
                  user_id: 0,
                  message: outbidData.message,
                  status: 'unread',
                  created_at: new Date().toISOString(),
                } as NotificationItem));
              }
              break;
            }
            case 'auction_sold': {
              const soldData = parsed.data as WsAuctionSoldData;
              dispatch(handleAuctionSold(soldData));
              if (soldData.message) {
                toast(soldData.message);
                dispatch(addNotification({
                  id: soldData.notification_id,
                  user_id: 0,
                  message: soldData.message,
                  status: 'unread',
                  created_at: new Date().toISOString(),
                } as NotificationItem));
              }
              break;
            }
            case 'auction_won': {
              const wonData = parsed.data as WsAuctionWonData;
              dispatch(handleAuctionWon(wonData));
              if (wonData.message) {
                toast(wonData.message);
                dispatch(addNotification({
                  id: wonData.notification_id,
                  user_id: 0,
                  message: wonData.message,
                  status: 'unread',
                  created_at: new Date().toISOString(),
                } as NotificationItem));
              }
              break;
            }
            case 'auction_expired': {
              const expiredData = parsed.data as WsAuctionExpiredData;
              dispatch(handleAuctionExpired(expiredData));
              if (expiredData.message) {
                toast(expiredData.message);
                dispatch(addNotification({
                  id: expiredData.notification_id,
                  user_id: 0,
                  message: expiredData.message,
                  status: 'unread',
                  created_at: new Date().toISOString(),
                } as NotificationItem));
              }
              break;
            }
            case 'ticket_reply': {
              const ticketReplyData = parsed.data as {
                ticket_id: number;
                notification_id?: number;
                message?: string;
              };
              dispatch(receiveTicketReply(ticketReplyData));
              if (ticketReplyData.notification_id && ticketReplyData.message) {
                dispatch(addNotification({
                  id: ticketReplyData.notification_id,
                  user_id: 0,
                  message: ticketReplyData.message,
                  status: 'unread',
                  created_at: new Date().toISOString(),
                } as NotificationItem));
                toast(ticketReplyData.message);
              }
              break;
            }
            case 'ticket_new_message': {
              const ticketNewMsgData = parsed.data as { ticket_id: number };
              dispatch(receiveTicketNewMessage(ticketNewMsgData));
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
        activeWs = null;
      }

      setConnected(false);
    };
  }, [dispatch]);

  return { connected };
};

export { useWebSocket };
export default useWebSocket;
